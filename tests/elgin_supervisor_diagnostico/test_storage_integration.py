"""Integration tests for the real serialized SQLite schema and compaction path."""

from __future__ import annotations

import asyncio
from concurrent.futures import Future
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest

from _bootstrap import PACKAGE, load


# ``storage`` only needs these constants at runtime.  Keeping this test stubbed
# avoids importing Home Assistant while still executing the production storage.
const_stub = ModuleType(f"{PACKAGE}.const")
const_stub.DB_FILENAME = "elgin_supervisor_diagnostico.sqlite3"
const_stub.LEGACY_FALLBACK_FILENAME = "elgin_supervisor_diagnostico_critical_fallback.ndjson"
const_stub.SCHEMA_VERSION = 6
sys.modules[f"{PACKAGE}.const"] = const_stub
storage_module = load("storage")


class _Config:
    def __init__(self, root: Path) -> None:
        self.root = root

    def path(self, *parts: str) -> str:
        return str(self.root.joinpath(*parts))


class _Hass:
    def __init__(self, root: Path) -> None:
        self.config = _Config(root)

    def async_create_background_task(self, coroutine, name):
        return asyncio.create_task(coroutine, name=name)


def _settings() -> SimpleNamespace:
    return SimpleNamespace(
        queue_limit=20_000,
        critical_queue_limit=2_000,
        batch_size=100,
        flush_interval_seconds=0.25,
        compaction_enabled=True,
        compaction_window_seconds=60,
        compact_identical_evaluations=True,
        compact_no_change=True,
        compact_identical_states=True,
        compact_repeated_blocks=True,
        compact_repeated_unavailable=True,
        retention_trace_days=7,
        retention_error_days=30,
        retention_essential_days=60,
        maintenance_database_limit_mb=250,
        maintenance_cleanup_interval_hours=6,
    )


def _updated(settings: SimpleNamespace, **changes: object) -> SimpleNamespace:
    values = vars(settings).copy()
    values.update(changes)
    return SimpleNamespace(**values)


class StorageIntegrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.storage = storage_module.DiagnosticStorage(_Hass(self.root), _settings())
        self.storage._open_and_migrate()

    def tearDown(self) -> None:
        self.storage._close()
        self.storage._executor.shutdown(wait=True)
        self.temporary.cleanup()

    @staticmethod
    def event(index: int, **changes: object) -> dict[str, object]:
        occurred = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc) + timedelta(
            milliseconds=index % 50_000
        )
        payload: dict[str, object] = {
            "event_id": f"event-{index:06d}",
            "occurred_at": occurred.isoformat(),
            "occurred_at_local": occurred.isoformat(),
            "received_at": occurred.isoformat(),
            "category": "state",
            "event_type": "state.changed",
            "severity": "info",
            "outcome": "observed",
            "summary": "Estado repetido para compactação",
            "source_component": "sensor",
            "source_entity_id": "sensor.sensor_umidade_sensor_dedicado",
            "entity_domain": "sensor",
            "correlation_id": "correlation-volume",
            "changed_fields_all": ["state"],
            "changed_fields_relevant": ["state"],
            "before_json": {"state": "73"},
            "after_json": {"state": "74"},
            "diff_json": {"state": {"before": "73", "after": "74"}},
            "details_json": {"humidity": 74},
            "retention_class": "trace",
            "fingerprint": "identical-state",
            "is_external": False,
            "is_anomaly": False,
        }
        payload.update(changes)
        return payload

    def test_schema_wal_and_required_indexes(self) -> None:
        connection = self.storage._require_connection()
        self.assertEqual("wal", connection.execute("PRAGMA journal_mode").fetchone()[0])
        self.assertEqual(6, connection.execute("PRAGMA user_version").fetchone()[0])
        indexes = {
            row[1]
            for row in connection.execute("PRAGMA index_list(events)").fetchall()
        }
        required = {
            "idx_events_time",
            "idx_events_category_time",
            "idx_events_type_time",
            "idx_events_severity_time",
            "idx_events_entity_time",
            "idx_events_actor_time",
            "idx_events_user_time",
            "idx_events_context_time",
            "idx_events_corr_time",
            "idx_events_eval_time",
            "idx_events_mode_time",
            "idx_events_treatment_time",
            "idx_events_outcome_time",
            "idx_events_external_time",
            "idx_events_anomaly_time",
        }
        self.assertTrue(required <= indexes)

    def test_live_queue_limit_uses_stable_physical_queue_without_losing_items(self) -> None:
        self.storage.settings = _updated(self.storage.settings, queue_limit=100)
        self.assertEqual(100_000, self.storage._normal_queue.maxsize)

        for index in range(100):
            self.assertTrue(self.storage.enqueue(self.event(index)))
        self.assertFalse(self.storage.enqueue(self.event(100)))
        self.assertEqual(1, self.storage.dropped_events)

        # The real options flow replaces the immutable settings object.  Raising
        # the logical limit must immediately admit more items in the same queue.
        self.storage.settings = _updated(self.storage.settings, queue_limit=200)
        self.assertTrue(self.storage.enqueue(self.event(101)))
        self.assertEqual(101, self.storage._normal_queue.qsize())

        health = self.storage._health()
        self.assertEqual(200, health["normal_queue_limit"])
        self.assertEqual(100_000, health["physical_queue_capacity"])

    def test_writer_reads_batch_size_again_after_each_batch(self) -> None:
        self.storage.settings = _updated(
            self.storage.settings, batch_size=1, flush_interval_seconds=60
        )
        for index in range(3):
            self.assertTrue(self.storage.enqueue(self.event(index)))

        batches: list[list[str]] = []

        async def run_writer() -> None:
            async def fake_run(_function: object, payload: list[dict[str, object]]):
                batches.append([str(item["event_id"]) for item in payload])
                if len(batches) == 1:
                    self.storage.settings = _updated(
                        self.storage.settings, batch_size=2
                    )
                return len(payload), 0

            original_run = self.storage._run
            self.storage._run = fake_run
            self.storage._stopping = True
            try:
                await self.storage._writer_loop()
            finally:
                self.storage._run = original_run

        asyncio.run(run_writer())
        self.assertEqual([1, 2], [len(batch) for batch in batches])
        self.assertEqual(0, self.storage.queue_size)

    def test_settings_replacement_wakes_writer_waiting_on_old_flush_interval(self) -> None:
        self.storage.settings = _updated(
            self.storage.settings, batch_size=10, flush_interval_seconds=60
        )
        processed = asyncio.Event()

        async def run_writer() -> None:
            async def fake_run(_function: object, payload: list[dict[str, object]]):
                self.assertEqual(["event-000001"], [item["event_id"] for item in payload])
                self.storage._stopping = True
                processed.set()
                return 1, 0

            original_run = self.storage._run
            self.storage._run = fake_run
            self.storage._stopping = False
            task = asyncio.create_task(self.storage._writer_loop())
            try:
                await asyncio.sleep(0)
                self.assertTrue(self.storage.enqueue(self.event(1)))
                self.storage.settings = _updated(
                    self.storage.settings, flush_interval_seconds=0.01
                )
                await asyncio.wait_for(processed.wait(), timeout=0.5)
                await asyncio.wait_for(task, timeout=0.5)
            finally:
                if not task.done():
                    self.storage._stopping = True
                    self.storage._writer_wakeup.set()
                    task.cancel()
                self.storage._run = original_run

        asyncio.run(run_writer())

    def test_cleanup_due_recalculates_interval_from_live_settings(self) -> None:
        opened_at = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)
        check_at = opened_at + timedelta(hours=5)
        self.storage._opened_at = opened_at
        self.storage._last_cleanup = None

        # The integration test opens SQLite synchronously in setUp, so exercise
        # the serialized helper directly on that same thread.  Production's
        # public async method delegates to this helper through ``_run``.
        not_due = self.storage._cleanup_if_due(check_at)
        self.storage.settings = _updated(
            self.storage.settings, maintenance_cleanup_interval_hours=4
        )
        due = self.storage._cleanup_if_due(check_at)
        self.storage.settings = _updated(
            self.storage.settings, maintenance_cleanup_interval_hours=12
        )
        postponed = self.storage._cleanup_if_due(check_at + timedelta(hours=6))
        self.assertTrue(not_due["skipped"])
        self.assertFalse(due["skipped"])
        self.assertEqual(check_at.isoformat(), due["finished_at"])
        self.assertTrue(postponed["skipped"])

    def test_reference_schema_is_backed_up_and_migrated_without_reinterpreting_evidence(self) -> None:
        legacy_root = self.root / "legacy"
        legacy_storage = legacy_root / ".storage"
        legacy_storage.mkdir(parents=True)
        database = legacy_storage / "elgin_supervisor_diagnostico.sqlite3"
        with closing(sqlite3.connect(database)) as connection:
            connection.executescript(
                """
                CREATE TABLE events (
                    event_id TEXT PRIMARY KEY, occurred_at TEXT NOT NULL,
                    occurred_at_local TEXT NOT NULL, received_at TEXT NOT NULL,
                    category TEXT NOT NULL, event_type TEXT NOT NULL,
                    severity TEXT NOT NULL, retention_class TEXT NOT NULL,
                    summary TEXT NOT NULL, technical_message TEXT, outcome TEXT NOT NULL,
                    source_component TEXT, source_entity_id TEXT, source_automation_id TEXT,
                    source_script_id TEXT, action_domain TEXT, action_name TEXT,
                    correlation_id TEXT, parent_correlation_id TEXT, context_id TEXT,
                    parent_context_id TEXT, user_id TEXT, user_name TEXT,
                    actor_type TEXT, actor_name TEXT, origin_class TEXT,
                    origin_confidence TEXT, trigger_platform TEXT, trigger_entity_id TEXT,
                    from_state TEXT, to_state TEXT, climate_mode TEXT, treatment TEXT,
                    expected_audibility TEXT, observed_audibility TEXT,
                    expected_beep_count INTEGER, transmission_id TEXT, frame_kind TEXT,
                    frame_hash TEXT, is_external INTEGER NOT NULL DEFAULT 0,
                    is_anomaly INTEGER NOT NULL DEFAULT 0, anomaly_type TEXT,
                    compacted_count INTEGER NOT NULL DEFAULT 1, details_json TEXT,
                    before_json TEXT, desired_json TEXT, confirmed_json TEXT
                );
                CREATE TABLE anomalies (
                    anomaly_id TEXT PRIMARY KEY, anomaly_type TEXT NOT NULL,
                    severity TEXT NOT NULL, first_seen TEXT NOT NULL,
                    last_seen TEXT NOT NULL, count INTEGER NOT NULL,
                    status TEXT NOT NULL, related_event_ids TEXT NOT NULL,
                    explanation TEXT NOT NULL, recommendation TEXT NOT NULL,
                    acknowledged_at TEXT, resolved_at TEXT, notified_at TEXT,
                    details_json TEXT NOT NULL
                );
                CREATE TABLE metadata (key TEXT PRIMARY KEY,value TEXT NOT NULL);
                CREATE UNIQUE INDEX idx_anomalies_active_type
                    ON anomalies(anomaly_type) WHERE status='active';
                INSERT INTO events (
                    event_id,occurred_at,occurred_at_local,received_at,category,
                    event_type,severity,retention_class,summary,outcome,is_external,
                    is_anomaly,confirmed_json
                ) VALUES (
                    'legacy-1','2026-08-01T12:00:00+00:00','2026-08-01T09:00:00-03:00',
                    '2026-08-01T12:00:00+00:00','transmission','legacy.request',
                    'info','absolute','Registro legado','requested',0,0,
                    '{"legacy":"valor_sem_semantica_after"}'
                );
                PRAGMA user_version=1;
                """
            )
        migrated = storage_module.DiagnosticStorage(_Hass(legacy_root), _settings())
        try:
            migrated._open_and_migrate()
            connection = migrated._require_connection()
            row = connection.execute(
                "SELECT confirmed_json,after_json,diff_json,legacy_semantics FROM events "
                "WHERE event_id='legacy-1'"
            ).fetchone()
            self.assertEqual('{"legacy":"valor_sem_semantica_after"}', row["confirmed_json"])
            self.assertIsNone(row["after_json"])
            self.assertIsNone(row["diff_json"])
            self.assertEqual(
                "confirmed_json_preservado_sem_reinterpretacao", row["legacy_semantics"]
            )
            self.assertEqual(6, connection.execute("PRAGMA user_version").fetchone()[0])
            self.assertTrue(
                database.with_suffix(".pre-v6.sqlite3.bak").exists(),
                "A migração deve preservar um backup anterior ao schema 6",
            )
            self.assertNotIn(
                "idx_anomalies_active_type",
                {
                    row[1]
                    for row in connection.execute("PRAGMA index_list(anomalies)")
                },
            )
        finally:
            migrated._close()
            migrated._executor.shutdown(wait=True)

    def test_exact_volume_contract_compacts_only_repetitive_noncritical_rows(self) -> None:
        batch: list[dict[str, object]] = []
        batch.extend(self.event(index) for index in range(10_000))
        batch.extend(
            self.event(
                10_000 + index,
                category="evaluation",
                event_type="evaluation.no_change",
                summary="Avaliação sem mudança",
                fingerprint="identical-evaluation",
            )
            for index in range(1_000)
        )
        batch.extend(
            self.event(
                11_000 + index,
                category="transmission",
                event_type="transmission.requested_by_ha",
                summary=f"Transmissão {index}",
                transmission_id=f"tx-{index}",
                fingerprint=f"tx-{index}",
            )
            for index in range(100)
        )
        batch.extend(
            self.event(
                11_100 + index,
                category="error",
                event_type="supervisor.error",
                severity="error",
                summary=f"Erro {index}",
                fingerprint=f"error-{index}",
                retention_class="error",
            )
            for index in range(100)
        )
        batch.extend(
            self.event(
                11_200 + index,
                category="external",
                event_type="localtuya.external_or_indeterminate",
                summary=f"Mudança externa {index}",
                is_external=True,
                fingerprint=f"external-{index}",
                retention_class="essential",
            )
            for index in range(100)
        )

        written, compacted = self.storage._write_batch(batch)
        connection = self.storage._require_connection()
        self.assertEqual(302, written)
        self.assertEqual(10_998, compacted)
        self.assertEqual(302, connection.execute("SELECT COUNT(*) FROM events").fetchone()[0])
        self.assertEqual(
            10_000,
            connection.execute(
                "SELECT compacted_count FROM events WHERE fingerprint='identical-state'"
            ).fetchone()[0],
        )
        self.assertEqual(
            1_000,
            connection.execute(
                "SELECT compacted_count FROM events WHERE fingerprint='identical-evaluation'"
            ).fetchone()[0],
        )
        self.assertEqual(100, connection.execute("SELECT COUNT(*) FROM events WHERE transmission_id IS NOT NULL").fetchone()[0])
        self.assertEqual(100, connection.execute("SELECT COUNT(*) FROM events WHERE severity='error'").fetchone()[0])
        self.assertEqual(100, connection.execute("SELECT COUNT(*) FROM events WHERE is_external=1").fetchone()[0])

        catalog = self.storage._get_filter_catalog({"categories": ["transmission"]})
        category_counts = {
            item["value"]: item["count"] for item in catalog["categories"]
        }
        self.assertEqual(100, category_counts["transmission"])
        self.assertIn("error", category_counts)
        self.assertIn("activation_models", catalog["facets"])
        statistics = self.storage._get_statistics({"categories": ["transmission"]})
        self.assertEqual(100, statistics["total_events"])
        self.assertEqual(100, statistics["transmissions"])

    def test_fingerprint_ignores_volatile_ids_but_preserves_semantics(self) -> None:
        first = self.event(
            1,
            event_id="evaluation-event-1",
            category="evaluation",
            event_type="evaluation.no_change",
            fingerprint=None,
            details_json={
                "stage": "evaluation_no_change",
                "humidity": 74,
                "reason": "Configuração desejada já aplicada",
                "payload": {
                    "evaluation_id": "evaluation-1",
                    "correlation_id": "correlation-1",
                    "occurred_at": "2026-08-08T12:00:00+00:00",
                },
            },
        )
        second = self.event(
            2,
            event_id="evaluation-event-2",
            category="evaluation",
            event_type="evaluation.no_change",
            fingerprint=None,
            details_json={
                "stage": "evaluation_no_change",
                "humidity": 74,
                "reason": "  CONFIGURAÇÃO   desejada já aplicada ",
                "payload": {
                    "evaluation_id": "evaluation-2",
                    "correlation_id": "correlation-2",
                    "occurred_at": "2026-08-08T12:00:01+00:00",
                },
            },
        )
        changed = {
            **second,
            "event_id": "evaluation-event-3",
            "details_json": {
                **second["details_json"],
                "humidity": 73,
            },
        }
        first["fingerprint"] = storage_module._event_fingerprint(first)
        second["fingerprint"] = storage_module._event_fingerprint(second)
        changed["fingerprint"] = storage_module._event_fingerprint(changed)

        self.assertEqual(first["fingerprint"], second["fingerprint"])
        self.assertNotEqual(first["fingerprint"], changed["fingerprint"])
        self.assertEqual((1, 1), self.storage._write_batch([first, second]))

    def test_filtered_clear_is_parameterized_and_creates_recoverable_backup(self) -> None:
        self.storage._write_batch(
            [
                self.event(1, fingerprint="state-one"),
                self.event(
                    2,
                    category="transmission",
                    event_type="transmission.requested_by_ha",
                    transmission_id="tx-preserved",
                    fingerprint="tx-preserved",
                ),
            ]
        )
        deleted = self.storage._clear_events(None, {"categories": ["state"]})
        self.assertEqual(1, deleted)
        connection = self.storage._require_connection()
        self.assertEqual(1, connection.execute("SELECT COUNT(*) FROM events").fetchone()[0])
        self.assertEqual(
            "tx-preserved",
            connection.execute("SELECT transmission_id FROM events").fetchone()[0],
        )
        self.assertIsNotNone(self.storage._last_backup)
        backup = Path(self.storage._last_backup)
        self.assertTrue(backup.exists())
        with closing(sqlite3.connect(backup)) as recovered:
            self.assertEqual(2, recovered.execute("SELECT COUNT(*) FROM events").fetchone()[0])

    def test_statistics_count_distinct_evaluations_and_persist_health_metadata(self) -> None:
        for evaluation_id, status, action in (
            ("eval-action", "completed", "transmission_path_evaluated"),
            ("eval-no-action", "no_change", "no_action"),
        ):
            self.storage._upsert_evaluation(
                {
                    "evaluation_id": evaluation_id,
                    "started_at": "2026-08-08T12:00:00+00:00",
                    "completed_at": "2026-08-08T12:00:01+00:00",
                    "status": status,
                    "result_json": {"action": action},
                    "related_event_ids": [],
                }
            )
        self.storage._write_batch(
            [
                self.event(1, evaluation_id="eval-action", fingerprint="eval-action-1"),
                self.event(2, evaluation_id="eval-action", fingerprint="eval-action-2"),
                self.event(3, evaluation_id="eval-no-action", fingerprint="eval-no-action"),
            ]
        )
        statistics = self.storage._get_statistics({})
        self.assertEqual(2, statistics["total_evaluations"])
        self.assertEqual(1, statistics["decisions_with_action"])
        self.assertEqual(1, statistics["decisions_without_action"])

        cleanup = self.storage._cleanup()
        self.storage._last_cleanup = cleanup["finished_at"]
        health = self.storage._health()
        self.assertEqual(3, health["total_events"])
        self.assertIsNotNone(health["last_migration"])
        self.assertEqual(cleanup["finished_at"], health["last_cleanup"])
        self.assertIsNotNone(health["next_cleanup"])
        self.assertIn("main_database_size_bytes", health)

    def test_deleting_observation_removes_its_timeline_row(self) -> None:
        observation_id = "observation-delete"
        self.storage._add_observation(
            {
                "observation_id": observation_id,
                "observation_type": "beep",
                "occurred_at": "2026-08-08T12:00:00+00:00",
                "created_at": "2026-08-08T12:00:00+00:00",
                "note": "teste",
                "expected_count": 1,
                "metadata": {"beep_count": "1"},
                "related_event_ids": [],
            }
        )
        self.storage._write_batch(
            [
                self.event(
                    10,
                    category="observation",
                    event_type="observation.beep",
                    details_json={"observation_id": observation_id},
                    fingerprint="observation-delete",
                    retention_class="essential",
                )
            ]
        )
        self.assertTrue(self.storage._delete_observation(observation_id))
        connection = self.storage._require_connection()
        self.assertEqual(0, connection.execute("SELECT COUNT(*) FROM observations").fetchone()[0])
        self.assertEqual(0, connection.execute("SELECT COUNT(*) FROM events").fetchone()[0])

    def test_anomaly_recurrence_groups_by_semantic_key_not_only_type(self) -> None:
        base = {
            "anomaly_type": "critical_entity_unavailable",
            "severity": "error",
            "title": "Entidade crítica indisponível",
            "explanation": "teste",
            "recommendation": "corrigir",
            "first_seen": "2026-08-08T12:00:00+00:00",
            "last_seen": "2026-08-08T12:00:00+00:00",
            "count": 1,
            "status": "active",
            "related_event_ids": [],
        }
        first = self.storage._upsert_anomaly(
            {
                **base,
                "anomaly_id": "anomaly-humidity",
                "details": {"group_key": "unavailable:humidity"},
            }
        )
        second = self.storage._upsert_anomaly(
            {
                **base,
                "anomaly_id": "anomaly-temperature",
                "details": {"group_key": "unavailable:temperature"},
            }
        )
        repeated = self.storage._upsert_anomaly(
            {
                **base,
                "anomaly_id": "ignored-new-id",
                "last_seen": "2026-08-08T12:00:01+00:00",
                "details": {"group_key": "unavailable:humidity"},
            }
        )
        self.assertNotEqual(first["anomaly_id"], second["anomaly_id"])
        self.assertEqual(first["anomaly_id"], repeated["anomaly_id"])
        self.assertEqual(2, repeated["count"])
        self.assertEqual(
            2,
            self.storage._require_connection()
            .execute("SELECT COUNT(*) FROM anomalies")
            .fetchone()[0],
        )

        self.assertTrue(
            self.storage._set_anomaly_status(
                first["anomaly_id"], "acknowledged", "user-1", "verificado"
            )
        )
        recurrence = self.storage._upsert_anomaly(
            {
                **base,
                "anomaly_id": "ignored-after-ack",
                "last_seen": "2026-08-08T12:00:02+00:00",
                "details": {"group_key": "unavailable:humidity"},
            }
        )
        self.assertEqual(first["anomaly_id"], recurrence["anomaly_id"])
        self.assertEqual("active", recurrence["status"])
        self.assertEqual(3, recurrence["count"])
        self.assertIsNone(recurrence["acknowledged_at"])
        self.assertIsNone(recurrence["acknowledged_by"])

        self.assertTrue(
            self.storage._set_anomaly_status(
                first["anomaly_id"], "resolved", "user-1", "corrigido"
            )
        )
        after_resolution = self.storage._upsert_anomaly(
            {
                **base,
                "anomaly_id": "new-after-resolution",
                "last_seen": "2026-08-08T12:00:03+00:00",
                "details": {"group_key": "unavailable:humidity"},
            }
        )
        self.assertEqual("new-after-resolution", after_resolution["anomaly_id"])
        self.assertEqual(
            2,
            self.storage._require_connection()
            .execute(
                "SELECT COUNT(*) FROM anomalies WHERE "
                "json_extract(details_json,'$.group_key')='unavailable:humidity'"
            )
            .fetchone()[0],
        )

    def test_notification_timestamp_is_persisted_per_anomaly_group(self) -> None:
        anomaly = self.storage._upsert_anomaly(
            {
                "anomaly_id": "notification-group",
                "anomaly_type": "repeated_commands",
                "severity": "warning",
                "title": "Teste",
                "explanation": "teste",
                "recommendation": "revisar",
                "first_seen": "2026-08-08T12:00:00+00:00",
                "last_seen": "2026-08-08T12:00:00+00:00",
                "count": 1,
                "details": {"group_key": "commands:dry"},
            }
        )
        notified_at = "2026-08-08T12:01:00+00:00"
        self.assertTrue(
            self.storage._mark_anomaly_notified(
                anomaly["anomaly_id"], notified_at
            )
        )
        self.assertEqual(
            notified_at,
            self.storage._get_anomaly(anomaly["anomaly_id"])["notified_at"],
        )
        recurrence = self.storage._upsert_anomaly(
            {
                **anomaly,
                "anomaly_id": "ignored-notification-id",
                "last_seen": "2026-08-08T12:02:00+00:00",
            }
        )
        self.assertEqual(notified_at, recurrence["notified_at"])

    def test_clear_watermark_preserves_events_received_after_confirmation(self) -> None:
        self.storage._write_batch(
            [
                self.event(
                    1,
                    received_at="2026-08-08T12:00:00+00:00",
                    fingerprint="before-barrier",
                ),
                self.event(
                    2,
                    received_at="2026-08-08T12:00:02+00:00",
                    fingerprint="after-barrier",
                ),
            ]
        )
        deleted = self.storage._clear_events(
            None, {}, "2026-08-08T12:00:01+00:00"
        )
        self.assertEqual(1, deleted)
        remaining = self.storage._require_connection().execute(
            "SELECT event_id FROM events"
        ).fetchall()
        self.assertEqual(["event-000002"], [row[0] for row in remaining])

    def test_clear_preserves_protected_event_even_with_old_received_at(self) -> None:
        before = self.event(
            1,
            received_at="2020-01-01T00:00:00+00:00",
            occurred_at="2026-08-08T12:00:00+00:00",
            event_type="state.no_relevant_change",
            fingerprint="same-meaning",
        )
        after_confirmation = self.event(
            2,
            received_at="2020-01-01T00:00:00+00:00",
            occurred_at="2026-08-08T12:00:01+00:00",
            event_type="state.no_relevant_change",
            fingerprint="same-meaning",
        )
        self.storage._write_batch([before])
        with self.storage._clear_state_lock:
            self.storage._clear_in_progress = True
            self.storage._clear_protected_event_ids.add(
                after_confirmation["event_id"]
            )
        try:
            written, compacted = self.storage._write_batch([after_confirmation])
            self.assertEqual((1, 0), (written, compacted))
            deleted = self.storage._clear_events(
                None, {}, "2026-08-08T12:00:02+00:00"
            )
        finally:
            with self.storage._clear_state_lock:
                self.storage._clear_in_progress = False
                self.storage._clear_protected_event_ids.clear()
        self.assertEqual(1, deleted)
        remaining = self.storage._require_connection().execute(
            "SELECT event_id FROM events"
        ).fetchall()
        self.assertEqual(["event-000002"], [row[0] for row in remaining])

    def test_clear_before_date_only_removes_older_rows(self) -> None:
        self.storage._write_batch(
            [
                self.event(
                    1,
                    occurred_at="2026-08-01T00:00:00+00:00",
                    fingerprint="old-by-date",
                ),
                self.event(
                    2,
                    occurred_at="2026-08-08T00:00:00+00:00",
                    fingerprint="new-by-date",
                ),
            ]
        )
        self.assertEqual(
            1,
            self.storage._clear_events(
                "2026-08-05T00:00:00+00:00", {}
            ),
        )
        remaining = self.storage._require_connection().execute(
            "SELECT event_id FROM events"
        ).fetchall()
        self.assertEqual(["event-000002"], [row[0] for row in remaining])

    def test_clear_rolls_back_every_table_after_intermediate_failure(self) -> None:
        self.storage._upsert_evaluation(
            {
                "evaluation_id": "eval-rollback",
                "started_at": "2026-08-08T12:00:00+00:00",
                "status": "completed",
                "related_event_ids": ["event-000001"],
            }
        )
        self.storage._write_batch(
            [self.event(1, evaluation_id="eval-rollback", fingerprint="rollback")]
        )
        connection = self.storage._require_connection()
        connection.execute(
            "CREATE TRIGGER fail_evaluation_delete BEFORE DELETE ON evaluations "
            "BEGIN SELECT RAISE(ABORT,'falha simulada'); END"
        )
        with self.assertRaises(sqlite3.DatabaseError):
            self.storage._clear_events(None, {"categories": ["state"]})
        self.assertEqual(
            1, connection.execute("SELECT COUNT(*) FROM events").fetchone()[0]
        )
        self.assertEqual(
            1, connection.execute("SELECT COUNT(*) FROM evaluations").fetchone()[0]
        )
        self.assertTrue(Path(self.storage._last_backup).exists())

    def test_public_clear_drains_writer_queue_before_delete(self) -> None:
        async def scenario() -> None:
            root = self.root / "writer-barrier"
            storage = storage_module.DiagnosticStorage(_Hass(root), _settings())
            storage._open_and_migrate()

            async def direct_run(function, *arguments):
                return function(*arguments)

            storage._run = direct_run
            storage._stopping = False
            storage._writer_task = asyncio.create_task(storage._writer_loop())
            try:
                self.assertTrue(
                    storage.enqueue(
                        self.event(
                            20,
                            received_at="2020-01-01T00:00:00+00:00",
                            fingerprint="queued",
                        )
                    )
                )
                deleted = await storage.async_clear_events()
                self.assertEqual(1, deleted)
                self.assertEqual(
                    0,
                    storage._require_connection()
                    .execute("SELECT COUNT(*) FROM events")
                    .fetchone()[0],
                )
            finally:
                await storage.async_stop()

        asyncio.run(scenario())

    def test_fallback_replays_valid_lines_quarantines_invalid_and_is_idempotent(self) -> None:
        event = self.event(30, fingerprint="fallback-valid")
        self.storage._append_fallback_batch([event])
        with self.storage.fallback_path.open("a", encoding="utf-8") as stream:
            stream.write("{linha-corrompida}\n")
        self.storage._close()
        self.storage._open_and_migrate()
        connection = self.storage._require_connection()
        self.assertEqual(
            1,
            connection.execute(
                "SELECT COUNT(*) FROM events WHERE event_id='event-000030'"
            ).fetchone()[0],
        )
        self.assertFalse(self.storage.fallback_path.exists())
        self.assertTrue(self.storage._fallback_quarantine_path.exists())
        self.assertEqual(1, self.storage._fallback_replayed)
        self.assertEqual(1, self.storage._fallback_invalid_lines)
        self.assertTrue(self.storage._fallback_status()["degraded"])

        # Replaying the same committed event is a no-op and removes the source
        # only after the transaction commits.
        self.storage._append_fallback_batch([event])
        self.storage._close()
        self.storage._open_and_migrate()
        self.assertEqual(
            1,
            self.storage._require_connection()
            .execute("SELECT COUNT(*) FROM events WHERE event_id='event-000030'")
            .fetchone()[0],
        )
        self.assertGreaterEqual(self.storage._fallback_duplicates, 1)

    def test_sqlite_writer_failure_uses_fallback_and_isolates_fallback_failure(self) -> None:
        async def sqlite_failure() -> None:
            self.assertTrue(
                self.storage.enqueue(
                    self.event(40, fingerprint="sqlite-unavailable")
                )
            )

            async def fake_run(function, *arguments):
                if function == self.storage._write_batch:
                    raise sqlite3.OperationalError("SQLite indisponível")
                return function(*arguments)

            original_run = self.storage._run
            self.storage._run = fake_run
            self.storage._stopping = True
            try:
                with self.assertLogs(storage_module._LOGGER.name, level="ERROR"):
                    await self.storage._writer_loop()
            finally:
                self.storage._run = original_run
            self.assertTrue(self.storage.fallback_path.exists())
            self.assertEqual(0, self.storage.queue_size)
            self.assertFalse(self.storage.healthy)

        asyncio.run(sqlite_failure())

        async def double_failure() -> None:
            blocked = self.root / "blocked-fallback"
            blocked.mkdir()
            self.storage.fallback_path = blocked
            self.assertTrue(
                self.storage.enqueue(
                    self.event(41, fingerprint="double-failure")
                )
            )

            async def fake_run(function, *arguments):
                if function == self.storage._write_batch:
                    raise sqlite3.OperationalError("SQLite indisponível")
                return function(*arguments)

            original_run = self.storage._run
            self.storage._run = fake_run
            self.storage._stopping = True
            try:
                with self.assertLogs(storage_module._LOGGER.name, level="ERROR"):
                    await self.storage._writer_loop()
            finally:
                self.storage._run = original_run
            self.assertEqual(0, self.storage.queue_size)
            self.assertEqual(1, self.storage._fallback_write_failures)
            self.assertFalse(self.storage.healthy)

        asyncio.run(double_failure())

    def test_fallback_rotates_and_reports_unavailable_destination(self) -> None:
        original_limit = storage_module._FALLBACK_MAX_BYTES
        storage_module._FALLBACK_MAX_BYTES = 2_000
        try:
            for index in range(10):
                self.storage._append_fallback_batch(
                    [
                        self.event(
                            100 + index,
                            summary="x" * 450,
                            fingerprint=f"rotation-{index}",
                        )
                    ]
                )
            status = self.storage._fallback_status()
            self.assertGreater(status["runtime_rotations"], 0)
            self.assertLessEqual(status["pending_files"], 4)
            self.assertTrue(
                all(
                    path.stat().st_size <= storage_module._FALLBACK_MAX_BYTES
                    for path in self.storage._fallback_files()
                )
            )
        finally:
            storage_module._FALLBACK_MAX_BYTES = original_limit

        blocked = self.root / "fallback-is-directory"
        blocked.mkdir()
        self.storage.fallback_path = blocked
        future: Future[None] = Future()
        future.set_exception(IsADirectoryError(str(blocked)))
        with self.assertLogs(storage_module._LOGGER.name, level="ERROR"):
            self.storage._observe_fallback_future(future)
        self.assertFalse(self.storage.healthy)
        self.assertEqual(1, self.storage._fallback_write_failures)
        self.assertIn("fallback", self.storage._last_failure)

    def test_disjunctive_facets_respect_other_filters_and_keep_choices(self) -> None:
        batch = [
            self.event(
                20_000 + index,
                event_type=f"decision.cool.{index}",
                category="decision",
                climate_mode="cool",
                severity="info",
                power_profile="Fraco",
                fingerprint=f"cool-{index}",
            )
            for index in range(2)
        ]
        batch.extend(
            self.event(
                20_100 + index,
                event_type=f"decision.heat.{index}",
                category="decision",
                climate_mode="heat",
                severity="warning",
                power_profile="Moderado",
                fingerprint=f"heat-{index}",
            )
            for index in range(3)
        )
        batch.extend(
            (
                self.event(20_200, event_type="legacy.power.one", power_profile="1", fingerprint="power-one"),
                self.event(20_201, event_type="legacy.power.boolean", power_profile="true", fingerprint="power-true"),
            )
        )
        self.storage._write_batch(batch)
        catalog = self.storage._get_filter_catalog(
            {"modes": ["cool"], "severities": ["warning"]}
        )
        severities = catalog["facets"]["severity"]
        self.assertEqual(
            ["debug", "info", "success", "warning", "error", "critical"],
            [item["value"] for item in severities],
        )
        severity_counts = {item["value"]: item["count"] for item in severities}
        self.assertEqual(2, severity_counts["info"])
        self.assertEqual(0, severity_counts["warning"])
        modes = {item["value"]: item["count"] for item in catalog["facets"]["mode"]}
        self.assertEqual(3, modes["heat"])
        self.assertEqual(0, modes["cool"])

        power_catalog = self.storage._get_filter_catalog({})["facets"]["power"]
        power_values = {str(item["value"]) for item in power_catalog}
        self.assertIn("Fraco", power_values)
        self.assertIn("Moderado", power_values)
        self.assertTrue({"0", "1", "true", "false", "on", "off"}.isdisjoint(power_values))

    def test_latest_operational_correlation_uses_time_and_sqlite_history(self) -> None:
        old = self.event(
            30_000,
            occurred_at="2026-08-09T10:00:00+00:00",
            event_type="localtuya.confirmed_full_state",
            category="state",
            correlation_id="corr-old-confirmation",
            outcome="confirmed_by_localtuya",
            fingerprint="old-confirmation",
        )
        newer = self.event(
            30_001,
            occurred_at="2026-08-09T11:00:00+00:00",
            event_type="decision.calculated",
            category="decision",
            correlation_id="corr-new-decision",
            outcome="calculated",
            fingerprint="new-decision",
        )
        action = self.event(
            30_002,
            occurred_at="2026-08-09T11:00:01+00:00",
            event_type="transmission.accepted_by_software",
            category="transmission",
            correlation_id="corr-new-decision",
            outcome="accepted_by_software",
            fingerprint="new-action",
        )
        self.storage._write_batch([old, newer, action])
        result = self.storage._get_latest_operational_correlation()
        self.assertEqual("corr-new-decision", result["correlation_id"])
        self.assertEqual(
            ["event-030001", "event-030002"],
            [item["event_id"] for item in result["events"]],
        )


if __name__ == "__main__":
    unittest.main()
