from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import json
import unittest

from _bootstrap import load


snapshot = load("snapshot")
models = load("models")


@dataclass
class FakeContext:
    id: str
    parent_id: str | None = None
    user_id: str | None = None


@dataclass
class FakeState:
    entity_id: str
    state: str | None
    attributes: dict
    last_changed: datetime
    last_updated: datetime
    context: FakeContext


class SnapshotTests(unittest.TestCase):
    def make_state(self, value: str = "24", **attributes: object) -> FakeState:
        now = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc)
        return FakeState(
            "sensor.quarto",
            value,
            dict(attributes),
            now,
            now,
            FakeContext("ctx-1", "parent-1", "user-1"),
        )

    def test_snapshot_is_atomic_deeply_immutable_and_json_serializable(self) -> None:
        state = self.make_state(
            "24",
            nested={"readings": [24, {"humidity": 74}]},
            nullable=None,
        )
        captured = snapshot.capture_state_snapshot(state.entity_id, state)
        self.assertIsNotNone(captured)

        state.state = "25"
        state.attributes["nested"]["readings"][1]["humidity"] = 60
        state.attributes["new"] = True
        state.context.id = "ctx-mutated"

        self.assertEqual(captured["state"], "24")
        self.assertEqual(captured["attributes"]["nested"]["readings"][1]["humidity"], 74)
        self.assertNotIn("new", captured["attributes"])
        self.assertEqual(captured["context"]["id"], "ctx-1")
        with self.assertRaises(TypeError):
            captured["state"] = "26"
        with self.assertRaises(TypeError):
            captured["attributes"]["nested"]["readings"].append(99)
        json.dumps(captured, ensure_ascii=False)

    def test_freeze_thaw_cycle_bounds_and_dataclass_with_frozen_member(self) -> None:
        cyclic: list[object] = []
        cyclic.append(cyclic)
        frozen = snapshot.freeze_json({"cycle": cyclic, "nan": float("nan")})
        self.assertEqual(frozen["cycle"][0]["reason"], "cyclic_reference")
        self.assertEqual(frozen["nan"], "NaN")
        thawed = snapshot.thaw_json(frozen)
        thawed["cycle"].append("mutable")
        self.assertEqual(len(frozen["cycle"]), 1)

        @dataclass
        class Holder:
            payload: object

        holder = snapshot.freeze_json(Holder(snapshot.freeze_json({"a": [1]})))
        self.assertEqual(holder, {"payload": {"a": [1]}})
        with self.assertRaises(TypeError):
            snapshot.freeze_json(snapshot.MISSING)

    def test_diff_distinguishes_missing_null_unknown_unavailable_and_removal(self) -> None:
        before = snapshot.capture_state_snapshot(
            "sensor.quarto",
            self.make_state("unknown", removed="old", friendly_name="Quarto"),
        )
        after = snapshot.capture_state_snapshot(
            "sensor.quarto",
            self.make_state("unavailable", nullable=None, friendly_name="Novo nome"),
        )
        diff = snapshot.build_state_diff(before, after)

        self.assertEqual(diff["diff"]["state"]["before"], "unknown")
        self.assertEqual(diff["diff"]["state"]["after"], "unavailable")
        self.assertFalse(diff["diff"]["nullable"]["before_present"])
        self.assertTrue(diff["diff"]["nullable"]["after_present"])
        self.assertIsNone(diff["diff"]["nullable"]["after"])
        self.assertTrue(diff["diff"]["removed"]["before_present"])
        self.assertFalse(diff["diff"]["removed"]["after_present"])
        self.assertIn("friendly_name", diff["changed_fields_all"])
        self.assertNotIn("friendly_name", diff["changed_fields_relevant"])
        self.assertIn("state", diff["changed_fields_relevant"])

    def test_numeric_diffs_preserve_each_rapid_transition(self) -> None:
        first = snapshot.capture_state_snapshot(
            "sensor.quarto", self.make_state("24", temperature=24)
        )
        second = snapshot.capture_state_snapshot(
            "sensor.quarto", self.make_state("25", temperature=25)
        )
        third = snapshot.capture_state_snapshot(
            "sensor.quarto", self.make_state("26", temperature=26)
        )
        diff_a = snapshot.build_state_diff(first, second, {"state", "temperature"})
        diff_b = snapshot.build_state_diff(second, third, {"state", "temperature"})
        self.assertEqual(diff_a["diff"]["temperature"]["delta"], 1)
        self.assertEqual(diff_b["diff"]["temperature"]["before"], 25)
        self.assertEqual(diff_b["diff"]["temperature"]["after"], 26)
        self.assertEqual(
            list(diff_b["changed_fields_relevant"]), ["state", "temperature"]
        )

    def test_entity_creation_and_removal_are_lossless(self) -> None:
        state = snapshot.capture_state_snapshot(
            "sensor.quarto", self.make_state("on", nullable=None)
        )
        created = snapshot.build_state_diff(None, state)
        removed = snapshot.build_state_diff(state, None)
        self.assertEqual(created["diff"]["state"]["change"], "added")
        self.assertEqual(removed["diff"]["state"]["change"], "removed")
        self.assertFalse(removed["diff"]["nullable"]["after_present"])


class ModelTests(unittest.TestCase):
    def test_audit_event_accepts_and_exposes_canonical_and_storage_aliases(self) -> None:
        event = models.AuditEvent.from_mapping(
            {
                "event_id": "evt-1",
                "occurred_at": "2026-08-08T12:00:00-03:00",
                "received_at": "2026-08-08T15:00:01Z",
                "source_entity_id": "climate.esp8266_elgin_aux_quarto",
                "entity_domain": "climate",
                "climate_mode": "dry",
                "agenda_state": "ativa",
                "expected_audibility": "audible_expected",
                "trigger_model": "automatic_supervisor",
                "relation_kind": "expected_value_match",
                "relation_strength": "strong",
                "relation_evidence": ["context.id", "valor esperado"],
                "severity": "error",
                "outcome": "confirmed_by_localtuya",
                "summary": "Solicitação correlacionada",
                "temperature": 25.2,
                "target_temperature": 22,
                "reason": "Umidade acima do início",
                "blocked_by": ["minimum_time"],
                "diff": {
                    "changed_fields_all": ["state", "target_temperature"],
                    "changed_fields_relevant": ["target_temperature"],
                    "diff": {"target_temperature": {"before": 23, "after": 22}},
                },
                "retention_class": "full",
                "desired": {"mode": "dry", "target_temperature": 22},
            }
        )
        self.assertEqual(event.entity_id, "climate.esp8266_elgin_aux_quarto")
        self.assertEqual(event.mode, "dry")
        self.assertEqual(event.correlation_relation, "expected_value_match")
        self.assertEqual(event.correlation_strength, 0.9)
        self.assertTrue(event.has_error)
        self.assertEqual(event.outcome, "confirmed_by_localtuya")
        self.assertEqual(event.diff_json["target_temperature"]["after"], 22)

        payload = event.as_dict()
        self.assertEqual(payload["entity_id"], payload["source_entity_id"])
        self.assertEqual(payload["domain"], payload["entity_domain"])
        self.assertEqual(payload["mode"], payload["climate_mode"])
        self.assertEqual(payload["agenda"], payload["agenda_state"])
        self.assertEqual(payload["audibility"], payload["expected_audibility"])
        self.assertEqual(payload["retention_class_canonical"], "trace")
        self.assertEqual(payload["retention_class"], "full")
        self.assertEqual(payload["details_json"]["reason"], "Umidade acima do início")
        json.dumps(payload, ensure_ascii=False)

    def test_evaluation_storage_round_trip_and_duration(self) -> None:
        evaluation = models.EvaluationRecord.from_mapping(
            {
                "evaluation_id": "eval-1",
                "correlation_id": "corr-1",
                "context_id": "ctx-1",
                "started_at": "2026-08-08T10:00:00Z",
                "completed_at": "2026-08-08T10:00:00.250Z",
                "status": "completed",
                "summary": "Refrigeração mantida",
                "trigger_json": {"entity_id": "sensor.quarto"},
                "inputs_json": {"temperature": 25},
                "desired_json": {"mode": "cool"},
                "reason_json": {
                    "reason": "Acima do limite",
                    "blocked_by": ["no_change"],
                    "mode": "cool",
                    "treatment": "cooling",
                },
                "related_event_ids": ["evt-1", "evt-2"],
            }
        )
        self.assertEqual(evaluation.duration_ms, 250)
        self.assertEqual(evaluation.reason, "Acima do limite")
        self.assertEqual(evaluation.blocked_by, ("no_change",))
        payload = evaluation.as_dict()
        self.assertEqual(payload["completed_at"], evaluation.finished_at)
        self.assertEqual(payload["inputs_json"]["temperature"], 25)
        self.assertEqual(payload["related_event_ids"], ["evt-1", "evt-2"])
        json.dumps(payload, ensure_ascii=False)

    def test_anomaly_and_observation_storage_aliases(self) -> None:
        anomaly = models.AnomalyRecord.from_mapping(
            {
                "anomaly_id": "anom-1",
                "anomaly_type": "repeated_commands",
                "title": "Comandos repetidos",
                "first_seen": "2026-08-08T10:00:00Z",
                "last_seen": "2026-08-08T10:01:00Z",
                "count": 3,
                "acknowledged_by": "Pedro",
                "acknowledgement_note": "Investigando",
                "details": {"window": 60},
            }
        )
        anomaly_payload = anomaly.as_dict()
        self.assertEqual(anomaly_payload["title"], "Comandos repetidos")
        self.assertEqual(anomaly_payload["count"], 3)
        self.assertEqual(anomaly_payload["acknowledged_by"], "Pedro")

        observation = models.ObservationRecord.from_mapping(
            {
                "observation_id": "obs-1",
                "observation_type": "beep",
                "occurred_at": "2026-08-08T10:00:00Z",
                "created_at": "2026-08-08T10:00:01Z",
                "note": "Ouvi dois bips",
                "expected_count": 2,
                "metadata": {"tags": ["dry"], "context_id": "ctx-1"},
                "related_event_ids": ["evt-1"],
            }
        )
        observation_payload = observation.as_dict()
        self.assertEqual(observation.beep_count, "2")
        self.assertEqual(observation_payload["note"], "Ouvi dois bips")
        self.assertEqual(observation_payload["expected_count"], 2)
        self.assertEqual(observation_payload["related_event_ids"], ["evt-1"])
        json.dumps(observation_payload, ensure_ascii=False)

    def test_settings_defaults_legacy_aliases_validation_and_persistence(self) -> None:
        defaults = models.DiagnosticSettings.from_options(None)
        payload = defaults.as_dict()
        self.assertEqual(len(payload), 77)
        self.assertEqual(payload["capture_power_profiles"], True)
        self.assertEqual(payload["retention_essential_days"], 60)
        self.assertEqual(payload["retention_trace_days"], 7)
        self.assertEqual(payload["interface_items_per_page"], 50)
        self.assertNotIn("retention_absolute_days", payload)
        self.assertEqual(
            models.DiagnosticSettings.from_options(payload).as_dict(), payload
        )
        json.dumps(payload, ensure_ascii=False)

        migrated = models.DiagnosticSettings.from_options(
            {
                "capture_power": False,
                "retention_absolute_days": 120,
                "retention_full_days": 14,
                "localtuya_confirmation_seconds": 45,
                "notification_minimum_severity": "error",
                "export_max_events": 12_345,
                "saved_filters": [{"name": "Bips", "filters": {"mode": "dry"}}],
            }
        )
        self.assertFalse(migrated.capture_power_profiles)
        self.assertEqual(migrated.retention_absolute_days, 120)
        self.assertEqual(migrated.retention_full_days, 14)
        self.assertEqual(migrated.localtuya_confirmation_window_seconds, 45)
        self.assertEqual(migrated.notification_min_severity, "error")
        self.assertEqual(migrated.maintenance_export_max_rows, 12_345)
        with self.assertRaises(TypeError):
            migrated.saved_filters.append({})
        with self.assertRaises(ValueError):
            models.DiagnosticSettings.from_options({"queue_limit": 1})

    def test_cursor_functions_are_reexported_for_compatibility(self) -> None:
        cursor = models.encode_cursor("2026-08-08T10:00:00Z", "evt-1")
        self.assertEqual(models.decode_cursor(cursor).event_id, "evt-1")


if __name__ == "__main__":
    unittest.main()
