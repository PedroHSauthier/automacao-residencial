"""Constants for Elgin Supervisor Agenda."""

from __future__ import annotations

from datetime import timedelta

from homeassistant.const import Platform

DOMAIN = "elgin_supervisor_agenda"
NAME = "Elgin Supervisor Agenda"
PLATFORMS = [
    Platform.CALENDAR,
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.BUTTON,
    Platform.SELECT,
]
STORAGE_VERSION = 1
STORAGE_KEY_PREFIX = DOMAIN
UPDATE_INTERVAL = timedelta(seconds=30)

FRONTEND_STATIC_URL = f"/{DOMAIN}/frontend"
FRONTEND_RESOURCE_BASE = f"{FRONTEND_STATIC_URL}/elgin-supervisor-agenda-card.js"
FRONTEND_RESOURCE_URL = f"{FRONTEND_RESOURCE_BASE}?v=20260730.3"

MODE_NAMES = {
    "heat": "Aquecimento",
    "cool": "Refrigeração",
    "dry": "Desumidificação",
}
MODES = tuple(MODE_NAMES)

LEGACY_PRESET_ENTITIES = {
    "heat": "input_select.elgin_supervisor_preset_aquecimento",
    "cool": "input_select.elgin_supervisor_preset_refrigeracao",
    "dry": "input_select.elgin_supervisor_preset_desumidificacao",
}
PRESET_BASE_SELECT_ENTITIES = {
    "heat": "select.elgin_supervisor_preset_base_aquecimento",
    "cool": "select.elgin_supervisor_preset_base_refrigeracao",
    "dry": "select.elgin_supervisor_preset_base_desumidificacao",
}
PRESET_MANUAL_ADJUST_ENTITIES = {
    "heat": "input_number.elgin_supervisor_ajuste_nivel_preset_aquecimento",
    "cool": "input_number.elgin_supervisor_ajuste_nivel_preset_refrigeracao",
    "dry": "input_number.elgin_supervisor_ajuste_nivel_preset_desumidificacao",
}
PRESET_DEFAULT_IDS = {
    "heat": "heat_equilibrio",
    "cool": "cool_equilibrio",
    "dry": "dry_equilibrio",
}
PRESET_ACTIVE_TREATMENT_ENTITY = "sensor.elgin_supervisor_tratamento_desejado"
PRESET_REACTIVE_ENTITIES = (
    tuple(PRESET_MANUAL_ADJUST_ENTITIES.values())
    + (
        "binary_sensor.elgin_supervisor_clima_regional_efetivo",
        "binary_sensor.elgin_supervisor_clima_regional_valido",
        "binary_sensor.elgin_supervisor_limites_automaticos_efetivos",
        PRESET_ACTIVE_TREATMENT_ENTITY,
        "weather.forecast_casa",
        "input_number.elgin_supervisor_regional_frio",
        "input_number.elgin_supervisor_regional_frio_extremo",
        "input_number.elgin_supervisor_regional_quente",
        "input_number.elgin_supervisor_regional_quente_extremo",
        "input_number.elgin_supervisor_regional_faixa_intermediaria_temperatura",
        "input_number.elgin_supervisor_regional_orvalho_alto",
        "input_number.elgin_supervisor_regional_orvalho_extremo",
        "input_number.elgin_supervisor_regional_umidade_alta",
        "input_number.elgin_supervisor_regional_margem_umidade_extrema",
    )
)
POWER_ENTITIES = {
    "heat": "select.elgin_supervisor_potencia_base_aquecimento",
    "cool": "select.elgin_supervisor_potencia_base_refrigeracao",
    "dry": "select.elgin_supervisor_potencia_base_desumidificacao",
}
POWER_SENSOR_ENTITY = "sensor.elgin_supervisor_potencias"
CATALOG_ENTITIES = PRESET_REACTIVE_ENTITIES + (
    "sensor.sensor_temperatura_sensor_dedicado",
    "sensor.sensor_umidade_sensor_dedicado",
    "input_select.elgin_supervisor_tratamento_ativo",
)


GLOBAL_ACTIONS = {
    "normal": 0,
    "suspend": 10,
    "shadow": 20,
    "disable_supervisor": 30,
    "power_off": 40,
    "power_off_block": 50,
}

ADDITIVE_EFFECTS = {
    "power_delta",
    "preset_level_delta",
    "priority_delta",
    "start_offset",
    "stop_offset",
    "dry_min_temperature_offset",
    "humidity_start_offset",
    "humidity_stop_offset",
}

ABSOLUTE_MODE_EFFECTS = {
    "preset": "preset",
    "power_base": "power_base",
    "power_force": "power_force",
    "power_min": "power_min",
    "power_max": "power_max",
    "swing": "swing",
    "fan": "fan",
}


EFFECT_LABELS = {
    "global_action": "Ação global",
    "enable_modes": "Habilitar modos",
    "disable_modes": "Desabilitar modos",
    "only_modes": "Permitir somente modos",
    "enable_all_modes": "Habilitar todos os modos",
    "disable_all_modes": "Desabilitar todos os modos",
    "power_delta": "Ajuste de potência",
    "preset_level_delta": "Ajuste de nível do preset",
    "power_base": "Potência base temporária",
    "power_force": "Potência final forçada",
    "power_min": "Potência mínima",
    "power_max": "Potência máxima",
    "preset": "Preset",
    "eco": "Eco",
    "regional": "Clima regional",
    "limits_auto": "Limites automáticos",
    "physical_semiautomatic": "Físico semi-automático",
    "respect_manual": "Respeitar controle manual",
    "turbo": "Turbo",
    "sleep": "Sleep",
    "health": "Health / IonAir",
    "ifeel": "I Feel",
    "ifeel_source": "Fonte do I Feel",
    "swing": "Swing",
    "fan": "Ventilação",
    "priority_delta": "Ajuste de prioridade",
    "start_offset": "Offset do início",
    "stop_offset": "Offset do fim",
    "dry_min_temperature_offset": "Offset da mínima do Dry",
    "humidity_start_offset": "Offset de umidade inicial",
    "humidity_stop_offset": "Offset de umidade final",
    "minimum_on_minutes": "Mínimo ligado",
    "minimum_off_minutes": "Mínimo desligado",
    "mode_protection_minutes": "Proteção entre modos",
    "manual_pause_minutes": "Pausa manual",
    "block_start": "Bloquear partida",
    "block_automatic_off": "Bloquear desligamento automático",
    "cancel_manual_pause": "Cancelar pausa manual",
}

EFFECT_VALUE_LABELS = {
    "global_action": {
        "normal": "operação normal",
        "suspend": "suspender decisões",
        "shadow": "modo sombra",
        "disable_supervisor": "desativar Supervisor",
        "power_off": "desligar uma vez",
        "power_off_block": "desligar e bloquear religamento",
    },
    "fan": {
        "auto": "automática",
        "low": "baixa",
        "medium": "média",
        "high": "alta",
        "quiet": "silenciosa (IR baixa)",
    },
    "swing": {
        "auto": "automático do Supervisor",
        "off": "desligado",
        "vertical": "vertical",
        "horizontal": "horizontal",
        "both": "ambos",
    },
    "ifeel_source": {
        "Manual": "manual",
        "Sensor dedicado": "sensor dedicado",
        "Semi-automático": "semi-automático",
    },
}

ABSOLUTE_GLOBAL_EFFECTS = {
    "eco": "eco",
    "regional": "regional",
    "limits_auto": "limits_auto",
    "physical_semiautomatic": "physical_semiautomatic",
    "respect_manual": "respect_manual",
    "turbo": "turbo",
    "sleep": "sleep",
    "health": "health",
    "ifeel": "ifeel",
    "ifeel_source": "ifeel_source",
    "minimum_on_minutes": "minimum_on_minutes",
    "minimum_off_minutes": "minimum_off_minutes",
    "mode_protection_minutes": "mode_protection_minutes",
    "manual_pause_minutes": "manual_pause_minutes",
    "block_start": "block_start",
    "block_automatic_off": "block_automatic_off",
    "cancel_manual_pause": "cancel_manual_pause",
}
