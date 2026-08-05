"""Independent condition-preset catalog for the Elgin Supervisor."""

from __future__ import annotations

from copy import deepcopy
from typing import Any
from uuid import uuid4

from homeassistant.core import HomeAssistant

from .const import (
    LEGACY_PRESET_ENTITIES,
    MODE_NAMES,
    MODES,
    PRESET_ACTIVE_TREATMENT_ENTITY,
    PRESET_DEFAULT_IDS,
    PRESET_MANUAL_ADJUST_ENTITIES,
)

MODE_FROM_TREATMENT = {
    "Aquecimento": "heat",
    "Refrigeração": "cool",
    "Desumidificação": "dry",
}


class PresetValidationError(ValueError):
    """Raised when a preset violates the mode-specific contract."""


def _state_float(hass: HomeAssistant, entity_id: str, default: float) -> float:
    state = hass.states.get(entity_id)
    try:
        return float(state.state) if state else default
    except (TypeError, ValueError):
        return default


def _attr_float(hass: HomeAssistant, entity_id: str, attribute: str, default: float) -> float:
    state = hass.states.get(entity_id)
    try:
        return float(state.attributes.get(attribute)) if state else default
    except (TypeError, ValueError):
        return default


def _state_on(hass: HomeAssistant, entity_id: str) -> bool:
    state = hass.states.get(entity_id)
    return bool(state and state.state == "on")


def _round_mode_value(mode: str, value: Any) -> float | int:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = 0.0
    if mode == "dry":
        return int(round(number))
    return round(number, 1)


def default_presets(hass: HomeAssistant) -> list[dict[str, Any]]:
    """Return the migrated built-in presets, preserving the old semantics."""
    custom_values = {
        "heat": {
            "start": _state_float(hass, "input_number.elgin_supervisor_aquecimento_inicio", 18.0),
            "stop": _state_float(hass, "input_number.elgin_supervisor_aquecimento_fim", 20.2),
        },
        "cool": {
            "start": _state_float(hass, "input_number.elgin_supervisor_refrigeracao_inicio", 25.2),
            "stop": _state_float(hass, "input_number.elgin_supervisor_refrigeracao_fim", 22.7),
        },
        "dry": {
            "start": _state_float(hass, "input_number.elgin_supervisor_desumidificacao_inicio", 63),
            "stop": _state_float(hass, "input_number.elgin_supervisor_desumidificacao_fim", 57),
            "minimum_temperature": _state_float(
                hass,
                "input_number.elgin_supervisor_desumidificacao_temperatura_minima",
                19.0,
            ),
        },
    }
    definitions: dict[str, list[dict[str, Any]]] = {
        "heat": [
            {"id": "heat_economia", "name": "Economia", "level": -1, "start": 16.5, "stop": 19.0, "power_modifier": 0},
            {"id": "heat_equilibrio", "name": "Equilíbrio", "level": 0, "start": 18.0, "stop": 20.2, "power_modifier": 0, "default": True, "protected": True},
            {"id": "heat_conforto", "name": "Conforto", "level": 1, "start": 19.5, "stop": 21.3, "power_modifier": 1},
            {"id": "heat_agressivo", "name": "Agressivo", "level": 2, "start": 21.0, "stop": 22.5, "power_modifier": 1},
        ],
        "cool": [
            {"id": "cool_economia", "name": "Economia", "level": -1, "start": 26.0, "stop": 23.0, "power_modifier": 0},
            {"id": "cool_equilibrio", "name": "Equilíbrio", "level": 0, "start": 25.2, "stop": 22.7, "power_modifier": 0, "default": True, "protected": True},
            {"id": "cool_conforto", "name": "Conforto", "level": 1, "start": 24.3, "stop": 22.3, "power_modifier": 1},
            {"id": "cool_agressivo", "name": "Agressivo", "level": 2, "start": 23.5, "stop": 22.0, "power_modifier": 1},
        ],
        "dry": [
            {"id": "dry_economia", "name": "Economia", "level": -1, "start": 65, "stop": 60, "minimum_temperature": 20.0, "power_modifier": 0},
            {"id": "dry_equilibrio", "name": "Equilíbrio", "level": 0, "start": 63, "stop": 57, "minimum_temperature": 19.0, "power_modifier": 0, "default": True, "protected": True},
            {"id": "dry_conforto", "name": "Conforto", "level": 1, "start": 61, "stop": 54, "minimum_temperature": 18.0, "power_modifier": 1},
            {"id": "dry_agressivo", "name": "Agressivo", "level": 2, "start": 60, "stop": 52, "minimum_temperature": 17.5, "power_modifier": 1},
        ],
    }
    result: list[dict[str, Any]] = []
    for mode in MODES:
        for item in definitions[mode]:
            item = {
                **item,
                "mode": mode,
                "enabled": True,
                "description": f"Preset migrado do modelo anterior de {MODE_NAMES[mode].lower()}.",
                "protected": bool(item.get("protected", False)),
                "default": bool(item.get("default", False)),
            }
            result.append(normalize_preset(item))

        legacy_state = hass.states.get(LEGACY_PRESET_ENTITIES[mode])
        legacy_selected = legacy_state.state if legacy_state else "Equilíbrio"
        custom = {
            "id": f"{mode}_personalizado",
            "name": "Personalizado",
            "mode": mode,
            "level": 3 if legacy_selected == "Personalizado" else 0,
            "enabled": legacy_selected == "Personalizado",
            "description": "Valores personalizados migrados dos helpers manuais anteriores. Defina um nível exclusivo antes de habilitar.",
            "start": custom_values[mode]["start"],
            "stop": custom_values[mode]["stop"],
            "minimum_temperature": custom_values[mode].get("minimum_temperature"),
            "power_modifier": 0,
            "protected": False,
            "default": False,
        }
        result.append(normalize_preset(custom))
    return result


def normalize_preset(preset: dict[str, Any], existing: dict[str, Any] | None = None) -> dict[str, Any]:
    """Normalize one persistent preset without silently changing its mode or id."""
    mode = str((existing or {}).get("mode") or preset.get("mode") or "")
    if mode not in MODES:
        raise PresetValidationError("O modo do preset deve ser heat, cool ou dry.")
    preset_id = str((existing or {}).get("id") or preset.get("id") or uuid4())
    normalized: dict[str, Any] = {
        "id": preset_id,
        "name": str(preset.get("name") or "Preset sem nome").strip()[:80],
        "mode": mode,
        "level": int(round(float(preset.get("level", 0)))),
        "enabled": bool(preset.get("enabled", True)),
        "description": str(preset.get("description") or "").strip()[:500],
        "start": _round_mode_value(mode, preset.get("start", 0)),
        "stop": _round_mode_value(mode, preset.get("stop", 0)),
        "power_modifier": int(round(float(preset.get("power_modifier", 0)))),
        "protected": bool((existing or {}).get("protected", preset.get("protected", False))),
        "default": bool((existing or {}).get("default", preset.get("default", False))),
    }
    normalized["minimum_temperature"] = (
        round(float(preset.get("minimum_temperature", 19.0)), 1)
        if mode == "dry"
        else None
    )
    return normalized


def validate_preset(preset: dict[str, Any], catalog: list[dict[str, Any]]) -> None:
    """Validate uniqueness and mode-specific hysteresis semantics."""
    if not preset["name"]:
        raise PresetValidationError("Informe o nome do preset.")
    if not -100 <= preset["level"] <= 100:
        raise PresetValidationError("O nível deve ficar entre -100 e 100.")
    if not -20 <= preset["power_modifier"] <= 20:
        raise PresetValidationError("O modificador de potência deve ficar entre -20 e 20.")

    for item in catalog:
        if item["id"] == preset["id"] or item["mode"] != preset["mode"]:
            continue
        if item["name"].casefold() == preset["name"].casefold():
            raise PresetValidationError("Já existe um preset com esse nome neste modo.")
        if item.get("enabled", True) and preset.get("enabled", True) and item["level"] == preset["level"]:
            raise PresetValidationError(
                f"O nível {preset['level']} já pertence ao preset {item['name']} em {MODE_NAMES[preset['mode']]}.")

    start = float(preset["start"])
    stop = float(preset["stop"])
    if preset["mode"] == "heat":
        if not 5 <= start <= 32 or not 5 <= stop <= 35:
            raise PresetValidationError("Os limites de aquecimento devem ficar entre 5 e 35 °C.")
        if start >= stop:
            raise PresetValidationError("No aquecimento, o início deve ser menor que o encerramento.")
    elif preset["mode"] == "cool":
        if not 10 <= start <= 45 or not 10 <= stop <= 40:
            raise PresetValidationError("Os limites de refrigeração devem ficar entre 10 e 45 °C.")
        if start <= stop:
            raise PresetValidationError("Na refrigeração, o início deve ser maior que o encerramento.")
    else:
        if not 30 <= start <= 100 or not 20 <= stop <= 95:
            raise PresetValidationError("Os limites de desumidificação devem ficar entre 20% e 100%.")
        if start <= stop:
            raise PresetValidationError("Na desumidificação, o início deve ser maior que o encerramento.")
        minimum = float(preset.get("minimum_temperature", 19.0))
        if not 5 <= minimum <= 30:
            raise PresetValidationError("A temperatura mínima do Dry deve ficar entre 5 e 30 °C.")

    if preset.get("default") and not preset.get("enabled"):
        raise PresetValidationError("O preset padrão protegido não pode ser desabilitado.")


def migrate_base_presets(hass: HomeAssistant, presets: list[dict[str, Any]]) -> dict[str, str]:
    """Choose a base per mode from the legacy selectors when possible."""
    result: dict[str, str] = {}
    for mode in MODES:
        legacy = hass.states.get(LEGACY_PRESET_ENTITIES[mode])
        legacy_name = legacy.state if legacy else "Equilíbrio"
        match = next(
            (
                item
                for item in presets
                if item["mode"] == mode and item["enabled"] and item["name"] == legacy_name
            ),
            None,
        )
        result[mode] = (match or find_preset(presets, PRESET_DEFAULT_IDS[mode]))["id"]
    return result


def find_preset(presets: list[dict[str, Any]], preset_id_or_name: Any, mode: str | None = None) -> dict[str, Any] | None:
    """Find by immutable id first, then by legacy display name within a mode."""
    if preset_id_or_name in (None, "", "default"):
        return None
    value = str(preset_id_or_name)
    exact = next((item for item in presets if item["id"] == value and (mode is None or item["mode"] == mode)), None)
    if exact:
        return exact
    return next(
        (
            item
            for item in presets
            if item["name"] == value and (mode is None or item["mode"] == mode)
        ),
        None,
    )


def public_catalog(presets: list[dict[str, Any]], base_presets: dict[str, str]) -> dict[str, Any]:
    """Return a JSON-serialisable mode-separated catalog."""
    by_mode: dict[str, list[dict[str, Any]]] = {}
    for mode in MODES:
        by_mode[mode] = sorted(
            [deepcopy(item) for item in presets if item["mode"] == mode],
            key=lambda item: (item["level"], item["name"].casefold()),
        )
    return {
        "presets": by_mode,
        "preset_options": {
            mode: [
                {"id": item["id"], "name": item["name"], "level": item["level"]}
                for item in by_mode[mode]
                if item["enabled"]
            ]
            for mode in MODES
        },
        "base_presets": dict(base_presets),
        "default_presets": dict(PRESET_DEFAULT_IDS),
    }


def _regional_target_level(
    hass: HomeAssistant,
    mode: str,
    enabled_presets: list[dict[str, Any]],
) -> tuple[int | None, str]:
    if not (
        _state_on(hass, "binary_sensor.elgin_supervisor_clima_regional_efetivo")
        and _state_on(hass, "binary_sensor.elgin_supervisor_clima_regional_valido")
        and _state_on(hass, "binary_sensor.elgin_supervisor_limites_automaticos_efetivos")
    ):
        return None, "Clima regional ou limites automáticos inativos/ inválidos"

    levels = sorted(item["level"] for item in enabled_presets)
    if not levels:
        return None, "Nenhum preset habilitado"
    low = levels[0]
    neutral = min(levels, key=lambda level: (abs(level), level))
    high = levels[-1]
    medium_high = sorted(levels)[-2] if len(levels) > 1 else high

    weather = hass.states.get("weather.forecast_casa")
    temperature = _attr_float(hass, "weather.forecast_casa", "temperature", 99 if mode == "heat" else -99)
    humidity = _attr_float(hass, "weather.forecast_casa", "humidity", -1)
    dew_point = _attr_float(hass, "weather.forecast_casa", "dew_point", -99)
    if weather is None:
        return None, "Entidade regional indisponível"

    if mode == "heat":
        cold = _state_float(hass, "input_number.elgin_supervisor_regional_frio", 14)
        extreme = _state_float(hass, "input_number.elgin_supervisor_regional_frio_extremo", 8)
        band = _state_float(hass, "input_number.elgin_supervisor_regional_faixa_intermediaria_temperatura", 4)
        if temperature <= extreme:
            return high, "Frio extremo"
        if temperature <= cold:
            return medium_high, "Frio"
        if temperature <= cold + band:
            return neutral, "Faixa intermediária"
        return low, "Temperatura externa amena"

    if mode == "cool":
        hot = _state_float(hass, "input_number.elgin_supervisor_regional_quente", 28)
        extreme = _state_float(hass, "input_number.elgin_supervisor_regional_quente_extremo", 33)
        band = _state_float(hass, "input_number.elgin_supervisor_regional_faixa_intermediaria_temperatura", 4)
        if temperature >= extreme:
            return high, "Calor extremo"
        if temperature >= hot:
            return medium_high, "Calor"
        if temperature >= hot - band:
            return neutral, "Faixa intermediária"
        return low, "Temperatura externa amena"

    dew_high = _state_float(hass, "input_number.elgin_supervisor_regional_orvalho_alto", 18)
    dew_extreme = _state_float(hass, "input_number.elgin_supervisor_regional_orvalho_extremo", 22)
    humidity_high = _state_float(hass, "input_number.elgin_supervisor_regional_umidade_alta", 80)
    margin = _state_float(hass, "input_number.elgin_supervisor_regional_margem_umidade_extrema", 10)
    if dew_point >= dew_extreme or humidity >= humidity_high + margin:
        return high, "Umidade ou ponto de orvalho extremo"
    if dew_point >= dew_high and humidity >= humidity_high:
        return medium_high, "Umidade e ponto de orvalho altos"
    if dew_point >= dew_high or humidity >= humidity_high:
        return neutral, "Uma condição regional alta"
    return low, "Condições regionais moderadas"


def calculate_preset_state(
    hass: HomeAssistant,
    presets: list[dict[str, Any]],
    base_presets: dict[str, str],
    policy: dict[str, Any],
    revision: int,
) -> dict[str, Any]:
    """Resolve base and effective presets independently for all modes."""
    results: dict[str, Any] = {}
    agenda_forced = policy.get("preset") or {}
    agenda_delta = policy.get("preset_level_delta") or {}
    effect_sources = policy.get("effect_sources") or {}

    for mode in MODES:
        mode_presets = [item for item in presets if item["mode"] == mode]
        enabled = sorted(
            [item for item in mode_presets if item.get("enabled", True)],
            key=lambda item: (item["level"], item["name"].casefold()),
        )
        default = find_preset(presets, PRESET_DEFAULT_IDS[mode], mode)
        base = find_preset(presets, base_presets.get(mode), mode)
        diagnostics: list[str] = []
        if not base or not base.get("enabled"):
            base = default if default and default.get("enabled") else (enabled[0] if enabled else None)
            diagnostics.append("Preset base inválido; aplicado o padrão protegido.")
        if not enabled or base is None:
            results[mode] = {
                "mode": mode,
                "mode_name": MODE_NAMES[mode],
                "available": False,
                "diagnostics": ["Nenhum preset habilitado neste modo."],
            }
            continue

        forced_value = agenda_forced.get(mode)
        forced = find_preset(presets, forced_value, mode)
        if forced_value not in (None, "", "default") and (not forced or not forced.get("enabled")):
            diagnostics.append("Preset solicitado pela Agenda não existe, está desabilitado ou pertence a outro modo.")
            forced = None
        calculation_base = forced or base

        manual_delta = int(round(_state_float(hass, PRESET_MANUAL_ADJUST_ENTITIES[mode], 0)))
        agenda_adjustment = int(round(float(agenda_delta.get(mode, 0) or 0)))
        regional_target, regional_reason = _regional_target_level(hass, mode, enabled)
        regional_delta = 0 if regional_target is None else int(regional_target - calculation_base["level"])
        target_level = calculation_base["level"] + manual_delta + agenda_adjustment + regional_delta

        minimum = enabled[0]["level"]
        maximum = enabled[-1]["level"]
        limited_level = min(max(target_level, minimum), maximum)
        if limited_level != target_level:
            diagnostics.append(
                f"Nível calculado {target_level} limitado para {limited_level} dentro da faixa habilitada {minimum}…{maximum}."
            )

        exact = next((item for item in enabled if item["level"] == limited_level), None)
        if exact:
            effective = exact
            resolution = "exato"
        else:
            effective = min(
                enabled,
                key=lambda item: (abs(item["level"] - limited_level), item["level"]),
            )
            resolution = "aproximado"
            diagnostics.append(
                f"Nenhum preset no nível {limited_level}; selecionado {effective['name']} no nível {effective['level']}, favorecendo o menos agressivo em empate."
            )

        hysteresis = (
            round(float(effective["stop"]) - float(effective["start"]), 1)
            if mode == "heat"
            else int(round(float(effective["start"]) - float(effective["stop"])))
            if mode == "dry"
            else round(float(effective["start"]) - float(effective["stop"]), 1)
        )
        results[mode] = {
            "mode": mode,
            "mode_name": MODE_NAMES[mode],
            "available": True,
            "base_id": base["id"],
            "base_name": base["name"],
            "base_level": base["level"],
            "calculation_base_id": calculation_base["id"],
            "calculation_base_name": calculation_base["name"],
            "calculation_base_level": calculation_base["level"],
            "agenda_base_override": forced["id"] if forced else None,
            "manual_level_delta": manual_delta,
            "agenda_level_delta": agenda_adjustment,
            "regional_level_delta": regional_delta,
            "regional_target_level": regional_target,
            "regional_reason": regional_reason,
            "calculated_level": target_level,
            "limited_level": limited_level,
            "minimum_enabled_level": minimum,
            "maximum_enabled_level": maximum,
            "effective_id": effective["id"],
            "effective_name": effective["name"],
            "effective_level": effective["level"],
            "resolution": resolution,
            "start": effective["start"],
            "stop": effective["stop"],
            "hysteresis": hysteresis,
            "minimum_temperature": effective.get("minimum_temperature"),
            "power_modifier": effective["power_modifier"],
            "enabled_count": len(enabled),
            "diagnostics": diagnostics,
            "sources": {
                "agenda_base": effect_sources.get(f"preset:{mode}"),
                "agenda_level": effect_sources.get(f"preset_level_delta:{mode}", []),
            },
        }

    treatment = hass.states.get(PRESET_ACTIVE_TREATMENT_ENTITY)
    active_mode = MODE_FROM_TREATMENT.get(treatment.state if treatment else "")
    active = results.get(active_mode) if active_mode else None
    return {
        "revision": revision,
        "modes": results,
        "active_mode": active_mode,
        "active_mode_name": MODE_NAMES.get(active_mode, "Nenhum"),
        "preset_in_use": active.get("effective_name") if active and active.get("available") else "Nenhum",
        "preset_in_use_id": active.get("effective_id") if active and active.get("available") else None,
        "power_modifier_in_use": active.get("power_modifier", 0) if active else 0,
        "start_in_use": active.get("start") if active else None,
        "stop_in_use": active.get("stop") if active else None,
        "minimum_temperature_in_use": active.get("minimum_temperature") if active else None,
    }
