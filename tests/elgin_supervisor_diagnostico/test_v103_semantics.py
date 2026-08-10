"""Focused semantic contracts introduced by Diagnostics 1.0.3."""

from __future__ import annotations

import json
import sqlite3
import unittest

from _bootstrap import COMPONENT, load


migrations = load("migrations")
models = load("models")


class SeveritySemanticsTests(unittest.TestCase):
    def test_one_deterministic_example_per_level(self) -> None:
        examples = (
            ({"event_type": "agenda.evaluated", "category": "agenda", "severity": "info"}, "debug"),
            ({"event_type": "decision.calculated", "category": "decision", "severity": "info"}, "info"),
            ({"event_type": "transmission.accepted_by_software", "category": "transmission", "severity": "info"}, "success"),
            ({"event_type": "decision.blocked", "category": "decision", "severity": "info"}, "warning"),
            ({"event_type": "supervisor.error", "category": "evaluation", "severity": "info"}, "error"),
            ({"event_type": "diagnostic.component_unavailable", "category": "system", "severity": "info"}, "critical"),
        )
        for payload, expected in examples:
            with self.subTest(expected=expected):
                self.assertEqual(expected, models.classify_event_severity(payload))

    def test_protected_events_cannot_be_downgraded_and_has_error_is_coherent(self) -> None:
        protected = (
            ({"event_type": "transmission.logical_request", "category": "transmission", "severity": "debug", "expected_audibility": "audible_expected"}, "info"),
            ({"event_type": "localtuya.external_or_indeterminate", "category": "external", "severity": "debug", "is_external": True}, "warning"),
            ({"event_type": "supervisor.error", "category": "error", "severity": "debug"}, "error"),
            ({"event_type": "observation.beep", "category": "observation", "severity": "debug"}, "info"),
        )
        for payload, expected in protected:
            with self.subTest(expected=expected):
                self.assertEqual(expected, models.classify_event_severity(payload))
        event = models.AuditEvent.from_mapping(
            {"event_type": "decision.calculated", "severity": "info", "has_error": True}
        )
        self.assertFalse(event.has_error)
        failed = models.AuditEvent.from_mapping(
            {"event_type": "supervisor.error", "severity": "info", "has_error": False}
        )
        self.assertTrue(failed.has_error)


class PowerSemanticsTests(unittest.TestCase):
    def test_profile_state_and_level_are_not_ambiguous(self) -> None:
        named = models.AuditEvent.from_mapping({"power_profile": "Fraco"})
        self.assertEqual("Fraco", named.power_profile)
        self.assertIsNone(models.AuditEvent.from_mapping({"power": True}).power_profile)
        for value in (True, False, 0, 1, "0", "1", "on", "off", "true", "false"):
            with self.subTest(value=value):
                self.assertIsNone(
                    models.AuditEvent.from_mapping({"power_profile": value}).power_profile
                )
        level = models.AuditEvent.from_mapping({"power_level": "2"})
        self.assertEqual(2, level.power_level)
        self.assertIsNone(level.power_profile)
        legacy = models.AuditEvent.from_mapping({"potencia": "Moderado"})
        self.assertEqual("Moderado", legacy.power_profile)

    def test_semantic_database_migration_is_exact_and_idempotent(self) -> None:
        connection = sqlite3.connect(":memory:", isolation_level=None)
        self.addCleanup(connection.close)
        connection.row_factory = sqlite3.Row
        connection.executescript(
            """
            CREATE TABLE metadata(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE events(
                event_id TEXT PRIMARY KEY,severity TEXT,event_type TEXT,category TEXT,
                source_entity_id TEXT,is_external INTEGER,expected_audibility TEXT,
                power_profile TEXT,power_level REAL,details_json TEXT,desired_json TEXT
            );
            """
        )
        rows = (
            ("routine", "info", "agenda.evaluated", "agenda", None, 0, None, None, None, None, None),
            ("helper", "info", "state.changed", "state", "input_datetime.elgin_supervisor_ultimo_comando", 0, None, None, None, None, None),
            ("functional", "info", "state.changed", "state", "input_select.elgin_supervisor_tratamento_ativo", 0, None, None, None, None, None),
            ("transmission", "info", "transmission.logical_request", "transmission", None, 0, "audible_expected", None, None, None, None),
            ("external", "info", "localtuya.external_or_indeterminate", "external", None, 1, None, None, None, None, None),
            ("raw-state", "info", "decision.calculated", "decision", None, 0, None, "1", None, json.dumps({"payload": {"power": True}}), None),
            ("backfill", "info", "decision.calculated", "decision", None, 0, None, "1", None, json.dumps({"payload": {"power_profile": "Fraco", "power_level": 2}}), None),
        )
        connection.executemany(
            "INSERT INTO events VALUES(?,?,?,?,?,?,?,?,?,?,?)", rows
        )
        first = migrations.migrate_event_semantics_v6(connection)
        changes_after_first = connection.total_changes
        second = migrations.migrate_event_semantics_v6(connection)
        self.assertTrue(first["applied"])
        self.assertFalse(second["applied"])
        self.assertEqual(changes_after_first, connection.total_changes)
        self.assertEqual(2, first["severity_rows_reclassified"])
        severities = dict(connection.execute("SELECT event_id,severity FROM events"))
        self.assertEqual("debug", severities["routine"])
        self.assertEqual("debug", severities["helper"])
        self.assertEqual("info", severities["functional"])
        self.assertEqual("info", severities["transmission"])
        self.assertEqual("info", severities["external"])
        power = connection.execute(
            "SELECT power_profile,power_level FROM events WHERE event_id='raw-state'"
        ).fetchone()
        self.assertIsNone(power["power_profile"])
        recovered = connection.execute(
            "SELECT power_profile,power_level FROM events WHERE event_id='backfill'"
        ).fetchone()
        self.assertEqual("Fraco", recovered["power_profile"])
        self.assertEqual(2, recovered["power_level"])


class FlowSemanticsTests(unittest.TestCase):
    def test_complete_and_incomplete_flows_only_contain_present_phases(self) -> None:
        base = [
            {"event_id": "decision", "occurred_at": "2026-08-09T10:00:00+00:00", "correlation_id": "corr", "category": "decision", "event_type": "decision.calculated", "summary": "Decisão", "outcome": "calculated"},
            {"event_id": "action", "occurred_at": "2026-08-09T10:00:01+00:00", "correlation_id": "corr", "category": "transmission", "event_type": "transmission.accepted_by_software", "summary": "Solicitação aceita", "outcome": "accepted_by_software"},
        ]
        incomplete = models.build_operational_flow(base, "corr")
        self.assertEqual("incomplete", incomplete["state"])
        self.assertFalse(incomplete["terminal"])
        self.assertEqual(["decision", "action"], [item["phase"] for item in incomplete["steps"]])
        complete = models.build_operational_flow(
            [
                *base,
                {"event_id": "confirmation", "occurred_at": "2026-08-09T10:00:02+00:00", "correlation_id": "corr", "category": "state", "event_type": "localtuya.confirmed_full_state", "summary": "Confirmado", "outcome": "confirmed_by_localtuya"},
            ],
            "corr",
        )
        self.assertEqual("complete", complete["state"])
        self.assertTrue(complete["terminal"])
        self.assertEqual("result", complete["steps"][-1]["phase"])


class FrontendSmokeContracts(unittest.TestCase):
    def test_picker_presentation_power_and_flow_contracts_are_wired(self) -> None:
        source = (
            COMPONENT / "frontend" / "elgin-supervisor-diagnostico-card.js"
        ).read_text()
        for contract in (
            'document.addEventListener("pointerdown", this._onDocumentPointerDown, true)',
            'document.addEventListener("keydown", this._onDocumentKeyDown, true)',
            'document.addEventListener("focusin", this._onDocumentFocusIn, true)',
            'document.removeEventListener("pointerdown", this._onDocumentPointerDown, true)',
            'event.composedPath().includes(this)',
            'detail: { picker: this }',
            'debug: "Rotina"',
            'cool: "Refrigeração"',
            'heat: "Aquecimento"',
            'dry: "Desumidificação"',
            '`Nível ${new Intl.NumberFormat("pt-BR").format(numeric)}`',
            'Nenhuma correlação operacional registrada até agora.',
            'Último fluxo observado',
            'Último fluxo completo',
            'data-flow-correlation',
        ):
            with self.subTest(contract=contract):
                self.assertIn(contract, source)
        self.assertNotIn("_flowPhase(step)", source)
        self.assertNotIn('["sensor", "Sensor mudou"]', source)


if __name__ == "__main__":
    unittest.main()
