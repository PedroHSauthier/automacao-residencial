"""Dedicated asynchronous SQLite persistence for Elgin Supervisor diagnostics."""

from __future__ import annotations

import asyncio
import base64
from collections import Counter
from collections.abc import Iterable
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
import json
import logging
from pathlib import Path
import sqlite3
import time
from typing import Any

from homeassistant.core import HomeAssistant, callback

from .const import (
    BATCH_SIZE,
    DB_FILENAME,
    FLUSH_INTERVAL_SECONDS,
    MAX_PAGE_SIZE,
    NORMAL_QUEUE_MAX,
    SCHEMA_VERSION,
)
from .models import AnomalyRecord, AuditEvent, DiagnosticSettings, RetentionClass

_LOGGER = logging.getLogger(__name__)

EVENT_COLUMNS = tuple(AuditEvent.__dataclass_fields__)
JSON_COLUMNS = {"details_json", "before_json", "desired_json", "confirmed_json"}
BOOL_COLUMNS = {"is_external", "is_anomaly"}


def _encode_cursor(occurred_at: str, event_id: str) -> str:
    payload = json.dumps([occurred_at, event_id], separators=(",", ":")).encode()
    return base64.urlsafe_b64encode(payload).decode().rstrip("=")


def _decode_cursor(cursor: str) -> tuple[str, str]:
    padding = "=" * (-len(cursor) % 4)
    value = json.loads(base64.urlsafe_b64decode(cursor + padding))
    if not isinstance(value, list) or len(value) != 2:
        raise ValueError("Cursor inválido.")
    return str(value[0]), str(value[1])


def _event_to_row(event: AuditEvent) -> tuple[Any, ...]:
    data = asdict(event)
    result: list[Any] = []
    for column in EVENT_COLUMNS:
        value = data[column]
        if column in JSON_COLUMNS:
            value = json.dumps(value, ensure_ascii=False, separators=(",", ":")) if value is not None else None
        elif column in BOOL_COLUMNS:
            value = int(bool(value))
        result.append(value)
    return tuple(result)


def _row_to_event(row: sqlite3.Row) -> AuditEvent:
    values = dict(row)
    for column in JSON_COLUMNS:
        raw = values.get(column)
        if raw:
            try:
                values[column] = json.loads(raw)
            except json.JSONDecodeError:
                values[column] = {"invalid_json": True, "raw": raw[:1000]}
        else:
            values[column] = None
    for column in BOOL_COLUMNS:
        values[column] = bool(values.get(column))
    return AuditEvent.from_mapping(values)


class DiagnosticStorage:
    """SQLite writer with a non-blocking normal queue and reserved critical queue."""

    def __init__(self, hass: HomeAssistant, settings: DiagnosticSettings) -> None:
        self.hass = hass
        self.settings = settings
        self.path = Path(hass.config.path(".storage", DB_FILENAME))
        self.fallback_path = Path(hass.config.path(".storage", "elgin_supervisor_diagnostico_critical_fallback.ndjson"))
        self._connection: sqlite3.Connection | None = None
        self._normal_queue: asyncio.Queue[AuditEvent] = asyncio.Queue(maxsize=NORMAL_QUEUE_MAX)
        self._critical_queue: asyncio.Queue[AuditEvent] = asyncio.Queue()
        self._writer_task: asyncio.Task[None] | None = None
        self._stop_event = asyncio.Event()
        self._ready = False
        self._writer_state = "stopped"
        self._last_failure: str | None = None
        self._last_cleanup: str | None = None
        self._dropped_events = 0
        self._written_events = 0
        self._last_write_latency_ms = 0.0
        self._max_write_latency_ms = 0.0
        self._overflow_report_pending = False
        self._schema_version = 0
        self._critical_fallback_events = 0

    @property
    def healthy(self) -> bool:
        return self._ready and self._last_failure is None and self._writer_state in {"idle", "writing"}

    @property
    def queue_size(self) -> int:
        return self._normal_queue.qsize() + self._critical_queue.qsize()

    @property
    def dropped_events(self) -> int:
        return self._dropped_events

    @property
    def critical_fallback_events(self) -> int:
        return self._critical_fallback_events

    async def async_start(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        try:
            await asyncio.to_thread(self._open_and_migrate)
        except Exception as err:  # noqa: BLE001
            self._last_failure = f"Falha ao abrir o banco: {err}"
            self._writer_state = "failed"
            raise
        self._stop_event.clear()
        self._ready = True
        self._writer_state = "idle"
        self._writer_task = self.hass.async_create_background_task(
            self._writer_loop(), f"{__package__}.sqlite_writer"
        )

    async def async_stop(self) -> None:
        self._stop_event.set()
        if self._writer_task:
            await self._writer_task
            self._writer_task = None
        await asyncio.to_thread(self._close)
        self._ready = False
        self._writer_state = "stopped"

    def _open_and_migrate(self) -> None:
        connection = sqlite3.connect(
            self.path,
            timeout=30,
            isolation_level=None,
            check_same_thread=False,
        )
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        connection.execute("PRAGMA foreign_keys=ON")
        connection.execute("PRAGMA busy_timeout=30000")
        connection.execute("PRAGMA temp_store=MEMORY")
        self._connection = connection
        current = int(connection.execute("PRAGMA user_version").fetchone()[0])
        if current > SCHEMA_VERSION:
            raise RuntimeError(
                f"Schema {current} é mais novo que o suportado ({SCHEMA_VERSION})."
            )
        if current < 1:
            self._migration_1(connection)
            connection.execute("PRAGMA user_version=1")
            current = 1
        self._schema_version = current

    @staticmethod
    def _migration_1(connection: sqlite3.Connection) -> None:
        event_columns = """
            event_id TEXT PRIMARY KEY,
            occurred_at TEXT NOT NULL,
            occurred_at_local TEXT NOT NULL,
            received_at TEXT NOT NULL,
            category TEXT NOT NULL,
            event_type TEXT NOT NULL,
            severity TEXT NOT NULL,
            retention_class TEXT NOT NULL,
            summary TEXT NOT NULL,
            technical_message TEXT,
            outcome TEXT NOT NULL,
            source_component TEXT,
            source_entity_id TEXT,
            source_automation_id TEXT,
            source_script_id TEXT,
            action_domain TEXT,
            action_name TEXT,
            correlation_id TEXT,
            parent_correlation_id TEXT,
            context_id TEXT,
            parent_context_id TEXT,
            user_id TEXT,
            user_name TEXT,
            actor_type TEXT,
            actor_name TEXT,
            origin_class TEXT,
            origin_confidence TEXT,
            trigger_platform TEXT,
            trigger_entity_id TEXT,
            from_state TEXT,
            to_state TEXT,
            climate_mode TEXT,
            treatment TEXT,
            expected_audibility TEXT,
            observed_audibility TEXT,
            expected_beep_count INTEGER,
            transmission_id TEXT,
            frame_kind TEXT,
            frame_hash TEXT,
            is_external INTEGER NOT NULL DEFAULT 0,
            is_anomaly INTEGER NOT NULL DEFAULT 0,
            anomaly_type TEXT,
            compacted_count INTEGER NOT NULL DEFAULT 1,
            details_json TEXT,
            before_json TEXT,
            desired_json TEXT,
            confirmed_json TEXT
        """
        connection.executescript(
            f"""
            BEGIN IMMEDIATE;
            CREATE TABLE IF NOT EXISTS events ({event_columns});
            CREATE INDEX IF NOT EXISTS idx_events_cursor ON events(occurred_at DESC, event_id DESC);
            CREATE INDEX IF NOT EXISTS idx_events_type ON events(event_type, occurred_at DESC);
            CREATE INDEX IF NOT EXISTS idx_events_category ON events(category, occurred_at DESC);
            CREATE INDEX IF NOT EXISTS idx_events_correlation ON events(correlation_id, occurred_at ASC);
            CREATE INDEX IF NOT EXISTS idx_events_transmission ON events(transmission_id, occurred_at ASC);
            CREATE INDEX IF NOT EXISTS idx_events_frame_hash ON events(frame_hash, occurred_at DESC);
            CREATE INDEX IF NOT EXISTS idx_events_retention ON events(retention_class, occurred_at ASC);
            CREATE INDEX IF NOT EXISTS idx_events_anomaly ON events(is_anomaly, occurred_at DESC);

            CREATE TABLE IF NOT EXISTS anomalies (
                anomaly_id TEXT PRIMARY KEY,
                anomaly_type TEXT NOT NULL,
                severity TEXT NOT NULL,
                first_seen TEXT NOT NULL,
                last_seen TEXT NOT NULL,
                count INTEGER NOT NULL,
                status TEXT NOT NULL,
                related_event_ids TEXT NOT NULL,
                explanation TEXT NOT NULL,
                recommendation TEXT NOT NULL,
                acknowledged_at TEXT,
                resolved_at TEXT,
                notified_at TEXT,
                details_json TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_anomalies_status ON anomalies(status, severity, last_seen DESC);
            CREATE UNIQUE INDEX IF NOT EXISTS idx_anomalies_active_type
                ON anomalies(anomaly_type) WHERE status='active';

            CREATE TABLE IF NOT EXISTS metadata (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
            COMMIT;
            """
        )

    def _close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    @callback
    def enqueue(self, event: AuditEvent, *, critical: bool = False) -> bool:
        """Enqueue without waiting; critical events use a reserved unbounded queue.

        Critical records are never silently discarded. If SQLite is unavailable, they
        are appended to a bounded-line NDJSON emergency journal outside the event loop.
        """
        normalized = event.normalized()
        if not self._ready:
            if critical:
                self._last_failure = "Evento crítico recebido com persistência indisponível."
                self.hass.async_create_background_task(
                    asyncio.to_thread(self._append_critical_fallback, [normalized]),
                    f"{__package__}.critical_fallback",
                )
            else:
                self._dropped_events += 1
            return False
        if critical:
            self._critical_queue.put_nowait(normalized)
            return True
        try:
            self._normal_queue.put_nowait(normalized)
            return True
        except asyncio.QueueFull:
            self._dropped_events += 1
            self._overflow_report_pending = True
            return False

    @callback
    def consume_overflow_report(self) -> bool:
        """Return and clear the queue-overflow notification latch."""
        pending = self._overflow_report_pending
        self._overflow_report_pending = False
        return pending

    def _append_critical_fallback(self, events: list[AuditEvent]) -> None:
        """Append critical events to an emergency NDJSON journal."""
        self.fallback_path.parent.mkdir(parents=True, exist_ok=True)
        with self.fallback_path.open("a", encoding="utf-8") as handle:
            for event in events:
                payload = event.as_public_dict(include_details=True)
                handle.write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")
                self._critical_fallback_events += 1

    async def _writer_loop(self) -> None:
        while not self._stop_event.is_set() or self.queue_size:
            batch: list[AuditEvent] = []
            deadline = asyncio.get_running_loop().time() + FLUSH_INTERVAL_SECONDS
            while len(batch) < BATCH_SIZE:
                event: AuditEvent | None = None
                try:
                    event = self._critical_queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass
                if event is None:
                    timeout = max(0.0, deadline - asyncio.get_running_loop().time())
                    if timeout == 0 and batch:
                        break
                    try:
                        event = await asyncio.wait_for(self._normal_queue.get(), timeout=timeout)
                    except TimeoutError:
                        break
                if event is not None:
                    batch.append(event)
                if asyncio.get_running_loop().time() >= deadline:
                    break

            if not batch:
                if self._stop_event.is_set():
                    break
                continue

            self._writer_state = "writing"
            started = time.perf_counter()
            try:
                await asyncio.to_thread(self._write_batch, batch)
                latency = (time.perf_counter() - started) * 1000
                self._last_write_latency_ms = round(latency, 2)
                self._max_write_latency_ms = max(self._max_write_latency_ms, latency)
                self._written_events += len(batch)
                self._last_failure = None
            except Exception as err:  # noqa: BLE001
                self._last_failure = f"Falha de persistência: {err}"
                _LOGGER.exception("Falha ao gravar lote de auditoria")
                critical_events: list[AuditEvent] = []
                for event in batch:
                    if event.severity in {"error", "critical"} or event.is_anomaly or event.transmission_id:
                        critical_events.append(event)
                    else:
                        self._dropped_events += 1
                if self._stop_event.is_set():
                    if critical_events:
                        await asyncio.to_thread(self._append_critical_fallback, critical_events)
                else:
                    for event in critical_events:
                        self._critical_queue.put_nowait(event)
                    await asyncio.sleep(1)
            finally:
                self._writer_state = "idle" if self._last_failure is None else "degraded"

    def _write_batch(self, events: list[AuditEvent]) -> None:
        connection = self._require_connection()
        columns = ",".join(EVENT_COLUMNS)
        placeholders = ",".join("?" for _ in EVENT_COLUMNS)
        insert_sql = f"INSERT INTO events ({columns}) VALUES ({placeholders})"
        connection.execute("BEGIN IMMEDIATE")
        try:
            for event in events:
                if self.settings.compaction_enabled and self._can_compact(event):
                    if self._try_compact(connection, event):
                        continue
                connection.execute(insert_sql, _event_to_row(event))
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise

    @staticmethod
    def _can_compact(event: AuditEvent) -> bool:
        return (
            event.event_type in {"evaluation.no_change", "evaluation.completed"}
            and not event.is_anomaly
            and event.severity not in {"error", "critical"}
            and not event.transmission_id
            and not event.is_external
        )

    @staticmethod
    def _try_compact(connection: sqlite3.Connection, event: AuditEvent) -> bool:
        cutoff = (
            datetime.fromisoformat(event.occurred_at).astimezone(timezone.utc)
            - timedelta(minutes=15)
        ).isoformat()
        row = connection.execute(
            """
            SELECT event_id, occurred_at, details_json, compacted_count
            FROM events
            WHERE event_type=? AND summary=?
              AND COALESCE(source_entity_id,'')=COALESCE(?, '')
              AND occurred_at>=?
              AND transmission_id IS NULL AND is_external=0 AND is_anomaly=0
            ORDER BY occurred_at DESC, event_id DESC LIMIT 1
            """,
            (event.event_type, event.summary, event.source_entity_id, cutoff),
        ).fetchone()
        if row is None:
            return False
        details: dict[str, Any]
        try:
            details = json.loads(row["details_json"] or "{}")
        except json.JSONDecodeError:
            details = {}
        first = details.get("compaction_first", row["occurred_at"])
        correlations = list(details.get("correlation_ids", []))
        if event.correlation_id and event.correlation_id not in correlations:
            correlations.append(event.correlation_id)
        triggers = list(details.get("trigger_entities", []))
        if event.trigger_entity_id and event.trigger_entity_id not in triggers:
            triggers.append(event.trigger_entity_id)
        details.update(
            {
                "compaction_first": first,
                "compaction_last": event.occurred_at,
                "correlation_ids": correlations[-100:],
                "trigger_entities": triggers[-100:],
            }
        )
        connection.execute(
            """
            UPDATE events
            SET occurred_at=?, occurred_at_local=?, received_at=?, compacted_count=compacted_count+1,
                details_json=?, correlation_id=?
            WHERE event_id=?
            """,
            (
                event.occurred_at,
                event.occurred_at_local,
                event.received_at,
                json.dumps(details, ensure_ascii=False, separators=(",", ":")),
                event.correlation_id,
                row["event_id"],
            ),
        )
        return True

    def _require_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise RuntimeError("Banco de diagnóstico não está aberto.")
        return self._connection

    async def async_update_event_details(self, event_id: str, details: dict[str, Any]) -> bool:
        return await asyncio.to_thread(self._update_event_details, event_id, details)

    def _update_event_details(self, event_id: str, details: dict[str, Any]) -> bool:
        cursor = self._require_connection().execute(
            "UPDATE events SET details_json=? WHERE event_id=?",
            (json.dumps(details, ensure_ascii=False, separators=(",", ":")), event_id),
        )
        return cursor.rowcount > 0

    async def async_get_event(self, event_id: str) -> dict[str, Any] | None:
        return await asyncio.to_thread(self._get_event, event_id)

    def _get_event(self, event_id: str) -> dict[str, Any] | None:
        row = self._require_connection().execute(
            "SELECT * FROM events WHERE event_id=?", (event_id,)
        ).fetchone()
        return _row_to_event(row).as_public_dict() if row else None

    async def async_get_correlation(self, correlation_id: str, limit: int = 500) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._get_correlation, correlation_id, min(limit, 1000))

    def _get_correlation(self, correlation_id: str, limit: int) -> list[dict[str, Any]]:
        rows = self._require_connection().execute(
            """
            SELECT * FROM events WHERE correlation_id=? OR parent_correlation_id=?
            ORDER BY occurred_at ASC, event_id ASC LIMIT ?
            """,
            (correlation_id, correlation_id, limit),
        ).fetchall()
        return [_row_to_event(row).as_public_dict() for row in rows]

    async def async_list_events(
        self,
        filters: dict[str, Any] | None = None,
        *,
        cursor: str | None = None,
        limit: int = 50,
        include_details: bool = False,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            self._list_events,
            filters or {},
            cursor,
            max(1, min(int(limit), MAX_PAGE_SIZE)),
            include_details,
        )

    def _list_events(
        self,
        filters: dict[str, Any],
        cursor: str | None,
        limit: int,
        include_details: bool,
    ) -> dict[str, Any]:
        where: list[str] = []
        params: list[Any] = []
        equality_fields = {
            "category": "category",
            "event_type": "event_type",
            "severity": "severity",
            "outcome": "outcome",
            "origin": "origin_class",
            "actor": "actor_name",
            "user": "user_name",
            "climate_mode": "climate_mode",
            "treatment": "treatment",
            "correlation_id": "correlation_id",
            "transmission_id": "transmission_id",
            "frame_hash": "frame_hash",
            "audibility": "expected_audibility",
            "retention_class": "retention_class",
        }
        for filter_name, column in equality_fields.items():
            value = filters.get(filter_name)
            if value not in (None, "", []):
                if isinstance(value, list):
                    placeholders = ",".join("?" for _ in value)
                    where.append(f"{column} IN ({placeholders})")
                    params.extend(value)
                else:
                    where.append(f"{column}=?")
                    params.append(value)
        for filter_name, column in (("external", "is_external"), ("anomaly", "is_anomaly")):
            if filter_name in filters and filters[filter_name] is not None:
                where.append(f"{column}=?")
                params.append(int(bool(filters[filter_name])))
        if start := filters.get("start"):
            where.append("occurred_at>=?")
            params.append(str(start))
        if end := filters.get("end"):
            where.append("occurred_at<=?")
            params.append(str(end))
        if text := filters.get("text"):
            where.append(
                "(summary LIKE ? ESCAPE '\\' OR technical_message LIKE ? ESCAPE '\\' OR actor_name LIKE ? ESCAPE '\\')"
            )
            pattern = "%" + str(text).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            params.extend((pattern, pattern, pattern))
        if cursor:
            cursor_time, cursor_id = _decode_cursor(cursor)
            where.append("(occurred_at < ? OR (occurred_at = ? AND event_id < ?))")
            params.extend((cursor_time, cursor_time, cursor_id))
        sql = "SELECT * FROM events"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY occurred_at DESC, event_id DESC LIMIT ?"
        params.append(limit + 1)
        rows = self._require_connection().execute(sql, params).fetchall()
        has_more = len(rows) > limit
        rows = rows[:limit]
        events = [_row_to_event(row).as_public_dict(include_details=include_details) for row in rows]
        next_cursor = (
            _encode_cursor(rows[-1]["occurred_at"], rows[-1]["event_id"])
            if has_more and rows
            else None
        )
        return {"events": events, "next_cursor": next_cursor, "has_more": has_more}

    async def async_upsert_anomaly(self, anomaly: AnomalyRecord) -> AnomalyRecord:
        return await asyncio.to_thread(self._upsert_anomaly, anomaly)

    def _upsert_anomaly(self, anomaly: AnomalyRecord) -> AnomalyRecord:
        connection = self._require_connection()
        active = connection.execute(
            "SELECT * FROM anomalies WHERE anomaly_type=? AND status='active' LIMIT 1",
            (anomaly.anomaly_type,),
        ).fetchone()
        if active:
            related = json.loads(active["related_event_ids"] or "[]")
            related.extend(item for item in anomaly.related_event_ids if item not in related)
            count = int(active["count"]) + anomaly.count
            connection.execute(
                """
                UPDATE anomalies SET severity=?, last_seen=?, count=?, related_event_ids=?,
                    explanation=?, recommendation=?, details_json=? WHERE anomaly_id=?
                """,
                (
                    anomaly.severity,
                    anomaly.last_seen,
                    count,
                    json.dumps(related[-250:], separators=(",", ":")),
                    anomaly.explanation,
                    anomaly.recommendation,
                    json.dumps(anomaly.details, ensure_ascii=False, separators=(",", ":")),
                    active["anomaly_id"],
                ),
            )
            anomaly.anomaly_id = active["anomaly_id"]
            anomaly.first_seen = active["first_seen"]
            anomaly.count = count
            anomaly.related_event_ids = related[-250:]
        else:
            connection.execute(
                """
                INSERT INTO anomalies (
                    anomaly_id, anomaly_type, severity, first_seen, last_seen, count, status,
                    related_event_ids, explanation, recommendation, acknowledged_at,
                    resolved_at, notified_at, details_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                """,
                (
                    anomaly.anomaly_id,
                    anomaly.anomaly_type,
                    anomaly.severity,
                    anomaly.first_seen,
                    anomaly.last_seen,
                    anomaly.count,
                    anomaly.status,
                    json.dumps(anomaly.related_event_ids, separators=(",", ":")),
                    anomaly.explanation,
                    anomaly.recommendation,
                    anomaly.acknowledged_at,
                    anomaly.resolved_at,
                    anomaly.notified_at,
                    json.dumps(anomaly.details, ensure_ascii=False, separators=(",", ":")),
                ),
            )
        return anomaly

    async def async_list_anomalies(self, status: str | None = None, limit: int = 200) -> list[dict[str, Any]]:
        return await asyncio.to_thread(self._list_anomalies, status, min(limit, 500))

    def _list_anomalies(self, status: str | None, limit: int) -> list[dict[str, Any]]:
        sql = "SELECT * FROM anomalies"
        params: list[Any] = []
        if status:
            sql += " WHERE status=?"
            params.append(status)
        sql += " ORDER BY last_seen DESC, anomaly_id DESC LIMIT ?"
        params.append(limit)
        rows = self._require_connection().execute(sql, params).fetchall()
        result: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            item["related_event_ids"] = json.loads(item.pop("related_event_ids") or "[]")
            item["details"] = json.loads(item.pop("details_json") or "{}")
            result.append(item)
        return result

    async def async_acknowledge_anomaly(self, anomaly_id: str) -> bool:
        return await asyncio.to_thread(self._acknowledge_anomaly, anomaly_id)

    def _acknowledge_anomaly(self, anomaly_id: str) -> bool:
        now = datetime.now(timezone.utc).isoformat()
        cursor = self._require_connection().execute(
            "UPDATE anomalies SET acknowledged_at=? WHERE anomaly_id=?",
            (now, anomaly_id),
        )
        return cursor.rowcount > 0

    async def async_cleanup(self) -> dict[str, Any]:
        result = await asyncio.to_thread(self._cleanup)
        self._last_cleanup = result["finished_at"]
        return result

    def _cleanup(self) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        cutoffs = {
            RetentionClass.ABSOLUTE: (now - timedelta(days=self.settings.retention_absolute_days)).isoformat(),
            RetentionClass.ERROR: (now - timedelta(days=self.settings.retention_error_days)).isoformat(),
            RetentionClass.FULL: (now - timedelta(days=self.settings.retention_full_days)).isoformat(),
        }
        connection = self._require_connection()
        deleted: dict[str, int] = {}
        connection.execute("BEGIN IMMEDIATE")
        try:
            for retention, cutoff in cutoffs.items():
                cursor = connection.execute(
                    "DELETE FROM events WHERE retention_class=? AND occurred_at<?",
                    (retention, cutoff),
                )
                deleted[str(retention)] = cursor.rowcount
            connection.execute(
                "DELETE FROM anomalies WHERE status='resolved' AND resolved_at IS NOT NULL AND resolved_at<?",
                (cutoffs[RetentionClass.ABSOLUTE],),
            )
            connection.execute("COMMIT")
        except Exception:
            connection.execute("ROLLBACK")
            raise
        connection.execute("PRAGMA wal_checkpoint(PASSIVE)")
        pressure_deleted = self._enforce_size_limit(connection)
        if pressure_deleted:
            connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            connection.execute("VACUUM")
        connection.execute("PRAGMA optimize")
        return {
            "deleted": deleted,
            "pressure_deleted": pressure_deleted,
            "finished_at": now.isoformat(),
            "cutoffs": {str(key): value for key, value in cutoffs.items()},
            "max_database_mb": self.settings.max_database_mb,
        }

    def _enforce_size_limit(self, connection: sqlite3.Connection) -> dict[str, int]:
        """Delete oldest lower-value records if the configured database cap is exceeded.

        SQLite normally keeps deleted pages in its freelist until ``VACUUM``.  Using
        only the physical file size inside the deletion loop would therefore keep
        deleting even after enough logical space had been reclaimed.  The pressure
        calculation below uses allocated pages minus freelist pages, plus the WAL,
        so the loop stops as soon as the live payload fits under the configured cap.
        """
        limit_bytes = int(self.settings.max_database_mb) * 1024 * 1024
        wal_path = Path(str(self.path) + "-wal")

        def logical_size() -> int:
            page_size = int(connection.execute("PRAGMA page_size").fetchone()[0])
            page_count = int(connection.execute("PRAGMA page_count").fetchone()[0])
            free_pages = int(connection.execute("PRAGMA freelist_count").fetchone()[0])
            wal_size = wal_path.stat().st_size if wal_path.exists() else 0
            return max(0, page_count - free_pages) * page_size + wal_size

        deleted: dict[str, int] = {}
        if logical_size() <= limit_bytes:
            return deleted

        # Preserve important events as long as possible: full trace -> error detail -> absolute.
        # Bounded iterations protect startup/cleanup from pathological databases.
        for retention in (RetentionClass.FULL, RetentionClass.ERROR, RetentionClass.ABSOLUTE):
            total = 0
            for _ in range(200):
                if logical_size() <= limit_bytes:
                    break
                cursor = connection.execute(
                    """
                    DELETE FROM events WHERE event_id IN (
                        SELECT event_id FROM events WHERE retention_class=?
                        ORDER BY occurred_at ASC, event_id ASC LIMIT 1000
                    )
                    """,
                    (retention,),
                )
                if cursor.rowcount <= 0:
                    break
                total += cursor.rowcount
            if total:
                deleted[str(retention)] = total
            if logical_size() <= limit_bytes:
                break
        return deleted

    async def async_clear_events(self, *, before: str | None = None) -> int:
        return await asyncio.to_thread(self._clear_events, before)

    def _clear_events(self, before: str | None) -> int:
        connection = self._require_connection()
        if before:
            cursor = connection.execute("DELETE FROM events WHERE occurred_at<?", (before,))
        else:
            cursor = connection.execute("DELETE FROM events")
        connection.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        return cursor.rowcount

    async def async_stats(self) -> dict[str, Any]:
        return await asyncio.to_thread(self._stats)

    def _stats(self) -> dict[str, Any]:
        connection = self._require_connection()
        total = int(connection.execute("SELECT COUNT(*) FROM events").fetchone()[0])
        by_class = {
            row["retention_class"]: int(row["count"])
            for row in connection.execute(
                "SELECT retention_class, COUNT(*) AS count FROM events GROUP BY retention_class"
            )
        }
        by_category = {
            row["category"]: int(row["count"])
            for row in connection.execute(
                "SELECT category, COUNT(*) AS count FROM events GROUP BY category"
            )
        }
        active_anomalies = int(
            connection.execute("SELECT COUNT(*) FROM anomalies WHERE status='active'").fetchone()[0]
        )
        size = self.path.stat().st_size if self.path.exists() else 0
        wal_path = Path(str(self.path) + "-wal")
        wal_size = wal_path.stat().st_size if wal_path.exists() else 0
        latest = connection.execute(
            "SELECT occurred_at, event_type, summary FROM events ORDER BY occurred_at DESC, event_id DESC LIMIT 1"
        ).fetchone()
        return {
            "database_path": str(self.path),
            "database_size_bytes": size,
            "wal_size_bytes": wal_size,
            "total_events": total,
            "events_by_retention_class": by_class,
            "events_by_category": by_category,
            "active_anomalies": active_anomalies,
            "queue_size": self.queue_size,
            "normal_queue_size": self._normal_queue.qsize(),
            "critical_queue_size": self._critical_queue.qsize(),
            "dropped_events": self._dropped_events,
            "critical_fallback_events": self._critical_fallback_events,
            "critical_fallback_path": str(self.fallback_path),
            "written_events": self._written_events,
            "last_cleanup": self._last_cleanup,
            "schema_version": self._schema_version,
            "writer_state": self._writer_state,
            "last_failure": self._last_failure,
            "last_write_latency_ms": self._last_write_latency_ms,
            "max_write_latency_ms": round(self._max_write_latency_ms, 2),
            "latest": dict(latest) if latest else None,
        }

    async def async_count_by_types(self, event_types: Iterable[str], since: str) -> Counter[str]:
        return await asyncio.to_thread(self._count_by_types, tuple(event_types), since)

    def _count_by_types(self, event_types: tuple[str, ...], since: str) -> Counter[str]:
        if not event_types:
            return Counter()
        placeholders = ",".join("?" for _ in event_types)
        rows = self._require_connection().execute(
            f"SELECT event_type, COUNT(*) AS count FROM events WHERE event_type IN ({placeholders}) AND occurred_at>=? GROUP BY event_type",
            (*event_types, since),
        )
        return Counter({row["event_type"]: int(row["count"]) for row in rows})
