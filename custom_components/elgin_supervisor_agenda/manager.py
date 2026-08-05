"""Local recurring-rule engine for Elgin Supervisor Agenda."""

from __future__ import annotations

from copy import deepcopy
import asyncio
from datetime import date, datetime, time, timedelta
import logging
from collections.abc import Callable
from typing import Any
from uuid import uuid4

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import (
    async_track_point_in_time,
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import (
    ABSOLUTE_GLOBAL_EFFECTS,
    ABSOLUTE_MODE_EFFECTS,
    ADDITIVE_EFFECTS,
    CATALOG_ENTITIES,
    DOMAIN,
    EFFECT_LABELS,
    EFFECT_VALUE_LABELS,
    GLOBAL_ACTIONS,
    MODE_NAMES,
    MODES,
    POWER_ENTITIES,
    STORAGE_KEY_PREFIX,
    STORAGE_VERSION,
    UPDATE_INTERVAL,
)
from .powers import PowerManagerMixin, find_power_profile
from .presets import (
    PresetValidationError,
    calculate_preset_state,
    default_presets,
    find_preset,
    migrate_base_presets,
    normalize_preset,
    public_catalog,
    validate_preset,
)

_LOGGER = logging.getLogger(__name__)

DEFAULT_POWER_LEVELS = ["Fraco", "Normal", "Forte", "Extremo"]
DEFAULT_PRESETS = ["Personalizado", "Economia", "Equilíbrio", "Conforto", "Agressivo"]


def _parse_date(value: Any, fallback: date | None = None) -> date | None:
    if isinstance(value, date) and not isinstance(value, datetime):
        return value
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            return fallback
    return fallback


def _parse_time(value: Any, fallback: time = time(0, 0)) -> time:
    if isinstance(value, time):
        return value.replace(tzinfo=None)
    if isinstance(value, str) and value:
        try:
            return time.fromisoformat(value[:8])
        except ValueError:
            return fallback
    return fallback


def _parse_datetime(value: Any, tz) -> datetime | None:
    if isinstance(value, datetime):
        result = value
    elif isinstance(value, str) and value:
        try:
            result = datetime.fromisoformat(value)
        except ValueError:
            return None
    else:
        return None
    if result.tzinfo is None:
        result = result.replace(tzinfo=tz)
    return dt_util.as_local(result)


def _as_bool(value: Any, default: bool = True) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() not in {"false", "off", "0", "no"}
    if value is None:
        return default
    return bool(value)


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _unique_ordered(values: list[str]) -> list[str]:
    result: list[str] = []
    for value in values:
        if value and value not in result:
            result.append(value)
    return result


class AgendaManager(PowerManagerMixin):
    """Store rules, expand recurrence, and consolidate active effects."""

    def __init__(self, hass: HomeAssistant, entry_id: str, name: str) -> None:
        self.hass = hass
        self.entry_id = entry_id
        self.name = name
        self.store = Store(
            hass, STORAGE_VERSION, f"{STORAGE_KEY_PREFIX}.{entry_id}"
        )
        self.enabled = True
        self.rules: list[dict[str, Any]] = []
        self.presets: list[dict[str, Any]] = []
        self.base_presets: dict[str, str] = {}
        self.preset_state: dict[str, Any] = {"modes": {}, "active_mode": None}
        self._preset_revision = 0
        self._listeners: set[Callable[[], None]] = set()
        self._revision = 0
        self._rules_revision = 0
        self._last_operation = "Inicialização concluída"
        self._last_operation_at: datetime | None = None
        self.policy: dict[str, Any] = self._empty_policy()
        self._power_init()
        self.catalog: dict[str, Any] = self._discover_catalog()
        self.current_occurrences: list[dict[str, Any]] = []
        self.next_transition: datetime | None = None
        self._unsub_interval = None
        self._unsub_states = None
        self._last_signature = ""
        self._evaluation_lock = asyncio.Lock()
        self._evaluation_sequence = 0
        self._evaluation_id = ""
        self._evaluated_at: datetime | None = None
        self._integrity: dict[str, Any] = {"ok": True, "issues": []}
        self._snapshot: dict[str, Any] = {}
        self._unsub_transition = None

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        """Register an entity/frontend update listener."""
        self._listeners.add(listener)

        @callback
        def remove_listener() -> None:
            self._listeners.discard(listener)

        return remove_listener

    @callback
    def _notify_listeners(self) -> None:
        """Push the current in-memory policy to every entity immediately."""
        for listener in tuple(self._listeners):
            try:
                listener()
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Falha ao atualizar uma entidade da Agenda")

    def _set_operation(self, message: str) -> None:
        """Record the last explicit operation for diagnostics."""
        self._last_operation = message
        self._last_operation_at = dt_util.now()

    async def async_load(self) -> None:
        """Load persistent data and start local evaluation."""
        data = await self.store.async_load() or {}
        self.enabled = _as_bool(data.get("enabled"), True)
        self.rules = [self._normalize_rule(rule) for rule in data.get("rules", [])]
        stored_presets = data.get("presets")
        if isinstance(stored_presets, list) and stored_presets:
            normalized_presets: list[dict[str, Any]] = []
            for preset in stored_presets:
                try:
                    item = normalize_preset(preset)
                    validate_preset(item, normalized_presets)
                    normalized_presets.append(item)
                except (PresetValidationError, TypeError, ValueError):
                    _LOGGER.exception("Preset persistido inválido ignorado: %s", preset)
            self.presets = normalized_presets or default_presets(self.hass)
        else:
            self.presets = default_presets(self.hass)
            self._preset_revision += 1
        stored_base = data.get("base_presets")
        self.base_presets = (
            {mode: str(stored_base.get(mode, "")) for mode in MODES}
            if isinstance(stored_base, dict)
            else migrate_base_presets(self.hass, self.presets)
        )
        self._repair_base_presets()
        # Migrate legacy rule values from display names to immutable preset ids
        # only after the mode-separated catalog exists.
        self.rules = [self._normalize_rule(rule) for rule in self.rules]
        self._power_load(data)
        self._repair_rule_profile_references()
        self.catalog = self._discover_catalog()
        await self.async_save()
        await self.async_evaluate(force=True)
        self._unsub_interval = async_track_time_interval(
            self.hass, self._async_interval, UPDATE_INTERVAL
        )
        self._unsub_states = async_track_state_change_event(
            self.hass, CATALOG_ENTITIES, self._async_catalog_changed
        )

    async def async_unload(self) -> None:
        """Stop listeners."""
        self._power_unload()
        if self._unsub_interval:
            self._unsub_interval()
        if self._unsub_states:
            self._unsub_states()
        if self._unsub_transition:
            self._unsub_transition()
            self._unsub_transition = None

    async def _async_interval(self, now: datetime) -> None:
        await self.async_evaluate()

    async def _async_catalog_changed(self, event) -> None:
        self.catalog = self._discover_catalog()
        await self.async_evaluate(force=True)

    async def async_save(self) -> None:
        await self.store.async_save(
            {
                "enabled": self.enabled,
                "rules": deepcopy(self.rules),
                "presets": deepcopy(self.presets),
                "base_presets": dict(self.base_presets),
                **self._power_storage_payload(),
            }
        )

    def _discover_catalog(self) -> dict[str, Any]:
        preset_catalog = public_catalog(self.presets, self.base_presets)
        return {
            "modes": dict(MODE_NAMES),
            **preset_catalog,
            **self._power_catalog(),
        }

    def _normalize_rule(self, rule: dict[str, Any], *, strict: bool = False) -> dict[str, Any]:
        today = dt_util.now().date()
        normalized = deepcopy(rule)
        normalized["id"] = str(normalized.get("id") or uuid4())
        normalized["name"] = str(normalized.get("name") or "Regra sem nome")[:120]
        normalized["enabled"] = _as_bool(normalized.get("enabled"), True)
        normalized["priority"] = max(0, min(100, _safe_int(normalized.get("priority"), 50)))
        normalized["recurrence"] = str(normalized.get("recurrence") or "weekly")
        normalized["interval"] = max(1, _safe_int(normalized.get("interval"), 1))
        normalized["start_date"] = str(
            _parse_date(normalized.get("start_date"), today) or today
        )
        end_date = _parse_date(normalized.get("end_date"))
        normalized["end_date"] = str(end_date) if end_date else ""
        normalized["start_time"] = _parse_time(
            normalized.get("start_time"), time(0, 0)
        ).strftime("%H:%M:%S")
        normalized["end_time"] = _parse_time(
            normalized.get("end_time"), time(23, 59, 59)
        ).strftime("%H:%M:%S")
        normalized["all_day"] = _as_bool(normalized.get("all_day"), False)
        normalized["weekdays"] = sorted(
            {
                max(0, min(6, _safe_int(day)))
                for day in normalized.get("weekdays", [])
            }
        )
        normalized["months"] = sorted(
            {
                max(1, min(12, _safe_int(month)))
                for month in normalized.get("months", [])
            }
        )
        normalized["monthdays"] = sorted(
            {
                max(1, min(31, _safe_int(day)))
                for day in normalized.get("monthdays", [])
            }
        )
        normalized["exclude_dates"] = sorted(
            {
                parsed.isoformat()
                for item in normalized.get("exclude_dates", [])
                if (parsed := _parse_date(item)) is not None
            }
        )
        normalized["ordinal"] = max(-5, min(5, _safe_int(normalized.get("ordinal"), 0)))
        normalized["ordinal_weekday"] = max(
            0, min(6, _safe_int(normalized.get("ordinal_weekday"), 0))
        )
        modes = normalized.get("modes", list(MODES))
        normalized["modes"] = [mode for mode in modes if mode in MODES] or list(MODES)
        effects = []
        for effect in normalized.get("effects", []):
            if not isinstance(effect, dict) or not effect.get("type"):
                continue
            item = deepcopy(effect)
            item["type"] = str(item["type"])
            supported_effects = (
                {"global_action", "enable_modes", "disable_modes", "only_modes", "enable_all_modes", "disable_all_modes"}
                | set(ADDITIVE_EFFECTS)
                | set(ABSOLUTE_MODE_EFFECTS)
                | set(ABSOLUTE_GLOBAL_EFFECTS)
            )
            if item["type"] not in supported_effects:
                if strict:
                    raise ValueError(f"Efeito não suportado pelo Supervisor: {item['type']}")
                item["unsupported"] = True
            item["modes"] = [
                mode for mode in item.get("modes", normalized["modes"]) if mode in MODES
            ] or list(normalized["modes"])
            if strict and item["type"] in ADDITIVE_EFFECTS:
                try:
                    float(item.get("value"))
                except (TypeError, ValueError) as err:
                    raise ValueError(
                        f"O efeito {item['type']} exige valor numérico."
                    ) from err
            if item["type"] == "preset":
                # Legacy rules could apply one display name to several modes.
                # Migrate them into one immutable preset reference per mode,
                # preserving the old scope without ever crossing mode catalogs.
                migrated = False
                for mode in item["modes"]:
                    match = (
                        find_preset(self.presets, item.get("value"), mode)
                        if self.presets
                        else None
                    )
                    if match:
                        effects.append(
                            {
                                **item,
                                "value": match["id"],
                                "modes": [mode],
                            }
                        )
                        migrated = True
                if not migrated and item["modes"]:
                    if strict:
                        raise ValueError(
                            "O preset informado não existe, está desabilitado ou pertence a outro modo."
                        )
                    # Keep one unresolved legacy reference for diagnostics; the
                    # calculator rejects it safely instead of crossing modes.
                    effects.append({**item, "modes": [item["modes"][0]], "invalid_reference": True})
                continue
            effects.append(item)
        normalized["effects"] = effects
        normalized["notes"] = str(normalized.get("notes") or "")[:500]
        return normalized

    def _repair_base_presets(self) -> None:
        """Guarantee one valid enabled base preset for every mode."""
        for mode in MODES:
            base = find_preset(self.presets, self.base_presets.get(mode), mode)
            if base and base.get("enabled", True):
                continue
            default = find_preset(self.presets, f"{mode}_equilibrio", mode)
            enabled = sorted(
                [item for item in self.presets if item["mode"] == mode and item.get("enabled", True)],
                key=lambda item: (abs(item["level"]), item["level"]),
            )
            replacement = default if default and default.get("enabled", True) else (enabled[0] if enabled else None)
            if replacement:
                self.base_presets[mode] = replacement["id"]

    async def async_upsert_preset(self, preset: dict[str, Any]) -> dict[str, Any]:
        """Create or update a mode-specific preset."""
        preset_id = str(preset.get("id") or "")
        existing = find_preset(self.presets, preset_id) if preset_id else None
        normalized = normalize_preset(preset, existing)
        validate_preset(normalized, self.presets)
        updated = existing is not None
        if updated:
            index = next(index for index, item in enumerate(self.presets) if item["id"] == existing["id"])
            self.presets[index] = normalized
        else:
            self.presets.append(normalized)
        self._repair_base_presets()
        self._preset_revision += 1
        self._rules_revision += 1
        self._set_operation(f"Preset {'atualizado' if updated else 'criado'}: {normalized['name']} ({MODE_NAMES[normalized['mode']]})")
        self.catalog = self._discover_catalog()
        await self.async_save()
        await self.async_evaluate(force=True)
        return deepcopy(normalized)

    async def async_delete_preset(self, preset_id: str) -> bool:
        """Delete a non-protected preset and repair references."""
        existing = find_preset(self.presets, preset_id)
        if existing is None:
            return False
        if existing.get("protected") or existing.get("default"):
            raise PresetValidationError("O preset padrão protegido não pode ser excluído.")
        self.presets = [item for item in self.presets if item["id"] != preset_id]
        for rule in self.rules:
            rule["effects"] = [
                effect
                for effect in rule.get("effects", [])
                if not (effect.get("type") == "preset" and str(effect.get("value")) == preset_id)
            ]
        self._repair_base_presets()
        self._preset_revision += 1
        self._rules_revision += 1
        self._set_operation(f"Preset excluído: {existing['name']} ({MODE_NAMES[existing['mode']]})")
        self.catalog = self._discover_catalog()
        await self.async_save()
        await self.async_evaluate(force=True)
        return True

    async def async_set_base_preset(self, mode: str, preset_id: str) -> dict[str, Any]:
        """Set the persistent manual base for exactly one mode."""
        if mode not in MODES:
            raise PresetValidationError("Modo de preset inválido.")
        preset = find_preset(self.presets, preset_id, mode)
        if preset is None or not preset.get("enabled", True):
            raise PresetValidationError("O preset base deve estar habilitado e pertencer ao modo selecionado.")
        self.base_presets[mode] = preset["id"]
        # The base condition preset and the local cycle limits are one
        # configuration surface. Keep both persistent views synchronized.
        if getattr(self, "power_settings", None):
            limits = self.power_settings.setdefault("cycle_limits", {}).setdefault(mode, {})
            limits["start"] = preset["start"]
            limits["stop"] = preset["stop"]
            if mode == "dry":
                limits["minimum_temperature"] = preset.get("minimum_temperature", 20.0)
            self._power_revision += 1
        self._preset_revision += 1
        self._set_operation(f"Preset base de {MODE_NAMES[mode]} alterado para {preset['name']}")
        self.catalog = self._discover_catalog()
        await self.async_save()
        await self.async_evaluate(force=True)
        return deepcopy(preset)

    async def async_duplicate_preset(self, preset_id: str, mode: str | None = None) -> dict[str, Any]:
        """Duplicate a preset, optionally translating it to another mode."""
        source = find_preset(self.presets, preset_id)
        if source is None:
            raise PresetValidationError("Preset de origem não encontrado.")
        target_mode = mode or source["mode"]
        if target_mode not in MODES:
            raise PresetValidationError("Modo de destino inválido.")
        duplicate = deepcopy(source)
        duplicate.pop("id", None)
        duplicate["mode"] = target_mode
        duplicate["name"] = f"{source['name']} — cópia"
        duplicate["enabled"] = False
        duplicate["protected"] = False
        duplicate["default"] = False
        if target_mode == "dry":
            duplicate["start"] = 63
            duplicate["stop"] = 57
            duplicate["minimum_temperature"] = 19.0
        elif source["mode"] == "dry":
            duplicate["start"] = 18.0 if target_mode == "heat" else 25.2
            duplicate["stop"] = 20.2 if target_mode == "heat" else 22.7
            duplicate["minimum_temperature"] = None
        return await self.async_upsert_preset(duplicate)

    def public_presets(self) -> list[dict[str, Any]]:
        return deepcopy(sorted(self.presets, key=lambda item: (MODES.index(item["mode"]), item["level"], item["name"].casefold())))

    async def async_set_enabled(self, enabled: bool) -> None:
        self.enabled = enabled
        self._rules_revision += 1
        self._set_operation("Agenda habilitada" if enabled else "Agenda desabilitada")
        await self.async_save()
        await self.async_evaluate(force=True)

    async def async_upsert_rule(self, rule: dict[str, Any]) -> dict[str, Any]:
        normalized = self._normalize_rule(rule, strict=True)
        for effect in normalized.get("effects", []):
            if effect.get("type") not in {"power_base", "power_force", "power_min", "power_max"}:
                continue
            modes = effect.get("modes") or normalized.get("modes") or list(MODES)
            value_by_mode = effect.get("value_by_mode") if isinstance(effect.get("value_by_mode"), dict) else {}
            for mode in modes:
                value = value_by_mode.get(mode, effect.get("value"))
                profile = find_power_profile(self.power_profiles, value, mode)
                if profile is None or not profile.get("enabled", True):
                    raise ValueError(
                        f"O perfil de potência {value!r} não existe, está desabilitado ou não pertence a {MODE_NAMES[mode]}."
                    )
        updated = False
        for index, existing in enumerate(self.rules):
            if existing["id"] == normalized["id"]:
                self.rules[index] = normalized
                updated = True
                break
        else:
            self.rules.append(normalized)
        self._repair_rule_profile_references()
        self.catalog = self._discover_catalog()
        self._rules_revision += 1
        self._set_operation(
            f"Regra {'atualizada' if updated else 'criada'}: {normalized['name']}"
        )
        await self.async_save()
        await self.async_evaluate(force=True)
        return normalized

    async def async_delete_rule(self, rule_id: str) -> bool:
        removed = next((rule for rule in self.rules if rule["id"] == rule_id), None)
        self.rules = [rule for rule in self.rules if rule["id"] != rule_id]
        changed = removed is not None
        if changed:
            self._rules_revision += 1
            self._set_operation(f"Regra excluída: {removed['name']}")
            await self.async_save()
        else:
            self._set_operation("Exclusão solicitada, mas a regra não foi encontrada")
        await self.async_evaluate(force=True)
        return changed

    async def async_set_rule_enabled(self, rule_id: str, enabled: bool) -> bool:
        for rule in self.rules:
            if rule["id"] == rule_id:
                rule["enabled"] = enabled
                self._rules_revision += 1
                self._set_operation(
                    f"Regra {'ativada' if enabled else 'pausada'}: {rule['name']}"
                )
                await self.async_save()
                await self.async_evaluate(force=True)
                return True
        self._set_operation("Alteração solicitada, mas a regra não foi encontrada")
        await self.async_evaluate(force=True)
        return False

    async def async_clear_rules(self) -> None:
        removed = len(self.rules)
        self.rules = []
        self._rules_revision += 1
        self._set_operation(f"Todas as regras foram removidas ({removed})")
        await self.async_save()
        await self.async_evaluate(force=True)

    async def async_cancel_active_once_rules(self) -> int:
        now = dt_util.now()
        changed = 0
        for rule in self.rules:
            if (
                rule.get("recurrence") == "once"
                and rule.get("enabled", True)
                and self._active_occurrence(rule, now)
            ):
                rule["enabled"] = False
                changed += 1
        if changed:
            self._rules_revision += 1
            self._set_operation(f"Exceções únicas canceladas: {changed}")
            await self.async_save()
        else:
            self._set_operation("Nenhuma exceção única ativa para cancelar")
        await self.async_evaluate(force=True)
        return changed

    async def async_manual_evaluate(self) -> None:
        """Force a complete catalog and policy refresh."""
        self.catalog = self._discover_catalog()
        self._set_operation("Reavaliação manual concluída")
        await self.async_evaluate(force=True)

    def _date_matches(self, rule: dict[str, Any], anchor: date) -> bool:
        start_date = _parse_date(rule.get("start_date"), anchor) or anchor
        end_date = _parse_date(rule.get("end_date"))
        if anchor < start_date or (end_date and anchor > end_date):
            return False
        if anchor.isoformat() in rule.get("exclude_dates", []):
            return False
        if rule.get("months") and anchor.month not in rule["months"]:
            return False

        recurrence = rule.get("recurrence", "weekly")
        interval = max(1, _safe_int(rule.get("interval"), 1))
        days = (anchor - start_date).days
        if days < 0:
            return False

        if recurrence == "daily":
            if days % interval != 0:
                return False
            weekdays = rule.get("weekdays", [])
            return not weekdays or anchor.weekday() in weekdays

        if recurrence == "weekly":
            weekdays = rule.get("weekdays") or [start_date.weekday()]
            weeks = (anchor - (start_date - timedelta(days=start_date.weekday()))).days // 7
            return weeks % interval == 0 and anchor.weekday() in weekdays

        if recurrence == "monthly":
            months_diff = (anchor.year - start_date.year) * 12 + anchor.month - start_date.month
            if months_diff < 0 or months_diff % interval != 0:
                return False
            monthdays = rule.get("monthdays") or [start_date.day]
            if rule.get("ordinal"):
                ordinal = _safe_int(rule.get("ordinal"))
                weekday = _safe_int(rule.get("ordinal_weekday"))
                same_weekdays = [
                    day
                    for day in range(1, 32)
                    if self._valid_date(anchor.year, anchor.month, day)
                    and date(anchor.year, anchor.month, day).weekday() == weekday
                ]
                wanted = (
                    same_weekdays[ordinal - 1]
                    if ordinal > 0 and len(same_weekdays) >= ordinal
                    else same_weekdays[ordinal]
                    if ordinal < 0 and len(same_weekdays) >= abs(ordinal)
                    else None
                )
                return anchor.day == wanted
            return anchor.day in monthdays

        if recurrence == "yearly":
            years = anchor.year - start_date.year
            return (
                years >= 0
                and years % interval == 0
                and anchor.month == start_date.month
                and anchor.day == start_date.day
            )

        return anchor == start_date

    @staticmethod
    def _valid_date(year: int, month: int, day: int) -> bool:
        try:
            date(year, month, day)
            return True
        except ValueError:
            return False

    def _occurrence_for_anchor(
        self, rule: dict[str, Any], anchor: date
    ) -> tuple[datetime, datetime] | None:
        if not self._date_matches(rule, anchor):
            return None
        tz = dt_util.DEFAULT_TIME_ZONE
        if rule.get("all_day"):
            start = datetime.combine(anchor, time.min, tzinfo=tz)
            return start, start + timedelta(days=1)
        start_time = _parse_time(rule.get("start_time"), time(0, 0))
        end_time = _parse_time(rule.get("end_time"), time(23, 59, 59))
        start = datetime.combine(anchor, start_time, tzinfo=tz)
        end_anchor = anchor + timedelta(days=1) if end_time <= start_time else anchor
        end = datetime.combine(end_anchor, end_time, tzinfo=tz)
        if end <= start:
            end = start + timedelta(minutes=1)
        return start, end

    def _active_occurrence(
        self, rule: dict[str, Any], now: datetime
    ) -> tuple[datetime, datetime] | None:
        if not rule.get("enabled", True):
            return None
        now = dt_util.as_local(now)
        if rule.get("recurrence") == "once":
            tz = dt_util.DEFAULT_TIME_ZONE
            if rule.get("all_day"):
                start_anchor = _parse_date(rule.get("start_date"), now.date()) or now.date()
                end_anchor = _parse_date(rule.get("end_date"), start_anchor) or start_anchor
                start = datetime.combine(start_anchor, time.min, tzinfo=tz)
                end = datetime.combine(end_anchor + timedelta(days=1), time.min, tzinfo=tz)
            else:
                start = _parse_datetime(rule.get("start_datetime"), tz)
                end = _parse_datetime(rule.get("end_datetime"), tz)
                if start is None:
                    anchor = _parse_date(rule.get("start_date"), now.date()) or now.date()
                    start = datetime.combine(
                        anchor, _parse_time(rule.get("start_time")), tzinfo=tz
                    )
                if end is None:
                    end_anchor = _parse_date(rule.get("end_date"), start.date()) or start.date()
                    end = datetime.combine(
                        end_anchor,
                        _parse_time(rule.get("end_time"), time(23, 59, 59)),
                        tzinfo=tz,
                    )
                    if end <= start:
                        end += timedelta(days=1)
            return (start, end) if start <= now < end else None

        for anchor in (now.date(), now.date() - timedelta(days=1)):
            occurrence = self._occurrence_for_anchor(rule, anchor)
            if occurrence and occurrence[0] <= now < occurrence[1]:
                return occurrence
        return None

    def occurrences_between(
        self, start: datetime, end: datetime, max_events: int = 2500
    ) -> list[dict[str, Any]]:
        """Expand all rule occurrences intersecting a time range."""
        start = dt_util.as_local(start)
        end = dt_util.as_local(end)
        result: list[dict[str, Any]] = []
        for rule in self.rules:
            if not rule.get("enabled", True):
                continue
            if rule.get("recurrence") == "once":
                tz = dt_util.DEFAULT_TIME_ZONE
                if rule.get("all_day"):
                    start_anchor = _parse_date(rule.get("start_date"), start.date()) or start.date()
                    end_anchor = _parse_date(rule.get("end_date"), start_anchor) or start_anchor
                    occ_start = datetime.combine(start_anchor, time.min, tzinfo=tz)
                    occ_end = datetime.combine(end_anchor + timedelta(days=1), time.min, tzinfo=tz)
                else:
                    occ_start = _parse_datetime(rule.get("start_datetime"), tz)
                    occ_end = _parse_datetime(rule.get("end_datetime"), tz)
                    if occ_start is None:
                        anchor = _parse_date(rule.get("start_date"), start.date()) or start.date()
                        occ_start = datetime.combine(
                            anchor, _parse_time(rule.get("start_time")), tzinfo=tz
                        )
                    if occ_end is None:
                        end_anchor = _parse_date(rule.get("end_date"), occ_start.date()) or occ_start.date()
                        occ_end = datetime.combine(
                            end_anchor,
                            _parse_time(rule.get("end_time"), time(23, 59, 59)),
                            tzinfo=tz,
                        )
                        if occ_end <= occ_start:
                            occ_end += timedelta(days=1)
                if occ_end > start and occ_start < end:
                    result.append(self._occurrence_dict(rule, occ_start, occ_end))
                continue

            cursor = start.date() - timedelta(days=1)
            last = end.date()
            while cursor <= last and len(result) < max_events:
                occurrence = self._occurrence_for_anchor(rule, cursor)
                if occurrence and occurrence[1] > start and occurrence[0] < end:
                    result.append(self._occurrence_dict(rule, *occurrence))
                cursor += timedelta(days=1)
        return sorted(result, key=lambda item: (item["start"], -item["priority"], item["name"]))

    def _occurrence_dict(
        self, rule: dict[str, Any], start: datetime, end: datetime
    ) -> dict[str, Any]:
        effects = [self._effect_summary(effect) for effect in rule.get("effects", [])]
        return {
            "rule_id": rule["id"],
            "name": rule["name"],
            "start": start,
            "end": end,
            "priority": rule["priority"],
            "modes": list(rule.get("modes", MODES)),
            "effects": effects,
            "notes": rule.get("notes", ""),
            "all_day": bool(rule.get("all_day", False)),
        }

    def _effect_summary(self, effect: dict[str, Any]) -> str:
        effect_type = str(effect.get("type", "efeito"))
        label = EFFECT_LABELS.get(effect_type, effect_type)
        value = effect.get("value")
        modes = [MODE_NAMES.get(mode, mode) for mode in effect.get("modes", [])]
        suffix = f" [{', '.join(modes)}]" if modes else ""
        if value in (None, ""):
            return f"{label}{suffix}"
        common_labels = {
            "default": "seguir configuração",
            "on": "ligado",
            "off": "desligado",
            True: "sim",
            False: "não",
        }
        if effect_type == "preset":
            mode = next(iter(effect.get("modes", [])), None)
            preset = find_preset(self.presets, str(value), mode)
            value_label = preset["name"] if preset else value
        elif effect_type in {"power_base", "power_force", "power_min", "power_max"}:
            mode = next(iter(effect.get("modes", [])), None)
            profile = find_power_profile(self.power_profiles, str(value), mode)
            value_label = profile["name"] if profile else value
        else:
            value_label = EFFECT_VALUE_LABELS.get(effect_type, {}).get(
                value, common_labels.get(value, value)
            )
        return f"{label}: {value_label}{suffix}"

    def _empty_policy(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "state": "Sem regras ativas",
            "active_rule_ids": [],
            "active_rule_names": [],
            "active_count": 0,
            "active_occurrences": [],
            "effective_effect_count": 0,
            "effect_sources": {},
            "global_action": "normal",
            "global_action_priority": -1,
            "modes": {mode: True for mode in MODES},
            "power_delta": {mode: 0 for mode in MODES},
            "preset_level_delta": {mode: 0 for mode in MODES},
            "priority_delta": {mode: 0 for mode in MODES},
            "preset": {mode: None for mode in MODES},
            "power_base": {mode: None for mode in MODES},
            "power_force": {mode: None for mode in MODES},
            "power_min": {mode: None for mode in MODES},
            "power_max": {mode: None for mode in MODES},
            "swing": {mode: None for mode in MODES},
            "fan": {mode: None for mode in MODES},
            "start_offset": {mode: 0.0 for mode in MODES},
            "stop_offset": {mode: 0.0 for mode in MODES},
            "dry_min_temperature_offset": {mode: 0.0 for mode in MODES},
            "humidity_start_offset": {mode: 0.0 for mode in MODES},
            "humidity_stop_offset": {mode: 0.0 for mode in MODES},
            "eco": "default",
            "regional": "default",
            "limits_auto": "default",
            "physical_semiautomatic": "default",
            "respect_manual": "default",
            "turbo": "default",
            "sleep": "default",
            "health": "default",
            "ifeel": "default",
            "ifeel_source": None,
            "minimum_on_minutes": None,
            "minimum_off_minutes": None,
            "mode_protection_minutes": None,
            "manual_pause_minutes": None,
            "block_start": False,
            "block_automatic_off": False,
            "cancel_manual_pause": False,
            "conflicts": [],
            "next_transition": None,
        }

    def _consolidate_policy(
        self, active: list[tuple[dict[str, Any], tuple[datetime, datetime]]]
    ) -> dict[str, Any]:
        policy = self._empty_policy()
        policy["enabled"] = self.enabled
        policy["active_rule_ids"] = [rule["id"] for rule, _ in active]
        policy["active_rule_names"] = [rule["name"] for rule, _ in active]
        policy["active_count"] = len(active)
        policy["active_occurrences"] = [
            {
                "rule_id": rule["id"],
                "name": rule["name"],
                "priority": rule["priority"],
                "start": occurrence[0].isoformat(),
                "end": occurrence[1].isoformat(),
                "all_day": bool(rule.get("all_day", False)),
                "effects": [self._effect_summary(effect) for effect in rule.get("effects", [])],
            }
            for rule, occurrence in sorted(
                active, key=lambda item: (-item[0]["priority"], item[1][1], item[0]["name"])
            )
        ]
        absolute: dict[str, tuple[int, int, Any, str, str]] = {}
        additive_sources: dict[str, list[dict[str, Any]]] = {}
        conflicts: list[str] = []

        def set_absolute(
            key: str,
            priority: int,
            order: int,
            value: Any,
            rule_name: str,
            rule_id: str,
        ) -> None:
            existing = absolute.get(key)
            if existing is None or priority > existing[0] or (
                priority == existing[0] and order >= existing[1]
            ):
                if existing and priority == existing[0] and existing[2] != value:
                    conflicts.append(
                        f"{key}: {existing[2]} ({existing[3]}) × {value} ({rule_name})"
                    )
                absolute[key] = (priority, order, value, rule_name, rule_id)

        for order, (rule, _) in enumerate(
            sorted(active, key=lambda item: (item[0]["priority"], item[0]["name"]))
        ):
            priority = rule["priority"]
            rule_modes = rule.get("modes", list(MODES))
            for effect in rule.get("effects", []):
                effect_type = effect.get("type")
                value = effect.get("value")
                modes = effect.get("modes") or rule_modes

                if effect_type == "global_action":
                    action = str(value or "normal")
                    existing = absolute.get("global_action")
                    if existing and priority == existing[0]:
                        current_severity = GLOBAL_ACTIONS.get(str(existing[2]), 0)
                        new_severity = GLOBAL_ACTIONS.get(action, 0)
                        if new_severity < current_severity:
                            continue
                    set_absolute("global_action", priority, order, action, rule["name"], rule["id"])
                    continue

                if effect_type in {"enable_modes", "disable_modes", "only_modes", "enable_all_modes", "disable_all_modes"}:
                    selected = set(modes)
                    if effect_type == "only_modes":
                        for mode in MODES:
                            set_absolute(
                                f"mode:{mode}", priority, order, mode in selected, rule["name"], rule["id"]
                            )
                    elif effect_type == "enable_all_modes":
                        for mode in MODES:
                            set_absolute(f"mode:{mode}", priority, order, True, rule["name"], rule["id"])
                    elif effect_type == "disable_all_modes":
                        for mode in MODES:
                            set_absolute(f"mode:{mode}", priority, order, False, rule["name"], rule["id"])
                    else:
                        allowed = effect_type == "enable_modes"
                        for mode in selected:
                            set_absolute(f"mode:{mode}", priority, order, allowed, rule["name"], rule["id"])
                    continue

                if effect_type in ADDITIVE_EFFECTS:
                    amount = _safe_float(value)
                    for mode in modes:
                        policy[effect_type][mode] += amount
                        if amount:
                            additive_sources.setdefault(f"{effect_type}:{mode}", []).append(
                                {
                                    "rule_id": rule["id"],
                                    "rule": rule["name"],
                                    "priority": priority,
                                    "value": amount,
                                }
                            )
                    continue

                if effect_type in ABSOLUTE_MODE_EFFECTS:
                    key_name = ABSOLUTE_MODE_EFFECTS[effect_type]
                    value_by_mode = effect.get("value_by_mode") if isinstance(effect.get("value_by_mode"), dict) else {}
                    for mode in modes:
                        mode_value = value_by_mode.get(mode, value)
                        set_absolute(
                            f"{key_name}:{mode}", priority, order, mode_value, rule["name"], rule["id"]
                        )
                    continue

                if effect_type in ABSOLUTE_GLOBAL_EFFECTS:
                    key_name = ABSOLUTE_GLOBAL_EFFECTS[effect_type]
                    set_absolute(key_name, priority, order, value, rule["name"], rule["id"])

        for key, (priority, _order, value, rule_name, rule_id) in absolute.items():
            policy["effect_sources"][key] = {
                "rule_id": rule_id,
                "rule": rule_name,
                "priority": priority,
                "value": value,
            }
            if key == "global_action":
                policy["global_action"] = value
                policy["global_action_priority"] = priority
            elif key.startswith("mode:"):
                policy["modes"][key.split(":", 1)[1]] = _as_bool(value, True)
            elif ":" in key:
                group, mode = key.split(":", 1)
                policy[group][mode] = value
            else:
                if key in {"block_start", "block_automatic_off", "cancel_manual_pause"}:
                    policy[key] = _as_bool(value, False)
                elif key in {
                    "minimum_on_minutes",
                    "minimum_off_minutes",
                    "mode_protection_minutes",
                    "manual_pause_minutes",
                }:
                    policy[key] = max(0, _safe_float(value))
                else:
                    policy[key] = value

        for mode in MODES:
            policy["power_delta"][mode] = int(round(policy["power_delta"][mode]))
            policy["preset_level_delta"][mode] = int(round(policy["preset_level_delta"][mode]))
            policy["priority_delta"][mode] = int(round(policy["priority_delta"][mode]))
            for key in (
                "start_offset",
                "stop_offset",
                "dry_min_temperature_offset",
                "humidity_start_offset",
                "humidity_stop_offset",
            ):
                policy[key][mode] = round(policy[key][mode], 2)

        policy["effect_sources"].update(additive_sources)
        policy["effective_effect_count"] = len(policy["effect_sources"])
        policy["conflicts"] = _unique_ordered(conflicts)
        if not self.enabled:
            policy["state"] = "Agenda desabilitada"
        elif not active:
            policy["state"] = "Sem regras ativas"
        else:
            policy["state"] = f"{len(active)} regra(s) ativa(s)"
        return policy

    async def async_evaluate(self, force: bool = False) -> None:
        """Build and publish one atomic Agenda → preset → power snapshot."""
        async with self._evaluation_lock:
            await self._async_evaluate_locked(force)

    async def _async_evaluate_locked(self, force: bool = False) -> None:
        now = dt_util.now()
        active: list[tuple[dict[str, Any], tuple[datetime, datetime]]] = []
        if self.enabled:
            for rule in self.rules:
                occurrence = self._active_occurrence(rule, now)
                if occurrence:
                    active.append((rule, occurrence))

        new_policy = self._consolidate_policy(active)
        preset_state = calculate_preset_state(
            self.hass,
            self.presets,
            self.base_presets,
            new_policy,
            self._preset_revision,
        )
        self.preset_state = preset_state
        new_policy["preset_state_revision"] = self._preset_revision
        new_policy["preset_in_use"] = preset_state.get("preset_in_use")
        new_policy["preset_mode_in_use"] = preset_state.get("active_mode")

        runtime_changed = self._power_evaluate(new_policy)
        power_state = self.power_state
        new_policy["power_state_revision"] = self._power_revision
        new_policy["power_profile_in_use"] = power_state.get("profile_in_use")
        new_policy["power_profile_in_use_id"] = power_state.get("profile_in_use_id")

        future = self.occurrences_between(now - timedelta(days=1), now + timedelta(days=400))
        transitions: list[datetime] = []
        for occurrence in future:
            if occurrence["start"] > now:
                transitions.append(occurrence["start"])
            if occurrence["end"] > now:
                transitions.append(occurrence["end"])
        self.next_transition = min(transitions) if transitions else None
        new_policy["next_transition"] = (
            self.next_transition.isoformat() if self.next_transition else None
        )
        self.current_occurrences = [
            self._occurrence_dict(rule, *occurrence) for rule, occurrence in active
        ]

        # Build the effective signature before timestamps/revisions. Include all
        # stages so a preset-only change cannot be hidden by a stable policy.
        effective_signature = repr((new_policy, preset_state, power_state))
        changed = force or effective_signature != self._last_signature
        if changed:
            self._revision += 1
            self._last_signature = effective_signature

        self._evaluation_sequence += 1
        self._evaluation_id = f"{self.entry_id}:{self._evaluation_sequence}:{uuid4()}"
        self._evaluated_at = now
        snapshot_meta = {
            "evaluation_id": self._evaluation_id,
            "evaluated_at": now.isoformat(),
            "snapshot_revision": self._revision,
            "policy_revision": self._revision,
            "rules_revision": self._rules_revision,
            "presets_revision": self._preset_revision,
            "power_revision": self._power_revision,
            "supervisor_revision": self._revision,
        }

        new_policy.update(snapshot_meta)
        new_policy["registered_rule_count"] = len(self.rules)
        new_policy["enabled_rule_count"] = sum(
            1 for rule in self.rules if rule.get("enabled", True)
        )
        new_policy["last_evaluated"] = now.isoformat()
        new_policy["last_operation"] = self._last_operation
        new_policy["last_operation_at"] = (
            self._last_operation_at.isoformat() if self._last_operation_at else None
        )
        preset_state.update(snapshot_meta)
        power_state.update(snapshot_meta)

        self._integrity = self._validate_pipeline(new_policy, preset_state, power_state)
        new_policy["integrity"] = deepcopy(self._integrity)
        preset_state["integrity"] = deepcopy(self._integrity)
        power_state["integrity"] = deepcopy(self._integrity)
        new_policy["effect_traces"] = self._build_effect_traces(
            active, new_policy, preset_state, power_state
        )

        self.policy = new_policy
        self.preset_state = preset_state
        self.power_state = power_state
        self._snapshot = self._build_public_snapshot(snapshot_meta)
        self._schedule_transition_evaluation()

        if runtime_changed:
            await self.async_save()
        if changed:
            self._notify_listeners()
            self.hass.bus.async_fire(
                f"{DOMAIN}_policy_changed",
                {
                    "entry_id": self.entry_id,
                    **snapshot_meta,
                    "state": self.policy["state"],
                    "active_rules": self.policy["active_rule_names"],
                    "global_action": self.policy["global_action"],
                    "last_operation": self._last_operation,
                    "integrity_ok": self._integrity.get("ok", False),
                },
            )

    @callback
    def _schedule_transition_evaluation(self) -> None:
        """Evaluate exactly at the next occurrence boundary."""
        if self._unsub_transition:
            self._unsub_transition()
            self._unsub_transition = None
        if self.next_transition is None or self.next_transition <= dt_util.now():
            return
        self._unsub_transition = async_track_point_in_time(
            self.hass, self._async_transition_reached, self.next_transition
        )

    async def _async_transition_reached(self, _now: datetime) -> None:
        self._unsub_transition = None
        await self.async_evaluate(force=True)

    def _validate_pipeline(
        self,
        policy: dict[str, Any],
        preset_state: dict[str, Any],
        power_state: dict[str, Any],
    ) -> dict[str, Any]:
        """Validate the complete Agenda → preset → power chain."""
        issues: list[dict[str, Any]] = []
        preset_modes = preset_state.get("modes") or {}
        power_modes = power_state.get("modes") or {}
        for mode in MODES:
            requested = int(round(_safe_float((policy.get("preset_level_delta") or {}).get(mode), 0)))
            preset_mode = preset_modes.get(mode) or {}
            applied = int(round(_safe_float(preset_mode.get("agenda_level_delta"), 0)))
            if requested != applied:
                issues.append({
                    "stage": "policy_to_preset",
                    "mode": mode,
                    "message": (
                        f"A política contém preset_level_delta.{mode}={requested}, "
                        f"porém o preset foi calculado com agenda_level_delta={applied}."
                    ),
                })
            expected_modifier = int(round(_safe_float(preset_mode.get("power_modifier"), 0)))
            power_mode = power_modes.get(mode) or {}
            power_modifier = int(round(_safe_float((power_mode.get("modifiers") or {}).get("preset"), 0)))
            if expected_modifier != power_modifier:
                issues.append({
                    "stage": "preset_to_power",
                    "mode": mode,
                    "message": (
                        f"O preset efetivo de {mode} fornece modificador {expected_modifier}, "
                        f"mas a potência usou {power_modifier}."
                    ),
                })
        return {
            "ok": not issues,
            "issues": issues,
            "checked_at": self._evaluated_at.isoformat() if self._evaluated_at else None,
        }

    def _build_effect_traces(
        self,
        active: list[tuple[dict[str, Any], tuple[datetime, datetime]]],
        policy: dict[str, Any],
        preset_state: dict[str, Any],
        power_state: dict[str, Any],
    ) -> dict[str, list[dict[str, Any]]]:
        """Expose the real result of every active temporal effect."""
        traces: dict[str, list[dict[str, Any]]] = {}
        preset_modes = preset_state.get("modes") or {}
        power_modes = power_state.get("modes") or {}
        for rule, occurrence in active:
            rows: list[dict[str, Any]] = []
            for effect in rule.get("effects", []):
                effect_type = str(effect.get("type") or "")
                modes = effect.get("modes") or rule.get("modes") or list(MODES)
                for mode in modes:
                    if mode not in MODES:
                        continue
                    row: dict[str, Any] = {
                        "type": effect_type,
                        "mode": mode,
                        "requested": effect.get("value"),
                        "priority": rule.get("priority", 0),
                        "occurrence_start": occurrence[0].isoformat(),
                        "occurrence_end": occurrence[1].isoformat(),
                    }
                    source_key = f"{effect_type}:{mode}"
                    sources = (policy.get("effect_sources") or {}).get(source_key)
                    row["sources"] = deepcopy(sources)
                    if effect_type == "preset_level_delta":
                        preset = preset_modes.get(mode) or {}
                        row.update({
                            "consolidated": (policy.get("preset_level_delta") or {}).get(mode, 0),
                            "base_name": preset.get("calculation_base_name"),
                            "base_level": preset.get("calculation_base_level"),
                            "manual_delta": preset.get("manual_level_delta", 0),
                            "agenda_delta": preset.get("agenda_level_delta", 0),
                            "regional_delta": preset.get("regional_level_delta", 0),
                            "calculated_level": preset.get("calculated_level"),
                            "effective_name": preset.get("effective_name"),
                            "effective_level": preset.get("effective_level"),
                            "power_modifier": preset.get("power_modifier", 0),
                            "applied": any(
                                item.get("rule_id") == rule.get("id")
                                for item in (sources if isinstance(sources, list) else [])
                            ),
                        })
                    elif effect_type == "power_delta":
                        power = power_modes.get(mode) or {}
                        row.update({
                            "consolidated": (policy.get("power_delta") or {}).get(mode, 0),
                            "calculated_level": power.get("calculated_level"),
                            "applied_level": power.get("applied_level"),
                            "effective_name": power.get("effective_name"),
                            "applied": any(
                                item.get("rule_id") == rule.get("id")
                                for item in (sources if isinstance(sources, list) else [])
                            ),
                        })
                    elif effect_type in ABSOLUTE_MODE_EFFECTS:
                        winner = (policy.get("effect_sources") or {}).get(source_key) or {}
                        row.update({
                            "consolidated": (policy.get(ABSOLUTE_MODE_EFFECTS[effect_type]) or {}).get(mode),
                            "winner": winner,
                            "applied": winner.get("rule_id") == rule.get("id"),
                        })
                    elif effect_type in ADDITIVE_EFFECTS:
                        row.update({
                            "consolidated": (policy.get(effect_type) or {}).get(mode, 0),
                            "applied": any(
                                item.get("rule_id") == rule.get("id")
                                for item in (sources if isinstance(sources, list) else [])
                            ),
                        })
                    else:
                        winner = (policy.get("effect_sources") or {}).get(effect_type) or {}
                        row.update({
                            "consolidated": policy.get(ABSOLUTE_GLOBAL_EFFECTS.get(effect_type, effect_type)),
                            "winner": winner,
                            "applied": winner.get("rule_id") == rule.get("id"),
                        })
                    rows.append(row)
            traces[rule["id"]] = rows
        return traces

    def _build_public_snapshot(self, meta: dict[str, Any]) -> dict[str, Any]:
        return {
            "entry_id": self.entry_id,
            "enabled": self.enabled,
            "snapshot": deepcopy(meta),
            "integrity": deepcopy(self._integrity),
            "rules": self.public_rules(),
            "policy": deepcopy(self.policy),
            "catalog": deepcopy(self.catalog),
            "presets": self.public_presets(),
            "base_presets": dict(self.base_presets),
            "preset_state": deepcopy(self.preset_state),
            "power_profiles": self.public_power_profiles(),
            "base_power_profiles": dict(self.base_power_profiles),
            "power_rules": self.public_power_rules(),
            "power_settings": deepcopy(self.power_settings),
            "power_state": deepcopy(self.power_state),
            "occurrences": self.public_occurrences(
                dt_util.now() - timedelta(days=1),
                dt_util.now() + timedelta(days=45),
                max_events=750,
            ),
        }

    def public_snapshot(self) -> dict[str, Any]:
        """Return one atomic deep-copied runtime snapshot."""
        if not self._snapshot:
            meta = {
                "evaluation_id": self._evaluation_id,
                "evaluated_at": self._evaluated_at.isoformat() if self._evaluated_at else None,
                "snapshot_revision": self._revision,
                "policy_revision": self._revision,
                "rules_revision": self._rules_revision,
                "presets_revision": self._preset_revision,
                "power_revision": self._power_revision,
                "supervisor_revision": self._revision,
            }
            self._snapshot = self._build_public_snapshot(meta)
        return deepcopy(self._snapshot)

    def public_occurrences(
        self, start: datetime, end: datetime, max_events: int = 1000
    ) -> list[dict[str, Any]]:
        """Return JSON-serializable expanded occurrences for the frontend."""
        return [
            {
                **occurrence,
                "start": occurrence["start"].isoformat(),
                "end": occurrence["end"].isoformat(),
            }
            for occurrence in self.occurrences_between(start, end, max_events=max_events)
        ]

    def current_or_next_occurrence(self) -> dict[str, Any] | None:
        now = dt_util.now()
        events = self.occurrences_between(now - timedelta(days=1), now + timedelta(days=400))
        active = [event for event in events if event["start"] <= now < event["end"]]
        if active:
            return sorted(active, key=lambda item: (-item["priority"], item["end"]))[0]
        upcoming = [event for event in events if event["start"] >= now]
        return upcoming[0] if upcoming else None

    @callback
    def public_rules(self) -> list[dict[str, Any]]:
        return deepcopy(sorted(self.rules, key=lambda rule: (-rule["priority"], rule["name"])))
