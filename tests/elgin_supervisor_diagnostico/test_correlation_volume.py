from __future__ import annotations

import ast
from datetime import datetime, timedelta, timezone
import inspect
import json
from pathlib import Path
import sqlite3
import unittest

from _bootstrap import COMPONENT, load


correlation = load("correlation")
models = load("models")
query = load("query")
snapshot = load("snapshot")


class CorrelationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime.now(timezone.utc).replace(microsecond=0)
        self.engine = correlation.CorrelationEngine(
            max_roots=100, retention_seconds=600
        )
        self.root = self.engine.begin(
            correlation_id="corr-root",
            context_id="ctx-root",
            evaluation_id="eval-root",
            user_id="user-1",
            source_entity_id="sensor.quarto",
            action="evaluate",
            actor="Supervisor",
            started_at=self.now,
            metadata={"trigger": "temperature"},
        )

    def test_explicit_and_direct_causality_are_distinct(self) -> None:
        explicit = self.engine.resolve(
            explicit_id="corr-root", occurred_at=self.now + timedelta(seconds=1)
        )
        self.assertEqual(explicit.relation, "explicit_correlation")
        self.assertFalse(explicit.causality_asserted)
        direct = self.engine.resolve(
            explicit_id="corr-root",
            causal_evidence="ação carregou correlation_id até o resultado",
            occurred_at=self.now + timedelta(seconds=2),
        )
        self.assertEqual(direct.relation, "direct_causality")
        self.assertTrue(direct.causality_asserted)
        self.assertEqual(direct.strength, 1.0)
        json.dumps(direct.as_dict(), ensure_ascii=False)

    def test_context_descendant_and_evaluation_relations_do_not_assert_cause(self) -> None:
        same = self.engine.resolve(
            context_id="ctx-root", occurred_at=self.now + timedelta(seconds=1)
        )
        self.assertEqual(same.relation, "same_context")
        self.assertFalse(same.causality_asserted)

        descendant = self.engine.resolve(
            context_id="ctx-child",
            parent_context_id="ctx-root",
            occurred_at=self.now + timedelta(seconds=2),
        )
        self.assertEqual(descendant.relation, "descendant_context")
        self.assertFalse(descendant.causality_asserted)
        rebound = self.engine.resolve(
            context_id="ctx-child", occurred_at=self.now + timedelta(seconds=3)
        )
        self.assertEqual(rebound.relation, "same_context")

        evaluation = self.engine.resolve(
            evaluation_id="eval-root", occurred_at=self.now + timedelta(seconds=4)
        )
        self.assertEqual(evaluation.relation, "correlated_by_evaluation")
        self.assertFalse(evaluation.causality_asserted)

    def test_temporal_matches_are_partial_and_never_causal(self) -> None:
        probable = self.engine.resolve(
            source_entity_id="sensor.quarto",
            action="evaluate",
            occurred_at=self.now + timedelta(seconds=5),
        )
        self.assertEqual(probable.relation, "probably_related")
        self.assertTrue(probable.partial)
        self.assertFalse(probable.causality_asserted)
        self.assertGreater(probable.strength, 0.2)

        temporal_only = self.engine.resolve(
            source_entity_id="sensor.outro",
            action="unrelated",
            occurred_at=self.now + timedelta(seconds=6),
        )
        self.assertEqual(temporal_only.relation, "temporal_proximity_only")
        self.assertEqual(temporal_only.strength, 0.2)
        self.assertFalse(temporal_only.causality_asserted)
        self.assertIsNone(
            self.engine.resolve(
                source_entity_id="sensor.sem_relacao",
                occurred_at=self.now + timedelta(hours=1),
                allow_temporal=False,
                create_if_missing=False,
            )
        )

    def test_bind_complete_and_snapshot_are_serializable_and_immutable(self) -> None:
        bound = self.engine.bind_context(
            correlation_id="corr-root",
            context_id="ctx-service",
            parent_context_id="ctx-root",
        )
        self.assertEqual(bound.correlation_id, "corr-root")
        result = {"confirmed": {"mode": "dry"}}
        completed = self.engine.complete(
            "corr-root",
            completed_at=self.now + timedelta(seconds=10),
            result=result,
        )
        result["confirmed"]["mode"] = "off"
        self.assertEqual(completed["result"]["confirmed"]["mode"], "dry")
        state = self.engine.snapshot()
        self.assertEqual(state["active_count"], 0)
        self.assertEqual(state["roots"][0]["contexts"], ["ctx-root", "ctx-service"])
        json.dumps(state, ensure_ascii=False)

    def test_capacity_and_retention_are_bounded(self) -> None:
        engine = correlation.CorrelationEngine(max_roots=10, retention_seconds=60)
        engine.begin(
            correlation_id="expired",
            started_at=self.now - timedelta(seconds=120),
        )
        for index in range(12):
            engine.begin(
                correlation_id=f"corr-{index:02d}",
                started_at=self.now + timedelta(seconds=index),
            )
        state = engine.snapshot()
        self.assertEqual(state["total_retained"], 10)
        ids = [item["correlation_id"] for item in state["roots"]]
        self.assertNotIn("expired", ids)
        self.assertNotIn("corr-00", ids)


class PureCoreVolumeTests(unittest.TestCase):
    def test_four_core_modules_have_no_home_assistant_imports(self) -> None:
        for name in ("models.py", "snapshot.py", "query.py", "correlation.py"):
            tree = ast.parse((COMPONENT / name).read_text(encoding="utf-8"))
            imported: list[str] = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    imported.extend(alias.name for alias in node.names)
                elif isinstance(node, ast.ImportFrom) and node.module:
                    imported.append(node.module)
            self.assertFalse(
                any(module.startswith("homeassistant") for module in imported), name
            )
        self.assertFalse(inspect.iscoroutinefunction(snapshot.capture_state_snapshot))

    def test_volume_contract_10k_1k_and_100_critical_each(self) -> None:
        repeated = [
            models.AuditEvent.from_mapping(
                {
                    "event_id": f"repeat-{index:05d}",
                    "occurred_at": "2026-08-08T10:00:00Z",
                    "received_at": "2026-08-08T10:00:01Z",
                    "category": "state",
                    "event_type": "state.changed",
                    "summary": "Estado idêntico",
                    "source_entity_id": "sensor.quarto",
                    "before_json": {"state": "24"},
                    "after_json": {"state": "24"},
                    "changed_fields_all": [],
                    "changed_fields_relevant": [],
                }
            )
            for index in range(10_000)
        ]
        # The storage compactor can collapse these safely because the pure model
        # produces one deterministic fingerprint while retaining unique event IDs.
        self.assertEqual(len({event.fingerprint for event in repeated}), 1)
        self.assertEqual(len({event.event_id for event in repeated}), 10_000)

        evaluations = [
            models.EvaluationRecord.from_mapping(
                {
                    "evaluation_id": f"eval-{index:04d}",
                    "correlation_id": f"corr-eval-{index:04d}",
                    "started_at": "2026-08-08T10:00:00Z",
                    "status": "no_change",
                    "summary": "Configuração desejada não mudou",
                    "result": {"changed": False},
                }
            )
            for index in range(1_000)
        ]
        self.assertEqual(len({item.evaluation_id for item in evaluations}), 1_000)

        transmissions = [
            models.AuditEvent.from_mapping(
                {
                    "event_id": f"tx-{index:03d}",
                    "occurred_at": "2026-08-08T10:01:00Z",
                    "received_at": "2026-08-08T10:01:00Z",
                    "category": "transmission",
                    "event_type": "esphome.action_requested",
                    "summary": "Solicitação ESPHome",
                    "transmission_id": f"transmission-{index:03d}",
                    "expected_audibility": "audible_expected",
                    "retention_class": "absolute",
                }
            )
            for index in range(100)
        ]
        errors = [
            models.AuditEvent.from_mapping(
                {
                    "event_id": f"error-{index:03d}",
                    "occurred_at": "2026-08-08T10:02:00Z",
                    "received_at": "2026-08-08T10:02:00Z",
                    "category": "error",
                    "event_type": "diagnostic.error",
                    "severity": "error",
                    "summary": f"Erro {index}",
                }
            )
            for index in range(100)
        ]
        external = [
            models.AuditEvent.from_mapping(
                {
                    "event_id": f"external-{index:03d}",
                    "occurred_at": "2026-08-08T10:03:00Z",
                    "received_at": "2026-08-08T10:03:00Z",
                    "category": "external",
                    "event_type": "localtuya.external_or_indeterminate",
                    "summary": f"Mudança externa {index}",
                    "is_external": True,
                }
            )
            for index in range(100)
        ]
        self.assertEqual(len({item.transmission_id for item in transmissions}), 100)
        self.assertTrue(all(item.audibility == "audible_expected" for item in transmissions))
        self.assertTrue(all(item.has_error for item in errors))
        self.assertTrue(all(item.is_external for item in external))
        critical_ids = {
            item.event_id for item in transmissions + errors + external
        }
        self.assertEqual(len(critical_ids), 300)
        json.dumps(evaluations[-1].as_dict(), ensure_ascii=False)

    def test_query_volume_is_bounded_and_parameterized(self) -> None:
        db = sqlite3.connect(":memory:")
        try:
            db.execute(
                """CREATE TABLE events (
                    event_id TEXT PRIMARY KEY, occurred_at TEXT, category TEXT,
                    severity TEXT, source_entity_id TEXT, entity_domain TEXT,
                    changed_fields_all TEXT, transmission_id TEXT,
                    is_external INTEGER, is_anomaly INTEGER
                )"""
            )
            rows = [
                (
                    f"repeat-{index:05d}",
                    f"2026-08-08T10:{index // 60 % 60:02d}:{index % 60:02d}+00:00",
                    "state",
                    "info",
                    "sensor.quarto",
                    "sensor",
                    "[]",
                    None,
                    0,
                    0,
                )
                for index in range(10_000)
            ]
            rows.extend(
                (
                    f"critical-{kind}-{index:03d}",
                    f"2026-08-08T12:{index // 60:02d}:{index % 60:02d}+00:00",
                    kind,
                    "error" if kind == "error" else "info",
                    "climate.quarto",
                    "climate",
                    "[]",
                    f"tx-{index}" if kind == "transmission" else None,
                    int(kind == "external"),
                    0,
                )
                for kind in ("transmission", "error", "external")
                for index in range(100)
            )
            db.executemany("INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?)", rows)
            where, params = query.compile_event_predicate(
                {"categories": ["transmission", "error", "external"]}
            )
            critical_count = db.execute(
                "SELECT COUNT(*) FROM events AS e" + where, params
            ).fetchone()[0]
            self.assertEqual(critical_count, 300)
            sql, params = query.compile_event_query(
                {"category": "state"}, limit=100, include_details=True
            )
            page = db.execute(sql, params).fetchall()
            self.assertEqual(len(page), 101)
            self.assertEqual(params[-1], 101)
        finally:
            db.close()


if __name__ == "__main__":
    unittest.main()
