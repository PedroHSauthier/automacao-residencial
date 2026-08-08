"""Pure helpers for immutable, JSON-safe Home Assistant state snapshots.

This module deliberately does not import Home Assistant.  Event-bus callbacks can
therefore call :func:`capture_state_snapshot` synchronously, before their first
``await``, and hand the resulting value to a queue without retaining a reference
to the mutable input object.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import fields as dataclass_fields, is_dataclass
from datetime import date, datetime, time
from enum import Enum
import base64
import math
from pathlib import Path
from typing import Any, Final
from uuid import UUID


class _Missing:
    """Sentinel used to distinguish an absent key from an explicit JSON null."""

    __slots__ = ()

    def __repr__(self) -> str:
        return "MISSING"

    def __bool__(self) -> bool:
        return False


MISSING: Final = _Missing()


class FrozenDict(dict):
    """A ``dict`` subclass that remains directly JSON serializable and immutable."""

    __slots__ = ()

    @staticmethod
    def _immutable(*_args: Any, **_kwargs: Any) -> None:
        raise TypeError("FrozenDict is immutable")

    __setitem__ = _immutable
    __delitem__ = _immutable
    clear = _immutable
    pop = _immutable
    popitem = _immutable
    setdefault = _immutable
    update = _immutable
    __ior__ = _immutable

    def copy(self) -> "FrozenDict":
        return self


class FrozenList(list):
    """A ``list`` subclass that remains directly JSON serializable and immutable."""

    __slots__ = ()

    @staticmethod
    def _immutable(*_args: Any, **_kwargs: Any) -> None:
        raise TypeError("FrozenList is immutable")

    __setitem__ = _immutable
    __delitem__ = _immutable
    __iadd__ = _immutable
    __imul__ = _immutable
    append = _immutable
    clear = _immutable
    extend = _immutable
    insert = _immutable
    pop = _immutable
    remove = _immutable
    reverse = _immutable
    sort = _immutable

    def copy(self) -> "FrozenList":
        return self


_MAX_DEPTH: Final = 20
_MAX_ITEMS: Final = 1_000
_MAX_TEXT: Final = 32_768

DEFAULT_IRRELEVANT_FIELDS: Final = frozenset(
    {
        "attribution",
        "device_class",
        "entity_picture",
        "friendly_name",
        "icon",
        "restored",
        "state_class",
        "supported_color_modes",
        "supported_features",
        "unit_of_measurement",
    }
)


def _safe_text(value: Any) -> str:
    text = str(value)
    if len(text) <= _MAX_TEXT:
        return text
    return text[: _MAX_TEXT - 1] + "…"


def _freeze_json(
    value: Any,
    *,
    depth: int,
    active_ids: set[int],
) -> Any:
    if value is MISSING:
        raise TypeError("MISSING is an internal sentinel and cannot be serialized")
    if value is None or isinstance(value, (bool, int, str)):
        return _safe_text(value) if isinstance(value, str) else value
    if isinstance(value, float):
        if math.isfinite(value):
            return value
        if math.isnan(value):
            return "NaN"
        return "Infinity" if value > 0 else "-Infinity"
    if isinstance(value, Enum):
        return _freeze_json(value.value, depth=depth, active_ids=active_ids)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, (UUID, Path)):
        return str(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return FrozenDict(
            {
                "encoding": "base64",
                "value": base64.b64encode(bytes(value)).decode("ascii"),
            }
        )
    if depth >= _MAX_DEPTH:
        return FrozenDict({"truncated": True, "reason": "maximum_depth"})

    object_id = id(value)
    if object_id in active_ids:
        return FrozenDict({"truncated": True, "reason": "cyclic_reference"})

    if is_dataclass(value) and not isinstance(value, type):
        # ``dataclasses.asdict`` deep-copies values and therefore tries to mutate
        # ``FrozenDict``/``FrozenList`` instances. Field-wise traversal keeps the
        # same cycle guard and never touches caller-owned objects.
        value = {
            item.name: getattr(value, item.name)
            for item in dataclass_fields(value)
        }
    elif hasattr(value, "as_dict") and callable(value.as_dict):
        try:
            value = value.as_dict()
        except Exception:  # pragma: no cover - defensive for third-party objects
            return _safe_text(value)

    if isinstance(value, Mapping):
        active_ids.add(object_id)
        try:
            result: dict[str, Any] = {}
            for index, (key, item) in enumerate(value.items()):
                if index >= _MAX_ITEMS:
                    result["__truncated_items__"] = len(value) - _MAX_ITEMS
                    break
                result[_safe_text(key)] = _freeze_json(
                    item,
                    depth=depth + 1,
                    active_ids=active_ids,
                )
            return FrozenDict(result)
        finally:
            active_ids.discard(object_id)

    if isinstance(value, set | frozenset):
        value = sorted(value, key=lambda item: repr(item))
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        active_ids.add(object_id)
        try:
            items = [
                _freeze_json(item, depth=depth + 1, active_ids=active_ids)
                for item in value[:_MAX_ITEMS]
            ]
            if len(value) > _MAX_ITEMS:
                items.append(
                    FrozenDict(
                        {
                            "truncated": True,
                            "reason": "maximum_items",
                            "discarded": len(value) - _MAX_ITEMS,
                        }
                    )
                )
            return FrozenList(items)
        finally:
            active_ids.discard(object_id)

    return _safe_text(value)


def freeze_json(value: Any) -> Any:
    """Return a deeply immutable value accepted by :mod:`json`.

    ``dict`` and ``list`` subclasses are used instead of mapping proxies and
    tuples so ``json.dumps(freeze_json(value))`` works without a custom encoder.
    """

    return _freeze_json(value, depth=0, active_ids=set())


def thaw_json(value: Any) -> Any:
    """Return a new mutable JSON tree, never a reference to the frozen input."""

    if isinstance(value, Mapping):
        return {str(key): thaw_json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [thaw_json(item) for item in value]
    return value


def _read(source: Any, key: str, default: Any = MISSING) -> Any:
    if isinstance(source, Mapping):
        return source.get(key, default)
    return getattr(source, key, default)


def _capture_context(value: Any) -> FrozenDict:
    if value is MISSING or value is None:
        return FrozenDict({"id": None, "parent_id": None, "user_id": None})
    return FrozenDict(
        {
            "id": freeze_json(_read(value, "id", None)),
            "parent_id": freeze_json(_read(value, "parent_id", None)),
            "user_id": freeze_json(_read(value, "user_id", None)),
        }
    )


def capture_state_snapshot(entity_id: str, state: Any) -> FrozenDict | None:
    """Atomically copy one state-like object into a deeply immutable snapshot.

    ``state`` may be a Home Assistant ``State`` instance, an ``as_dict``-style
    mapping, or ``None``.  The function is synchronous by design; callers must
    invoke it in the event callback before scheduling or awaiting other work.
    """

    if state is None:
        return None

    state_entity_id = _read(state, "entity_id", entity_id)
    state_value = _read(state, "state", None)
    attributes = _read(state, "attributes", {})
    if not isinstance(attributes, Mapping):
        attributes = {"value": attributes}
    context = _read(state, "context", None)

    return FrozenDict(
        {
            "entity_id": _safe_text(entity_id or state_entity_id or ""),
            "state": freeze_json(state_value),
            "attributes": freeze_json(dict(attributes)),
            "last_changed": freeze_json(_read(state, "last_changed", None)),
            "last_updated": freeze_json(_read(state, "last_updated", None)),
            "context": _capture_context(context),
        }
    )


def _value_equal(before: Any, after: Any) -> bool:
    if before is MISSING or after is MISSING:
        return before is after
    if isinstance(before, bool) != isinstance(after, bool):
        return False
    return before == after


def _diff_entry(before: Any, after: Any) -> FrozenDict:
    before_present = before is not MISSING
    after_present = after is not MISSING
    if not before_present:
        change = "added"
    elif not after_present:
        change = "removed"
    else:
        change = "changed"

    result: dict[str, Any] = {
        "before_present": before_present,
        "after_present": after_present,
        # ``None`` is meaningful only when the corresponding *_present is true.
        "before": None if before is MISSING else freeze_json(before),
        "after": None if after is MISSING else freeze_json(after),
        "change": change,
    }
    if (
        before_present
        and after_present
        and isinstance(before, (int, float))
        and isinstance(after, (int, float))
        and not isinstance(before, bool)
        and not isinstance(after, bool)
    ):
        delta = after - before
        if math.isfinite(float(delta)):
            result["delta"] = delta
            result["direction"] = (
                "increased" if delta > 0 else "decreased" if delta < 0 else "unchanged"
            )
    return FrozenDict(result)


def _attributes(snapshot: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if not snapshot:
        return {}
    value = snapshot.get("attributes", {})
    return value if isinstance(value, Mapping) else {}


def build_state_diff(
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
    relevant_fields: set[str] | frozenset[str] | Sequence[str] | None = None,
) -> FrozenDict:
    """Build a lossless operational diff between two captured snapshots.

    Missing fields and explicit ``null`` values are represented independently by
    ``before_present``/``after_present``.  ``unknown`` and ``unavailable`` remain
    literal string values.  Technical-only attributes remain in ``diff`` and
    ``changed_fields_all`` but are omitted from ``changed_fields_relevant``.
    """

    diff: dict[str, FrozenDict] = {}

    before_state = MISSING if before is None else before.get("state", MISSING)
    after_state = MISSING if after is None else after.get("state", MISSING)
    if not _value_equal(before_state, after_state):
        diff["state"] = _diff_entry(before_state, after_state)

    before_attributes = _attributes(before)
    after_attributes = _attributes(after)
    keys = sorted(set(before_attributes) | set(after_attributes), key=str.casefold)
    for key in keys:
        old_value = before_attributes.get(key, MISSING)
        new_value = after_attributes.get(key, MISSING)
        if _value_equal(old_value, new_value):
            continue
        field_name = f"attributes.{key}" if key == "state" else str(key)
        diff[field_name] = _diff_entry(old_value, new_value)

    changed_all = tuple(diff)
    if relevant_fields is None:
        changed_relevant = tuple(
            field for field in changed_all if field == "state" or field not in DEFAULT_IRRELEVANT_FIELDS
        )
    else:
        relevant = {str(item) for item in relevant_fields}
        changed_relevant = tuple(field for field in changed_all if field in relevant)

    return FrozenDict(
        {
            "changed_fields": FrozenList(changed_relevant),
            "changed_fields_all": FrozenList(changed_all),
            "changed_fields_relevant": FrozenList(changed_relevant),
            "diff": FrozenDict(diff),
            "has_changes": bool(changed_all),
            "has_relevant_changes": bool(changed_relevant),
        }
    )


__all__ = [
    "DEFAULT_IRRELEVANT_FIELDS",
    "FrozenDict",
    "FrozenList",
    "MISSING",
    "build_state_diff",
    "capture_state_snapshot",
    "freeze_json",
    "thaw_json",
]
