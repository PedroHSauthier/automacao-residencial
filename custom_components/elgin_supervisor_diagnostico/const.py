"""Constants and persisted options for Elgin Supervisor diagnostics."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Final

from homeassistant.const import Platform

DOMAIN: Final = "elgin_supervisor_diagnostico"
NAME: Final = "Elgin Supervisor — Diagnóstico"
VERSION: Final = "1.0.0"

PLATFORMS: Final = (
    Platform.SENSOR,
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.EVENT,
)

DATA_ENTRIES: Final = "entries"
DATA_FRONTEND_REGISTERED: Final = "frontend_registered"
DATA_WEBSOCKET_REGISTERED: Final = "websocket_registered"

DATABASE_FILENAME: Final = "elgin_supervisor_diagnostico.sqlite3"
DB_FILENAME: Final = DATABASE_FILENAME
SCHEMA_VERSION: Final = 5
LEGACY_FALLBACK_FILENAME: Final = (
    "elgin_supervisor_diagnostico_critical_fallback.ndjson"
)
DIAGNOSTIC_EVENT: Final = "elgin_supervisor_diagnostic_event"
UPDATED_EVENT: Final = f"{DOMAIN}_updated"

FRONTEND_STATIC_URL: Final = f"/{DOMAIN}/frontend"
FRONTEND_RESOURCE_BASE: Final = (
    f"{FRONTEND_STATIC_URL}/elgin-supervisor-diagnostico-card.js"
)
FRONTEND_RESOURCE_URL: Final = f"{FRONTEND_RESOURCE_BASE}?v={VERSION}"

CAPTURE_MODES: Final = ("essential", "normal", "intensive")
SEVERITIES: Final = ("debug", "info", "success", "warning", "error", "critical")
DENSITIES: Final = ("comfortable", "compact")
DATE_FORMATS: Final = ("locale", "iso", "relative")
DETAIL_MODES: Final = ("panel", "modal")

ANOMALY_TYPES: Final = (
    "commands_too_close",
    "repeated_commands",
    "decision_oscillation",
    "desired_state_divergence",
    "localtuya_not_confirmed",
    "external_change_reaction",
    "excessive_volume",
    "repeated_error",
    "critical_entity_unavailable",
)

DEFAULT_COLUMNS: Final = (
    "occurred_at",
    "severity",
    "category",
    "summary",
    "actor",
    "origin",
    "entity_id",
    "before",
    "after",
    "outcome",
    "correlation_id",
)

# These are the only sources captured automatically. The evaluation event emitted by
# the Supervisor carries its complete input snapshot, including sources that must not
# create independent state_changed rows.
SELF_ENTITY_PREFIXES: Final = (
    "sensor.elgin_supervisor_diagnostico_",
    "binary_sensor.elgin_supervisor_diagnostico_",
    "event.elgin_supervisor_diagnostico_",
    "button.elgin_supervisor_diagnostico_",
    "switch.elgin_supervisor_diagnostico_",
)

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
    "sensor.sensor_temperatura_sensor_dedicado",
    "sensor.sensor_umidade_sensor_dedicado",
    "sensor.elgin_supervisor_tratamento_desejado",
    "input_select.elgin_supervisor_tratamento_ativo",
    "sensor.elgin_supervisor_configuracao_desejada",
    "sensor.elgin_supervisor_presets_de_condicao",
    "sensor.elgin_supervisor_potencias",
    "sensor.elgin_supervisor_agenda_politica",
    "binary_sensor.elgin_supervisor_eco_efetivo",
    "binary_sensor.elgin_supervisor_ifeel_efetivo",
    "timer.elgin_supervisor_janela_reconciliacao",
    "timer.elgin_supervisor_pausa_manual",
    "timer.elgin_supervisor_protecao_troca_modo",
)

SENSITIVE_KEYS: Final = frozenset(
    {
        "access_token",
        "api_key",
        "apikey",
        "authorization",
        "client_secret",
        "cookie",
        "encryption_key",
        "external_url",
        "internal_url",
        "latitude",
        "longitude",
        "password",
        "passwd",
        "refresh_token",
        "secret",
        "ssid",
        "token",
        "wifi",
        "wifi_password",
    }
)

# Every user setting lives in ConfigEntry.options. No YAML helper is needed or
# allowed for the diagnostic subsystem.
DEFAULT_OPTIONS: Final[dict[str, Any]] = {
    # Capture
    "capture_mode": "normal",
    "capture_decisions": True,
    "capture_state_changes": True,
    "capture_service_calls": True,
    "capture_localtuya": True,
    "capture_climate": True,
    "capture_agenda": True,
    "capture_presets": True,
    "capture_power_profiles": True,
    "capture_protections": True,
    "capture_errors": True,
    "capture_external_changes": True,
    # Retention
    "retention_essential_days": 60,
    "retention_error_days": 30,
    "retention_trace_days": 7,
    # Compaction / storm protection
    "compaction_enabled": True,
    "compaction_window_seconds": 60,
    "compact_identical_evaluations": True,
    "compact_no_change": True,
    "compact_identical_states": True,
    "compact_repeated_blocks": True,
    "compact_repeated_unavailable": True,
    "rate_window_seconds": 60,
    "rate_warning_events": 500,
    "rate_hard_limit_events": 2_000,
    "queue_limit": 5_000,
    "critical_queue_limit": 2_000,
    "batch_size": 100,
    "flush_interval_seconds": 0.25,
    # Correlation
    "correlation_window_seconds": 30,
    "localtuya_confirmation_window_seconds": 30,
    "external_observation_window_seconds": 60,
    "beep_window_before_seconds": 120,
    "beep_window_after_seconds": 120,
    # Anomalies
    "anomaly_enabled_types": list(ANOMALY_TYPES),
    "anomalies_enabled": True,
    "anomaly_close_commands_seconds": 2,
    "anomaly_repeated_command_window_seconds": 300,
    "anomaly_oscillation_window_seconds": 600,
    "anomaly_oscillation_min_changes": 4,
    "anomaly_divergence_seconds": 60,
    "anomaly_volume_window_seconds": 60,
    "anomaly_volume_event_limit": 1_000,
    "anomaly_repeated_error_window_seconds": 300,
    "anomaly_repeated_error_count": 3,
    "anomaly_unavailable_seconds": 120,
    "anomaly_no_change_threshold": 100,
    "anomaly_duplicate_window_seconds": 10,
    "anomaly_audible_burst_seconds": 20,
    "anomaly_audible_burst_count": 3,
    "anomaly_window_minutes": 15,
    # Notifications
    "notifications_enabled": False,
    "notification_min_severity": "warning",
    "notification_types": list(ANOMALY_TYPES),
    "notification_cooldown_seconds": 900,
    "notification_persistent": True,
    "notification_service": "",
    # Interface and saved searches
    "interface_items_per_page": 50,
    "interface_auto_refresh": True,
    "interface_columns": list(DEFAULT_COLUMNS),
    "interface_density": "comfortable",
    "interface_show_technical_codes": False,
    "interface_show_unchanged_attributes": False,
    "interface_date_format": "locale",
    "interface_detail_mode": "panel",
    "saved_filters": [],
    "default_saved_filter_id": "",
    # Privacy
    "privacy_resolve_user_names": True,
    "privacy_store_user_ids": True,
    "privacy_store_user_names": True,
    "privacy_capture_raw_events": True,
    "privacy_capture_service_data": True,
    "privacy_redact_sensitive_values": True,
    # Maintenance
    "maintenance_database_limit_mb": 250,
    "maintenance_cleanup_interval_hours": 6,
    "maintenance_export_max_rows": 50_000,
    "anonymize_entity_ids": False,
}


def default_options() -> dict[str, Any]:
    """Return an independent, JSON-serializable copy of all defaults."""

    return deepcopy(DEFAULT_OPTIONS)


def merged_options(options: dict[str, Any] | None) -> dict[str, Any]:
    """Merge persisted values over current defaults without sharing containers."""

    merged = default_options()
    if options:
        for key, value in options.items():
            if key in merged:
                merged[key] = deepcopy(value)
    return merged
