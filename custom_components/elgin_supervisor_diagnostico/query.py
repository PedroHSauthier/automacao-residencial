"""Safe SQL query compiler for the diagnostic event store.

Only SQL fragments declared in this module can reach the generated statement.
All user-controlled values, including JSON paths, are bound parameters.
"""

from __future__ import annotations

import base64
from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any, Final

from .snapshot import freeze_json, thaw_json


class QueryValidationError(ValueError):
    """Raised when a frontend filter cannot be represented safely."""


@dataclass(frozen=True, slots=True)
class FieldSpec:
    column: str
    kind: str = "text"


@dataclass(frozen=True, slots=True)
class CursorData:
    occurred_at: str
    event_id: str
    direction: str = "older"
    query_fingerprint: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "occurred_at": self.occurred_at,
            "event_id": self.event_id,
            "direction": self.direction,
            "query_fingerprint": self.query_fingerprint,
        }


FILTER_FIELDS: Final[dict[str, FieldSpec]] = {
    "event_id": FieldSpec("e.event_id"),
    "occurred_at": FieldSpec("e.occurred_at", "datetime"),
    "received_at": FieldSpec("e.received_at", "datetime"),
    "category": FieldSpec("e.category"),
    "event_type": FieldSpec("e.event_type"),
    "severity": FieldSpec("e.severity"),
    "outcome": FieldSpec("e.outcome"),
    "summary": FieldSpec("e.summary"),
    "technical_message": FieldSpec("e.technical_message"),
    "entity_id": FieldSpec("e.source_entity_id"),
    "domain": FieldSpec("e.entity_domain"),
    "source_component": FieldSpec("e.source_component"),
    "origin": FieldSpec("e.origin_class"),
    "origin_class": FieldSpec("e.origin_class"),
    "actor_type": FieldSpec("e.actor_type"),
    "actor_name": FieldSpec("e.actor_name"),
    "user_id": FieldSpec("e.user_id"),
    "user_name": FieldSpec("e.user_name"),
    "context_id": FieldSpec("e.context_id"),
    "parent_context_id": FieldSpec("e.parent_context_id"),
    "correlation_id": FieldSpec("e.correlation_id"),
    "evaluation_id": FieldSpec("e.evaluation_id"),
    "mode": FieldSpec("e.climate_mode"),
    "treatment": FieldSpec("e.treatment"),
    "preset": FieldSpec("e.preset"),
    "power_profile": FieldSpec("e.power_profile"),
    "agenda": FieldSpec("e.agenda_state"),
    "rule": FieldSpec("json_extract(e.details_json, '$.rule')"),
    "protection": FieldSpec("e.protection"),
    "activation_model": FieldSpec("e.trigger_model"),
    "function": FieldSpec("e.function"),
    "temperature": FieldSpec("json_extract(e.details_json, '$.temperature')", "number"),
    "target_temperature": FieldSpec("json_extract(e.details_json, '$.target_temperature')", "number"),
    "humidity": FieldSpec("json_extract(e.details_json, '$.humidity')", "number"),
    "action_domain": FieldSpec("e.action_domain"),
    "action_name": FieldSpec("e.action_name"),
    "transmission_id": FieldSpec("e.transmission_id"),
    "audibility": FieldSpec("e.expected_audibility"),
    "is_external": FieldSpec("e.is_external", "boolean"),
    "is_anomaly": FieldSpec("e.is_anomaly", "boolean"),
    "anomaly_type": FieldSpec("e.anomaly_type"),
    "confirmation_state": FieldSpec("e.confirmation_state"),
    "changed_fields_all": FieldSpec("e.changed_fields_all", "json_array"),
    "changed_fields_relevant": FieldSpec("e.changed_fields_relevant", "json_array"),
    "retention_class": FieldSpec("e.retention_class"),
    "compacted_count": FieldSpec("e.compacted_count", "number"),
    "fingerprint": FieldSpec("e.fingerprint"),
}

OPERATORS: Final = frozenset(
    {
        "eq",
        "ne",
        "contains",
        "not_contains",
        "starts",
        "ends",
        "gt",
        "gte",
        "lt",
        "lte",
        "in",
        "not_in",
        "exists",
        "not_exists",
        "changed",
        "not_changed",
        "before",
        "after",
        "between",
    }
)

_MAX_LIMIT: Final = 250
_MAX_GROUP_DEPTH: Final = 5
_MAX_CONDITIONS: Final = 100
_MAX_MULTISELECT: Final = 250
_DYNAMIC_FIELD = re.compile(r"^(before|after|diff)\.([A-Za-z0-9_.:-]{1,180})$")

_SUMMARY_COLUMNS: Final = (
    "e.event_id",
    "e.occurred_at",
    "e.occurred_at_local",
    "e.received_at",
    "e.category",
    "e.event_type",
    "e.severity",
    "e.summary",
    "e.source_entity_id",
    "e.entity_domain",
    "e.actor_type",
    "e.actor_name",
    "e.origin_class",
    "e.user_id",
    "e.user_name",
    "e.correlation_id",
    "e.evaluation_id",
    "e.climate_mode",
    "e.treatment",
    "e.preset",
    "e.power_profile",
    "e.agenda_state",
    "e.protection",
    "e.trigger_model",
    "e.function",
    "e.outcome",
    "e.action_domain",
    "e.action_name",
    "e.transmission_id",
    "e.expected_audibility",
    "e.is_external",
    "e.is_anomaly",
    "e.anomaly_type",
    "e.confirmation_state",
    "e.changed_fields_all",
    "e.changed_fields_relevant",
    "e.retention_class",
    "e.compacted_count",
    "e.fingerprint",
)

_SIMPLE_FILTERS: Final[dict[str, tuple[str, str]]] = {
    "category": ("category", "eq"),
    "categories": ("category", "in"),
    "event_type": ("event_type", "eq"),
    "event_types": ("event_type", "in"),
    "severity": ("severity", "eq"),
    "severities": ("severity", "in"),
    "outcome": ("outcome", "eq"),
    "outcomes": ("outcome", "in"),
    "actor": ("actor_name", "eq"),
    "actors": ("actor_name", "in"),
    "origin": ("origin", "eq"),
    "origins": ("origin", "in"),
    # The filter catalog exposes resolved display names under ``user``.
    "user": ("user_name", "eq"),
    "users": ("user_name", "in"),
    "user_id": ("user_id", "eq"),
    "user_ids": ("user_id", "in"),
    "entity": ("entity_id", "eq"),
    "entities": ("entity_id", "in"),
    "entity_id": ("entity_id", "eq"),
    "entity_ids": ("entity_id", "in"),
    "domain": ("domain", "eq"),
    "domains": ("domain", "in"),
    "mode": ("mode", "eq"),
    "modes": ("mode", "in"),
    "treatment": ("treatment", "eq"),
    "treatments": ("treatment", "in"),
    "preset": ("preset", "eq"),
    "presets": ("preset", "in"),
    "power_profile": ("power_profile", "eq"),
    "power_profiles": ("power_profile", "in"),
    "power": ("power_profile", "eq"),
    "powers": ("power_profile", "in"),
    "agenda": ("agenda", "eq"),
    "agendas": ("agenda", "in"),
    "protection": ("protection", "eq"),
    "protections": ("protection", "in"),
    "audibility": ("audibility", "eq"),
    "audibilities": ("audibility", "in"),
    "activation_model": ("activation_model", "eq"),
    "activation_models": ("activation_model", "in"),
    "function": ("function", "eq"),
    "functions": ("function", "in"),
    "action": ("action_name", "eq"),
    "actions": ("action_name", "in"),
    "temperature": ("temperature", "eq"),
    "target_temperature": ("target_temperature", "eq"),
    "humidity": ("humidity", "eq"),
    "is_external": ("is_external", "eq"),
    "external": ("is_external", "eq"),
    "is_anomaly": ("is_anomaly", "eq"),
    "anomaly": ("is_anomaly", "eq"),
    "anomaly_type": ("anomaly_type", "eq"),
    "anomaly_types": ("anomaly_type", "in"),
    "confirmation_state": ("confirmation_state", "eq"),
    "confirmation_states": ("confirmation_state", "in"),
    "has_error": ("has_error", "eq"),
    "changed_fields": ("changed_field", "changed"),
    "fields_changed": ("changed_field", "changed"),
    "correlation_id": ("correlation_id", "eq"),
    "evaluation_id": ("evaluation_id", "eq"),
    "transmission_id": ("transmission_id", "eq"),
    "retention_class": ("retention_class", "eq"),
    "retention_classes": ("retention_class", "in"),
}


def _canonical_payload(filters: dict[str, Any] | None) -> str:
    value = thaw_json(freeze_json(filters or {}))
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def fingerprint_filters(filters: dict[str, Any] | None) -> str:
    return hashlib.sha256(_canonical_payload(filters).encode("utf-8")).hexdigest()[:24]


def encode_cursor(
    occurred_at: str,
    event_id: str,
    direction: str = "older",
    query_fingerprint: str | None = None,
) -> str:
    if direction not in {"older", "newer"}:
        raise QueryValidationError("Direção de cursor inválida")
    if not occurred_at or not event_id:
        raise QueryValidationError("Cursor exige horário e event_id")
    payload = {
        "v": 1,
        "t": str(occurred_at),
        "i": str(event_id),
        "d": direction,
        "q": str(query_fingerprint) if query_fingerprint else None,
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str) -> CursorData:
    if not isinstance(cursor, str) or not 1 <= len(cursor) <= 2_048:
        raise QueryValidationError("Cursor inválido")
    try:
        padding = "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(cursor + padding))
    except Exception as err:  # noqa: BLE001 - normalized as a validation error
        raise QueryValidationError("Cursor inválido") from err
    # Read legacy [occurred_at, event_id] cursors without weakening validation.
    if isinstance(payload, list) and len(payload) == 2:
        return CursorData(str(payload[0]), str(payload[1]))
    if not isinstance(payload, dict) or payload.get("v") != 1:
        raise QueryValidationError("Versão de cursor inválida")
    direction = payload.get("d", "older")
    if direction not in {"older", "newer"}:
        raise QueryValidationError("Direção de cursor inválida")
    occurred_at = payload.get("t")
    event_id = payload.get("i")
    if not isinstance(occurred_at, str) or not occurred_at or not isinstance(event_id, str) or not event_id:
        raise QueryValidationError("Cursor incompleto")
    query_fingerprint = payload.get("q")
    if query_fingerprint is not None and not isinstance(query_fingerprint, str):
        raise QueryValidationError("Fingerprint de cursor inválido")
    return CursorData(occurred_at, event_id, direction, query_fingerprint)


def _like_pattern(value: Any, position: str) -> str:
    escaped = str(value).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    if position == "contains":
        return f"%{escaped}%"
    if position == "starts":
        return f"{escaped}%"
    if position == "ends":
        return f"%{escaped}"
    return escaped


def _json_path(field: str) -> str:
    parts = field.split(".")
    if parts[0] == "attributes":
        path_parts = parts
    elif parts[0] in {"state", "entity_id", "last_changed", "last_updated", "context"}:
        path_parts = parts
    else:
        path_parts = ["attributes", *parts]
    return "$" + "".join(f".{json.dumps(part, ensure_ascii=False)}" for part in path_parts)


@dataclass(slots=True)
class _Expression:
    sql: str
    params: list[Any]
    kind: str
    json_column: str | None = None
    json_path: str | None = None


def _resolve_field(field: str) -> _Expression:
    spec = FILTER_FIELDS.get(field)
    if spec:
        return _Expression(spec.column, [], spec.kind)
    dynamic = _DYNAMIC_FIELD.fullmatch(field)
    if dynamic:
        location, json_field = dynamic.groups()
        column = {
            "before": "e.before_json",
            "after": "e.after_json",
            "diff": "e.diff_json",
        }[location]
        path = _json_path(json_field) if location != "diff" else "$" + "".join(
            f".{json.dumps(part, ensure_ascii=False)}" for part in json_field.split(".")
        )
        return _Expression(
            f"json_extract({column}, ?)",
            [path],
            "json",
            json_column=column,
            json_path=path,
        )
    if field in {"changed_field", "has_change", "has_correlation", "has_transmission", "has_error"}:
        return _Expression(field, [], "special")
    raise QueryValidationError(f"Campo de filtro não permitido: {field!r}")


def _normalize_multiselect(value: Any) -> list[Any]:
    if isinstance(value, (list, tuple, set, frozenset)):
        values = list(value)
    else:
        values = [value]
    if not values or len(values) > _MAX_MULTISELECT:
        raise QueryValidationError("Multiselect vazio ou acima do limite")
    return values


def _boolean(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = str(value or "").strip().casefold()
    if normalized in {"1", "true", "yes", "on", "sim"}:
        return True
    if normalized in {"0", "false", "no", "off", "não", "nao", ""}:
        return False
    raise QueryValidationError(f"Valor booleano inválido: {value!r}")


def _numeric(value: Any) -> float:
    if isinstance(value, bool):
        raise QueryValidationError(f"Valor numérico inválido: {value!r}")
    try:
        numeric = float(value)
    except (TypeError, ValueError, OverflowError) as err:
        raise QueryValidationError(f"Valor numérico inválido: {value!r}") from err
    if numeric != numeric or numeric in {float("inf"), float("-inf")}:
        raise QueryValidationError(f"Valor numérico inválido: {value!r}")
    return numeric


def _retention_values(value: Any) -> list[Any]:
    """Return every persisted spelling equivalent to one retention class.

    Schema versions before the canonical terminology stored ``absolute`` and
    ``full``.  New rows store ``essential`` and ``trace``.  Queries must span
    both spellings until all supported databases have naturally aged out their
    legacy rows; mapping to only one spelling would make half the timeline
    invisible.
    """

    aliases: dict[str, tuple[str, str]] = {
        "essential": ("essential", "absolute"),
        "absolute": ("essential", "absolute"),
        "trace": ("trace", "full"),
        "full": ("trace", "full"),
    }
    if isinstance(value, str):
        return list(aliases.get(value.casefold(), (value,)))
    return [value]


def _expanded_retention_values(value: Any) -> list[Any]:
    values: list[Any] = []
    for item in _normalize_multiselect(value):
        for candidate in _retention_values(item):
            if candidate not in values:
                values.append(candidate)
    return values


def _changed_field_sql(value: Any, *, negate: bool = False) -> tuple[str, list[Any]]:
    values = _normalize_multiselect(value)
    placeholders = ",".join("?" for _ in values)
    expression = (
        "EXISTS (SELECT 1 FROM json_each(COALESCE(e.changed_fields_all, '[]')) AS cf "
        f"WHERE cf.value IN ({placeholders}))"
    )
    return (f"NOT ({expression})" if negate else expression, values)


def _compile_special(field: str, operator: str, value: Any) -> tuple[str, list[Any]]:
    if field == "changed_field":
        if operator in {"changed", "eq", "in", "contains"}:
            return _changed_field_sql(value)
        if operator in {"not_changed", "ne", "not_in", "not_contains"}:
            return _changed_field_sql(value, negate=True)
        raise QueryValidationError("Operador inválido para changed_field")

    positive = _boolean(value) if value is not None else True
    if operator == "ne":
        positive = not positive
    elif operator not in {"eq", "exists", "not_exists"}:
        raise QueryValidationError(f"Operador inválido para {field}")
    if operator == "not_exists":
        positive = False
    expressions = {
        "has_change": "json_array_length(COALESCE(e.changed_fields_all, '[]')) > 0",
        "has_correlation": "e.correlation_id IS NOT NULL AND e.correlation_id <> ''",
        "has_transmission": "e.transmission_id IS NOT NULL AND e.transmission_id <> ''",
        "has_error": "e.severity IN ('error','critical')",
    }
    expression = expressions[field]
    return (expression if positive else f"NOT ({expression})", [])


def _compile_condition(condition: dict[str, Any]) -> tuple[str, list[Any]]:
    if not isinstance(condition, dict):
        raise QueryValidationError("Condição deve ser um objeto")
    unknown = set(condition) - {"field", "operator", "value"}
    if unknown:
        raise QueryValidationError(
            "Propriedades de condição desconhecidas: " + ", ".join(sorted(unknown))
        )
    field = str(condition.get("field") or "")
    operator = str(condition.get("operator", "eq")).casefold()
    if operator not in OPERATORS:
        raise QueryValidationError(f"Operador não permitido: {operator!r}")
    value = condition.get("value")
    expression = _resolve_field(field)
    if expression.kind == "special":
        return _compile_special(field, operator, value)

    if operator in {"changed", "not_changed"}:
        changed_name = field.split(".", 1)[1] if field.startswith(("before.", "after.", "diff.")) else field
        return _changed_field_sql(changed_name, negate=operator == "not_changed")

    if expression.json_column and operator in {"exists", "not_exists"}:
        sql = f"json_type({expression.json_column}, ?) IS {'NOT ' if operator == 'exists' else ''}NULL"
        return sql, [expression.json_path]
    if operator == "exists":
        return f"{expression.sql} IS NOT NULL", expression.params
    if operator == "not_exists":
        return f"{expression.sql} IS NULL", expression.params

    sql_expression = expression.sql
    params = list(expression.params)
    if expression.kind == "boolean":
        value = int(_boolean(value))
    elif (
        expression.kind == "number"
        and value is not None
        and operator in {"eq", "ne", "gt", "gte", "lt", "lte", "before", "after"}
    ):
        value = _numeric(value)
    if operator in {"eq", "ne"}:
        if value is None:
            if expression.json_column:
                comparison = "='null'" if operator == "eq" else "<>'null'"
                return f"json_type({expression.json_column}, ?){comparison}", [expression.json_path]
            return f"{sql_expression} IS {'NOT ' if operator == 'ne' else ''}NULL", params
        if field == "retention_class":
            values = _retention_values(value)
            placeholders = ",".join("?" for _ in values)
            params.extend(values)
            return (
                f"{sql_expression} {'NOT IN' if operator == 'ne' else 'IN'} "
                f"({placeholders})",
                params,
            )
        params.append(value)
        return f"{sql_expression} {'<>' if operator == 'ne' else '='} ?", params

    if operator in {"contains", "not_contains", "starts", "ends"}:
        pattern_kind = "contains" if operator in {"contains", "not_contains"} else operator
        params.append(_like_pattern(value, pattern_kind))
        sql = f"LOWER(COALESCE(CAST({sql_expression} AS TEXT), '')) LIKE LOWER(?) ESCAPE '\\'"
        return (f"NOT ({sql})" if operator == "not_contains" else sql, params)

    if operator in {"gt", "gte", "lt", "lte", "before", "after"}:
        translated = {"gt": ">", "gte": ">=", "lt": "<", "lte": "<=", "before": "<", "after": ">"}[operator]
        if expression.kind == "json" and isinstance(value, (int, float)) and not isinstance(value, bool):
            sql_expression = f"CAST({sql_expression} AS REAL)"
        params.append(value)
        return f"{sql_expression} {translated} ?", params

    if operator == "between":
        values = _normalize_multiselect(value)
        if len(values) != 2:
            raise QueryValidationError("between exige exatamente dois valores")
        if expression.kind == "number":
            values = [_numeric(item) for item in values]
        if expression.kind == "json" and all(isinstance(item, (int, float)) for item in values):
            sql_expression = f"CAST({sql_expression} AS REAL)"
        params.extend(values)
        return f"{sql_expression} BETWEEN ? AND ?", params

    if operator in {"in", "not_in"}:
        values = _normalize_multiselect(value)
        if expression.kind == "number":
            values = [_numeric(item) for item in values]
        if field == "retention_class":
            values = _expanded_retention_values(values)
        placeholders = ",".join("?" for _ in values)
        params.extend(values)
        return f"{sql_expression} {'NOT IN' if operator == 'not_in' else 'IN'} ({placeholders})", params

    raise QueryValidationError(f"Operador não implementado: {operator}")


def _compile_group(
    group: dict[str, Any],
    *,
    depth: int = 0,
    budget: list[int] | None = None,
) -> tuple[str, list[Any]]:
    if depth > _MAX_GROUP_DEPTH:
        raise QueryValidationError("Filtro avançado excede a profundidade permitida")
    if not isinstance(group, dict):
        raise QueryValidationError("Grupo deve ser um objeto")
    logic = str(group.get("logic", group.get("operator", "and"))).casefold()
    aliases = {"all": "and", "todas": "and", "any": "or", "qualquer": "or"}
    logic = aliases.get(logic, logic)
    if logic not in {"and", "or"}:
        raise QueryValidationError("Grupo deve usar AND ou OR")
    children = group.get("conditions", group.get("children"))
    if not isinstance(children, list) or not children:
        raise QueryValidationError("Grupo de filtros vazio")
    if budget is None:
        budget = [_MAX_CONDITIONS]
    fragments: list[str] = []
    params: list[Any] = []
    for child in children:
        budget[0] -= 1
        if budget[0] < 0:
            raise QueryValidationError("Filtro excede a quantidade máxima de condições")
        if isinstance(child, dict) and ("conditions" in child or "children" in child):
            sql, child_params = _compile_group(child, depth=depth + 1, budget=budget)
        else:
            sql, child_params = _compile_condition(child)
        fragments.append(f"({sql})")
        params.extend(child_params)
    return f" {logic.upper()} ".join(fragments), params


def _global_search(value: Any) -> tuple[str, list[Any]]:
    text = str(value).strip()
    if not text:
        raise QueryValidationError("Busca global vazia")
    if len(text) > 500:
        raise QueryValidationError("Busca global excede 500 caracteres")
    pattern = _like_pattern(text, "contains")
    columns = (
        "e.summary",
        "e.technical_message",
        "e.source_entity_id",
        "e.user_name",
        "e.category",
        "e.event_type",
        "json_extract(e.details_json, '$.reason')",
        "json_extract(e.details_json, '$.rule')",
        "e.preset",
        "e.power_profile",
        "e.protection",
        "e.action_name",
        "e.correlation_id",
    )
    fragment = " OR ".join(
        f"LOWER(COALESCE({column}, '')) LIKE LOWER(?) ESCAPE '\\'" for column in columns
    )
    return f"({fragment})", [pattern] * len(columns)


def _simple_conditions(filters: dict[str, Any]) -> tuple[list[str], list[Any], set[str]]:
    fragments: list[str] = []
    params: list[Any] = []
    consumed: set[str] = set()
    for key, (field, default_operator) in _SIMPLE_FILTERS.items():
        if key not in filters or filters[key] in ("", [], ()):
            continue
        value = filters[key]
        operator = default_operator
        if operator == "eq" and isinstance(value, (list, tuple, set, frozenset)):
            operator = "in"
        sql, condition_params = _compile_condition(
            {"field": field, "operator": operator, "value": value}
        )
        fragments.append(sql)
        params.extend(condition_params)
        consumed.add(key)

    start = filters.get("start")
    end = filters.get("end")
    period = filters.get("period")
    if isinstance(period, dict):
        start = period.get("start", start)
        end = period.get("end", end)
        consumed.add("period")
    if start not in (None, ""):
        fragments.append("e.occurred_at >= ?")
        params.append(str(start))
        consumed.add("start")
    if end not in (None, ""):
        fragments.append("e.occurred_at <= ?")
        params.append(str(end))
        consumed.add("end")

    for key in ("search", "text"):
        if filters.get(key):
            sql, search_params = _global_search(filters[key])
            fragments.append(sql)
            params.extend(search_params)
            consumed.add(key)
            break

    if "changed_field" in filters and filters["changed_field"] not in (None, "", [], ()):
        sql, change_params = _changed_field_sql(filters["changed_field"])
        fragments.append(sql)
        params.extend(change_params)
        consumed.add("changed_field")

    for key in ("has_change", "has_correlation", "has_transmission"):
        if key in filters and filters[key] is not None:
            sql, special_params = _compile_special(key, "eq", filters[key])
            fragments.append(sql)
            params.extend(special_params)
            consumed.add(key)
    return fragments, params, consumed


def _compile_filter_fragments(
    filters: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[str], list[Any]]:
    if not isinstance(filters, dict | type(None)):
        raise QueryValidationError("Filtros devem ser um objeto")
    normalized = dict(filters or {})
    fragments, params, consumed = _simple_conditions(normalized)
    advanced_keys = ("advanced", "group")
    advanced = next(
        (normalized[key] for key in advanced_keys if normalized.get(key)), None
    )
    if advanced is None and ("conditions" in normalized or "children" in normalized):
        advanced = normalized
        consumed.update(
            {"logic", "operator", "conditions", "children"} & set(normalized)
        )
    if advanced is not None:
        sql, advanced_params = _compile_group(advanced)
        fragments.append(sql)
        params.extend(advanced_params)
        consumed.update(key for key in advanced_keys if key in normalized)

    allowed_meta = {"logic", "operator", "conditions", "children"}
    unknown = set(normalized) - consumed - allowed_meta
    if unknown:
        raise QueryValidationError(
            "Filtros desconhecidos: " + ", ".join(sorted(unknown))
        )
    return normalized, fragments, params


def compile_event_predicate(
    filters: dict[str, Any] | None = None,
) -> tuple[str, list[Any]]:
    """Compile filters into a safe ``WHERE`` clause for aggregate queries.

    The returned fragment assumes the events table is aliased as ``e``. It has no
    cursor, ordering, projection, or limit, so catalog/statistics backends can
    reuse the exact same filtering semantics as the timeline.
    """

    _normalized, fragments, params = _compile_filter_fragments(filters)
    where = (
        " WHERE " + " AND ".join(f"({fragment})" for fragment in fragments)
        if fragments
        else ""
    )
    return where, params


def compile_event_query(
    filters: dict[str, Any] | None = None,
    cursor: str | None = None,
    limit: int = 50,
    direction: str = "older",
    include_details: bool = False,
) -> tuple[str, list[Any]]:
    """Compile one cursor-paginated event query into SQL and bound values.

    The function never accepts table names, column names, JSON expressions, SQL,
    or ordering fragments from the caller.  ``direction='newer'`` uses an inner
    ascending page and restores descending timeline order in the outer query.
    """

    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= _MAX_LIMIT:
        raise QueryValidationError(f"Limite deve ficar entre 1 e {_MAX_LIMIT}")
    if direction not in {"older", "newer"}:
        raise QueryValidationError("Direção deve ser older ou newer")

    filters, fragments, params = _compile_filter_fragments(filters)

    if cursor:
        boundary = decode_cursor(cursor)
        expected_fingerprint = fingerprint_filters(filters)
        if boundary.query_fingerprint and boundary.query_fingerprint != expected_fingerprint:
            raise QueryValidationError("Cursor pertence a outra consulta")
        if boundary.direction != direction:
            raise QueryValidationError("Direção solicitada diverge do cursor")
        if direction == "older":
            fragments.append("(e.occurred_at < ? OR (e.occurred_at = ? AND e.event_id < ?))")
        else:
            fragments.append("(e.occurred_at > ? OR (e.occurred_at = ? AND e.event_id > ?))")
        params.extend([boundary.occurred_at, boundary.occurred_at, boundary.event_id])

    where = " WHERE " + " AND ".join(f"({fragment})" for fragment in fragments) if fragments else ""
    selection = "e.*" if include_details else ", ".join(_SUMMARY_COLUMNS)
    order = "ASC" if direction == "newer" else "DESC"
    inner = (
        f"SELECT {selection} FROM events AS e{where} "
        f"ORDER BY e.occurred_at {order}, e.event_id {order} LIMIT ?"
    )
    # The extra row is deliberate: callers trim it after deriving ``has_more``.
    params.append(limit + 1)
    if direction == "newer":
        return (
            f"SELECT * FROM ({inner}) AS page ORDER BY occurred_at DESC, event_id DESC",
            params,
        )
    return inner, params


__all__ = [
    "CursorData",
    "FILTER_FIELDS",
    "OPERATORS",
    "QueryValidationError",
    "compile_event_predicate",
    "compile_event_query",
    "decode_cursor",
    "encode_cursor",
    "fingerprint_filters",
]
