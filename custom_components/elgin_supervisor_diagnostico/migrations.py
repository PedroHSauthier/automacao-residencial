"""Pure, repeatable migration rules for the production diagnostic integration."""

from __future__ import annotations

from copy import deepcopy
import json
import math
import sqlite3
from typing import Any, Mapping, Sequence


ROUTINE_EVENT_TYPES = frozenset(
    {
        "agenda.evaluated",
        "evaluation.triggered",
        "evaluation.started",
        "evaluation.no_change",
        "action.script_requested_by_ha",
    }
)

# Only state rows from these exact internal bookkeeping helpers are routine.
# Functional helpers, LocalTuya entities and Climate are deliberately absent.
ROUTINE_STATE_ENTITY_IDS = frozenset(
    {
        "input_datetime.elgin_supervisor_inicio_do_ciclo",
        "input_datetime.elgin_supervisor_ultima_atualizacao_condicoes_regionais",
        "input_datetime.elgin_supervisor_ultima_classificacao_fisica",
        "input_datetime.elgin_supervisor_ultima_mudanca_power",
        "input_datetime.elgin_supervisor_ultimo_comando",
        "input_text.elgin_supervisor_agenda_power_off_token",
        "input_text.elgin_supervisor_assinatura_localtuya_esperada",
        "input_text.elgin_supervisor_assinatura_ultimo_ir",
        "input_text.elgin_supervisor_ultima_atualizacao_condicoes_regionais",
        "input_text.elgin_supervisor_ultima_classificacao_fisica",
        "input_text.elgin_supervisor_ultima_decisao",
        "input_text.elgin_supervisor_ultimo_envio_ir",
    }
)

INVALID_POWER_PROFILE_TOKENS = frozenset(
    {"0", "1", "true", "false", "on", "off"}
)

EVENT_SEMANTICS_V6_METADATA_KEY = "event_semantics_v6"


def is_unprotected_routine_event(data: Mapping[str, Any]) -> bool:
    """Match only the exact routine rows permitted by the v6 migration."""

    event_type = str(data.get("event_type") or "")
    category = str(data.get("category") or "")
    entity_id = str(data.get("source_entity_id", data.get("entity_id", "")) or "")
    audibility = str(
        data.get("expected_audibility", data.get("audibility", "")) or ""
    )
    return bool(
        not data.get("is_external")
        and category
        not in {"transmission", "external", "error", "observation", "user_observation"}
        and audibility != "audible_expected"
        and (
            event_type in ROUTINE_EVENT_TYPES
            or (
                event_type in {"state.changed", "state.no_relevant_change"}
                and entity_id in ROUTINE_STATE_ENTITY_IDS
            )
        )
    )


def normalize_power_profile(value: Any) -> str | None:
    """Return a real named profile, never a power-state or bare level."""

    if value is None or isinstance(value, bool) or isinstance(value, (int, float)):
        return None
    candidate = str(value).strip()
    if not candidate or candidate.casefold() in INVALID_POWER_PROFILE_TOKENS:
        return None
    try:
        numeric = float(candidate.replace(",", "."))
    except ValueError:
        return candidate
    return None if math.isfinite(numeric) else candidate


def normalize_power_level(value: Any) -> int | float | None:
    """Normalize an explicitly named numeric power level."""

    if value is None or value == "" or isinstance(value, bool):
        return None
    try:
        numeric = float(str(value).replace(",", "."))
    except (TypeError, ValueError, OverflowError):
        return None
    if not math.isfinite(numeric):
        return None
    return int(numeric) if numeric.is_integer() else numeric


def _json_mapping(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if not isinstance(value, str) or not value:
        return {}
    try:
        decoded = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {}
    return dict(decoded) if isinstance(decoded, Mapping) else {}


def _power_evidence(
    details_value: Any, desired_value: Any
) -> tuple[str | None, int | float | None]:
    """Read only unequivocally named historical power fields."""

    details = _json_mapping(details_value)
    desired = _json_mapping(desired_value)
    payload = _json_mapping(details.get("payload"))
    snapshot = _json_mapping(details.get("snapshot"))
    payload_snapshot = _json_mapping(payload.get("snapshot"))
    snapshot_desired = _json_mapping(snapshot.get("desired"))
    payload_desired = _json_mapping(payload_snapshot.get("desired"))
    sources = (
        payload,
        payload_snapshot,
        payload_desired,
        snapshot,
        snapshot_desired,
        details,
        desired,
    )
    profile = next(
        (
            normalized
            for source in sources
            for key in ("power_profile", "potencia")
            if (normalized := normalize_power_profile(source.get(key))) is not None
        ),
        None,
    )
    level = next(
        (
            normalized
            for source in sources
            if (normalized := normalize_power_level(source.get("power_level")))
            is not None
        ),
        None,
    )
    return profile, level


def migrate_event_semantics_v6(connection: sqlite3.Connection) -> dict[str, Any]:
    """Reclassify exact routine rows and repair ambiguous power columns once.

    The caller may already own a transaction (the production schema upgrade
    does). Direct callers receive the same atomic BEGIN/COMMIT/ROLLBACK guard.
    """

    existing = connection.execute(
        "SELECT value FROM metadata WHERE key=?",
        (EVENT_SEMANTICS_V6_METADATA_KEY,),
    ).fetchone()
    if existing:
        try:
            result = json.loads(str(existing[0]))
        except json.JSONDecodeError:
            result = {}
        return {**result, "applied": False}

    owns_transaction = not connection.in_transaction
    if owns_transaction:
        connection.execute("BEGIN IMMEDIATE")
    try:
        event_placeholders = ",".join("?" for _ in ROUTINE_EVENT_TYPES)
        entity_placeholders = ",".join("?" for _ in ROUTINE_STATE_ENTITY_IDS)
        cursor = connection.execute(
            f"""
            UPDATE events
               SET severity='debug'
             WHERE severity='info'
               AND is_external=0
               AND category NOT IN ('transmission','external','error','observation','user_observation')
               AND COALESCE(expected_audibility,'')<>'audible_expected'
               AND (
                    event_type IN ({event_placeholders})
                    OR (
                        event_type IN ('state.changed','state.no_relevant_change')
                        AND source_entity_id IN ({entity_placeholders})
                    )
               )
            """,
            (*sorted(ROUTINE_EVENT_TYPES), *sorted(ROUTINE_STATE_ENTITY_IDS)),
        )
        severity_rows = max(0, int(cursor.rowcount))

        power_profiles_cleared = 0
        power_profiles_backfilled = 0
        power_levels_backfilled = 0
        rows = connection.execute(
            "SELECT event_id,power_profile,power_level,details_json,desired_json FROM events "
            "WHERE power_profile IS NOT NULL OR power_level IS NOT NULL "
            "OR details_json LIKE '%\"power_profile\"%' "
            "OR details_json LIKE '%\"power_level\"%' "
            "OR details_json LIKE '%\"potencia\"%' "
            "OR desired_json LIKE '%\"power_profile\"%' "
            "OR desired_json LIKE '%\"power_level\"%' "
            "OR desired_json LIKE '%\"potencia\"%'"
        ).fetchall()
        for row in rows:
            current_profile = row[1]
            normalized_current = normalize_power_profile(current_profile)
            evidence_profile, evidence_level = _power_evidence(row[3], row[4])
            next_profile = normalized_current or evidence_profile
            current_level = normalize_power_level(row[2])
            next_level = current_level if current_level is not None else evidence_level
            if current_profile is not None and normalized_current is None:
                power_profiles_cleared += 1
            if normalized_current is None and evidence_profile is not None:
                power_profiles_backfilled += 1
            if current_level is None and evidence_level is not None:
                power_levels_backfilled += 1
            if next_profile != current_profile or next_level != row[2]:
                connection.execute(
                    "UPDATE events SET power_profile=?,power_level=? WHERE event_id=?",
                    (next_profile, next_level, row[0]),
                )

        result = {
            "applied": True,
            "severity_rows_reclassified": severity_rows,
            "power_profiles_cleared": power_profiles_cleared,
            "power_profiles_backfilled": power_profiles_backfilled,
            "power_levels_backfilled": power_levels_backfilled,
        }
        connection.execute(
            "INSERT INTO metadata(key,value) VALUES(?,?)",
            (
                EVENT_SEMANTICS_V6_METADATA_KEY,
                json.dumps(result, ensure_ascii=False, sort_keys=True),
            ),
        )
        if owns_transaction:
            connection.execute("COMMIT")
        return result
    except Exception:
        if owns_transaction:
            connection.execute("ROLLBACK")
        raise


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
