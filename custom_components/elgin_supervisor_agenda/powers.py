"""Dynamic power profiles, rules, limits, and mode priorities for Elgin Supervisor."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import logging
from typing import Any
from uuid import uuid4

from homeassistant.const import EVENT_STATE_CHANGED
from homeassistant.core import Event, HomeAssistant, callback
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util

from .const import MODE_NAMES, MODES

_LOGGER = logging.getLogger(__name__)

MODE_FROM_TREATMENT = {
    "Aquecimento": "heat",
    "Refrigeração": "cool",
    "Desumidificação": "dry",
}
TREATMENT_FROM_MODE = {value: key for key, value in MODE_FROM_TREATMENT.items()}

POWER_DEFAULT_IDS = {
    "heat": "heat_normal",
    "cool": "cool_normal",
    "dry": "dry_normal",
}
POWER_BASE_LEGACY_ENTITIES = {
    "heat": "input_select.elgin_supervisor_potencia_manual_aquecimento",
    "cool": "input_select.elgin_supervisor_potencia_manual_refrigeracao",
    "dry": "input_select.elgin_supervisor_potencia_manual_desumidificacao",
}
POWER_TARGET_LEGACY_ENTITIES = {
    "heat": {
        "Fraco": "input_number.elgin_supervisor_alvo_aquecimento_fraco",
        "Normal": "input_number.elgin_supervisor_alvo_aquecimento_normal",
        "Forte": "input_number.elgin_supervisor_alvo_aquecimento_forte",
        "Extremo": "input_number.elgin_supervisor_alvo_aquecimento_extremo",
    },
    "cool": {
        "Fraco": "input_number.elgin_supervisor_alvo_refrigeracao_fraco",
        "Normal": "input_number.elgin_supervisor_alvo_refrigeracao_normal",
        "Forte": "input_number.elgin_supervisor_alvo_refrigeracao_forte",
        "Extremo": "input_number.elgin_supervisor_alvo_refrigeracao_extremo",
    },
    "dry": {
        "Fraco": "input_number.elgin_supervisor_alvo_desumidificacao_fraco",
        "Normal": "input_number.elgin_supervisor_alvo_desumidificacao_normal",
        "Forte": "input_number.elgin_supervisor_alvo_desumidificacao_forte",
        "Extremo": "input_number.elgin_supervisor_alvo_desumidificacao_extremo",
    },
}
POWER_FANS = {
    "Fraco": "low",
    "Normal": "low",
    "Forte": "medium",
    "Extremo": "high",
}
POWER_LEVELS = {
    "Fraco": 0,
    "Normal": 1,
    "Forte": 2,
    "Extremo": 3,
}
POWER_ALLOWED_FANS = ("auto", "low", "medium", "high")

CYCLE_LIMIT_LEGACY_ENTITIES = {
    "heat": {
        "start": "input_number.elgin_supervisor_aquecimento_inicio",
        "stop": "input_number.elgin_supervisor_aquecimento_fim",
    },
    "cool": {
        "start": "input_number.elgin_supervisor_refrigeracao_inicio",
        "stop": "input_number.elgin_supervisor_refrigeracao_fim",
    },
    "dry": {
        "start": "input_number.elgin_supervisor_desumidificacao_inicio",
        "stop": "input_number.elgin_supervisor_desumidificacao_fim",
        "minimum_temperature": "input_number.elgin_supervisor_desumidificacao_temperatura_minima",
    },
}
PRIORITY_LEGACY_ENTITIES = {
    "heat": "input_number.elgin_supervisor_prioridade_aquecimento",
    "cool": "input_number.elgin_supervisor_prioridade_refrigeracao",
    "dry": "input_number.elgin_supervisor_prioridade_desumidificacao",
}
CONTINUITY_BONUS_ENTITY = "input_number.elgin_supervisor_bonus_permanencia"

RULE_DEFAULT_SOURCE_ENTITIES = {
    "temperature": "sensor.sensor_temperatura_sensor_dedicado",
    "humidity": "sensor.sensor_umidade_sensor_dedicado",
    "number": "",
}
RULE_OPERATIONS = {
    "current_minus_reference",
    "reference_minus_current",
    "absolute_difference",
    "directional_by_mode",
}
RULE_OPERATORS = {"ge", "gt", "le", "lt"}
RULE_REFERENCE_KINDS = {
    "fixed",
    "entity",
    "cycle_start",
    "cycle_end",
    "preset_start",
    "preset_end",
    "dry_minimum",
}


class PowerValidationError(ValueError):
    """Raised when a dynamic power object violates the contract."""


def _state_float(hass: HomeAssistant, entity_id: str, default: float) -> float:
    state = hass.states.get(entity_id)
    try:
        return float(state.state) if state else default
    except (TypeError, ValueError):
        return default


def _state_text(hass: HomeAssistant, entity_id: str, default: str) -> str:
    state = hass.states.get(entity_id)
    if state is None or state.state in {"unknown", "unavailable", "none", ""}:
        return default
    return str(state.state)


def _state_on(hass: HomeAssistant, entity_id: str) -> bool:
    state = hass.states.get(entity_id)
    return bool(state and state.state == "on")


def _number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def _integer(value: Any, default: int = 0) -> int:
    try:
        return int(round(float(value)))
    except (TypeError, ValueError):
        return default


def _iso_now() -> str:
    return dt_util.now().isoformat()


def _slug(value: str) -> str:
    result = "".join(char.lower() if char.isalnum() else "_" for char in value.strip())
    while "__" in result:
        result = result.replace("__", "_")
    return result.strip("_") or uuid4().hex[:8]


def find_power_profile(
    profiles: list[dict[str, Any]],
    value: str | None,
    mode: str | None = None,
) -> dict[str, Any] | None:
    """Find by immutable id first, then by display name for migration."""
    if not value:
        return None
    text = str(value)
    exact = next(
        (
            profile
            for profile in profiles
            if profile["id"] == text and (mode is None or profile["mode"] == mode)
        ),
        None,
    )
    if exact:
        return exact
    return next(
        (
            profile
            for profile in profiles
            if profile["name"].casefold() == text.casefold()
            and (mode is None or profile["mode"] == mode)
        ),
        None,
    )


def normalize_power_profile(
    profile: dict[str, Any],
    existing: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Normalize one persistent mode-specific power profile."""
    mode = str((existing or {}).get("mode") or profile.get("mode") or "")
    if mode not in MODES:
        raise PowerValidationError("O modo do perfil deve ser heat, cool ou dry.")
    profile_id = str((existing or {}).get("id") or profile.get("id") or f"{mode}_{_slug(str(profile.get('name') or 'perfil'))}_{uuid4().hex[:6]}")
    updated_at = str(profile.get("updated_at") or _iso_now())
    normalized = {
        "id": profile_id,
        "name": str(profile.get("name") or "Perfil sem nome").strip()[:80],
        "mode": mode,
        "level": _integer(profile.get("level"), 0),
        "target_temperature": round(_number(profile.get("target_temperature"), 24.0), 1),
        "fan": str(profile.get("fan") or "low"),
        "enabled": bool(profile.get("enabled", True)),
        "description": str(profile.get("description") or "").strip()[:500],
        "protected": bool((existing or {}).get("protected", profile.get("protected", False))),
        "default": bool((existing or {}).get("default", profile.get("default", False))),
        "updated_at": updated_at,
    }
    return normalized


def validate_power_profile(
    profile: dict[str, Any],
    catalog: list[dict[str, Any]],
    base_profiles: dict[str, str] | None = None,
) -> None:
    """Validate one profile without crossing mode boundaries."""
    if not profile["name"]:
        raise PowerValidationError("Informe o nome do perfil de potência.")
    if not -100 <= profile["level"] <= 100:
        raise PowerValidationError("O nível deve ficar entre -100 e 100.")
    if profile["fan"] not in POWER_ALLOWED_FANS:
        raise PowerValidationError("A ventilação deve ser auto, low, medium ou high.")
    if not 16.0 <= float(profile["target_temperature"]) <= 30.0:
        raise PowerValidationError("A temperatura-alvo deve ficar entre 16 e 30 °C.")
    for item in catalog:
        if item["id"] == profile["id"] or item["mode"] != profile["mode"]:
            continue
        if item["name"].casefold() == profile["name"].casefold():
            raise PowerValidationError("Já existe um perfil com esse nome neste modo.")
        if item.get("enabled", True) and profile.get("enabled", True) and item["level"] == profile["level"]:
            raise PowerValidationError(
                f"O nível {profile['level']} já pertence ao perfil {item['name']} em {MODE_NAMES[profile['mode']]}.")
    if profile.get("default") and not profile.get("enabled"):
        raise PowerValidationError("Um perfil padrão protegido não pode ser desabilitado.")
    if base_profiles and base_profiles.get(profile["mode"]) == profile["id"] and not profile.get("enabled"):
        raise PowerValidationError("A potência base do modo não pode ser desabilitada.")


def default_power_profiles(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Migrate the twelve fixed profiles as protected initial records."""
    defaults = {
        "heat": {"Fraco": 22.0, "Normal": 24.0, "Forte": 26.0, "Extremo": 30.0},
        "cool": {"Fraco": 25.0, "Normal": 23.0, "Forte": 22.0, "Extremo": 18.0},
        "dry": {"Fraco": 26.0, "Normal": 24.0, "Forte": 24.0, "Extremo": 20.0},
    }
    result: list[dict[str, Any]] = []
    for mode in MODES:
        for name in ("Fraco", "Normal", "Forte", "Extremo"):
            value = _state_float(
                hass,
                POWER_TARGET_LEGACY_ENTITIES[mode][name],
                defaults[mode][name],
            )
            result.append(
                normalize_power_profile(
                    {
                        "id": f"{mode}_{_slug(name)}",
                        "name": name,
                        "mode": mode,
                        "level": POWER_LEVELS[name],
                        "target_temperature": value,
                        "fan": POWER_FANS[name],
                        "enabled": True,
                        "description": f"Perfil protegido migrado da matriz fixa de {MODE_NAMES[mode].lower()}.",
                        "protected": True,
                        "default": True,
                    }
                )
            )
    return result


def migrate_base_power_profiles(
    hass: HomeAssistant,
    profiles: list[dict[str, Any]],
) -> dict[str, str]:
    """Migrate each legacy manual selector as the persistent base/fallback."""
    result: dict[str, str] = {}
    for mode in MODES:
        legacy_name = _state_text(hass, POWER_BASE_LEGACY_ENTITIES[mode], "Normal")
        profile = find_power_profile(profiles, legacy_name, mode)
        if profile is None or not profile.get("enabled", True):
            profile = find_power_profile(profiles, POWER_DEFAULT_IDS[mode], mode)
        if profile is None:
            profile = next(
                (item for item in profiles if item["mode"] == mode and item.get("enabled", True)),
                None,
            )
        if profile:
            result[mode] = profile["id"]
    return result


def default_power_settings(hass: HomeAssistant) -> dict[str, Any]:
    """Capture current local limits, priorities, and continuity bonus."""
    defaults = {
        "heat": {"start": 16.5, "stop": 19.0},
        "cool": {"start": 24.3, "stop": 22.3},
        "dry": {"start": 65, "stop": 60, "minimum_temperature": 20.0},
    }
    cycle_limits: dict[str, dict[str, Any]] = {}
    for mode in MODES:
        cycle_limits[mode] = {
            "start": int(round(_state_float(hass, CYCLE_LIMIT_LEGACY_ENTITIES[mode]["start"], defaults[mode]["start"])))
            if mode == "dry"
            else round(_state_float(hass, CYCLE_LIMIT_LEGACY_ENTITIES[mode]["start"], defaults[mode]["start"]), 1),
            "stop": int(round(_state_float(hass, CYCLE_LIMIT_LEGACY_ENTITIES[mode]["stop"], defaults[mode]["stop"])))
            if mode == "dry"
            else round(_state_float(hass, CYCLE_LIMIT_LEGACY_ENTITIES[mode]["stop"], defaults[mode]["stop"]), 1),
        }
        if mode == "dry":
            cycle_limits[mode]["minimum_temperature"] = round(
                _state_float(
                    hass,
                    CYCLE_LIMIT_LEGACY_ENTITIES[mode]["minimum_temperature"],
                    defaults[mode]["minimum_temperature"],
                ),
                1,
            )
    priorities = {
        mode: _integer(
            _state_float(hass, PRIORITY_LEGACY_ENTITIES[mode], 60 if mode != "dry" else 50)
        )
        for mode in MODES
    }
    return {
        "cycle_limits": cycle_limits,
        "priorities": priorities,
        "continuity_bonus": _integer(_state_float(hass, CONTINUITY_BONUS_ENTITY, 10)),
    }


def normalize_power_settings(settings: dict[str, Any], fallback: dict[str, Any]) -> dict[str, Any]:
    """Normalize persisted settings without changing their semantics."""
    source = deepcopy(fallback)
    source.update({key: value for key, value in (settings or {}).items() if key != "cycle_limits" and key != "priorities"})
    cycle_source = settings.get("cycle_limits", {}) if isinstance(settings, dict) else {}
    priority_source = settings.get("priorities", {}) if isinstance(settings, dict) else {}
    cycle_limits: dict[str, dict[str, Any]] = {}
    for mode in MODES:
        base = fallback["cycle_limits"][mode]
        item = cycle_source.get(mode, {}) if isinstance(cycle_source, dict) else {}
        cycle_limits[mode] = {
            "start": int(round(_number(item.get("start"), base["start"]))) if mode == "dry" else round(_number(item.get("start"), base["start"]), 1),
            "stop": int(round(_number(item.get("stop"), base["stop"]))) if mode == "dry" else round(_number(item.get("stop"), base["stop"]), 1),
        }
        if mode == "dry":
            cycle_limits[mode]["minimum_temperature"] = round(
                _number(item.get("minimum_temperature"), base.get("minimum_temperature", 20.0)), 1
            )
    priorities = {
        mode: _integer(priority_source.get(mode), fallback["priorities"][mode])
        for mode in MODES
    }
    normalized = {
        "cycle_limits": cycle_limits,
        "priorities": priorities,
        "continuity_bonus": _integer(source.get("continuity_bonus"), fallback["continuity_bonus"]),
    }
    validate_power_settings(normalized)
    return normalized


def validate_power_settings(settings: dict[str, Any]) -> None:
    """Validate mode-specific cycle semantics and priority values."""
    limits = settings["cycle_limits"]
    heat = limits["heat"]
    cool = limits["cool"]
    dry = limits["dry"]
    if not 5 <= float(heat["start"]) < float(heat["stop"]) <= 35:
        raise PowerValidationError("No aquecimento, o início deve ser menor que o fim e ambos devem ficar entre 5 e 35 °C.")
    if not 10 <= float(cool["stop"]) < float(cool["start"]) <= 45:
        raise PowerValidationError("Na refrigeração, o início deve ser maior que o fim e ambos devem ficar entre 10 e 45 °C.")
    if not 20 <= float(dry["stop"]) < float(dry["start"]) <= 100:
        raise PowerValidationError("No Dry, o início deve ser maior que o fim e ambos devem ficar entre 20% e 100%.")
    if not 16 <= float(dry.get("minimum_temperature", 20)) <= 30:
        raise PowerValidationError("A temperatura mínima do Dry deve ficar entre 16 e 30 °C.")
    for mode, value in settings["priorities"].items():
        if not 0 <= int(value) <= 1000:
            raise PowerValidationError(f"A prioridade de {MODE_NAMES[mode]} deve ficar entre 0 e 1000.")
    if not 0 <= int(settings["continuity_bonus"]) <= 1000:
        raise PowerValidationError("O bônus de continuidade deve ficar entre 0 e 1000.")


def normalize_power_rule(rule: dict[str, Any], existing: dict[str, Any] | None = None) -> dict[str, Any]:
    """Normalize one multi-mode stateful hysteresis rule."""
    rule_id = str((existing or {}).get("id") or rule.get("id") or uuid4())
    source = deepcopy(rule.get("source") or {})
    reference = deepcopy(rule.get("reference") or {})
    variable = str(source.get("variable") or "temperature")
    source_kind = str(source.get("kind") or "entity")
    normalized_source = {
        "kind": source_kind,
        "variable": variable,
        "entity_id": str(source.get("entity_id") or RULE_DEFAULT_SOURCE_ENTITIES.get(variable, "")),
        "attribute": str(source.get("attribute") or ""),
        "value": _number(source.get("value"), 0),
    }
    reference_kind = str(reference.get("kind") or "cycle_end")
    normalized_reference = {
        "kind": reference_kind,
        "entity_id": str(reference.get("entity_id") or ""),
        "attribute": str(reference.get("attribute") or ""),
        "value": _number(reference.get("value"), 0),
    }
    adjustments_source = rule.get("adjustments") or {}
    adjustments = {mode: _integer(adjustments_source.get(mode), 0) for mode in MODES}
    modes = [mode for mode in rule.get("modes", MODES) if mode in MODES and adjustments.get(mode, 0) != 0]
    if not modes:
        modes = [mode for mode in MODES if adjustments.get(mode, 0) != 0]
    runtime = deepcopy((existing or {}).get("runtime") or rule.get("runtime") or {})
    mode_states = runtime.get("mode_states") if isinstance(runtime.get("mode_states"), dict) else {}
    normalized_runtime = {
        "mode_states": {
            mode: {
                "active": bool((mode_states.get(mode) or {}).get("active", False)),
                "last_activation": (mode_states.get(mode) or {}).get("last_activation"),
                "last_deactivation": (mode_states.get(mode) or {}).get("last_deactivation"),
                "last_reason": str((mode_states.get(mode) or {}).get("last_reason") or "Inicialização"),
            }
            for mode in MODES
        }
    }
    normalized = {
        "id": rule_id,
        "name": str(rule.get("name") or "Regra sem nome").strip()[:100],
        "description": str(rule.get("description") or "").strip()[:500],
        "enabled": bool(rule.get("enabled", True)),
        "source": normalized_source,
        "reference": normalized_reference,
        "operation": str(rule.get("operation") or "directional_by_mode"),
        "entry_operator": str(rule.get("entry_operator") or "ge"),
        "entry_value": round(_number(rule.get("entry_value"), 0), 2),
        "exit_operator": str(rule.get("exit_operator") or "le"),
        "exit_value": round(_number(rule.get("exit_value"), 0), 2),
        "modes": modes,
        "adjustments": adjustments,
        "exclusive_group": str(rule.get("exclusive_group") or "").strip()[:80],
        "priority": _integer(rule.get("priority"), 0),
        "runtime": normalized_runtime,
        "updated_at": str(rule.get("updated_at") or _iso_now()),
    }
    return normalized


def validate_power_rule(rule: dict[str, Any], catalog: list[dict[str, Any]]) -> None:
    """Validate state machine, numeric source, modes, and group determinism."""
    if not rule["name"]:
        raise PowerValidationError("Informe o nome da regra.")
    for item in catalog:
        if item["id"] != rule["id"] and item["name"].casefold() == rule["name"].casefold():
            raise PowerValidationError("Já existe uma regra com esse nome.")
    if rule["operation"] not in RULE_OPERATIONS:
        raise PowerValidationError("Operação de diferença inválida.")
    if rule["entry_operator"] not in RULE_OPERATORS or rule["exit_operator"] not in RULE_OPERATORS:
        raise PowerValidationError("Operador de entrada ou saída inválido.")
    if rule["reference"]["kind"] not in RULE_REFERENCE_KINDS:
        raise PowerValidationError("Referência da regra inválida.")
    if rule["source"]["kind"] == "entity" and not rule["source"]["entity_id"]:
        raise PowerValidationError("Informe a entidade observada.")
    if rule["reference"]["kind"] == "entity" and not rule["reference"]["entity_id"]:
        raise PowerValidationError("Informe a entidade usada como referência.")
    if not rule["modes"]:
        raise PowerValidationError("A regra deve afetar ao menos um modo.")
    if all(rule["adjustments"].get(mode, 0) == 0 for mode in MODES):
        raise PowerValidationError("A regra deve possuir ao menos um ajuste diferente de zero.")
    rising = rule["entry_operator"] in {"ge", "gt"}
    if rising:
        if rule["exit_operator"] not in {"le", "lt"} or not rule["exit_value"] < rule["entry_value"]:
            raise PowerValidationError("Para entrada por subida, a saída deve usar <= ou < com limiar menor que o de entrada.")
    else:
        if rule["exit_operator"] not in {"ge", "gt"} or not rule["exit_value"] > rule["entry_value"]:
            raise PowerValidationError("Para entrada por queda, a saída deve usar >= ou > com limiar maior que o de entrada.")
    if rule["exclusive_group"] and not -1000 <= int(rule["priority"]) <= 1000:
        raise PowerValidationError("A prioridade do grupo deve ficar entre -1000 e 1000.")


def default_power_rules(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Migrate the fixed Normal/Forte/Extremo thresholds into exclusive rules."""
    temp_thresholds = [
        ("Normal", _state_float(hass, "input_number.elgin_supervisor_delta_normal", 1.5), 1),
        ("Forte", _state_float(hass, "input_number.elgin_supervisor_delta_forte", 3.0), 2),
        ("Extremo", _state_float(hass, "input_number.elgin_supervisor_delta_extremo", 5.0), 3),
    ]
    humidity_thresholds = [
        ("Normal", _state_float(hass, "input_number.elgin_supervisor_umidade_delta_normal", 8), 1),
        ("Forte", _state_float(hass, "input_number.elgin_supervisor_umidade_delta_forte", 12), 2),
        ("Extremo", _state_float(hass, "input_number.elgin_supervisor_umidade_delta_extremo", 15), 3),
    ]
    result: list[dict[str, Any]] = []
    previous = 0.0
    for index, (name, threshold, adjustment) in enumerate(temp_thresholds):
        exit_value = previous if index else max(0.0, threshold - 0.5)
        result.append(
            normalize_power_rule(
                {
                    "id": f"regra_temperatura_{_slug(name)}",
                    "name": f"Distância térmica — {name}",
                    "description": "Migrada dos limiares fixos de temperatura. O grupo exclusivo preserva o comportamento progressivo sem somar faixas.",
                    "enabled": True,
                    "source": {"kind": "entity", "variable": "temperature", "entity_id": RULE_DEFAULT_SOURCE_ENTITIES["temperature"]},
                    "reference": {"kind": "cycle_end"},
                    "operation": "directional_by_mode",
                    "entry_operator": "ge",
                    "entry_value": threshold,
                    "exit_operator": "le",
                    "exit_value": exit_value,
                    "adjustments": {"heat": adjustment, "cool": adjustment, "dry": 0},
                    "modes": ["heat", "cool"],
                    "exclusive_group": "intensidade_por_distancia_termica",
                    "priority": index,
                }
            )
        )
        previous = threshold
    previous = 0.0
    for index, (name, threshold, adjustment) in enumerate(humidity_thresholds):
        exit_value = previous if index else max(0.0, threshold - 1)
        result.append(
            normalize_power_rule(
                {
                    "id": f"regra_umidade_{_slug(name)}",
                    "name": f"Distância de umidade — {name}",
                    "description": "Migrada dos limiares fixos de umidade do Dry. O grupo exclusivo impede acumulação de Normal, Forte e Extremo.",
                    "enabled": True,
                    "source": {"kind": "entity", "variable": "humidity", "entity_id": RULE_DEFAULT_SOURCE_ENTITIES["humidity"]},
                    "reference": {"kind": "cycle_end"},
                    "operation": "directional_by_mode",
                    "entry_operator": "ge",
                    "entry_value": threshold,
                    "exit_operator": "le",
                    "exit_value": exit_value,
                    "adjustments": {"heat": 0, "cool": 0, "dry": adjustment},
                    "modes": ["dry"],
                    "exclusive_group": "intensidade_por_distancia_umidade",
                    "priority": index,
                }
            )
        )
        previous = threshold
    return result


def _compare(operator: str, value: float, threshold: float) -> bool:
    if operator == "ge":
        return value >= threshold
    if operator == "gt":
        return value > threshold
    if operator == "le":
        return value <= threshold
    if operator == "lt":
        return value < threshold
    return False


def _profile_sort_key(profile: dict[str, Any]) -> tuple[Any, ...]:
    return (profile["level"], profile["name"].casefold())


def public_power_catalog(
    profiles: list[dict[str, Any]],
    base_profiles: dict[str, str],
) -> dict[str, Any]:
    by_mode: dict[str, list[dict[str, Any]]] = {}
    for mode in MODES:
        by_mode[mode] = sorted(
            [deepcopy(item) for item in profiles if item["mode"] == mode],
            key=_profile_sort_key,
        )
    return {
        "power_profiles": by_mode,
        "power_profile_options": {
            mode: [
                {"id": item["id"], "name": item["name"], "level": item["level"]}
                for item in by_mode[mode]
                if item.get("enabled", True)
            ]
            for mode in MODES
        },
        "base_power_profiles": dict(base_profiles),
        "default_power_profiles": dict(POWER_DEFAULT_IDS),
    }


class PowerManagerMixin:
    """Mixin extending AgendaManager with dynamic local power configuration."""

    def _power_init(self) -> None:
        self.power_profiles: list[dict[str, Any]] = []
        self.base_power_profiles: dict[str, str] = {}
        self.power_rules: list[dict[str, Any]] = []
        self.power_settings: dict[str, Any] = {}
        self.power_state: dict[str, Any] = {"modes": {}, "active_mode": None}
        self._power_revision = 0
        self._power_runtime_dirty = False
        self._power_unsub_state_event = None
        self._power_debounce_unsub = None
        self._power_watch_entities: set[str] = set()
        self._effective_cycle_limits: dict[str, dict[str, Any]] = {}

    def _power_load(self, data: dict[str, Any]) -> None:
        stored_profiles = data.get("power_profiles")
        profiles: list[dict[str, Any]] = []
        if isinstance(stored_profiles, list) and stored_profiles:
            for raw in stored_profiles:
                try:
                    profile = normalize_power_profile(raw)
                    validate_power_profile(profile, profiles)
                    profiles.append(profile)
                except (PowerValidationError, TypeError, ValueError):
                    _LOGGER.exception("Perfil de potência persistido inválido ignorado: %s", raw)
        self.power_profiles = profiles or default_power_profiles(self.hass)

        stored_base = data.get("base_power_profiles")
        self.base_power_profiles = (
            {mode: str(stored_base.get(mode, "")) for mode in MODES}
            if isinstance(stored_base, dict)
            else migrate_base_power_profiles(self.hass, self.power_profiles)
        )
        self._repair_base_power_profiles()

        fallback_settings = default_power_settings(self.hass)
        try:
            self.power_settings = normalize_power_settings(
                data.get("power_settings") if isinstance(data.get("power_settings"), dict) else {},
                fallback_settings,
            )
        except PowerValidationError:
            _LOGGER.exception("Configuração persistida de potência inválida; valores atuais migrados")
            self.power_settings = fallback_settings

        stored_rules = data.get("power_rules")
        rules: list[dict[str, Any]] = []
        if isinstance(stored_rules, list):
            for raw in stored_rules:
                try:
                    rule = normalize_power_rule(raw)
                    validate_power_rule(rule, rules)
                    rules.append(rule)
                except (PowerValidationError, TypeError, ValueError):
                    _LOGGER.exception("Regra de potência persistida inválida ignorada: %s", raw)
            self.power_rules = rules
        else:
            self.power_rules = default_power_rules(self.hass)
        self._repair_rule_profile_references()
        self._power_revision += 1
        self._power_rebuild_watch_entities()

    def _power_storage_payload(self) -> dict[str, Any]:
        return {
            "power_profiles": deepcopy(self.power_profiles),
            "base_power_profiles": dict(self.base_power_profiles),
            "power_rules": deepcopy(self.power_rules),
            "power_settings": deepcopy(self.power_settings),
        }

    def _power_catalog(self) -> dict[str, Any]:
        return {
            **public_power_catalog(self.power_profiles, self.base_power_profiles),
            "power_rules": self.public_power_rules(),
            "power_settings": deepcopy(self.power_settings),
        }

    def _repair_base_power_profiles(self) -> None:
        for mode in MODES:
            base = find_power_profile(self.power_profiles, self.base_power_profiles.get(mode), mode)
            if base and base.get("enabled", True):
                self.base_power_profiles[mode] = base["id"]
                continue
            default = find_power_profile(self.power_profiles, POWER_DEFAULT_IDS[mode], mode)
            enabled = sorted(
                [item for item in self.power_profiles if item["mode"] == mode and item.get("enabled", True)],
                key=_profile_sort_key,
            )
            replacement = default if default and default.get("enabled", True) else (enabled[0] if enabled else None)
            if replacement:
                self.base_power_profiles[mode] = replacement["id"]

    def _repair_rule_profile_references(self) -> None:
        """Migrate Agenda power references from display names to immutable IDs."""
        for rule in getattr(self, "rules", []):
            rule_modes = rule.get("modes") or list(MODES)
            for effect in rule.get("effects", []):
                if effect.get("type") not in {"power_base", "power_force", "power_min", "power_max"}:
                    continue
                modes = effect.get("modes") or rule_modes
                value = effect.get("value")
                if isinstance(value, dict):
                    migrated = {}
                    for mode in modes:
                        profile = find_power_profile(self.power_profiles, value.get(mode), mode)
                        if profile:
                            migrated[mode] = profile["id"]
                    effect["value_by_mode"] = migrated
                    if len(migrated) == 1:
                        effect["value"] = next(iter(migrated.values()))
                else:
                    mapped = {}
                    for mode in modes:
                        profile = find_power_profile(self.power_profiles, value, mode)
                        if profile:
                            mapped[mode] = profile["id"]
                    if mapped:
                        effect["value_by_mode"] = mapped
                        if len(mapped) == 1:
                            effect["value"] = next(iter(mapped.values()))

    def _power_rebuild_watch_entities(self) -> None:
        watched = {
            "sensor.sensor_temperatura_sensor_dedicado",
            "sensor.sensor_umidade_sensor_dedicado",
            "weather.forecast_casa",
            "sensor.elgin_supervisor_tratamento_desejado",
            "input_select.elgin_supervisor_tratamento_ativo",
            "binary_sensor.elgin_supervisor_demanda_aquecimento",
            "binary_sensor.elgin_supervisor_demanda_refrigeracao",
            "binary_sensor.elgin_supervisor_demanda_desumidificacao",
            "binary_sensor.elgin_supervisor_clima_regional_efetivo",
            "binary_sensor.elgin_supervisor_clima_regional_valido",
        }
        for rule in self.power_rules:
            source = rule.get("source") or {}
            reference = rule.get("reference") or {}
            if source.get("kind") == "entity" and source.get("entity_id"):
                watched.add(str(source["entity_id"]))
            if reference.get("kind") == "entity" and reference.get("entity_id"):
                watched.add(str(reference["entity_id"]))
        self._power_watch_entities = watched
        if self._power_unsub_state_event:
            self._power_unsub_state_event()
            self._power_unsub_state_event = None
        self._power_unsub_state_event = self.hass.bus.async_listen(
            EVENT_STATE_CHANGED, self._power_state_changed
        )

    @callback
    def _power_state_changed(self, event: Event) -> None:
        entity_id = event.data.get("entity_id")
        if entity_id not in self._power_watch_entities:
            return
        if self._power_debounce_unsub:
            self._power_debounce_unsub()
        self._power_debounce_unsub = async_call_later(
            self.hass, 0.25, self._power_debounced_evaluate
        )

    async def _power_debounced_evaluate(self, _now) -> None:
        self._power_debounce_unsub = None
        await self.async_evaluate(force=True)

    def _power_unload(self) -> None:
        if self._power_unsub_state_event:
            self._power_unsub_state_event()
            self._power_unsub_state_event = None
        if self._power_debounce_unsub:
            self._power_debounce_unsub()
            self._power_debounce_unsub = None

    def public_power_profiles(self) -> list[dict[str, Any]]:
        return deepcopy(sorted(self.power_profiles, key=lambda item: (MODES.index(item["mode"]), *_profile_sort_key(item))))

    def public_power_rules(self) -> list[dict[str, Any]]:
        return deepcopy(sorted(self.power_rules, key=lambda item: (item.get("exclusive_group", ""), item.get("priority", 0), item["name"].casefold())))

    async def async_upsert_power_profile(self, raw: dict[str, Any]) -> dict[str, Any]:
        profile_id = str(raw.get("id") or "")
        existing = find_power_profile(self.power_profiles, profile_id) if profile_id else None
        profile = normalize_power_profile(raw, existing)
        validate_power_profile(profile, self.power_profiles, self.base_power_profiles)
        if existing:
            index = next(index for index, item in enumerate(self.power_profiles) if item["id"] == existing["id"])
            self.power_profiles[index] = profile
        else:
            self.power_profiles.append(profile)
        self._repair_base_power_profiles()
        self._power_revision += 1
        self._set_operation(f"Perfil de potência salvo: {profile['name']} ({MODE_NAMES[profile['mode']]})")
        self.catalog = self._discover_catalog()
        await self.async_save()
        await self.async_evaluate(force=True)
        return deepcopy(profile)

    async def async_duplicate_power_profile(self, profile_id: str, mode: str | None = None) -> dict[str, Any]:
        source = find_power_profile(self.power_profiles, profile_id)
        if source is None:
            raise PowerValidationError("Perfil de potência não encontrado.")
        target_mode = mode or source["mode"]
        if target_mode not in MODES:
            raise PowerValidationError("Modo de destino inválido.")
        existing_levels = {item["level"] for item in self.power_profiles if item["mode"] == target_mode and item.get("enabled", True)}
        level = source["level"]
        while level in existing_levels:
            level += 1
        duplicate = {
            **source,
            "id": f"{target_mode}_{_slug(source['name'])}_{uuid4().hex[:6]}",
            "name": f"{source['name']} (cópia)",
            "mode": target_mode,
            "level": level,
            "protected": False,
            "default": False,
            "updated_at": _iso_now(),
        }
        return await self.async_upsert_power_profile(duplicate)

    async def async_delete_power_profile(self, profile_id: str) -> bool:
        profile = find_power_profile(self.power_profiles, profile_id)
        if profile is None:
            return False
        if profile.get("protected"):
            raise PowerValidationError("Um perfil padrão protegido não pode ser excluído.")
        if self.base_power_profiles.get(profile["mode"]) == profile_id:
            raise PowerValidationError("Selecione outra potência base antes de excluir este perfil.")
        self.power_profiles = [item for item in self.power_profiles if item["id"] != profile_id]
        invalid_references: list[str] = []
        for rule in getattr(self, "rules", []):
            for effect in rule.get("effects", []):
                if effect.get("type") not in {"power_base", "power_force", "power_min", "power_max"}:
                    continue
                value_by_mode = effect.get("value_by_mode") or {}
                if profile_id in value_by_mode.values() or effect.get("value") == profile_id:
                    invalid_references.append(rule["name"])
        self._power_revision += 1
        self._set_operation(
            f"Perfil de potência excluído: {profile['name']}"
            + (f"; referências inválidas: {', '.join(invalid_references)}" if invalid_references else "")
        )
        self.catalog = self._discover_catalog()
        await self.async_save()
        await self.async_evaluate(force=True)
        return True

    async def async_set_base_power_profile(self, mode: str, profile_id: str) -> dict[str, Any]:
        if mode not in MODES:
            raise PowerValidationError("Modo de potência inválido.")
        profile = find_power_profile(self.power_profiles, profile_id, mode)
        if profile is None or not profile.get("enabled", True):
            raise PowerValidationError("A potência base deve estar habilitada e pertencer ao modo selecionado.")
        self.base_power_profiles[mode] = profile["id"]
        self._power_revision += 1
        self._set_operation(f"Potência base de {MODE_NAMES[mode]} alterada para {profile['name']}")
        self.catalog = self._discover_catalog()
        await self.async_save()
        await self.async_evaluate(force=True)
        return deepcopy(profile)

    async def async_upsert_power_rule(self, raw: dict[str, Any]) -> dict[str, Any]:
        rule_id = str(raw.get("id") or "")
        existing = next((item for item in self.power_rules if item["id"] == rule_id), None) if rule_id else None
        rule = normalize_power_rule(raw, existing)
        validate_power_rule(rule, self.power_rules)
        if existing:
            index = next(index for index, item in enumerate(self.power_rules) if item["id"] == existing["id"])
            self.power_rules[index] = rule
        else:
            self.power_rules.append(rule)
        self._power_revision += 1
        self._power_rebuild_watch_entities()
        self._set_operation(f"Regra dinâmica de potência salva: {rule['name']}")
        self.catalog = self._discover_catalog()
        await self.async_save()
        await self.async_evaluate(force=True)
        return deepcopy(rule)

    async def async_delete_power_rule(self, rule_id: str) -> bool:
        existing = next((item for item in self.power_rules if item["id"] == rule_id), None)
        if existing is None:
            return False
        self.power_rules = [item for item in self.power_rules if item["id"] != rule_id]
        self._power_revision += 1
        self._power_rebuild_watch_entities()
        self._set_operation(f"Regra dinâmica de potência excluída: {existing['name']}")
        self.catalog = self._discover_catalog()
        await self.async_save()
        await self.async_evaluate(force=True)
        return True

    async def async_set_power_rule_enabled(self, rule_id: str, enabled: bool) -> dict[str, Any]:
        existing = next((item for item in self.power_rules if item["id"] == rule_id), None)
        if existing is None:
            raise PowerValidationError("Regra dinâmica de potência não encontrada.")
        existing["enabled"] = bool(enabled)
        existing["updated_at"] = _iso_now()
        self._power_revision += 1
        self._set_operation(f"Regra dinâmica {'habilitada' if enabled else 'desabilitada'}: {existing['name']}")
        await self.async_save()
        await self.async_evaluate(force=True)
        return deepcopy(existing)

    async def async_update_power_settings(self, raw: dict[str, Any]) -> dict[str, Any]:
        settings = normalize_power_settings(raw, self.power_settings or default_power_settings(self.hass))
        self.power_settings = settings
        # Local cycle limits are the canonical editable limits. Mirror them
        # into each mode's current base preset so the existing cycle engine
        # consumes the same values without duplicate controls.
        for mode in MODES:
            base_id = getattr(self, "base_presets", {}).get(mode)
            preset = next((item for item in getattr(self, "presets", []) if item.get("id") == base_id and item.get("mode") == mode), None)
            limits = settings["cycle_limits"][mode]
            if preset is not None:
                preset["start"] = limits["start"]
                preset["stop"] = limits["stop"]
                if mode == "dry":
                    preset["minimum_temperature"] = limits.get("minimum_temperature", 20.0)
        if hasattr(self, "_preset_revision"):
            self._preset_revision += 1
        self._power_revision += 1
        self._set_operation("Limites locais, prioridades e continuidade atualizados")
        self.catalog = self._discover_catalog()
        await self.async_save()
        await self.async_evaluate(force=True)
        return deepcopy(settings)

    async def async_restore_default_power_profiles(self) -> dict[str, Any]:
        """Restore only protected defaults; keep every custom profile and rule."""
        if _state_on(self.hass, "input_boolean.elgin_supervisor_habilitado") or not _state_on(
            self.hass, "input_boolean.elgin_supervisor_modo_sombra"
        ):
            raise PowerValidationError(
                "Para restaurar os padrões, desative o Supervisor e ative o modo sombra."
            )
        defaults = default_power_profiles(self.hass)
        by_id = {item["id"]: item for item in self.power_profiles}
        restored: list[str] = []
        recreated: list[str] = []
        for default in defaults:
            current = by_id.get(default["id"])
            if current is None:
                self.power_profiles.append(default)
                recreated.append(default["name"] + " / " + MODE_NAMES[default["mode"]])
            else:
                index = next(index for index, item in enumerate(self.power_profiles) if item["id"] == default["id"])
                self.power_profiles[index] = default
                restored.append(default["name"] + " / " + MODE_NAMES[default["mode"]])
        self._repair_base_power_profiles()
        self._power_revision += 1
        self._set_operation("Perfis padrões protegidos restaurados")
        self.catalog = self._discover_catalog()
        await self.async_save()
        await self.async_evaluate(force=True)
        return {"restored": restored, "recreated": recreated}

    def _entity_numeric_value(self, entity_id: str, attribute: str = "") -> tuple[float | None, str]:
        state = self.hass.states.get(entity_id)
        if state is None:
            return None, "Entidade inexistente"
        raw = state.attributes.get(attribute) if attribute else state.state
        if raw is None or str(raw).strip().lower() in {"unknown", "unavailable", "none", ""}:
            return None, f"{entity_id} indisponível"
        try:
            return float(raw), "Disponível"
        except (TypeError, ValueError):
            return None, f"{entity_id}{'.' + attribute if attribute else ''} não é numérico"

    def _rule_source_value(self, rule: dict[str, Any]) -> tuple[float | None, str]:
        source = rule["source"]
        if source["kind"] == "fixed":
            return float(source["value"]), "Valor fixo"
        return self._entity_numeric_value(source["entity_id"], source.get("attribute", ""))

    def _build_effective_cycle_limits(self, policy: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """Combine persistent local limits, effective preset limits and Agenda offsets."""
        result: dict[str, dict[str, Any]] = {}
        preset_modes = (self.preset_state.get("modes") or {})
        for mode in MODES:
            local = deepcopy((self.power_settings.get("cycle_limits") or {}).get(mode, {}))
            preset = preset_modes.get(mode) or {}
            if mode == "dry":
                start_offset = _number((policy.get("humidity_start_offset") or {}).get(mode), 0)
                stop_offset = _number((policy.get("humidity_stop_offset") or {}).get(mode), 0)
            else:
                start_offset = _number((policy.get("start_offset") or {}).get(mode), 0)
                stop_offset = _number((policy.get("stop_offset") or {}).get(mode), 0)
            base_start = _number(preset.get("start"), _number(local.get("start"), 0))
            base_stop = _number(preset.get("stop"), _number(local.get("stop"), 0))
            item = {
                "local_start": _number(local.get("start"), base_start),
                "local_stop": _number(local.get("stop"), base_stop),
                "preset_start": base_start,
                "preset_stop": base_stop,
                "start_offset": start_offset,
                "stop_offset": stop_offset,
                "start": round(base_start + start_offset, 2),
                "stop": round(base_stop + stop_offset, 2),
            }
            if mode == "dry":
                local_min = _number(local.get("minimum_temperature"), 20.0)
                preset_min = _number(preset.get("minimum_temperature"), local_min)
                minimum_offset = _number(
                    (policy.get("dry_min_temperature_offset") or {}).get(mode), 0
                )
                item.update({
                    "local_minimum_temperature": local_min,
                    "preset_minimum_temperature": preset_min,
                    "minimum_temperature_offset": minimum_offset,
                    "minimum_temperature": round(preset_min + minimum_offset, 2),
                })
            result[mode] = item
        return result

    def _rule_reference_value(self, rule: dict[str, Any], mode: str) -> tuple[float | None, str]:
        reference = rule["reference"]
        kind = reference["kind"]
        if kind == "fixed":
            return float(reference["value"]), "Referência fixa"
        if kind == "entity":
            return self._entity_numeric_value(reference["entity_id"], reference.get("attribute", ""))
        if kind in {"preset_start", "preset_end"}:
            preset = (self.preset_state.get("modes") or {}).get(mode) or {}
            key = "start" if kind == "preset_start" else "stop"
            value = preset.get(key)
            return (float(value), f"{key} do preset efetivo") if value is not None else (None, "Preset efetivo indisponível")
        if kind == "dry_minimum":
            if mode != "dry":
                return None, "Temperatura mínima do Dry não se aplica a este modo"
            preset = (self.preset_state.get("modes") or {}).get("dry") or {}
            value = preset.get("minimum_temperature")
            if value is None:
                value = self._effective_cycle_limits.get("dry", {}).get("minimum_temperature")
            return (float(value), "Temperatura mínima efetiva do Dry") if value is not None else (None, "Mínima do Dry indisponível")
        limits = self._effective_cycle_limits.get(mode, {})
        key = "start" if kind == "cycle_start" else "stop"
        value = limits.get(key)
        return (float(value), f"Limite efetivo de {key}") if value is not None else (None, "Limite efetivo indisponível")

    def _rule_difference(self, rule: dict[str, Any], mode: str, current: float, reference: float) -> float:
        operation = rule["operation"]
        if operation == "current_minus_reference":
            return current - reference
        if operation == "reference_minus_current":
            return reference - current
        if operation == "absolute_difference":
            return abs(current - reference)
        variable = rule["source"].get("variable")
        if variable == "temperature":
            if mode == "heat":
                return max(0.0, reference - current)
            if mode == "cool":
                return max(0.0, current - reference)
            return max(0.0, current - reference)
        return max(0.0, current - reference)

    def _evaluate_rule_states(self) -> tuple[dict[str, int], list[dict[str, Any]], bool]:
        candidates: dict[str, list[dict[str, Any]]] = {mode: [] for mode in MODES}
        diagnostics: list[dict[str, Any]] = []
        runtime_changed = False
        now_iso = _iso_now()

        for rule in self.power_rules:
            source_value, source_reason = self._rule_source_value(rule)
            rule_diag = {
                "id": rule["id"],
                "name": rule["name"],
                "enabled": rule["enabled"],
                "source_value": source_value,
                "source_reason": source_reason,
                "modes": {},
                "group": rule.get("exclusive_group") or None,
                "priority": rule.get("priority", 0),
            }
            for mode in MODES:
                runtime = rule["runtime"]["mode_states"][mode]
                previous_active = bool(runtime.get("active"))
                active = previous_active
                reason = runtime.get("last_reason") or "Inicialização"
                reference_value = None
                difference = None
                available = False
                if not rule["enabled"] or mode not in rule["modes"] or rule["adjustments"].get(mode, 0) == 0:
                    active = False
                    reason = "Regra desabilitada ou sem contribuição neste modo"
                elif source_value is None:
                    active = False
                    reason = source_reason
                else:
                    reference_value, reference_reason = self._rule_reference_value(rule, mode)
                    if reference_value is None:
                        active = False
                        reason = reference_reason
                    else:
                        available = True
                        difference = round(self._rule_difference(rule, mode, source_value, reference_value), 3)
                        if previous_active:
                            if _compare(rule["exit_operator"], difference, rule["exit_value"]):
                                active = False
                                reason = f"Saída atendida: {difference} {rule['exit_operator']} {rule['exit_value']}"
                            else:
                                active = True
                                reason = "Mantida na faixa de histerese"
                        else:
                            if _compare(rule["entry_operator"], difference, rule["entry_value"]):
                                active = True
                                reason = f"Entrada atendida: {difference} {rule['entry_operator']} {rule['entry_value']}"
                            else:
                                active = False
                                reason = "Critério de entrada não atendido"
                if active != previous_active:
                    runtime_changed = True
                    runtime["active"] = active
                    runtime["last_reason"] = reason
                    if active:
                        runtime["last_activation"] = now_iso
                    else:
                        runtime["last_deactivation"] = now_iso
                else:
                    runtime["last_reason"] = reason
                mode_diag = {
                    "active": active,
                    "available": available,
                    "source_value": source_value,
                    "reference_value": reference_value,
                    "difference": difference,
                    "adjustment": rule["adjustments"].get(mode, 0),
                    "entry": {"operator": rule["entry_operator"], "value": rule["entry_value"]},
                    "exit": {"operator": rule["exit_operator"], "value": rule["exit_value"]},
                    "reason": reason,
                    "contributing": False,
                }
                rule_diag["modes"][mode] = mode_diag
                if active:
                    rising = rule["entry_operator"] in {"ge", "gt"}
                    specificity = rule["entry_value"] if rising else -rule["entry_value"]
                    candidates[mode].append(
                        {
                            "rule": rule,
                            "diag": mode_diag,
                            "group": rule.get("exclusive_group") or "",
                            "specificity": specificity,
                        }
                    )
            diagnostics.append(rule_diag)

        contributions = {mode: 0 for mode in MODES}
        for mode in MODES:
            independent = [item for item in candidates[mode] if not item["group"]]
            grouped: dict[str, list[dict[str, Any]]] = {}
            for item in candidates[mode]:
                if item["group"]:
                    grouped.setdefault(item["group"], []).append(item)
            winners = list(independent)
            for group_items in grouped.values():
                winner = max(
                    group_items,
                    key=lambda item: (
                        item["specificity"],
                        int(item["rule"].get("priority", 0)),
                        item["rule"]["id"],
                    ),
                )
                winners.append(winner)
            for item in winners:
                adjustment = int(item["rule"]["adjustments"].get(mode, 0))
                contributions[mode] += adjustment
                item["diag"]["contributing"] = True
        return contributions, diagnostics, runtime_changed

    def _regional_power_adjustment(self, mode: str) -> tuple[int, str]:
        if not (
            _state_on(self.hass, "binary_sensor.elgin_supervisor_clima_regional_efetivo")
            and _state_on(self.hass, "binary_sensor.elgin_supervisor_clima_regional_valido")
        ):
            return 0, "Clima regional inativo ou inválido"
        weather = self.hass.states.get("weather.forecast_casa")
        if weather is None:
            return 0, "Entidade regional indisponível"
        temperature = _number(weather.attributes.get("temperature"), 99 if mode == "heat" else -99)
        humidity = _number(weather.attributes.get("humidity"), -1)
        dew_point = _number(weather.attributes.get("dew_point"), -99)
        if mode == "heat":
            cold = _state_float(self.hass, "input_number.elgin_supervisor_regional_frio", 14)
            extreme = _state_float(self.hass, "input_number.elgin_supervisor_regional_frio_extremo", 8)
            high_h = _state_float(self.hass, "input_number.elgin_supervisor_regional_umidade_alta", 80)
            adjustment = 2 if temperature <= extreme else 1 if temperature <= cold else 0
            if temperature <= cold and humidity >= high_h:
                adjustment += 1
            return adjustment, f"Temperatura externa {temperature} °C; umidade {humidity}%"
        if mode == "cool":
            hot = _state_float(self.hass, "input_number.elgin_supervisor_regional_quente", 28)
            extreme = _state_float(self.hass, "input_number.elgin_supervisor_regional_quente_extremo", 33)
            adjustment = 2 if temperature >= extreme else 1 if temperature >= hot else 0
            return adjustment, f"Temperatura externa {temperature} °C"
        dew_high = _state_float(self.hass, "input_number.elgin_supervisor_regional_orvalho_alto", 18)
        dew_extreme = _state_float(self.hass, "input_number.elgin_supervisor_regional_orvalho_extremo", 22)
        humidity_high = _state_float(self.hass, "input_number.elgin_supervisor_regional_umidade_alta", 80)
        margin = _state_float(self.hass, "input_number.elgin_supervisor_regional_margem_umidade_extrema", 10)
        adjustment = 2 if dew_point >= dew_extreme or humidity >= humidity_high + margin else 1 if dew_point >= dew_high or humidity >= humidity_high else 0
        return adjustment, f"Umidade {humidity}%; ponto de orvalho {dew_point} °C"

    def _resolve_profile(
        self,
        mode: str,
        level: int,
        diagnostics: list[str],
    ) -> tuple[dict[str, Any] | None, int, str]:
        enabled = sorted(
            [item for item in self.power_profiles if item["mode"] == mode and item.get("enabled", True)],
            key=_profile_sort_key,
        )
        if not enabled:
            diagnostics.append("Nenhum perfil de potência habilitado neste modo.")
            return None, level, "indisponível"
        minimum = enabled[0]["level"]
        maximum = enabled[-1]["level"]
        limited = min(max(level, minimum), maximum)
        if limited != level:
            diagnostics.append(f"Nível calculado {level} limitado para {limited} na faixa habilitada {minimum}…{maximum}.")
        exact = next((item for item in enabled if item["level"] == limited), None)
        if exact:
            return exact, limited, "exato"
        effective = min(enabled, key=lambda item: (abs(item["level"] - limited), item["level"]))
        diagnostics.append(
            f"Nível {limited} sem correspondência exata; aplicado {effective['name']} no nível {effective['level']}, favorecendo menor intensidade em empate."
        )
        return effective, limited, "aproximado"

    def _agenda_profile_value(self, policy: dict[str, Any], field: str, mode: str) -> Any:
        value = (policy.get(field) or {}).get(mode)
        source = (policy.get("effect_sources") or {}).get(f"{field}:{mode}") or {}
        if source.get("value_by_mode"):
            return source["value_by_mode"].get(mode)
        return value

    def _power_evaluate(self, policy: dict[str, Any]) -> bool:
        self._effective_cycle_limits = self._build_effective_cycle_limits(policy)
        rule_adjustments, rule_diagnostics, runtime_changed = self._evaluate_rule_states()
        modes_state: dict[str, Any] = {}
        agenda_delta = policy.get("power_delta") or {}
        preset_modes = self.preset_state.get("modes") or {}
        priorities = self.power_settings.get("priorities", {})
        continuity_bonus = int(self.power_settings.get("continuity_bonus", 0))
        current_treatment = _state_text(self.hass, "input_select.elgin_supervisor_tratamento_ativo", "Nenhum")
        current_mode = MODE_FROM_TREATMENT.get(current_treatment)

        for mode in MODES:
            diagnostics: list[str] = []
            enabled_profiles = [item for item in self.power_profiles if item["mode"] == mode and item.get("enabled", True)]
            base = find_power_profile(self.power_profiles, self.base_power_profiles.get(mode), mode)
            if base is None or not base.get("enabled", True):
                base = find_power_profile(self.power_profiles, POWER_DEFAULT_IDS[mode], mode) or (sorted(enabled_profiles, key=_profile_sort_key)[0] if enabled_profiles else None)
                diagnostics.append("Potência base inválida; aplicado o perfil padrão habilitado.")
            agenda_base_id = self._agenda_profile_value(policy, "power_base", mode)
            agenda_base = find_power_profile(self.power_profiles, agenda_base_id, mode)
            if agenda_base_id and (agenda_base is None or not agenda_base.get("enabled", True)):
                diagnostics.append("Potência base solicitada pela Agenda é inválida; mantido o fallback do modo.")
                agenda_base = None
            calculation_base = agenda_base or base
            if calculation_base is None:
                modes_state[mode] = {"mode": mode, "mode_name": MODE_NAMES[mode], "available": False, "diagnostics": diagnostics}
                continue

            preset_modifier = int((preset_modes.get(mode) or {}).get("power_modifier", 0) or 0)
            agenda_modifier = int(round(_number(agenda_delta.get(mode), 0)))
            regional_modifier, regional_reason = self._regional_power_adjustment(mode)
            rules_modifier = int(rule_adjustments.get(mode, 0))
            calculated = int(calculation_base["level"] + preset_modifier + agenda_modifier + regional_modifier + rules_modifier)

            forced_id = self._agenda_profile_value(policy, "power_force", mode)
            forced = find_power_profile(self.power_profiles, forced_id, mode)
            if forced_id and (forced is None or not forced.get("enabled", True)):
                diagnostics.append("Perfil final forçado pela Agenda é inválido; cálculo normal utilizado.")
                forced = None

            minimum_profile = find_power_profile(self.power_profiles, self._agenda_profile_value(policy, "power_min", mode), mode)
            maximum_profile = find_power_profile(self.power_profiles, self._agenda_profile_value(policy, "power_max", mode), mode)
            bounded = calculated
            if minimum_profile and minimum_profile.get("enabled", True) and bounded < minimum_profile["level"]:
                bounded = minimum_profile["level"]
                diagnostics.append(f"Aplicada potência mínima da Agenda: {minimum_profile['name']}.")
            if maximum_profile and maximum_profile.get("enabled", True) and bounded > maximum_profile["level"]:
                bounded = maximum_profile["level"]
                diagnostics.append(f"Aplicada potência máxima da Agenda: {maximum_profile['name']}.")

            if forced:
                effective = forced
                limited = forced["level"]
                resolution = "forçado pela Agenda"
            else:
                effective, limited, resolution = self._resolve_profile(mode, bounded, diagnostics)

            automatic_level = int(calculation_base["level"] + regional_modifier + rules_modifier)
            automatic_profile, automatic_limited, automatic_resolution = self._resolve_profile(mode, automatic_level, [])
            modes_state[mode] = {
                "mode": mode,
                "mode_name": MODE_NAMES[mode],
                "available": effective is not None,
                "base_id": base["id"] if base else None,
                "base_name": base["name"] if base else None,
                "base_level": base["level"] if base else None,
                "calculation_base_id": calculation_base["id"],
                "calculation_base_name": calculation_base["name"],
                "calculation_base_level": calculation_base["level"],
                "agenda_base_override": agenda_base["id"] if agenda_base else None,
                "modifiers": {
                    "preset": preset_modifier,
                    "agenda": agenda_modifier,
                    "regional": regional_modifier,
                    "rules": rules_modifier,
                },
                "regional_reason": regional_reason,
                "calculated_level": calculated,
                "bounded_level": bounded,
                "applied_level": effective["level"] if effective else None,
                "effective_id": effective["id"] if effective else None,
                "effective_name": effective["name"] if effective else "Desativado",
                "target_temperature": effective["target_temperature"] if effective else None,
                "fan": effective["fan"] if effective else None,
                "resolution": resolution,
                "automatic_level": automatic_level,
                "automatic_limited_level": automatic_limited,
                "automatic_profile_id": automatic_profile["id"] if automatic_profile else None,
                "automatic_profile_name": automatic_profile["name"] if automatic_profile else "Desativado",
                "automatic_resolution": automatic_resolution,
                "minimum_profile_id": minimum_profile["id"] if minimum_profile else None,
                "maximum_profile_id": maximum_profile["id"] if maximum_profile else None,
                "forced_profile_id": forced["id"] if forced else None,
                "enabled_levels": sorted(item["level"] for item in enabled_profiles),
                "diagnostics": diagnostics,
            }

        candidate_state: dict[str, Any] = {}
        selected_mode = None
        selected_score = None
        for mode in MODES:
            demand_entity = {
                "heat": "binary_sensor.elgin_supervisor_demanda_aquecimento",
                "cool": "binary_sensor.elgin_supervisor_demanda_refrigeracao",
                "dry": "binary_sensor.elgin_supervisor_demanda_desumidificacao",
            }[mode]
            eligible = _state_on(self.hass, demand_entity)
            agenda_priority = int(round(_number((policy.get("priority_delta") or {}).get(mode), 0)))
            base_priority = int(priorities.get(mode, 0))
            continuity = continuity_bonus if current_mode == mode and eligible else 0
            limits = self._effective_cycle_limits.get(mode, {})
            temperature = _state_float(self.hass, "sensor.sensor_temperatura_sensor_dedicado", 0)
            humidity = _state_float(self.hass, "sensor.sensor_umidade_sensor_dedicado", 0)
            if mode == "heat":
                severity = max(0.0, (_number(limits.get("stop"), 19.0) - temperature) * 10.0)
                severity_reason = f"distância térmica {severity / 10.0:.1f} °C"
            elif mode == "cool":
                severity = max(0.0, (temperature - _number(limits.get("stop"), 22.3)) * 10.0)
                severity_reason = f"distância térmica {severity / 10.0:.1f} °C"
            else:
                severity = max(0.0, (humidity - _number(limits.get("stop"), 60)) * 3.0)
                severity_reason = f"distância de umidade {severity / 3.0:.1f}%"
            score = base_priority + agenda_priority + continuity + severity if eligible else None
            candidate_state[mode] = {
                "eligible": eligible,
                "priority_base": base_priority,
                "agenda_delta": agenda_priority,
                "continuity_bonus": continuity,
                "severity_bonus": round(severity, 2),
                "score": round(score, 2) if score is not None else None,
                "reason": f"Demanda ativa; {severity_reason}" if eligible else "Sem demanda elegível",
            }
            if eligible:
                tie_active = mode == current_mode
                key = (score, 1 if tie_active else 0, -MODES.index(mode))
                selected_key = (selected_score, 1 if selected_mode == current_mode else 0, -MODES.index(selected_mode)) if selected_mode else None
                if selected_key is None or key > selected_key:
                    selected_mode = mode
                    selected_score = score

        active_treatment = _state_text(self.hass, "sensor.elgin_supervisor_tratamento_desejado", "Nenhum")
        active_mode = MODE_FROM_TREATMENT.get(active_treatment)
        active = modes_state.get(active_mode) if active_mode else None
        self.power_state = {
            "revision": self._power_revision,
            "active_mode": active_mode,
            "active_mode_name": MODE_NAMES.get(active_mode, "Nenhum"),
            "profile_in_use": active.get("effective_name") if active and active.get("available") else "Nenhum",
            "profile_in_use_id": active.get("effective_id") if active and active.get("available") else None,
            "target_temperature_in_use": active.get("target_temperature") if active else None,
            "fan_in_use": active.get("fan") if active else None,
            "modes": modes_state,
            "rules": rule_diagnostics,
            "active_rules": [
                {
                    "id": item["id"],
                    "name": item["name"],
                    "group": item["group"],
                    "modes": {
                        mode: data
                        for mode, data in item["modes"].items()
                        if data.get("active") or data.get("contributing")
                    },
                }
                for item in rule_diagnostics
                if any(data.get("active") for data in item["modes"].values())
            ],
            "cycle_limits": {
                mode: {
                    key: value
                    for key, value in item.items()
                    if key in {"start", "stop", "minimum_temperature"}
                }
                for mode, item in self._effective_cycle_limits.items()
            },
            "cycle_limit_details": deepcopy(self._effective_cycle_limits),
            "priorities": dict(priorities),
            "continuity_bonus": continuity_bonus,
            "mode_decision": {
                "candidates": candidate_state,
                "selected": selected_mode,
                "selected_name": MODE_NAMES.get(selected_mode, "Nenhum"),
                "reason": "Maior pontuação; empate favorece o modo já ativo e depois a ordem estável heat → cool → dry" if selected_mode else "Nenhum modo elegível",
            },
            "last_operation": getattr(self, "_last_operation", ""),
            "last_operation_at": getattr(self, "_last_operation_at", None).isoformat() if getattr(self, "_last_operation_at", None) else None,
        }
        self._power_runtime_dirty = runtime_changed
        return runtime_changed
