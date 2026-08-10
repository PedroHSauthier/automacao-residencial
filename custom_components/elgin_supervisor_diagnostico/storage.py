"""Serialized SQLite persistence for Elgin Supervisor diagnostics."""

from __future__ import annotations

import asyncio
from collections import Counter
from concurrent.futures import Future, ThreadPoolExecutor
from contextlib import suppress
from copy import deepcopy
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
import os
from pathlib import Path
import sqlite3
import threading
from typing import TYPE_CHECKING, Any, Callable, Iterable, Mapping, TypeVar

from .const import DB_FILENAME, LEGACY_FALLBACK_FILENAME, SCHEMA_VERSION
from .migrations import (
    INVALID_POWER_PROFILE_TOKENS,
    is_unprotected_routine_event,
    migrate_event_semantics_v6,
    normalize_power_level,
    normalize_power_profile,
)
from .query import (
    compile_event_predicate,
    compile_event_query,
    encode_cursor,
    fingerprint_filters,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

    from .models import (
        AnomalyRecord,
        AuditEvent,
        DiagnosticSettings,
        EvaluationRecord,
        ObservationRecord,
    )

_LOGGER = logging.getLogger(__name__)
_T = TypeVar("_T")

# DiagnosticSettings validates both logical limits to at most 100,000.  Keep
# the asyncio queues at that stable physical capacity and enforce the current
# option separately so increasing a limit does not require replacing a live
# queue (which would risk losing queued records).
_PHYSICAL_QUEUE_CAPACITY = 100_000
_FALLBACK_MAX_BYTES = 5 * 1024 * 1024
_FALLBACK_ROTATIONS = 3

JSON_COLUMNS = {
    "changed_fields_all",
    "changed_fields_relevant",
    "before_json",
    "after_json",
    "diff_json",
    "desired_json",
    "confirmed_json",
    "details_json",
    "relation_evidence",
}

EVENT_COLUMNS = (
    "event_id",
    "occurred_at",
    "occurred_at_local",
    "received_at",
    "category",
    "event_type",
    "severity",
    "outcome",
    "summary",
    "technical_message",
    "source_component",
    "source_entity_id",
    "entity_domain",
    "action_domain",
    "action_name",
    "evaluation_id",
    "correlation_id",
    "parent_correlation_id",
    "relation_kind",
    "relation_strength",
    "relation_evidence",
    "context_id",
    "parent_context_id",
    "user_id",
    "user_name",
    "actor_type",
    "actor_name",
    "origin_class",
    "origin_confidence",
    "trigger_model",
    "trigger_entity_id",
    "climate_mode",
    "treatment",
    "preset",
    "power_profile",
    "power_level",
    "agenda_state",
    "protection",
    "function",
    "expected_audibility",
    "transmission_id",
    "request_id",
    "confirmation_state",
    "is_external",
    "is_anomaly",
    "anomaly_type",
    "changed_fields_all",
    "changed_fields_relevant",
    "before_json",
    "after_json",
    "diff_json",
    "desired_json",
    "confirmed_json",
    "details_json",
    "fingerprint",
    "retention_class",
    "legacy_semantics",
)


def _json_dump(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), sort_keys=True)


def _json_load(value: str | None, default: Any) -> Any:
    if value is None or value == "":
        return default
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return default


def _as_mapping(record: Any) -> dict[str, Any]:
    if isinstance(record, Mapping):
        return dict(record)
    for name in ("as_dict", "as_public_dict"):
        method = getattr(record, name, None)
        if callable(method):
            return dict(method())
    raise TypeError(f"Registro não serializável: {type(record)!r}")


_SEMANTIC_DETAIL_KEYS = (
    "stage",
    "reason",
    "rule",
    "classification",
    "temperature",
    "target_temperature",
    "humidity",
    "action",
    "protection",
    "blocked_by",
    "state",
)


def _stable_value(value: Any) -> Any:
    """Remove identity/timing metadata from an otherwise semantic value."""

    if isinstance(value, Mapping):
        volatile = {
            "evaluation_id",
            "correlation_id",
            "context_id",
            "parent_context_id",
            "event_id",
            "transmission_id",
            "request_id",
            "occurred_at",
            "occurred_at_local",
            "received_at",
            "created_at",
            "updated_at",
            "timestamp",
            "compaction",
        }
        return {
            str(key): _stable_value(item)
            for key, item in value.items()
            if str(key) not in volatile
        }
    if isinstance(value, (list, tuple)):
        return [_stable_value(item) for item in value]
    if isinstance(value, str):
        return " ".join(value.split()).casefold()
    return value


def _semantic_details(data: Mapping[str, Any]) -> dict[str, Any]:
    details = data.get("details_json")
    if not isinstance(details, Mapping):
        return {}
    payload = details.get("payload")
    payload = payload if isinstance(payload, Mapping) else {}
    semantic: dict[str, Any] = {}
    for key in _SEMANTIC_DETAIL_KEYS:
        value = details.get(key)
        if value is None:
            value = payload.get(key)
        if value is not None:
            semantic[key] = _stable_value(value)
    return semantic


def _event_fingerprint(data: Mapping[str, Any]) -> str:
    explicit = data.get("fingerprint")
    if explicit:
        return str(explicit)
    basis = {
        "category": data.get("category"),
        "event_type": data.get("event_type"),
        "source_entity_id": data.get("source_entity_id"),
        "outcome": data.get("outcome"),
        "changed_fields_relevant": _stable_value(data.get("changed_fields_relevant")),
        "diff_json": _stable_value(data.get("diff_json")),
        "climate_mode": data.get("climate_mode"),
        "treatment": data.get("treatment"),
        "preset": data.get("preset"),
        "power_profile": data.get("power_profile"),
        "power_level": data.get("power_level"),
        "agenda_state": data.get("agenda_state"),
        "protection": data.get("protection"),
        "function": data.get("function"),
        "desired_json": _stable_value(data.get("desired_json")),
        "details": _semantic_details(data),
    }
    return hashlib.sha256(_json_dump(basis).encode()).hexdigest()[:32]


def _event_row(data: Mapping[str, Any]) -> tuple[Any, ...]:
    values: list[Any] = []
    for column in EVENT_COLUMNS:
        value = data.get(column)
        if column == "severity" and value == "info" and is_unprotected_routine_event(data):
            value = "debug"
        elif column == "power_profile":
            value = normalize_power_profile(value)
        elif column == "power_level":
            value = normalize_power_level(value)
        elif column in JSON_COLUMNS:
            value = _json_dump(value)
        elif column in {"is_external", "is_anomaly"}:
            value = int(bool(value))
        elif hasattr(value, "value"):
            value = value.value
        values.append(value)
    return tuple(values)


def _event_dict(row: sqlite3.Row, *, include_details: bool = True) -> dict[str, Any]:
    result = dict(row)
    for column in JSON_COLUMNS:
        if column in result:
            default = [] if column.startswith("changed_fields") or column == "relation_evidence" else None
            result[column] = _json_load(result[column], default)
    result["is_external"] = bool(result.get("is_external"))
    result["is_anomaly"] = bool(result.get("is_anomaly"))
    # Canonical public aliases keep the storage migration compatible with the
    # previous column names while giving the card one stable event contract.
    result.setdefault("entity_id", result.get("source_entity_id"))
    result.setdefault("domain", result.get("entity_domain"))
    result.setdefault("mode", result.get("climate_mode"))
    result.setdefault("agenda", result.get("agenda_state"))
    result.setdefault("activation_model", result.get("trigger_model"))
    result.setdefault("audibility", result.get("expected_audibility"))
    result.setdefault("changed_fields_all_json", result.get("changed_fields_all"))
    result.setdefault("changed_fields_relevant_json", result.get("changed_fields_relevant"))
    if not include_details:
        for column in ("before_json", "after_json", "diff_json", "desired_json", "confirmed_json", "details_json"):
            result.pop(column, None)
    return result


_FACET_FILTER_KEYS: dict[str, frozenset[str]] = {
    "category": frozenset({"category", "categories"}),
    "event_type": frozenset({"event_type", "event_types"}),
    "severity": frozenset({"severity", "severities"}),
    "outcome": frozenset({"outcome", "outcomes"}),
    "actor": frozenset({"actor", "actors"}),
    "user": frozenset({"user", "users", "user_id", "user_ids"}),
    "origin": frozenset({"origin", "origins"}),
    "entity_id": frozenset({"entity", "entities", "entity_id", "entity_ids"}),
    "domain": frozenset({"domain", "domains"}),
    "mode": frozenset({"mode", "modes"}),
    "treatment": frozenset({"treatment", "treatments"}),
    "preset": frozenset({"preset", "presets"}),
    "power": frozenset({"power", "powers", "power_profile", "power_profiles"}),
    "agenda": frozenset({"agenda", "agendas"}),
    "protection": frozenset({"protection", "protections"}),
    "audibility": frozenset({"audibility", "audibilities"}),
    "anomaly_type": frozenset({"anomaly_type", "anomaly_types"}),
    "function": frozenset({"function", "functions"}),
    "activation_model": frozenset({"activation_model", "activation_models"}),
    "changed_fields": frozenset(
        {"changed_field", "changed_fields", "fields_changed"}
    ),
}

_FACET_ADVANCED_FIELDS: dict[str, frozenset[str]] = {
    **{
        name: keys
        for name, keys in _FACET_FILTER_KEYS.items()
    },
    "actor": frozenset({"actor", "actor_name"}),
    "user": frozenset({"user", "user_name", "user_id"}),
    "origin": frozenset({"origin", "origin_class"}),
    "entity_id": frozenset({"entity", "entity_id"}),
    "power": frozenset({"power", "power_profile"}),
    "changed_fields": frozenset(
        {"changed_field", "changed_fields_all", "changed_fields_relevant"}
    ),
}


def _strip_advanced_facet(value: Any, facet: str) -> Any:
    if not isinstance(value, Mapping):
        return deepcopy(value)
    fields = _FACET_ADVANCED_FIELDS.get(facet, frozenset())
    if value.get("field") in fields:
        return None
    result = dict(value)
    child_key = "conditions" if "conditions" in value else "children" if "children" in value else None
    if child_key:
        children = [
            stripped
            for item in value.get(child_key, [])
            if (stripped := _strip_advanced_facet(item, facet)) is not None
        ]
        if not children:
            return None
        result[child_key] = children
    return result


def filters_without_facet(filters: Mapping[str, Any], facet: str) -> dict[str, Any]:
    """Return the disjunctive-facet scope (all filters except itself)."""

    excluded = _FACET_FILTER_KEYS.get(facet, frozenset())
    result = {
        key: deepcopy(value)
        for key, value in filters.items()
        if key not in excluded and key != "advanced"
    }
    advanced = _strip_advanced_facet(filters.get("advanced"), facet)
    if advanced is not None:
        result["advanced"] = advanced
    return result


def _selected_facet_values(filters: Mapping[str, Any], facet: str) -> set[str]:
    fields = _FACET_ADVANCED_FIELDS.get(facet, frozenset())
    values: set[str] = set()
    for key in _FACET_FILTER_KEYS.get(facet, frozenset()):
        raw = filters.get(key)
        candidates = raw if isinstance(raw, (list, tuple, set, frozenset)) else [raw]
        values.update(str(item) for item in candidates if item not in (None, ""))

    def visit(value: Any) -> None:
        if not isinstance(value, Mapping):
            return
        if value.get("field") in fields:
            raw = value.get("value")
            candidates = raw if isinstance(raw, (list, tuple, set, frozenset)) else [raw]
            values.update(str(item) for item in candidates if item not in (None, ""))
        for item in value.get("conditions", value.get("children", [])):
            visit(item)

    visit(filters.get("advanced"))
    return values


class DiagnosticStorage:
    """Own the only SQLite connection and execute every DB operation serially."""

    def __init__(self, hass: HomeAssistant, settings: DiagnosticSettings) -> None:
        self.hass = hass
        self._settings = settings
        self._writer_wakeup = asyncio.Event()
        self._writer_drained = asyncio.Event()
        self._writer_drained.set()
        self._inflight_events = 0
        self.path = Path(hass.config.path(".storage", DB_FILENAME))
        self.fallback_path = Path(
            hass.config.path(".storage", LEGACY_FALLBACK_FILENAME)
        )
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="elgin-diagnostic-db")
        self._connection: sqlite3.Connection | None = None
        self._db_lock = asyncio.Lock()
        self._normal_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(
            maxsize=_PHYSICAL_QUEUE_CAPACITY
        )
        self._critical_queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue(
            maxsize=_PHYSICAL_QUEUE_CAPACITY
        )
        self._writer_task: asyncio.Task[None] | None = None
        self._clear_state_lock = threading.Lock()
        self._clear_in_progress = False
        self._clear_protected_event_ids: set[str] = set()
        self._stopping = False
        self._healthy = False
        self._schema_version = 0
        self._dropped_events = 0
        self._fallback_events = 0
        self._fallback_replayed = 0
        self._fallback_duplicates = 0
        self._fallback_invalid_lines = 0
        self._fallback_rotations = 0
        self._fallback_discarded_files = 0
        self._fallback_write_failures = 0
        self._fallback_degraded = False
        self._written_events = 0
        self._compacted_events = 0
        self._last_failure: str | None = None
        self._last_cleanup: str | None = None
        self._last_migration: str | None = None
        self._semantic_migration: dict[str, Any] = {}
        self._opened_at: datetime | None = None
        self._last_backup: str | None = None
        self._last_write_latency_ms = 0.0

    @property
    def settings(self) -> DiagnosticSettings:
        """Return the current immutable runtime settings."""

        return self._settings

    @settings.setter
    def settings(self, value: DiagnosticSettings) -> None:
        """Apply live options and wake a writer waiting on the old interval."""

        self._settings = value
        self._writer_wakeup.set()

    @property
    def healthy(self) -> bool:
        return self._healthy

    @property
    def queue_size(self) -> int:
        return self._normal_queue.qsize() + self._critical_queue.qsize()

    def _queue_limit(self, *, critical: bool) -> int:
        name = "critical_queue_limit" if critical else "queue_limit"
        default = 2_000 if critical else 5_000
        try:
            configured = int(getattr(self.settings, name, default))
        except (TypeError, ValueError, OverflowError):
            configured = default
        return max(1, min(_PHYSICAL_QUEUE_CAPACITY, configured))

    @property
    def dropped_events(self) -> int:
        return self._dropped_events

    async def async_start(self) -> None:
        await self._run(self._open_and_migrate)
        self._stopping = False
        self._writer_task = self.hass.async_create_background_task(
            self._writer_loop(), "elgin_supervisor_diagnostico.sqlite_writer"
        )

    async def async_stop(self) -> None:
        self._stopping = True
        self._writer_wakeup.set()
        if self._writer_task:
            with suppress(asyncio.TimeoutError):
                await asyncio.wait_for(self._writer_task, timeout=10)
            if not self._writer_task.done():
                self._writer_task.cancel()
                with suppress(asyncio.CancelledError):
                    await self._writer_task
            self._writer_task = None
        await self._run(self._close)
        self._executor.shutdown(wait=False, cancel_futures=False)

    async def _run(self, func: Callable[..., _T], *args: Any) -> _T:
        async with self._db_lock:
            loop = asyncio.get_running_loop()
            return await loop.run_in_executor(self._executor, func, *args)

    def _open_and_migrate(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        existed = self.path.exists()
        connection = sqlite3.connect(self.path, timeout=30, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        version = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if version > SCHEMA_VERSION:
            connection.close()
            raise RuntimeError(
                f"Banco de diagnóstico usa schema {version}, superior ao suportado {SCHEMA_VERSION}."
            )
        if existed and version < SCHEMA_VERSION:
            backup = self.path.with_suffix(f".pre-v{SCHEMA_VERSION}.sqlite3.bak")
            if not backup.exists():
                destination = sqlite3.connect(backup)
                try:
                    # SQLite's backup API includes committed WAL pages; copying
                    # only the main file could produce an incomplete rollback.
                    connection.backup(destination)
                finally:
                    destination.close()
        self._connection = connection
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._create_or_upgrade_schema(connection)
            if version < SCHEMA_VERSION:
                migration_at = datetime.now(timezone.utc).isoformat()
                connection.execute(
                    "INSERT OR REPLACE INTO metadata(key,value) VALUES('last_migration',?)",
                    (migration_at,),
                )
            connection.execute(f"PRAGMA user_version={SCHEMA_VERSION}")
            connection.execute("COMMIT")
            check = connection.execute("PRAGMA quick_check").fetchone()[0]
            if check != "ok":
                raise RuntimeError(f"Falha de integridade SQLite: {check}")
            self._schema_version = SCHEMA_VERSION
            self._opened_at = datetime.now(timezone.utc)
            migration_row = connection.execute(
                "SELECT value FROM metadata WHERE key='last_migration'"
            ).fetchone()
            cleanup_row = connection.execute(
                "SELECT value FROM metadata WHERE key='last_cleanup'"
            ).fetchone()
            self._last_migration = str(migration_row[0]) if migration_row else None
            self._last_cleanup = str(cleanup_row[0]) if cleanup_row else None
            self._replay_fallback_files(connection)
            self._healthy = not self._fallback_degraded
        except Exception:
            with suppress(sqlite3.Error):
                connection.execute("ROLLBACK")
            self._healthy = False
            raise

    @staticmethod
    def _columns(connection: sqlite3.Connection, table: str) -> set[str]:
        return {str(row[1]) for row in connection.execute(f"PRAGMA table_info({table})")}

    def _create_or_upgrade_schema(self, connection: sqlite3.Connection) -> None:
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS events (
                event_id TEXT PRIMARY KEY,
                occurred_at TEXT NOT NULL,
                occurred_at_local TEXT,
                received_at TEXT NOT NULL,
                category TEXT NOT NULL,
                event_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                outcome TEXT,
                summary TEXT NOT NULL,
                technical_message TEXT,
                source_component TEXT,
                source_entity_id TEXT,
                entity_domain TEXT,
                action_domain TEXT,
                action_name TEXT,
                evaluation_id TEXT,
                correlation_id TEXT,
                parent_correlation_id TEXT,
                relation_kind TEXT,
                relation_strength TEXT,
                relation_evidence TEXT,
                context_id TEXT,
                parent_context_id TEXT,
                user_id TEXT,
                user_name TEXT,
                actor_type TEXT,
                actor_name TEXT,
                origin_class TEXT,
                origin_confidence TEXT,
                trigger_model TEXT,
                trigger_entity_id TEXT,
                climate_mode TEXT,
                treatment TEXT,
                preset TEXT,
                power_profile TEXT,
                power_level REAL,
                agenda_state TEXT,
                protection TEXT,
                function TEXT,
                expected_audibility TEXT,
                transmission_id TEXT,
                request_id TEXT,
                confirmation_state TEXT,
                is_external INTEGER NOT NULL DEFAULT 0,
                is_anomaly INTEGER NOT NULL DEFAULT 0,
                anomaly_type TEXT,
                changed_fields_all TEXT,
                changed_fields_relevant TEXT,
                before_json TEXT,
                after_json TEXT,
                diff_json TEXT,
                desired_json TEXT,
                confirmed_json TEXT,
                details_json TEXT,
                fingerprint TEXT,
                compacted_count INTEGER NOT NULL DEFAULT 1,
                retention_class TEXT NOT NULL DEFAULT 'full',
                legacy_semantics TEXT
            )
            """
        )
        # Upgrade the previous reference schema in place while keeping ambiguous
        # confirmed_json untouched and explicitly labelled as legacy evidence.
        existing = self._columns(connection, "events")
        definitions = {
            "entity_domain": "TEXT",
            "evaluation_id": "TEXT",
            "relation_kind": "TEXT",
            "relation_strength": "TEXT",
            "relation_evidence": "TEXT",
            "trigger_model": "TEXT",
            "preset": "TEXT",
            "power_profile": "TEXT",
            "power_level": "REAL",
            "agenda_state": "TEXT",
            "protection": "TEXT",
            "function": "TEXT",
            "request_id": "TEXT",
            "confirmation_state": "TEXT",
            "changed_fields_all": "TEXT",
            "changed_fields_relevant": "TEXT",
            "after_json": "TEXT",
            "diff_json": "TEXT",
            "fingerprint": "TEXT",
            "legacy_semantics": "TEXT",
        }
        for name, definition in definitions.items():
            if name not in existing:
                connection.execute(f"ALTER TABLE events ADD COLUMN {name} {definition}")
        if "confirmed_json" in existing and "legacy_semantics" not in existing:
            connection.execute(
                "UPDATE events SET legacy_semantics='confirmed_json_preservado_sem_reinterpretacao' "
                "WHERE confirmed_json IS NOT NULL"
            )
        schema_script = """
            CREATE TABLE IF NOT EXISTS evaluations (
                evaluation_id TEXT PRIMARY KEY,
                started_at TEXT NOT NULL,
                completed_at TEXT,
                status TEXT NOT NULL,
                summary TEXT,
                trigger_json TEXT,
                actor_json TEXT,
                inputs_json TEXT,
                prior_decision_json TEXT,
                demands_json TEXT,
                priorities_json TEXT,
                agenda_json TEXT,
                presets_json TEXT,
                powers_json TEXT,
                limits_json TEXT,
                protections_json TEXT,
                desired_json TEXT,
                action_json TEXT,
                result_json TEXT,
                reason_json TEXT,
                related_event_ids TEXT,
                correlation_id TEXT,
                context_id TEXT,
                revision INTEGER NOT NULL DEFAULT 1
            );
            CREATE TABLE IF NOT EXISTS correlations (
                relation_id TEXT PRIMARY KEY,
                correlation_id TEXT NOT NULL,
                parent_correlation_id TEXT,
                evaluation_id TEXT,
                source_event_id TEXT,
                target_event_id TEXT,
                relation_kind TEXT NOT NULL,
                relation_strength TEXT NOT NULL,
                evidence_json TEXT,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS anomalies (
                anomaly_id TEXT PRIMARY KEY,
                anomaly_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                title TEXT,
                explanation TEXT NOT NULL,
                recommendation TEXT,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                count INTEGER NOT NULL DEFAULT 1,
                status TEXT NOT NULL DEFAULT 'active',
                related_event_ids TEXT,
                details_json TEXT,
                acknowledged_at TEXT,
                acknowledged_by TEXT,
                acknowledgement_note TEXT,
                resolved_at TEXT,
                resolved_by TEXT,
                resolution_note TEXT,
                notified_at TEXT
            );
            DROP INDEX IF EXISTS idx_anomalies_active_type;
            CREATE TABLE IF NOT EXISTS observations (
                observation_id TEXT PRIMARY KEY,
                observation_type TEXT NOT NULL,
                occurred_at TEXT NOT NULL,
                created_at TEXT NOT NULL,
                user_id TEXT,
                user_name TEXT,
                note TEXT,
                expected_count INTEGER,
                metadata_json TEXT,
                correlation_id TEXT,
                related_event_ids TEXT
            );
            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_events_time ON events(occurred_at DESC, event_id DESC);
            CREATE INDEX IF NOT EXISTS idx_events_type_time ON events(event_type, occurred_at DESC);
            CREATE INDEX IF NOT EXISTS idx_events_category_time ON events(category, occurred_at DESC);
            CREATE INDEX IF NOT EXISTS idx_events_entity_time ON events(source_entity_id, occurred_at DESC);
            CREATE INDEX IF NOT EXISTS idx_events_eval_time ON events(evaluation_id, occurred_at ASC);
            CREATE INDEX IF NOT EXISTS idx_events_corr_time ON events(correlation_id, occurred_at ASC);
            CREATE INDEX IF NOT EXISTS idx_events_transmission ON events(transmission_id);
            CREATE INDEX IF NOT EXISTS idx_events_external_time ON events(is_external, occurred_at DESC);
            CREATE INDEX IF NOT EXISTS idx_events_anomaly_time ON events(is_anomaly, occurred_at DESC);
            CREATE INDEX IF NOT EXISTS idx_events_fingerprint_time ON events(fingerprint, occurred_at DESC);
            CREATE INDEX IF NOT EXISTS idx_events_severity_time ON events(severity, occurred_at DESC);
            CREATE INDEX IF NOT EXISTS idx_events_actor_time ON events(actor_type, occurred_at DESC);
            CREATE INDEX IF NOT EXISTS idx_events_user_time ON events(user_id, occurred_at DESC);
            CREATE INDEX IF NOT EXISTS idx_events_context_time ON events(context_id, occurred_at DESC);
            CREATE INDEX IF NOT EXISTS idx_events_mode_time ON events(climate_mode, occurred_at DESC);
            CREATE INDEX IF NOT EXISTS idx_events_treatment_time ON events(treatment, occurred_at DESC);
            CREATE INDEX IF NOT EXISTS idx_events_outcome_time ON events(outcome, occurred_at DESC);
            CREATE INDEX IF NOT EXISTS idx_events_origin_time ON events(origin_class, occurred_at DESC);
            CREATE INDEX IF NOT EXISTS idx_events_preset_time ON events(preset, occurred_at DESC);
            CREATE INDEX IF NOT EXISTS idx_events_power_time ON events(power_profile, occurred_at DESC);
            CREATE INDEX IF NOT EXISTS idx_eval_started ON evaluations(started_at DESC, evaluation_id DESC);
            CREATE INDEX IF NOT EXISTS idx_corr_id ON correlations(correlation_id, created_at ASC);
            CREATE INDEX IF NOT EXISTS idx_anomaly_status_time ON anomalies(status, last_seen DESC);
            CREATE INDEX IF NOT EXISTS idx_observation_time ON observations(occurred_at DESC);
            """
        # ``sqlite3.executescript`` commits an active transaction implicitly.
        # Execute this trusted, static DDL statement-by-statement so the outer
        # BEGIN/COMMIT really makes the migration atomic.
        for statement in schema_script.split(";"):
            if statement.strip():
                connection.execute(statement)
        # Older anomalies tables may lack lifecycle attribution.
        anomaly_columns = self._columns(connection, "anomalies")
        for name, definition in {
            "title": "TEXT",
            "acknowledged_by": "TEXT",
            "acknowledgement_note": "TEXT",
            "resolved_by": "TEXT",
            "resolution_note": "TEXT",
            "notified_at": "TEXT",
        }.items():
            if name not in anomaly_columns:
                connection.execute(f"ALTER TABLE anomalies ADD COLUMN {name} {definition}")
        self._semantic_migration = migrate_event_semantics_v6(connection)

    def _close(self) -> None:
        if self._connection is not None:
            with suppress(sqlite3.Error):
                self._connection.execute("PRAGMA wal_checkpoint(PASSIVE)")
            self._connection.close()
            self._connection = None
        self._healthy = False

    def enqueue(self, event: AuditEvent | Mapping[str, Any], *, critical: bool = False) -> bool:
        data = _as_mapping(event)
        data["fingerprint"] = _event_fingerprint(data)
        with self._clear_state_lock:
            if self._clear_in_progress and data.get("event_id"):
                self._clear_protected_event_ids.add(str(data["event_id"]))
        queue = self._critical_queue if critical else self._normal_queue
        try:
            if queue.qsize() >= self._queue_limit(critical=critical):
                raise asyncio.QueueFull
            queue.put_nowait(data)
            self._writer_drained.clear()
            self._writer_wakeup.set()
            return True
        except asyncio.QueueFull:
            if not critical:
                self._dropped_events += 1
                return False
            # Preserve the critical record outside SQLite without blocking HA's
            # event loop. The dedicated executor serializes this emergency write.
            try:
                future = self._executor.submit(self._append_fallback_batch, [data])
                future.add_done_callback(self._observe_fallback_future)
                return True
            except RuntimeError as err:
                self._last_failure = f"fallback: {err}"
                _LOGGER.exception("Não foi possível agendar a preservação do evento crítico")
                return False

    async def _writer_loop(self) -> None:
        while not self._stopping or self.queue_size:
            # Options are immutable objects replaced by the manager.  Reading
            # them on every pass makes card changes effective without reload.
            interval = max(
                0.01, float(getattr(self.settings, "flush_interval_seconds", 0.25))
            )
            batch_size = max(1, int(getattr(self.settings, "batch_size", 100)))
            batch: list[tuple[asyncio.Queue[dict[str, Any]], dict[str, Any]]] = []
            while len(batch) < batch_size:
                try:
                    batch.append(
                        (self._critical_queue, self._critical_queue.get_nowait())
                    )
                    continue
                except asyncio.QueueEmpty:
                    pass
                try:
                    batch.append((self._normal_queue, self._normal_queue.get_nowait()))
                except asyncio.QueueEmpty:
                    break
            if not batch:
                if self._stopping:
                    await asyncio.sleep(0)
                    continue
                # A settings replacement interrupts a wait based on the old
                # flush interval.  Enqueued events still retain normal batching.
                self._writer_wakeup.clear()
                try:
                    await asyncio.wait_for(self._writer_wakeup.wait(), timeout=interval)
                except asyncio.TimeoutError:
                    pass
                continue
            payload = [item for _queue, item in batch]
            self._inflight_events += len(batch)
            started = asyncio.get_running_loop().time()
            try:
                try:
                    written, compacted = await self._run(self._write_batch, payload)
                    self._written_events += written
                    self._compacted_events += compacted
                    self._healthy = not self._fallback_degraded
                    if not self._fallback_degraded:
                        self._last_failure = None
                except Exception as err:  # Never propagate persistence errors to Supervisor.
                    self._healthy = False
                    self._last_failure = str(err)
                    _LOGGER.exception("Falha ao persistir lote de diagnóstico")
                    try:
                        await self._run(self._append_fallback_batch, payload)
                    except Exception as fallback_error:
                        self._fallback_write_failures += 1
                        self._last_failure = f"sqlite: {err}; fallback: {fallback_error}"
                        _LOGGER.exception(
                            "Fallback crítico também falhou; writer continuará isolado"
                        )
            finally:
                self._last_write_latency_ms = round(
                    (asyncio.get_running_loop().time() - started) * 1000, 2
                )
                for queue, _item in batch:
                    with suppress(ValueError):
                        queue.task_done()
                self._inflight_events = max(
                    0, self._inflight_events - len(batch)
                )
                if self.queue_size == 0 and self._inflight_events == 0:
                    self._writer_drained.set()

    def _append_fallback_batch(self, batch: list[dict[str, Any]]) -> None:
        self.fallback_path.parent.mkdir(parents=True, exist_ok=True)
        stream = None
        try:
            for item in batch:
                encoded = f"{_json_dump(item)}\n".encode("utf-8")
                current = (
                    self.fallback_path.stat().st_size
                    if self.fallback_path.exists()
                    else 0
                )
                if current and current + len(encoded) > _FALLBACK_MAX_BYTES:
                    if stream is not None:
                        stream.flush()
                        os.fsync(stream.fileno())
                        stream.close()
                        stream = None
                    self._rotate_if_needed(self.fallback_path, len(encoded))
                if stream is None:
                    stream = self.fallback_path.open("ab")
                stream.write(encoded)
            if stream is not None:
                stream.flush()
                os.fsync(stream.fileno())
        finally:
            if stream is not None:
                stream.close()
        self._fallback_events += len(batch)
        self._fallback_degraded = True
        self._healthy = False

    def _observe_fallback_future(self, future: Future[Any]) -> None:
        """Observe emergency executor failures instead of dropping exceptions."""

        try:
            future.result()
        except Exception as err:
            self._fallback_write_failures += 1
            self._fallback_degraded = True
            self._healthy = False
            self._last_failure = f"fallback: {err}"
            _LOGGER.exception(
                "Não foi possível preservar evento crítico no fallback",
                exc_info=err,
            )

    @staticmethod
    def _rotated_path(path: Path, index: int) -> Path:
        return path.with_name(f"{path.name}.{index}")

    def _rotate_if_needed(self, path: Path, incoming_bytes: int) -> None:
        current = path.stat().st_size if path.exists() else 0
        if current == 0 or current + incoming_bytes <= _FALLBACK_MAX_BYTES:
            return
        oldest = self._rotated_path(path, _FALLBACK_ROTATIONS)
        if oldest.exists():
            oldest.unlink()
            self._fallback_discarded_files += 1
        for index in range(_FALLBACK_ROTATIONS - 1, 0, -1):
            source = self._rotated_path(path, index)
            if source.exists():
                source.replace(self._rotated_path(path, index + 1))
        if path.exists():
            path.replace(self._rotated_path(path, 1))
        self._fallback_rotations += 1

    def _fallback_files(self) -> list[Path]:
        files = [
            self._rotated_path(self.fallback_path, index)
            for index in range(_FALLBACK_ROTATIONS, 0, -1)
        ]
        files.append(self.fallback_path)
        return [path for path in files if path.is_file()]

    def _quarantine_files(self) -> list[Path]:
        base = self._fallback_quarantine_path
        files = [
            self._rotated_path(base, index)
            for index in range(_FALLBACK_ROTATIONS, 0, -1)
        ]
        files.append(base)
        return [path for path in files if path.is_file()]

    @property
    def _fallback_quarantine_path(self) -> Path:
        return self.fallback_path.with_name(f"{self.fallback_path.name}.invalid")

    def _append_quarantine(self, lines: list[str]) -> None:
        if not lines:
            return
        encoded = "".join(
            line if line.endswith("\n") else f"{line}\n" for line in lines
        ).encode("utf-8", errors="replace")
        path = self._fallback_quarantine_path
        self._rotate_if_needed(path, len(encoded))
        with path.open("ab") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())

    def _replay_fallback_files(
        self, connection: sqlite3.Connection, *, strict: bool = False
    ) -> None:
        """Import valid fallback lines idempotently, quarantining bad records."""

        placeholders = ",".join("?" for _ in EVENT_COLUMNS)
        sql = (
            f"INSERT OR IGNORE INTO events ({','.join(EVENT_COLUMNS)}) "
            f"VALUES ({placeholders})"
        )
        for path in self._fallback_files():
            valid: list[dict[str, Any]] = []
            invalid: list[str] = []
            try:
                with path.open("r", encoding="utf-8", errors="replace") as stream:
                    for raw_line in stream:
                        try:
                            value = json.loads(raw_line)
                            required = {
                                "event_id",
                                "occurred_at",
                                "received_at",
                                "category",
                                "event_type",
                                "severity",
                                "summary",
                                "retention_class",
                            }
                            if not isinstance(value, Mapping) or any(
                                value.get(name) is None or value.get(name) == ""
                                for name in required
                            ):
                                raise ValueError("registro de fallback incompleto")
                            item = dict(value)
                            item["fingerprint"] = _event_fingerprint(item)
                            valid.append(item)
                        except (json.JSONDecodeError, TypeError, ValueError):
                            invalid.append(raw_line)
                connection.execute("BEGIN IMMEDIATE")
                inserted = duplicates = 0
                try:
                    for item in valid:
                        cursor = connection.execute(sql, _event_row(item))
                        if cursor.rowcount > 0:
                            inserted += 1
                        else:
                            duplicates += 1
                    connection.execute("COMMIT")
                except Exception:
                    connection.execute("ROLLBACK")
                    raise
                if invalid:
                    self._append_quarantine(invalid)
                # Removal happens only after both the SQLite commit and any
                # required quarantine write have succeeded.
                path.unlink()
                self._fallback_replayed += inserted
                self._fallback_duplicates += duplicates
                self._fallback_invalid_lines += len(invalid)
            except Exception as err:
                self._fallback_degraded = True
                self._last_failure = f"fallback replay: {err}"
                _LOGGER.exception("Falha ao reimportar fallback %s", path.name)
                if strict:
                    raise
        self._fallback_degraded = bool(
            self._fallback_files() or self._quarantine_files()
            or (self.fallback_path.exists() and not self.fallback_path.is_file())
            or (
                self._fallback_quarantine_path.exists()
                and not self._fallback_quarantine_path.is_file()
            )
        )

    @staticmethod
    def _line_count(path: Path) -> int:
        with path.open("rb") as stream:
            return sum(1 for _line in stream)

    def _fallback_status(self) -> dict[str, Any]:
        pending = self._fallback_files()
        quarantine = self._quarantine_files()
        return {
            "pending_files": len(pending),
            "pending_bytes": sum(path.stat().st_size for path in pending),
            "pending_lines": sum(self._line_count(path) for path in pending),
            "quarantine_files": len(quarantine),
            "quarantine_bytes": sum(path.stat().st_size for path in quarantine),
            "quarantine_lines": sum(self._line_count(path) for path in quarantine),
            "max_file_bytes": _FALLBACK_MAX_BYTES,
            "rotation_count": _FALLBACK_ROTATIONS,
            "runtime_rotations": self._fallback_rotations,
            "runtime_discarded_files": self._fallback_discarded_files,
            "runtime_written": self._fallback_events,
            "runtime_replayed": self._fallback_replayed,
            "runtime_duplicates": self._fallback_duplicates,
            "runtime_invalid_lines": self._fallback_invalid_lines,
            "runtime_write_failures": self._fallback_write_failures,
            "destination_invalid": bool(
                self.fallback_path.exists() and not self.fallback_path.is_file()
            ),
            "degraded": self._fallback_degraded,
        }

    async def async_get_fallback_snapshot(
        self, limit: int = 100
    ) -> dict[str, Any]:
        """Return bounded, allowlisted fallback evidence for admin diagnostics."""

        return await self._run(self._get_fallback_snapshot, min(max(limit, 1), 500))

    def _get_fallback_snapshot(self, limit: int) -> dict[str, Any]:
        allowed = {
            "event_id",
            "occurred_at",
            "category",
            "event_type",
            "severity",
            "summary",
            "source_component",
            "source_entity_id",
            "transmission_id",
            "is_external",
            "is_anomaly",
        }
        events: list[dict[str, Any]] = []
        for path in self._fallback_files():
            with path.open("r", encoding="utf-8", errors="replace") as stream:
                for line in stream:
                    if len(events) >= limit:
                        break
                    try:
                        value = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(value, Mapping):
                        events.append(
                            {
                                key: item
                                for key, item in value.items()
                                if key in allowed
                            }
                        )
            if len(events) >= limit:
                break
        return {"status": self._fallback_status(), "events": events}

    @staticmethod
    def _is_critical(data: Mapping[str, Any]) -> bool:
        return bool(
            data.get("transmission_id")
            or data.get("is_external")
            or data.get("is_anomaly")
            or data.get("category") in {"error", "observation", "transmission", "external"}
            or data.get("severity") in {"error", "critical"}
        )

    def _write_batch(self, batch: list[dict[str, Any]]) -> tuple[int, int]:
        connection = self._require_connection()
        written = compacted = 0
        placeholders = ",".join("?" for _ in EVENT_COLUMNS)
        sql = f"INSERT OR IGNORE INTO events ({','.join(EVENT_COLUMNS)}) VALUES ({placeholders})"
        connection.execute("BEGIN IMMEDIATE")
        try:
            for data in batch:
                event_id = str(data.get("event_id") or "")
                with self._clear_state_lock:
                    protected_from_clear = (
                        self._clear_in_progress
                        and event_id in self._clear_protected_event_ids
                    )
                # A record accepted after a destructive clear starts must keep
                # its own primary key.  Compacting it into an older row would
                # make the clear delete evidence that arrived after the user's
                # confirmation even though the new event ID is protected.
                if not protected_from_clear and self._try_compact(connection, data):
                    compacted += 1
                    continue
                cursor = connection.execute(sql, _event_row(data))
                written += max(cursor.rowcount, 0)
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise
        return written, compacted

    def _try_compact(self, connection: sqlite3.Connection, data: Mapping[str, Any]) -> bool:
        if not bool(getattr(self.settings, "compaction_enabled", True)):
            return False
        if self._is_critical(data):
            return False
        event_type = str(data.get("event_type") or "")
        compactable = False
        if event_type in {"evaluation.no_change", "evaluation.triggered_without_change"}:
            compactable = bool(getattr(self.settings, "compact_no_change", True))
        elif event_type in {"evaluation.started", "evaluation.triggered"}:
            compactable = bool(getattr(self.settings, "compact_identical_evaluations", True))
        elif event_type == "decision.blocked":
            compactable = bool(getattr(self.settings, "compact_repeated_blocks", True))
        elif event_type in {"state.changed", "state.no_relevant_change"}:
            after = data.get("after_json")
            unavailable = isinstance(after, Mapping) and after.get("state") in {
                "unknown",
                "unavailable",
            }
            compactable = bool(
                getattr(
                    self.settings,
                    "compact_repeated_unavailable" if unavailable else "compact_identical_states",
                    True,
                )
            )
        if not compactable:
            return False
        seconds = int(getattr(self.settings, "compaction_window_seconds", 60))
        occurred = datetime.fromisoformat(str(data["occurred_at"]).replace("Z", "+00:00"))
        cutoff = (occurred.astimezone(timezone.utc) - timedelta(seconds=seconds)).isoformat()
        row = connection.execute(
            """
            SELECT event_id, details_json, compacted_count, occurred_at
            FROM events WHERE fingerprint=? AND occurred_at>=?
              AND transmission_id IS NULL AND is_external=0 AND is_anomaly=0
            ORDER BY occurred_at DESC, event_id DESC LIMIT 1
            """,
            (data.get("fingerprint"), cutoff),
        ).fetchone()
        if row is None:
            return False
        details = _json_load(row["details_json"], {}) or {}
        details["compaction"] = {
            "first_at": (details.get("compaction") or {}).get("first_at", row["occurred_at"]),
            "last_at": data["occurred_at"],
            "last_event_id": data["event_id"],
        }
        connection.execute(
            """
            UPDATE events SET occurred_at=?, occurred_at_local=?, received_at=?,
                compacted_count=compacted_count+1, details_json=? WHERE event_id=?
            """,
            (
                data["occurred_at"],
                data.get("occurred_at_local"),
                data.get("received_at"),
                _json_dump(details),
                row["event_id"],
            ),
        )
        return True

    def _require_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise RuntimeError("Banco de diagnóstico não está aberto")
        return self._connection

    async def async_get_event(self, event_id: str) -> dict[str, Any] | None:
        return await self._run(self._get_event, event_id)

    def _get_event(self, event_id: str) -> dict[str, Any] | None:
        row = self._require_connection().execute(
            "SELECT * FROM events WHERE event_id=?", (event_id,)
        ).fetchone()
        return _event_dict(row) if row else None

    async def async_list_events(
        self,
        filters: Mapping[str, Any] | None = None,
        *,
        cursor: str | None = None,
        limit: int = 50,
        direction: str = "older",
        include_details: bool = False,
    ) -> dict[str, Any]:
        return await self._run(
            self._list_events,
            dict(filters or {}),
            cursor,
            max(1, min(int(limit), 250)),
            direction,
            include_details,
        )

    def _list_events(
        self,
        filters: dict[str, Any],
        cursor: str | None,
        limit: int,
        direction: str,
        include_details: bool,
    ) -> dict[str, Any]:
        compiled = compile_event_query(
            filters,
            cursor=cursor,
            limit=limit,
            direction=direction,
            include_details=include_details,
        )
        if hasattr(compiled, "sql"):
            sql, params = compiled.sql, compiled.params
        else:
            sql, params = compiled[0], compiled[1]
        rows = self._require_connection().execute(sql, params).fetchall()
        has_more = len(rows) > limit
        rows = rows[1:] if direction == "newer" and has_more else rows[:limit]
        items = [_event_dict(row, include_details=include_details) for row in rows]
        fingerprint = fingerprint_filters(filters)
        next_cursor = (
            encode_cursor(
                rows[-1]["occurred_at"], rows[-1]["event_id"], "older", fingerprint
            )
            if rows
            else None
        )
        previous_cursor = (
            encode_cursor(
                rows[0]["occurred_at"], rows[0]["event_id"], "newer", fingerprint
            )
            if rows
            else None
        )
        return {
            "items": items,
            "events": items,
            "next_cursor": next_cursor if has_more or rows else None,
            "previous_cursor": previous_cursor,
            "has_more": has_more,
            "total_estimate": self._estimate_count(filters),
        }

    def _estimate_count(self, filters: Mapping[str, Any]) -> int | None:
        if filters:
            return None
        return int(self._require_connection().execute("SELECT COUNT(*) FROM events").fetchone()[0])

    async def async_upsert_evaluation(self, evaluation: EvaluationRecord | Mapping[str, Any]) -> None:
        await self._run(self._upsert_evaluation, _as_mapping(evaluation))

    def _upsert_evaluation(self, data: dict[str, Any]) -> None:
        connection = self._require_connection()
        previous = connection.execute(
            "SELECT related_event_ids FROM evaluations WHERE evaluation_id=?",
            (data["evaluation_id"],),
        ).fetchone()
        related = _json_load(previous[0], []) if previous else []
        for event_id in data.get("related_event_ids") or []:
            if event_id and event_id not in related:
                related.append(event_id)
        data["related_event_ids"] = related[-2_000:]
        json_fields = (
            "trigger_json", "actor_json", "inputs_json", "prior_decision_json",
            "demands_json", "priorities_json", "agenda_json", "presets_json",
            "powers_json", "limits_json", "protections_json", "desired_json",
            "action_json", "result_json", "reason_json", "related_event_ids",
        )
        values = {key: _json_dump(data.get(key)) for key in json_fields}
        connection.execute(
            """
            INSERT INTO evaluations (
                evaluation_id,started_at,completed_at,status,summary,trigger_json,
                actor_json,inputs_json,prior_decision_json,demands_json,priorities_json,
                agenda_json,presets_json,powers_json,limits_json,protections_json,
                desired_json,action_json,result_json,reason_json,related_event_ids,
                correlation_id,context_id,revision
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            ON CONFLICT(evaluation_id) DO UPDATE SET
                completed_at=COALESCE(excluded.completed_at,evaluations.completed_at),
                status=CASE
                    WHEN evaluations.status IN ('completed','blocked','failed','no_change')
                         AND excluded.status='started' THEN evaluations.status
                    ELSE excluded.status END,
                summary=COALESCE(excluded.summary,evaluations.summary),
                trigger_json=COALESCE(excluded.trigger_json,evaluations.trigger_json),
                actor_json=COALESCE(excluded.actor_json,evaluations.actor_json),
                inputs_json=COALESCE(excluded.inputs_json,evaluations.inputs_json),
                prior_decision_json=COALESCE(excluded.prior_decision_json,evaluations.prior_decision_json),
                demands_json=COALESCE(excluded.demands_json,evaluations.demands_json),
                priorities_json=COALESCE(excluded.priorities_json,evaluations.priorities_json),
                agenda_json=COALESCE(excluded.agenda_json,evaluations.agenda_json),
                presets_json=COALESCE(excluded.presets_json,evaluations.presets_json),
                powers_json=COALESCE(excluded.powers_json,evaluations.powers_json),
                limits_json=COALESCE(excluded.limits_json,evaluations.limits_json),
                protections_json=COALESCE(excluded.protections_json,evaluations.protections_json),
                desired_json=COALESCE(excluded.desired_json,evaluations.desired_json),
                action_json=COALESCE(excluded.action_json,evaluations.action_json),
                result_json=COALESCE(excluded.result_json,evaluations.result_json),
                reason_json=COALESCE(excluded.reason_json,evaluations.reason_json),
                related_event_ids=excluded.related_event_ids,
                correlation_id=COALESCE(excluded.correlation_id,evaluations.correlation_id),
                context_id=COALESCE(excluded.context_id,evaluations.context_id),
                revision=evaluations.revision+1
            """,
            (
                data["evaluation_id"], data["started_at"], data.get("completed_at"),
                data.get("status", "started"), data.get("summary"),
                *(values[key] for key in json_fields), data.get("correlation_id"),
                data.get("context_id"), int(data.get("revision", 1)),
            ),
        )

    async def async_get_evaluation(self, evaluation_id: str) -> dict[str, Any] | None:
        return await self._run(self._get_evaluation, evaluation_id)

    def _get_evaluation(self, evaluation_id: str) -> dict[str, Any] | None:
        row = self._require_connection().execute(
            "SELECT * FROM evaluations WHERE evaluation_id=?", (evaluation_id,)
        ).fetchone()
        if not row:
            return None
        item = dict(row)
        for key in tuple(item):
            if key.endswith("_json") or key == "related_event_ids":
                item[key] = _json_load(item[key], [] if key == "related_event_ids" else None)
        item["events"] = self._get_events_for("evaluation_id", evaluation_id)
        return item

    async def async_get_correlation(self, correlation_id: str) -> dict[str, Any]:
        return await self._run(self._get_correlation, correlation_id)

    def _get_correlation(self, correlation_id: str) -> dict[str, Any]:
        events = self._get_events_for("correlation_id", correlation_id)
        relations = [
            dict(row)
            for row in self._require_connection().execute(
                "SELECT * FROM correlations WHERE correlation_id=? ORDER BY created_at ASC",
                (correlation_id,),
            )
        ]
        for relation in relations:
            relation["evidence"] = _json_load(relation.pop("evidence_json", None), [])
        return {"correlation_id": correlation_id, "events": events, "relations": relations}

    async def async_get_latest_operational_correlation(self) -> dict[str, Any]:
        return await self._run(self._get_latest_operational_correlation)

    def _get_latest_operational_correlation(self) -> dict[str, Any]:
        """Load the newest correlation anchored by a decision/action/result."""

        connection = self._require_connection()
        operational = """
            (
                e.category IN ('decision','action','transmission','external','error')
                OR e.event_type IN (
                    'evaluation.no_change','evaluation.completed',
                    'transmission.confirmation_timeout'
                )
                OR e.event_type LIKE 'localtuya.confirmed%'
                OR e.is_external=1
            )
        """
        anchor = connection.execute(
            "SELECT e.correlation_id,MAX(e.occurred_at) AS anchor_occurred_at "
            "FROM events AS e WHERE e.correlation_id IS NOT NULL "
            "AND e.correlation_id<>'' AND "
            f"{operational} GROUP BY e.correlation_id "
            "ORDER BY anchor_occurred_at DESC,e.correlation_id DESC LIMIT 1"
        ).fetchone()
        if not anchor:
            return {
                "correlation_id": None,
                "anchor_occurred_at": None,
                "events": [],
            }
        correlation_id = str(anchor["correlation_id"])
        # Keep the most recent evidence (including the terminal result) while
        # explicitly retaining the first trigger if a very noisy correlation
        # exceeds the defensive bound.
        recent_rows = connection.execute(
            "SELECT * FROM events WHERE correlation_id=? "
            "ORDER BY occurred_at DESC,event_id DESC LIMIT 999",
            (correlation_id,),
        ).fetchall()
        first_trigger = connection.execute(
            "SELECT * FROM events WHERE correlation_id=? "
            "AND event_type IN ('evaluation.triggered','supervisor.trigger_received') "
            "ORDER BY occurred_at ASC,event_id ASC LIMIT 1",
            (correlation_id,),
        ).fetchone()
        by_id = {str(row["event_id"]): row for row in recent_rows}
        if first_trigger is not None:
            by_id[str(first_trigger["event_id"])] = first_trigger
        ordered = sorted(
            by_id.values(),
            key=lambda row: (str(row["occurred_at"]), str(row["event_id"])),
        )
        return {
            "correlation_id": correlation_id,
            "anchor_occurred_at": str(anchor["anchor_occurred_at"]),
            "events": [_event_dict(row) for row in ordered],
        }

    def _get_events_for(self, column: str, value: str) -> list[dict[str, Any]]:
        if column not in {"evaluation_id", "correlation_id"}:
            raise ValueError("Coluna de correlação inválida")
        rows = self._require_connection().execute(
            f"SELECT * FROM events WHERE {column}=? ORDER BY occurred_at ASC,event_id ASC LIMIT 1000",
            (value,),
        ).fetchall()
        return [_event_dict(row) for row in rows]

    async def async_add_relation(self, relation: Mapping[str, Any]) -> None:
        await self._run(self._add_relation, dict(relation))

    def _add_relation(self, relation: dict[str, Any]) -> None:
        self._require_connection().execute(
            """INSERT OR IGNORE INTO correlations
               (relation_id,correlation_id,parent_correlation_id,evaluation_id,
                source_event_id,target_event_id,relation_kind,relation_strength,evidence_json,created_at)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (
                relation["relation_id"], relation["correlation_id"],
                relation.get("parent_correlation_id"), relation.get("evaluation_id"),
                relation.get("source_event_id"), relation.get("target_event_id"),
                relation["relation_kind"], relation["relation_strength"],
                _json_dump(relation.get("evidence", [])), relation["created_at"],
            ),
        )

    async def async_upsert_anomaly(self, anomaly: AnomalyRecord | Mapping[str, Any]) -> dict[str, Any]:
        return await self._run(self._upsert_anomaly, _as_mapping(anomaly))

    def _upsert_anomaly(self, data: dict[str, Any]) -> dict[str, Any]:
        connection = self._require_connection()
        details = dict(data.get("details", data.get("details_json", {})) or {})
        group_key = str(details.get("group_key") or data["anomaly_type"])
        active = connection.execute(
            "SELECT * FROM anomalies WHERE anomaly_type=? "
            "AND status IN ('active','acknowledged') "
            "AND COALESCE(json_extract(details_json,'$.group_key'),anomaly_type)=? "
            "ORDER BY last_seen DESC LIMIT 1",
            (data["anomaly_type"], group_key),
        ).fetchone()
        if active:
            related = _json_load(active["related_event_ids"], [])
            related.extend(item for item in data.get("related_event_ids", []) if item not in related)
            connection.execute(
                """UPDATE anomalies SET severity=?,title=?,explanation=?,recommendation=?,
                   last_seen=?,count=count+?,related_event_ids=?,details_json=?,
                   status='active',acknowledged_at=NULL,acknowledged_by=NULL,
                   acknowledgement_note=NULL WHERE anomaly_id=?""",
                (
                    data.get("severity", active["severity"]), data.get("title"),
                    data.get("explanation", active["explanation"]),
                    data.get("recommendation") or active["recommendation"] or "",
                    data.get("last_seen"), int(data.get("count", 1)), _json_dump(related[-500:]),
                    _json_dump(details), active["anomaly_id"],
                ),
            )
            anomaly_id = active["anomaly_id"]
        else:
            anomaly_id = data["anomaly_id"]
            connection.execute(
                """INSERT INTO anomalies
                   (anomaly_id,anomaly_type,severity,title,explanation,recommendation,
                    first_seen,last_seen,count,status,related_event_ids,details_json)
                   VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    anomaly_id, data["anomaly_type"], data.get("severity", "warning"),
                    data.get("title"), data.get("explanation", ""), data.get("recommendation") or "",
                    data["first_seen"], data.get("last_seen", data["first_seen"]),
                    int(data.get("count", 1)), data.get("status", "active"),
                    _json_dump(data.get("related_event_ids", [])),
                    _json_dump(details),
                ),
            )
        return self._get_anomaly(anomaly_id) or {}

    def _get_anomaly(self, anomaly_id: str) -> dict[str, Any] | None:
        row = self._require_connection().execute(
            "SELECT * FROM anomalies WHERE anomaly_id=?", (anomaly_id,)
        ).fetchone()
        if not row:
            return None
        item = dict(row)
        item["related_event_ids"] = _json_load(item.pop("related_event_ids", None), [])
        item["details"] = _json_load(item.pop("details_json", None), {})
        return item

    async def async_get_anomaly(self, anomaly_id: str) -> dict[str, Any] | None:
        return await self._run(self._get_anomaly, anomaly_id)

    async def async_mark_anomaly_notified(
        self, anomaly_id: str, notified_at: str
    ) -> bool:
        return await self._run(
            self._mark_anomaly_notified, anomaly_id, notified_at
        )

    def _mark_anomaly_notified(self, anomaly_id: str, notified_at: str) -> bool:
        cursor = self._require_connection().execute(
            "UPDATE anomalies SET notified_at=? WHERE anomaly_id=?",
            (notified_at, anomaly_id),
        )
        return cursor.rowcount > 0

    async def async_list_anomalies(self, status: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        return await self._run(self._list_anomalies, status, min(max(limit, 1), 500))

    def _list_anomalies(self, status: str | None, limit: int) -> list[dict[str, Any]]:
        sql = "SELECT anomaly_id FROM anomalies"
        params: list[Any] = []
        if status and status != "all":
            sql += " WHERE status=?"
            params.append(status)
        sql += " ORDER BY last_seen DESC,anomaly_id DESC LIMIT ?"
        params.append(limit)
        return [self._get_anomaly(row[0]) or {} for row in self._require_connection().execute(sql, params)]

    async def async_set_anomaly_status(
        self, anomaly_id: str, status: str, actor: str | None, note: str | None
    ) -> bool:
        return await self._run(self._set_anomaly_status, anomaly_id, status, actor, note)

    def _set_anomaly_status(self, anomaly_id: str, status: str, actor: str | None, note: str | None) -> bool:
        if status not in {"acknowledged", "resolved", "active"}:
            raise ValueError("Status de anomalia inválido")
        now = datetime.now(timezone.utc).isoformat()
        if status == "acknowledged":
            cursor = self._require_connection().execute(
                """UPDATE anomalies SET status='acknowledged',acknowledged_at=?,
                   acknowledged_by=?,acknowledgement_note=? WHERE anomaly_id=?""",
                (now, actor, note, anomaly_id),
            )
        elif status == "resolved":
            cursor = self._require_connection().execute(
                """UPDATE anomalies SET status='resolved',resolved_at=?,resolved_by=?,
                   resolution_note=? WHERE anomaly_id=?""",
                (now, actor, note, anomaly_id),
            )
        else:
            cursor = self._require_connection().execute(
                "UPDATE anomalies SET status='active',resolved_at=NULL WHERE anomaly_id=?",
                (anomaly_id,),
            )
        return cursor.rowcount > 0

    async def async_add_observation(self, observation: ObservationRecord | Mapping[str, Any]) -> dict[str, Any]:
        return await self._run(self._add_observation, _as_mapping(observation))

    def _add_observation(self, data: dict[str, Any]) -> dict[str, Any]:
        self._require_connection().execute(
            """INSERT INTO observations
               (observation_id,observation_type,occurred_at,created_at,user_id,user_name,
                note,expected_count,metadata_json,correlation_id,related_event_ids)
               VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
            (
                data["observation_id"], data["observation_type"], data["occurred_at"],
                data["created_at"], data.get("user_id"), data.get("user_name"),
                data.get("note"), data.get("expected_count"),
                _json_dump(data.get("metadata", data.get("metadata_json", {}))),
                data.get("correlation_id"), _json_dump(data.get("related_event_ids", [])),
            ),
        )
        return self._get_observation(data["observation_id"]) or {}

    def _get_observation(self, observation_id: str) -> dict[str, Any] | None:
        row = self._require_connection().execute(
            "SELECT * FROM observations WHERE observation_id=?", (observation_id,)
        ).fetchone()
        if not row:
            return None
        item = dict(row)
        item["metadata"] = _json_load(item.pop("metadata_json", None), {})
        item["related_event_ids"] = _json_load(item.pop("related_event_ids", None), [])
        return item

    async def async_list_observations(self, limit: int = 200) -> list[dict[str, Any]]:
        return await self._run(self._list_observations, min(max(limit, 1), 500))

    def _list_observations(self, limit: int) -> list[dict[str, Any]]:
        rows = self._require_connection().execute(
            "SELECT observation_id FROM observations ORDER BY occurred_at DESC LIMIT ?", (limit,)
        )
        return [self._get_observation(row[0]) or {} for row in rows]

    async def async_delete_observation(self, observation_id: str) -> bool:
        return await self._run(self._delete_observation, observation_id)

    def _delete_observation(self, observation_id: str) -> bool:
        connection = self._require_connection()
        connection.execute("BEGIN IMMEDIATE")
        try:
            cursor = connection.execute(
                "DELETE FROM observations WHERE observation_id=?", (observation_id,)
            )
            if cursor.rowcount > 0:
                connection.execute(
                    "DELETE FROM events WHERE category='observation' "
                    "AND json_extract(details_json,'$.observation_id')=?",
                    (observation_id,),
                )
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise
        return cursor.rowcount > 0

    async def async_get_filter_catalog(self, filters: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return await self._run(self._get_filter_catalog, dict(filters or {}))

    def _get_filter_catalog(self, filters: dict[str, Any]) -> dict[str, Any]:
        connection = self._require_connection()
        facets: dict[str, list[dict[str, Any]]] = {}
        columns = {
            "category": "category", "event_type": "event_type", "severity": "severity",
            "outcome": "outcome", "actor": "actor_name", "user": "user_name",
            "origin": "origin_class", "entity_id": "source_entity_id", "domain": "entity_domain",
            "mode": "climate_mode", "treatment": "treatment", "preset": "preset",
            "power": "power_profile", "agenda": "agenda_state", "protection": "protection",
            "audibility": "expected_audibility", "anomaly_type": "anomaly_type", "function": "function",
            "activation_model": "trigger_model",
        }
        for name, column in columns.items():
            facet_filters = filters_without_facet(filters, name)
            where, params = compile_event_predicate(facet_filters)
            suffix = " AND" if where else " WHERE"
            power_guard = ""
            if name == "power":
                placeholders = ",".join("?" for _ in INVALID_POWER_PROFILE_TOKENS)
                power_guard = (
                    f" AND LOWER(TRIM(CAST(e.{column} AS TEXT))) NOT IN ({placeholders})"
                    f" AND CAST(e.{column} AS TEXT) GLOB '*[^0-9., -]*'"
                )
                params = [*params, *sorted(INVALID_POWER_PROFILE_TOKENS)]
            rows = connection.execute(
                f"SELECT e.{column} AS value,COUNT(*) AS count FROM events AS e{where}"
                f"{suffix} e.{column} IS NOT NULL AND e.{column}<>''{power_guard} "
                f"GROUP BY e.{column} "
                "ORDER BY count DESC,value ASC LIMIT 250",
                params,
            ).fetchall()
            options = [
                {
                    "value": row["value"],
                    "label": self._facet_label(name, str(row["value"])),
                    "count": int(row["count"]),
                }
                for row in rows
            ]
            existing_values = {str(item["value"]) for item in options}
            for selected in sorted(_selected_facet_values(filters, name)):
                if selected in existing_values:
                    continue
                if name == "power" and (
                    selected.casefold() in INVALID_POWER_PROFILE_TOKENS
                    or not any(character.isalpha() for character in selected)
                ):
                    continue
                options.append(
                    {
                        "value": selected,
                        "label": self._facet_label(name, selected),
                        "count": 0,
                    }
                )
            facets[name] = options

        severity_counts = {
            str(item["value"]): int(item["count"])
            for item in facets["severity"]
        }
        severity_order = ("debug", "info", "success", "warning", "error", "critical")
        facets["severity"] = [
            {
                "value": value,
                "label": self._facet_label("severity", value),
                "count": severity_counts.get(value, 0),
            }
            for value in severity_order
        ]

        changed_filters = filters_without_facet(filters, "changed_fields")
        changed_where, changed_params = compile_event_predicate(changed_filters)
        change_suffix = " AND" if changed_where else " WHERE"
        changed_rows = connection.execute(
            "SELECT cf.value AS value,COUNT(*) AS count FROM events AS e "
            "JOIN json_each(COALESCE(e.changed_fields_all,'[]')) AS cf"
            f"{changed_where}{change_suffix} cf.value IS NOT NULL AND cf.value<>'' "
            "GROUP BY cf.value ORDER BY count DESC,value ASC LIMIT 250",
            changed_params,
        ).fetchall()
        facets["changed_fields"] = [
            {"value": row["value"], "label": str(row["value"]), "count": int(row["count"])}
            for row in changed_rows
        ]
        changed_existing = {str(item["value"]) for item in facets["changed_fields"]}
        for selected in sorted(_selected_facet_values(filters, "changed_fields")):
            if selected not in changed_existing:
                facets["changed_fields"].append(
                    {"value": selected, "label": selected, "count": 0}
                )
        aliases = {
            "categories": "category",
            "event_types": "event_type",
            "severities": "severity",
            "outcomes": "outcome",
            "actors": "actor",
            "users": "user",
            "origins": "origin",
            "entities": "entity_id",
            "domains": "domain",
            "modes": "mode",
            "treatments": "treatment",
            "presets": "preset",
            "power_profiles": "power",
            "agendas": "agenda",
            "protections": "protection",
            "audibilities": "audibility",
            "activation_models": "activation_model",
            "functions": "function",
        }
        for plural, singular in aliases.items():
            facets[plural] = facets[singular]
        return {
            "facets": facets,
            "count_scope": "current_query_without_own_facet",
            "count_scope_label": "Registros no recorte atual, desconsiderando esta faceta",
            **{key: facets[key] for key in aliases},
        }

    @staticmethod
    def _facet_label(facet: str, value: str) -> str:
        labels = {
            "debug": "Rotina",
            "info": "Informação",
            "success": "Sucesso",
            "warning": "Atenção",
            "error": "Erro",
            "critical": "Crítico",
            "cool": "Refrigeração",
            "heat": "Aquecimento",
            "dry": "Desumidificação",
            "fan": "Ventilação",
            "fan_only": "Ventilação",
            "auto": "Automático",
            "off": "Desligado",
            "essential": "Essencial",
            "normal": "Normal",
            "intensive": "Intensivo",
            "decision": "Decisão",
            "evaluation": "Avaliação",
            "state": "Estado",
            "state_import": "Importação de estado",
            "action": "Ação",
            "transmission": "Transmissão",
            "external": "Alteração externa",
            "observation": "Observação",
            "user_observation": "Observação do usuário",
            "anomaly": "Anomalia",
            "system": "Sistema",
            "maintenance": "Manutenção",
            "audible_expected": "Audível esperado",
            "silent_expected": "Silencioso esperado",
            "no_transmission": "Sem transmissão IR",
            "no_ir_transmission": "Sem transmissão IR",
            "external_or_indeterminate": "Externa ou indeterminada",
            "confirmed_by_localtuya": "Confirmado pelo LocalTuya",
            "started": "Iniciado",
            "calculated": "Calculado",
            "unchanged": "Sem mudança",
            "requested": "Solicitado",
            "requested_by_ha": "Solicitado pelo Home Assistant",
            "accepted": "Aceito",
            "accepted_by_software": "Aceito pelo software",
            "observed": "Observado",
            "observed_by_user": "Observado pelo usuário",
            "confirmed": "Confirmado",
            "blocked": "Bloqueado",
            "suppressed": "Suprimido",
            "failed": "Falhou",
            "completed": "Concluído",
            "no_action": "Nenhuma ação",
            "unknown": "Desconhecido",
        }
        if value in labels:
            return labels[value]
        if facet in {"entity_id", "actor", "user"}:
            return value
        return value.replace("_", " ").replace(".", " · ").strip()

    async def async_get_statistics(self, filters: Mapping[str, Any] | None = None) -> dict[str, Any]:
        return await self._run(self._get_statistics, dict(filters or {}))

    def _get_statistics(self, filters: dict[str, Any]) -> dict[str, Any]:
        connection = self._require_connection()
        where, params = compile_event_predicate(filters)

        def with_extra(extra: str) -> tuple[str, list[Any]]:
            if where:
                return f"{where} AND ({extra})", list(params)
            return f" WHERE ({extra})", []

        def count(extra: str | None = None) -> int:
            clause, bound = (with_extra(extra) if extra else (where, list(params)))
            return int(
                connection.execute(
                    f"SELECT COUNT(*) FROM events AS e{clause}", bound
                ).fetchone()[0]
            )

        def distinct_count(column: str, extra: str | None = None) -> int:
            if column not in {"e.evaluation_id", "e.correlation_id"}:
                raise ValueError("Coluna agregada inválida")
            clause, bound = (with_extra(extra) if extra else (where, list(params)))
            return int(
                connection.execute(
                    f"SELECT COUNT(DISTINCT {column}) FROM events AS e{clause}",
                    bound,
                ).fetchone()[0]
            )

        def evaluation_count(predicate: str) -> int:
            event_clause, bound = with_extra(
                "e.evaluation_id=v.evaluation_id"
            )
            return int(
                connection.execute(
                    "SELECT COUNT(*) FROM evaluations AS v "
                    f"WHERE EXISTS(SELECT 1 FROM events AS e{event_clause}) "
                    f"AND ({predicate})",
                    bound,
                ).fetchone()[0]
            )

        def grouped(column: str, limit: int = 50) -> list[dict[str, Any]]:
            return [
                {
                    "key": row["value"],
                    "label": str(row["value"]).replace("_", " "),
                    "value": row["value"],
                    "count": int(row["count"]),
                }
                for row in connection.execute(
                    f"SELECT COALESCE({column},'—') AS value,COUNT(*) AS count "
                    f"FROM events AS e{where} GROUP BY {column} ORDER BY count DESC LIMIT ?",
                    (*params, limit),
                )
            ]
        events_by_hour = grouped("strftime('%Y-%m-%dT%H:00:00',e.occurred_at)", 168)
        error_where, error_params = with_extra("e.severity IN ('error','critical')")
        errors_by_type = [
            {
                "key": row["value"],
                "label": str(row["value"]).replace("_", " "),
                "count": int(row["count"]),
            }
            for row in connection.execute(
                "SELECT COALESCE(e.event_type,'—') AS value,COUNT(*) AS count "
                f"FROM events AS e{error_where} GROUP BY e.event_type "
                "ORDER BY count DESC LIMIT 50",
                error_params,
            )
        ]
        top_producers = grouped(
            "COALESCE(e.source_entity_id,e.source_component,'—')", 10
        )
        transmissions = count(
            "e.event_type IN ('transmission.requested_by_ha','transmission.eco_requested_by_ha',"
            "'transmission.display_requested_by_ha','transmission.clean_requested_by_ha')"
        )
        sensor_updates = count("e.event_type='transmission.sensor_update_requested_by_ha'")
        confirmations = count(
            "e.confirmation_state='confirmed_by_localtuya' OR "
            "e.event_type LIKE 'localtuya.confirmed%'"
        )
        by_category = grouped("e.category")
        by_type = grouped("e.event_type")
        by_mode = grouped("e.climate_mode")
        by_actor = grouped("e.actor_name")
        by_origin = grouped("e.origin_class")
        decisions_with_action = evaluation_count(
            "v.status='completed' AND "
            "COALESCE(json_extract(v.result_json,'$.action'),'') "
            "NOT IN ('','no_action','already_off')"
        )
        decisions_without_action = evaluation_count(
            "v.status='no_change' OR (v.status='completed' AND "
            "COALESCE(json_extract(v.result_json,'$.action'),'') "
            "IN ('','no_action','already_off'))"
        )
        return {
            "total_events": count(),
            "total_evaluations": distinct_count(
                "e.evaluation_id", "e.evaluation_id IS NOT NULL"
            ),
            "total_transmission_requests": transmissions,
            "expected_audible_actions": transmissions,
            "localtuya_confirmations": confirmations,
            "external_changes": count("e.is_external=1"),
            "active_anomalies": int(connection.execute(
                "SELECT COUNT(*) FROM anomalies WHERE status IN ('active','acknowledged')"
            ).fetchone()[0]),
            "transmissions": transmissions,
            "sensor_updates": sensor_updates,
            "decisions_with_action": decisions_with_action,
            "decisions_without_action": decisions_without_action,
            "blocked": count("e.outcome='blocked' OR e.event_type='decision.blocked'"),
            "anomalies": count("e.is_anomaly=1"),
            "events_by_hour": events_by_hour,
            "events_by_category": by_category,
            "events_by_type": by_type,
            "events_by_origin": by_origin,
            "events_by_actor": by_actor,
            "events_by_mode": by_mode,
            "errors_by_type": errors_by_type,
            "top_producers": top_producers,
            "by_category": by_category,
            "by_type": by_type,
            "by_mode": by_mode,
            "by_treatment": grouped("e.treatment"),
            "by_preset": grouped("e.preset"),
            "by_power": grouped("e.power_profile"),
            "by_actor": by_actor,
            "by_audibility": grouped("e.expected_audibility"),
        }

    def _next_cleanup_at(self, now: datetime | None = None) -> datetime:
        """Calculate the next maintenance instant from the current options."""

        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        else:
            current = current.astimezone(timezone.utc)
        base = self._opened_at or current
        if self._last_cleanup:
            try:
                base = datetime.fromisoformat(
                    self._last_cleanup.replace("Z", "+00:00")
                )
            except ValueError:
                _LOGGER.warning(
                    "Data de última limpeza inválida no diagnóstico: %s",
                    self._last_cleanup,
                )
        if base.tzinfo is None:
            base = base.replace(tzinfo=timezone.utc)
        else:
            base = base.astimezone(timezone.utc)
        return base + timedelta(
            hours=max(
                1,
                int(getattr(self.settings, "maintenance_cleanup_interval_hours", 6)),
            )
        )

    async def async_cleanup_if_due(
        self, now: datetime | None = None
    ) -> dict[str, Any]:
        """Run cleanup only when due under the settings effective right now."""

        current = now or datetime.now(timezone.utc)
        if current.tzinfo is None:
            current = current.replace(tzinfo=timezone.utc)
        else:
            current = current.astimezone(timezone.utc)
        return await self._run(self._cleanup_if_due, current)

    def _cleanup_if_due(self, now: datetime) -> dict[str, Any]:
        next_cleanup = self._next_cleanup_at(now)
        if now < next_cleanup:
            return {
                "skipped": True,
                "reason": "not_due",
                "last_cleanup": self._last_cleanup,
                "next_cleanup": next_cleanup.isoformat(),
            }
        result = self._cleanup(now)
        result["skipped"] = False
        result["next_cleanup"] = self._next_cleanup_at(now).isoformat()
        return result

    async def async_cleanup(self) -> dict[str, Any]:
        result = await self._run(self._cleanup)
        self._last_cleanup = result["finished_at"]
        return result

    def _cleanup(self, now: datetime | None = None) -> dict[str, Any]:
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        else:
            now = now.astimezone(timezone.utc)
        trace_cutoff = (
            now - timedelta(days=int(getattr(self.settings, "retention_trace_days", 7)))
        ).isoformat()
        error_cutoff = (
            now - timedelta(days=int(getattr(self.settings, "retention_error_days", 30)))
        ).isoformat()
        essential_cutoff = (
            now - timedelta(days=int(getattr(self.settings, "retention_essential_days", 60)))
        ).isoformat()
        cutoffs = {
            "trace": trace_cutoff,
            "full": trace_cutoff,
            "error": error_cutoff,
            "essential": essential_cutoff,
            "absolute": essential_cutoff,
        }
        connection = self._require_connection()
        deleted: dict[str, int] = {}
        connection.execute("BEGIN IMMEDIATE")
        try:
            for retention, cutoff in cutoffs.items():
                cursor = connection.execute(
                    "DELETE FROM events WHERE retention_class=? AND occurred_at<?", (retention, cutoff)
                )
                deleted[retention] = max(cursor.rowcount, 0)
            observation_cutoff = (now - timedelta(
                days=int(getattr(self.settings, "retention_essential_days", 60))
            )).isoformat()
            deleted["observations"] = max(connection.execute(
                "DELETE FROM observations WHERE occurred_at<?", (observation_cutoff,)
            ).rowcount, 0)
            deleted["resolved_anomalies"] = max(
                connection.execute(
                    "DELETE FROM anomalies WHERE status='resolved' AND last_seen<?",
                    (essential_cutoff,),
                ).rowcount,
                0,
            )
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        pressure_deleted, over_limit = self._enforce_database_limit(connection)
        deleted["database_pressure"] = pressure_deleted
        connection.execute("PRAGMA optimize")
        connection.execute(
            "INSERT OR REPLACE INTO metadata(key,value) VALUES('last_cleanup',?)",
            (now.isoformat(),),
        )
        self._last_cleanup = now.isoformat()
        return {
            "deleted": deleted,
            "cutoffs": cutoffs,
            "database_limit_exceeded": over_limit,
            "finished_at": now.isoformat(),
        }

    def _enforce_database_limit(self, connection: sqlite3.Connection) -> tuple[int, bool]:
        """Trim only low-priority trace rows when the configured cap is exceeded."""
        limit_bytes = int(
            getattr(self.settings, "maintenance_database_limit_mb", 250)
        ) * 1024 * 1024
        wal = Path(str(self.path) + "-wal")

        def current_size() -> int:
            return (self.path.stat().st_size if self.path.exists() else 0) + (
                wal.stat().st_size if wal.exists() else 0
            )

        if current_size() <= limit_bytes:
            return 0, False
        deleted = 0
        while deleted < 100_000:
            cursor = connection.execute(
                """
                DELETE FROM events WHERE event_id IN (
                    SELECT event_id FROM events
                    WHERE retention_class IN ('trace','full')
                      AND transmission_id IS NULL
                      AND is_external=0 AND is_anomaly=0
                      AND severity NOT IN ('error','critical')
                      AND category NOT IN ('transmission','external','error','observation')
                    ORDER BY occurred_at ASC,event_id ASC LIMIT 5000
                )
                """
            )
            removed = max(cursor.rowcount, 0)
            deleted += removed
            if removed == 0:
                break
            # Page count reflects reusable pages even before VACUUM.
            pages = int(connection.execute("PRAGMA page_count").fetchone()[0])
            free = int(connection.execute("PRAGMA freelist_count").fetchone()[0])
            page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
            if (pages - free) * page_size <= limit_bytes:
                break
        if deleted:
            connection.execute("VACUUM")
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        return deleted, current_size() > limit_bytes

    async def async_clear_events(
        self,
        before: str | None = None,
        filters: Mapping[str, Any] | None = None,
    ) -> int:
        # received_at is assigned before enqueue.  Draining the queues writes
        # every record already accepted; the watermark then preserves anything
        # accepted after this destructive request even if it was flushed early.
        with self._clear_state_lock:
            if self._clear_in_progress:
                raise RuntimeError("Já existe uma exclusão de logs em andamento")
            self._clear_in_progress = True
            self._clear_protected_event_ids.clear()
        watermark = datetime.now(timezone.utc).isoformat()
        try:
            self._writer_wakeup.set()
            try:
                await asyncio.wait_for(self._writer_drained.wait(), timeout=30)
            except asyncio.TimeoutError as err:
                raise RuntimeError(
                    "Fila do diagnóstico não atingiu a barreira; nenhum log foi apagado"
                ) from err
            return await self._run(
                self._clear_events, before, dict(filters or {}), watermark
            )
        finally:
            with self._clear_state_lock:
                self._clear_in_progress = False
                self._clear_protected_event_ids.clear()

    def _backup_database(self, label: str) -> Path:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
        target = self.path.with_name(f"{self.path.stem}.{label}.{timestamp}.bak.sqlite3")
        destination = sqlite3.connect(target)
        try:
            self._require_connection().backup(destination)
        finally:
            destination.close()
        self._last_backup = str(target)
        return target

    def _clear_events(
        self,
        before: str | None,
        filters: dict[str, Any],
        watermark: str | None = None,
    ) -> int:
        connection = self._require_connection()
        # The single executor places this after any emergency fallback write
        # submitted before the barrier. Import valid records so this same
        # transaction can delete them and they cannot reappear after restart.
        self._replay_fallback_files(connection, strict=True)
        with self._clear_state_lock:
            protected_event_ids = tuple(self._clear_protected_event_ids)
        connection.execute(
            "CREATE TEMP TABLE IF NOT EXISTS clear_protected_events "
            "(event_id TEXT PRIMARY KEY)"
        )
        connection.execute("DELETE FROM clear_protected_events")
        if protected_event_ids:
            connection.executemany(
                "INSERT OR IGNORE INTO clear_protected_events(event_id) VALUES(?)",
                ((event_id,) for event_id in protected_event_ids),
            )
        where, params = compile_event_predicate(filters)
        if before:
            before_clause = "e.occurred_at<?"
            where = f"{where} AND ({before_clause})" if where else f" WHERE ({before_clause})"
            params.append(before)
        if watermark:
            watermark_clause = "e.received_at<=?"
            where = (
                f"{where} AND ({watermark_clause})"
                if where
                else f" WHERE ({watermark_clause})"
            )
            params.append(watermark)
        protected_clause = (
            "NOT EXISTS (SELECT 1 FROM clear_protected_events AS protected "
            "WHERE protected.event_id=e.event_id)"
        )
        where = (
            f"{where} AND ({protected_clause})"
            if where
            else f" WHERE ({protected_clause})"
        )
        self._backup_database("pre-clear")
        connection.execute("BEGIN IMMEDIATE")
        try:
            if where:
                # DELETE does not accept an alias on every supported SQLite build;
                # select IDs with the compiled alias and delete by primary key.
                cursor = connection.execute(
                    f"DELETE FROM events WHERE event_id IN (SELECT e.event_id FROM events AS e{where})",
                    params,
                )
            else:
                cursor = connection.execute("DELETE FROM events")
            connection.execute(
                "DELETE FROM evaluations WHERE evaluation_id NOT IN "
                "(SELECT DISTINCT evaluation_id FROM events WHERE evaluation_id IS NOT NULL)"
            )
            connection.execute(
                "DELETE FROM correlations WHERE correlation_id NOT IN "
                "(SELECT DISTINCT correlation_id FROM events WHERE correlation_id IS NOT NULL)"
            )
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        return max(cursor.rowcount, 0)

    async def async_health(self) -> dict[str, Any]:
        return await self._run(self._health)

    def _health(self) -> dict[str, Any]:
        connection = self._require_connection()
        main_size = self.path.stat().st_size if self.path.exists() else 0
        wal = Path(str(self.path) + "-wal")
        wal_size = wal.stat().st_size if wal.exists() else 0
        size = main_size + wal_size
        total_events = int(connection.execute("SELECT COUNT(*) FROM events").fetchone()[0])
        since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
        events_per_day = int(
            connection.execute(
                "SELECT COUNT(*) FROM events WHERE occurred_at>=?", (since,)
            ).fetchone()[0]
        )
        producer = connection.execute(
            "SELECT COALESCE(source_entity_id,source_component,'—') AS producer, "
            "COUNT(*) AS count FROM events GROUP BY producer "
            "ORDER BY count DESC LIMIT 1"
        ).fetchone()
        compacted_total = int(
            connection.execute(
                "SELECT COALESCE(SUM(compacted_count-1),0) FROM events"
            ).fetchone()[0]
        )
        next_cleanup = self._next_cleanup_at()
        fallback = self._fallback_status()
        return {
            "healthy": self._healthy and not fallback["degraded"],
            "quick_check": connection.execute("PRAGMA quick_check").fetchone()[0],
            "schema_version": self._schema_version,
            "database_path": str(self.path),
            "path": str(self.path),
            "main_database_size_bytes": main_size,
            "database_size_bytes": size,
            "size_bytes": size,
            "wal_size_bytes": wal_size,
            "total_events": total_events,
            "events_per_day": events_per_day,
            "top_producer": str(producer["producer"]) if producer else None,
            "top_producer_count": int(producer["count"]) if producer else 0,
            "queue_size": self.queue_size,
            "normal_queue_size": self._normal_queue.qsize(),
            "critical_queue_size": self._critical_queue.qsize(),
            "normal_queue_limit": self._queue_limit(critical=False),
            "critical_queue_limit": self._queue_limit(critical=True),
            "physical_queue_capacity": _PHYSICAL_QUEUE_CAPACITY,
            "dropped_events": self._dropped_events,
            "fallback_events": self._fallback_events,
            "fallback": fallback,
            "fallback_pending_files": fallback["pending_files"],
            "fallback_pending_lines": fallback["pending_lines"],
            "fallback_quarantine_lines": fallback["quarantine_lines"],
            "fallback_replayed_events": self._fallback_replayed,
            "fallback_write_failures": self._fallback_write_failures,
            "written_events": self._written_events,
            "compacted_events": compacted_total,
            "runtime_compacted_events": self._compacted_events,
            "last_failure": self._last_failure,
            "last_cleanup": self._last_cleanup,
            "last_migration": self._last_migration,
            "semantic_migration": dict(self._semantic_migration),
            "next_cleanup": next_cleanup.isoformat(),
            "last_backup": self._last_backup,
            "last_write_latency_ms": self._last_write_latency_ms,
        }

    async def async_count_by_types(self, event_types: Iterable[str], since: str) -> Counter[str]:
        return await self._run(self._count_by_types, tuple(event_types), since)

    def _count_by_types(self, event_types: tuple[str, ...], since: str) -> Counter[str]:
        if not event_types:
            return Counter()
        placeholders = ",".join("?" for _ in event_types)
        rows = self._require_connection().execute(
            f"SELECT event_type,COUNT(*) AS count FROM events WHERE event_type IN ({placeholders}) "
            "AND occurred_at>=? GROUP BY event_type", (*event_types, since),
        )
        return Counter({row["event_type"]: int(row["count"]) for row in rows})
