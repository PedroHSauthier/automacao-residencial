"""Pure, repeatable migration rules for the production diagnostic integration."""

from __future__ import annotations

from copy import deepcopy
from typing import Any, Mapping, Sequence


LEGACY_ENTITY_DOMAINS = {
    "status": "sensor",
    "last_event": "sensor",
    "last_transmission": "sensor",
    "counters": "sensor",
    "database": "sensor",
    "active_anomaly": "binary_sensor",
    "persistence_healthy": "binary_sensor",
    "instrumentation_complete": "binary_sensor",
    "intensive": "switch",
    "register_beep": "button",
    "force_cleanup": "button",
    "reevaluate_anomalies": "button",
    "event": "event",
}

LEGACY_ENTITY_MAP = {
    "status": "status",
    "last_event": "last_event",
    "last_transmission": "last_action",
    "database": "database_size",
    "persistence_healthy": "persistence_healthy",
    "instrumentation_complete": "instrumentation_complete",
    "register_beep": "register_beep",
    "reevaluate_anomalies": "reevaluate_anomalies",
    "event": "important_event",
}

LEGACY_RETIRED_KEYS = frozenset(
    {"counters", "active_anomaly", "intensive", "force_cleanup"}
)

LEGACY_OPTION_MAP = {
    "retention_absolute_days": "retention_essential_days",
    "retention_full_days": "retention_trace_days",
    "retention_observations_days": "retention_essential_days",
    "capture_state_changed": "capture_state_changes",
    "capture_power": "capture_power_profiles",
    "max_database_mb": "maintenance_database_limit_mb",
    "confirmation_window_seconds": "localtuya_confirmation_window_seconds",
    "localtuya_confirmation_seconds": "localtuya_confirmation_window_seconds",
    "close_transmissions_seconds": "anomaly_close_commands_seconds",
    "identical_frame_window_seconds": "anomaly_repeated_command_window_seconds",
    "logical_concurrency_seconds": "correlation_window_seconds",
    "external_reaction_window_seconds": "external_observation_window_seconds",
    "external_observation_seconds": "external_observation_window_seconds",
    "oscillation_window_seconds": "anomaly_oscillation_window_seconds",
    "oscillation_min_changes": "anomaly_oscillation_min_changes",
    "multiple_full_frames_limit": "anomaly_audible_burst_count",
    "multiple_full_frames_window_seconds": "anomaly_audible_burst_seconds",
    "enabled_anomaly_types": "anomaly_enabled_types",
    "notification_minimum_severity": "notification_min_severity",
    "persistent_notifications": "notification_persistent",
    "notify_service": "notification_service",
    "default_page_size": "interface_items_per_page",
    "page_size": "interface_items_per_page",
    "visible_columns": "interface_columns",
    "live_updates": "interface_auto_refresh",
    "density": "interface_density",
    "technical_details_enabled": "interface_show_technical_codes",
    "show_technical_codes": "interface_show_technical_codes",
    "show_unchanged_attributes": "interface_show_unchanged_attributes",
    "date_format": "interface_date_format",
    "detail_presentation": "interface_detail_mode",
    "resolve_user_names": "privacy_resolve_user_names",
    "cleanup_interval_hours": "maintenance_cleanup_interval_hours",
    "export_max_events": "maintenance_export_max_rows",
    "normal_queue_max": "queue_limit",
    "rate_limit_per_minute": "rate_hard_limit_events",
}

LEGACY_ANOMALY_TYPE_MAP = {
    "ir.transmissions_too_close": "commands_too_close",
    "ir.logical_emitter_concurrency": "commands_too_close",
    "ir.identical_frame_retransmitted": "repeated_commands",
    "ir.multiple_full_frames": "commands_too_close",
    "ir.command_without_correlation": "repeated_error",
    "ir.sensor_update_possibly_audible": "commands_too_close",
    "decision.oscillation": "decision_oscillation",
    "localtuya.confirmation_failed": "localtuya_not_confirmed",
    "localtuya.divergence": "desired_state_divergence",
    "localtuya.timeout": "localtuya_not_confirmed",
    "localtuya.external_change_followed_by_supervisor": "external_change_reaction",
    "system.persistence": "repeated_error",
}


def migrate_options_v1(
    options: Mapping[str, Any],
    defaults: Mapping[str, Any],
    anomaly_types: Sequence[str],
) -> dict[str, Any]:
    """Translate the complete reference options schema without losing values."""

    source = dict(options)
    migrated = deepcopy(dict(defaults))
    for key, value in source.items():
        if key in migrated:
            migrated[key] = deepcopy(value)
    for key, value in source.items():
        canonical = LEGACY_OPTION_MAP.get(key, key)
        if canonical in migrated and canonical not in source:
            migrated[canonical] = deepcopy(value)
    if "capture_mode" not in source and "intensive_mode" in source:
        migrated["capture_mode"] = (
            "intensive" if source["intensive_mode"] else "normal"
        )
    if (
        "anomaly_duplicate_window_seconds" not in source
        and "identical_frame_window_seconds" in source
    ):
        migrated["anomaly_duplicate_window_seconds"] = source[
            "identical_frame_window_seconds"
        ]
    if "anomaly_enabled_types" not in source and "enabled_anomaly_types" in source:
        legacy_types = source.get("enabled_anomaly_types")
        if isinstance(legacy_types, (list, tuple)) and not legacy_types:
            migrated["anomaly_enabled_types"] = list(anomaly_types)
        elif isinstance(legacy_types, (list, tuple)):
            migrated["anomaly_enabled_types"] = list(
                dict.fromkeys(
                    LEGACY_ANOMALY_TYPE_MAP.get(str(item), str(item))
                    for item in legacy_types
                    if LEGACY_ANOMALY_TYPE_MAP.get(str(item), str(item))
                    in set(anomaly_types)
                )
            )
    visible = source.get("visible_categories")
    if (
        "saved_filters" not in source
        and isinstance(visible, (list, tuple))
        and visible
    ):
        migrated["saved_filters"] = [
            {
                "id": "migrado_categorias_visiveis",
                "name": "Categorias visíveis migradas",
                "filters": {"categories": [str(item) for item in visible]},
            }
        ]
        migrated["default_saved_filter_id"] = "migrado_categorias_visiveis"
    return migrated
