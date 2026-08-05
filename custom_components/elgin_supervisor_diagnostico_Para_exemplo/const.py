"""Constants for Elgin Supervisor diagnostics."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

from homeassistant.const import Platform

DOMAIN: Final = "elgin_supervisor_diagnostico"
NAME: Final = "Elgin Supervisor — Auditoria e Diagnóstico"
VERSION: Final = "1.0.1"
PLATFORMS: Final = [
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.SWITCH,
    Platform.BUTTON,
    Platform.EVENT,
]

DATA_MANAGERS: Final = "managers"
DATA_WEBSOCKET_REGISTERED: Final = "websocket_registered"
DATA_FRONTEND_REGISTERED: Final = "frontend_registered"

DB_FILENAME: Final = "elgin_supervisor_diagnostico.sqlite3"
SCHEMA_VERSION: Final = 1
NORMAL_QUEUE_MAX: Final = 5_000
BATCH_SIZE: Final = 50
FLUSH_INTERVAL_SECONDS: Final = 0.250
MAX_PAGE_SIZE: Final = 250
DEFAULT_PAGE_SIZE: Final = 50
MAX_PAYLOAD_BYTES: Final = 128_000
MAX_TEXT_LENGTH: Final = 4_096
MAX_JSON_DEPTH: Final = 8

FRONTEND_STATIC_URL: Final = f"/{DOMAIN}/frontend"
FRONTEND_RESOURCE_BASE: Final = (
    f"{FRONTEND_STATIC_URL}/elgin-supervisor-diagnostico-card.js"
)
FRONTEND_RESOURCE_URL: Final = f"{FRONTEND_RESOURCE_BASE}?v=20260731.2"

EVENT_AGENDA_POLICY_CHANGED: Final = "elgin_supervisor_agenda_policy_changed"
EVENT_AGENDA_EVALUATED: Final = "elgin_supervisor_agenda_evaluated"
EVENT_DIAGNOSTIC_UPDATED: Final = f"{DOMAIN}_updated"
EVENT_ENTITY_TYPES: Final = (
    "anomaly",
    "transmission",
    "external_change",
    "user_observation",
    "error",
)

DEFAULT_OPTIONS: Final = {
    "intensive_mode": False,
    "retention_absolute_days": 60,
    "retention_error_days": 30,
    "retention_full_days": 7,
    "beep_window_before_seconds": 120,
    "beep_window_after_seconds": 120,
    "multiple_full_frames_limit": 2,
    "multiple_full_frames_window_seconds": 300,
    "close_transmissions_seconds": 2,
    "identical_frame_window_seconds": 300,
    "logical_concurrency_seconds": 5,
    "external_reaction_window_seconds": 60,
    "oscillation_window_seconds": 600,
    "oscillation_min_changes": 4,
    "localtuya_confirmation_seconds": 30,
    "notifications_enabled": True,
    "notification_min_severity": "warning",
    "notification_cooldown_seconds": 900,
    "notify_service": "",
    "compaction_enabled": True,
    "max_database_mb": 250,
    "default_page_size": DEFAULT_PAGE_SIZE,
    "technical_details_enabled": True,
    "visible_categories": [],
    "enabled_anomaly_types": [],
}

SEVERITY_ORDER: Final = {
    "debug": 0,
    "info": 1,
    "success": 2,
    "warning": 3,
    "error": 4,
    "critical": 5,
}

CRITICAL_EVENT_TYPES: Final = {
    "action.requested",
    "action.failed",
    "ir.full.requested",
    "ir.full.encoded",
    "ir.full.transmitter_called",
    "ir.full.response",
    "ir.full.failed",
    "ir.sensor_update.requested",
    "ir.sensor_update.encoded",
    "ir.sensor_update.transmitter_called",
    "ir.sensor_update.response",
    "ir.sensor_update.failed",
    "ir.display",
    "ir.clean",
    "localtuya.external_change",
    "localtuya.divergence",
    "user.beep_observed",
    "anomaly.detected",
    "anomaly.updated",
    "anomaly.resolved",
    "storage.queue_overflow",
}

TRANSMISSION_EVENT_TYPES: Final = {
    "ir.full.requested",
    "ir.full.encoded",
    "ir.full.transmitter_called",
    "ir.full.response",
    "ir.full.failed",
    "ir.sensor_update.requested",
    "ir.sensor_update.encoded",
    "ir.sensor_update.transmitter_called",
    "ir.sensor_update.response",
    "ir.sensor_update.failed",
    "ir.display",
    "ir.clean",
}

LOCALTUYA_ENTITIES: Final = (
    "switch.smart_air_conditioner_power_ar_condicionado_id_1",
    "number.smart_air_conditioner_temperatura_alvo_ar_condicionado_id_2",
    "select.smart_air_conditioner_mode_ar_condicionado_id_4",
    "select.smart_air_conditioner_windspeed_ar_condicionado_id_5",
    "switch.smart_air_conditioner_eco_ar_condicionado_id_8",
    "switch.smart_air_conditioner_swing_ar_condicionado_id_33",
    "switch.smart_air_conditioner_sleep_ar_condicionado_id_102",
    "switch.smart_air_conditioner_up_down_wind_ar_condicionado_id_105",
    "switch.smart_air_conditioner_health_ar_condicionado_id_106",
    "sensor.smart_air_conditioner_fault_up_ar_condicionado_id_107",
)

MONITORED_ENTITIES: Final = LOCALTUYA_ENTITIES + (
    "climate.esp8266_elgin_aux_quarto",
    "binary_sensor.esp8266_elgin_aux_estado_base_valido",
    "sensor.esp8266_elgin_aux_sequencia_relatorio",
    "sensor.sensor_temperatura_sensor_dedicado",
    "sensor.sensor_umidade_sensor_dedicado",
    "sensor.elgin_supervisor_tratamento_desejado",
    "input_select.elgin_supervisor_tratamento_ativo",
    "sensor.elgin_supervisor_configuracao_desejada",
    "sensor.elgin_supervisor_diagnostico_de_potencia",
    "sensor.elgin_supervisor_presets_de_condicao",
    "sensor.elgin_supervisor_potencias",
    "sensor.elgin_supervisor_agenda_politica",
    "binary_sensor.elgin_supervisor_eco_efetivo",
    "binary_sensor.elgin_supervisor_ifeel_efetivo",
    "input_boolean.elgin_aux_alteracoes_avancadas_pendentes",
    "timer.elgin_supervisor_janela_reconciliacao",
    "timer.elgin_supervisor_pausa_manual",
    "timer.elgin_supervisor_protecao_troca_modo",
)

RELEVANT_SERVICE_DOMAINS: Final = {
    "esphome",
    "climate",
    "switch",
    "select",
    "input_boolean",
    "input_number",
    "script",
    "automation",
    "timer",
    "elgin_supervisor_agenda",
}

CLEANUP_INTERVAL: Final = timedelta(hours=6)
ANOMALY_REEVALUATE_INTERVAL: Final = timedelta(minutes=5)

SENSITIVE_KEYS: Final = {
    "password",
    "passwd",
    "token",
    "access_token",
    "refresh_token",
    "api_key",
    "apikey",
    "secret",
    "encryption_key",
    "ssid",
    "wifi",
    "latitude",
    "longitude",
    "location",
    "external_url",
    "internal_url",
}
