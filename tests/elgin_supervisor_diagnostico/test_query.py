from __future__ import annotations

import json
import sqlite3
import unittest

from _bootstrap import load


query = load("query")


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
    "parent_context_id",
    "context_id",
    "user_id",
    "user_name",
    "actor_type",
    "actor_name",
    "origin_class",
    "trigger_model",
    "climate_mode",
    "treatment",
    "preset",
    "power_profile",
    "agenda_state",
    "protection",
    "function",
    "expected_audibility",
    "transmission_id",
    "confirmation_state",
    "is_external",
    "is_anomaly",
    "anomaly_type",
    "changed_fields_all",
    "changed_fields_relevant",
    "before_json",
    "after_json",
    "diff_json",
    "details_json",
    "retention_class",
    "compacted_count",
    "fingerprint",
)


class QueryCompilerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.db = sqlite3.connect(":memory:")
        self.db.row_factory = sqlite3.Row
        definitions = []
        for name in EVENT_COLUMNS:
            if name in {"is_external", "is_anomaly", "compacted_count"}:
                definition = "INTEGER"
            else:
                definition = "TEXT"
            if name == "event_id":
                definition += " PRIMARY KEY"
            definitions.append(f"{name} {definition}")
        self.db.execute(f"CREATE TABLE events ({','.join(definitions)})")
        self.insert_rows()

    def tearDown(self) -> None:
        self.db.close()

    @staticmethod
    def event(**changes: object) -> dict[str, object]:
        payload: dict[str, object] = {
            "event_id": "evt-a",
            "occurred_at": "2026-08-08T10:00:00+00:00",
            "occurred_at_local": "2026-08-08T07:00:00-03:00",
            "received_at": "2026-08-08T10:00:00.100000+00:00",
            "category": "state",
            "event_type": "state.changed",
            "severity": "info",
            "outcome": "observed",
            "summary": "Temperatura subiu",
            "technical_message": "sensor callback",
            "source_component": "sensor",
            "source_entity_id": "sensor.quarto",
            "entity_domain": "sensor",
            "action_domain": None,
            "action_name": None,
            "evaluation_id": "eval-1",
            "correlation_id": "corr-1",
            "parent_context_id": None,
            "context_id": "ctx-1",
            "user_id": "user-1",
            "user_name": "Pedro",
            "actor_type": "automation",
            "actor_name": "Supervisor",
            "origin_class": "supervisor",
            "trigger_model": "automatic_supervisor",
            "climate_mode": "cool",
            "treatment": "cooling",
            "preset": "conforto",
            "power_profile": "forte",
            "agenda_state": "ativa",
            "protection": "none",
            "function": "ifeel",
            "expected_audibility": "silent_expected",
            "transmission_id": None,
            "confirmation_state": "pending",
            "is_external": 0,
            "is_anomaly": 0,
            "anomaly_type": None,
            "changed_fields_all": json.dumps(["state", "target_temperature", "fan"]),
            "changed_fields_relevant": json.dumps(["target_temperature", "fan"]),
            "before_json": json.dumps(
                {
                    "state": "24",
                    "attributes": {
                        "target_temperature": 24,
                        "fan": "low",
                        "nullable": None,
                    },
                }
            ),
            "after_json": json.dumps(
                {
                    "state": "25",
                    "attributes": {"target_temperature": 23, "fan": "medium"},
                }
            ),
            "diff_json": json.dumps(
                {
                    "target_temperature": {"before": 24, "after": 23, "delta": -1},
                    "fan": {"before": "low", "after": "medium"},
                }
            ),
            "details_json": json.dumps(
                {
                    "reason": "Umidade acima do início",
                    "rule": "humidity_start",
                    "temperature": 25.2,
                    "target_temperature": 23,
                    "humidity": 74,
                }
            ),
            "retention_class": "full",
            "compacted_count": 1,
            "fingerprint": "fp-a",
        }
        payload.update(changes)
        return payload

    def insert(self, payload: dict[str, object]) -> None:
        placeholders = ",".join("?" for _ in EVENT_COLUMNS)
        self.db.execute(
            f"INSERT INTO events ({','.join(EVENT_COLUMNS)}) VALUES ({placeholders})",
            [payload.get(name) for name in EVENT_COLUMNS],
        )

    def insert_rows(self) -> None:
        self.insert(self.event())
        self.insert(
            self.event(
                event_id="evt-b",
                occurred_at="2026-08-08T10:01:00+00:00",
                category="transmission",
                event_type="esphome.action_requested",
                severity="warning",
                outcome="requested",
                summary="IR solicitado ao ESPHome",
                source_entity_id="climate.esp8266_elgin_aux_quarto",
                entity_domain="climate",
                action_domain="esphome",
                action_name="esp8266_elgin_send_state",
                origin_class="supervisor",
                climate_mode="dry",
                treatment="dehumidification",
                preset="seco",
                power_profile="moderada",
                expected_audibility="audible_expected",
                transmission_id="tx-1",
                confirmation_state="awaiting_localtuya",
                changed_fields_all="[]",
                changed_fields_relevant="[]",
                before_json="{}",
                after_json="{}",
                diff_json="{}",
                details_json=json.dumps(
                    {"temperature": 24.8, "target_temperature": 22, "humidity": 70}
                ),
                fingerprint="fp-b",
            )
        )
        self.insert(
            self.event(
                event_id="evt-c",
                occurred_at="2026-08-08T10:02:00+00:00",
                category="external",
                event_type="localtuya.external_or_indeterminate",
                severity="error",
                outcome="observed",
                summary="Mudança externa ou indeterminada",
                source_entity_id="switch.smart_air_conditioner_power_ar_condicionado_id_1",
                entity_domain="switch",
                user_id=None,
                user_name=None,
                actor_type="external",
                actor_name="Aparelho físico",
                origin_class="external_physical",
                climate_mode="off",
                treatment="none",
                preset=None,
                power_profile=None,
                agenda_state="inativa",
                expected_audibility="not_determined",
                confirmation_state="diverged",
                is_external=1,
                is_anomaly=1,
                anomaly_type="external_change_reaction",
                changed_fields_all=json.dumps(["state"]),
                changed_fields_relevant=json.dumps(["state"]),
                before_json=json.dumps({"state": "on", "attributes": {}}),
                after_json=json.dumps({"state": "off", "attributes": {}}),
                diff_json=json.dumps({"state": {"before": "on", "after": "off"}}),
                details_json=json.dumps({"temperature": 24, "humidity": 68}),
                fingerprint="fp-c",
            )
        )
        self.insert(
            self.event(
                event_id="evt-d",
                occurred_at="2026-08-08T10:03:00+00:00",
                category="state",
                event_type="climate.fan_changed",
                summary="Ventilador alterado por Ana",
                user_id="user-2",
                user_name="Ana",
                actor_type="user",
                actor_name="Ana",
                origin_class="home_assistant_user",
                source_entity_id="climate.esp8266_elgin_aux_quarto",
                entity_domain="climate",
                correlation_id=None,
                evaluation_id=None,
                climate_mode="heat",
                treatment="heating",
                preset="noturno",
                power_profile="silenciosa",
                agenda_state="ativa",
                changed_fields_all=json.dumps(["fan"]),
                changed_fields_relevant=json.dumps(["fan"]),
                before_json=json.dumps({"state": "heat", "attributes": {"fan": "low"}}),
                after_json=json.dumps({"state": "heat", "attributes": {"fan": "high"}}),
                diff_json=json.dumps({"fan": {"before": "low", "after": "high"}}),
                details_json=json.dumps({"temperature": 21, "humidity": 55}),
                fingerprint="fp-d",
            )
        )
        self.insert(
            self.event(
                event_id="evt-e",
                occurred_at="2026-08-08T10:04:00+00:00",
                category="decision",
                event_type="supervisor.action_suppressed",
                severity="critical",
                outcome="blocked",
                summary="Proteção 100% ativa",
                technical_message="minimum_time",
                origin_class="supervisor",
                source_entity_id="sensor.elgin_supervisor_tratamento_desejado",
                power_profile="bloqueada",
                climate_mode="cool",
                treatment="cooling",
                protection="minimum_time",
                function="protection",
                confirmation_state=None,
                changed_fields_all="[]",
                changed_fields_relevant="[]",
                before_json="{}",
                after_json="{}",
                diff_json="{}",
                details_json=json.dumps(
                    {
                        "reason": "minimum_time ainda ativo",
                        "temperature": 28,
                        "target_temperature": 22,
                        "humidity": 50,
                    }
                ),
                fingerprint="fp-e",
            )
        )
        self.db.commit()

    def run_query(
        self,
        filters: dict | None = None,
        *,
        cursor: str | None = None,
        limit: int = 50,
        direction: str = "older",
    ) -> list[sqlite3.Row]:
        sql, params = query.compile_event_query(
            filters,
            cursor=cursor,
            limit=limit,
            direction=direction,
            include_details=True,
        )
        return self.db.execute(sql, params).fetchall()

    def ids(self, filters: dict | None = None) -> list[str]:
        return [row["event_id"] for row in self.run_query(filters)]

    @staticmethod
    def advanced(field: str, operator: str, value: object = None) -> dict:
        condition = {"field": field, "operator": operator}
        if operator not in {"exists", "not_exists"} or value is not None:
            condition["value"] = value
        return {"advanced": {"logic": "and", "conditions": [condition]}}

    def test_schema_aliases_and_basic_multiselect_filters(self) -> None:
        self.assertEqual(query.FILTER_FIELDS["entity_id"].column, "e.source_entity_id")
        self.assertEqual(query.FILTER_FIELDS["domain"].column, "e.entity_domain")
        self.assertEqual(query.FILTER_FIELDS["mode"].column, "e.climate_mode")
        self.assertEqual(query.FILTER_FIELDS["agenda"].column, "e.agenda_state")
        self.assertEqual(
            query.FILTER_FIELDS["audibility"].column, "e.expected_audibility"
        )
        self.assertEqual(self.ids({"category": "external"}), ["evt-c"])
        self.assertEqual(
            set(self.ids({"categories": ["state", "transmission"]})),
            {"evt-a", "evt-b", "evt-d"},
        )
        self.assertEqual(self.ids({"event_types": ["state.changed"]}), ["evt-a"])
        self.assertEqual(self.ids({"severities": ["error", "critical"]}), ["evt-e", "evt-c"])
        self.assertEqual(self.ids({"user": "Ana"}), ["evt-d"])
        self.assertEqual(self.ids({"user_id": "user-2"}), ["evt-d"])
        self.assertEqual(self.ids({"entity": "sensor.quarto"}), ["evt-a"])
        self.assertEqual(self.ids({"modes": ["dry"]}), ["evt-b"])
        self.assertEqual(self.ids({"treatment": "heating"}), ["evt-d"])
        self.assertEqual(self.ids({"preset": "seco"}), ["evt-b"])
        self.assertEqual(self.ids({"power_profile": "forte"}), ["evt-a"])
        self.assertEqual(self.ids({"power": "moderada"}), ["evt-b"])
        self.assertEqual(self.ids({"humidity": 74}), ["evt-a"])
        self.assertEqual(self.ids({"agenda": "inativa"}), ["evt-c"])
        self.assertEqual(self.ids({"origin": "external_physical"}), ["evt-c"])
        self.assertEqual(
            self.ids({"anomaly_types": ["external_change_reaction"]}), ["evt-c"]
        )
        self.assertEqual(
            self.ids({"confirmation_state": "awaiting_localtuya"}), ["evt-b"]
        )

    def test_special_boolean_and_changed_field_filters(self) -> None:
        self.assertEqual(self.ids({"has_transmission": True}), ["evt-b"])
        self.assertEqual(set(self.ids({"has_error": "true"})), {"evt-c", "evt-e"})
        self.assertEqual(set(self.ids({"has_error": False})), {"evt-a", "evt-b", "evt-d"})
        self.assertEqual(set(self.ids({"has_change": False})), {"evt-b", "evt-e"})
        self.assertEqual(set(self.ids({"changed_field": "fan"})), {"evt-a", "evt-d"})
        self.assertEqual(
            set(self.ids({"changed_fields": ["state", "target_temperature"]})),
            {"evt-a", "evt-c"},
        )
        self.assertEqual(self.ids({"has_correlation": False}), ["evt-d"])
        with self.assertRaises(query.QueryValidationError):
            self.ids({"has_change": "talvez"})

    def test_retention_filters_span_canonical_and_legacy_values(self) -> None:
        self.insert(
            self.event(
                event_id="evt-retention-essential",
                occurred_at="2026-08-08T10:05:00+00:00",
                retention_class="essential",
            )
        )
        self.insert(
            self.event(
                event_id="evt-retention-absolute",
                occurred_at="2026-08-08T10:06:00+00:00",
                retention_class="absolute",
            )
        )
        self.insert(
            self.event(
                event_id="evt-retention-trace",
                occurred_at="2026-08-08T10:07:00+00:00",
                retention_class="trace",
            )
        )
        self.db.commit()

        essential = {"evt-retention-essential", "evt-retention-absolute"}
        trace = {"evt-a", "evt-b", "evt-c", "evt-d", "evt-e", "evt-retention-trace"}
        self.assertEqual(set(self.ids({"retention_class": "essential"})), essential)
        self.assertEqual(
            set(self.ids(self.advanced("retention_class", "eq", "absolute"))),
            essential,
        )
        self.assertEqual(set(self.ids({"retention_classes": ["trace"]})), trace)
        self.assertEqual(
            set(self.ids(self.advanced("retention_class", "not_in", ["full"]))),
            essential,
        )
        self.assertEqual(
            set(self.ids(self.advanced("retention_class", "ne", "essential"))),
            trace,
        )

    def test_all_scalar_text_numeric_and_temporal_operators(self) -> None:
        cases = (
            ("mode", "eq", "dry", {"evt-b"}),
            ("category", "ne", "state", {"evt-b", "evt-c", "evt-e"}),
            ("summary", "contains", "temperatura", {"evt-a"}),
            ("summary", "not_contains", "externa", {"evt-a", "evt-b", "evt-d", "evt-e"}),
            ("summary", "starts", "IR", {"evt-b"}),
            ("summary", "ends", "Ana", {"evt-d"}),
            ("humidity", "gt", 72, {"evt-a"}),
            ("humidity", "gte", 70, {"evt-a", "evt-b"}),
            ("temperature", "lt", 22, {"evt-d"}),
            ("temperature", "lte", 24, {"evt-c", "evt-d"}),
            ("category", "in", ["external", "decision"], {"evt-c", "evt-e"}),
            ("category", "not_in", ["state", "decision"], {"evt-b", "evt-c"}),
            ("occurred_at", "before", "2026-08-08T10:02:00+00:00", {"evt-a", "evt-b"}),
            ("occurred_at", "after", "2026-08-08T10:02:00+00:00", {"evt-d", "evt-e"}),
            (
                "occurred_at",
                "between",
                ["2026-08-08T10:01:00+00:00", "2026-08-08T10:03:00+00:00"],
                {"evt-b", "evt-c", "evt-d"},
            ),
        )
        for field, operator, value, expected in cases:
            with self.subTest(field=field, operator=operator):
                self.assertEqual(set(self.ids(self.advanced(field, operator, value))), expected)

    def test_json_missing_null_before_after_diff_and_changed_operators(self) -> None:
        self.assertEqual(
            self.ids(self.advanced("before.nullable", "exists")), ["evt-a"]
        )
        self.assertEqual(
            self.ids(self.advanced("before.nullable", "eq", None)), ["evt-a"]
        )
        self.assertEqual(
            set(self.ids(self.advanced("before.nullable", "not_exists"))),
            {"evt-b", "evt-c", "evt-d", "evt-e"},
        )
        self.assertEqual(
            self.ids(self.advanced("after.fan", "eq", "medium")), ["evt-a"]
        )
        self.assertEqual(
            self.ids(self.advanced("diff.target_temperature.delta", "lt", 0)),
            ["evt-a"],
        )
        self.assertEqual(
            self.ids(self.advanced("after.target_temperature", "changed")), ["evt-a"]
        )
        self.assertEqual(
            set(self.ids(self.advanced("after.target_temperature", "not_changed"))),
            {"evt-b", "evt-c", "evt-d", "evt-e"},
        )

    def test_nested_and_or_period_and_global_search(self) -> None:
        filters = {
            "advanced": {
                "logic": "and",
                "conditions": [
                    {
                        "logic": "or",
                        "conditions": [
                            {"field": "category", "operator": "eq", "value": "transmission"},
                            {"field": "category", "operator": "eq", "value": "external"},
                        ],
                    },
                    {"field": "mode", "operator": "in", "value": ["dry", "off"]},
                ],
            }
        }
        self.assertEqual(set(self.ids(filters)), {"evt-b", "evt-c"})
        self.assertEqual(
            set(
                self.ids(
                    {
                        "period": {
                            "start": "2026-08-08T10:01:00+00:00",
                            "end": "2026-08-08T10:02:00+00:00",
                        }
                    }
                )
            ),
            {"evt-b", "evt-c"},
        )
        self.assertEqual(self.ids({"search": "minimum_time"}), ["evt-e"])
        self.assertEqual(self.ids({"search": "100%"}), ["evt-e"])

    def test_predicate_reuses_full_filter_semantics_without_pagination(self) -> None:
        filters = {
            "categories": ["state", "external"],
            "advanced": {
                "logic": "or",
                "conditions": [
                    {"field": "humidity", "operator": "gte", "value": 70},
                    {"field": "is_external", "operator": "eq", "value": True},
                ],
            },
        }
        where, params = query.compile_event_predicate(filters)
        self.assertTrue(where.startswith(" WHERE "))
        self.assertNotIn("ORDER BY", where)
        self.assertNotIn("LIMIT", where)
        count = self.db.execute(
            "SELECT COUNT(*) FROM events AS e" + where, params
        ).fetchone()[0]
        self.assertEqual(count, 2)
        self.assertEqual(query.compile_event_predicate(None), ("", []))

    def test_stable_bidirectional_cursor_and_new_insert(self) -> None:
        filters = {"categories": ["state", "transmission", "external", "decision"]}
        fingerprint = query.fingerprint_filters(filters)
        first = self.run_query(filters, limit=2)
        self.assertEqual([row["event_id"] for row in first[:2]], ["evt-e", "evt-d"])
        older = query.encode_cursor(
            first[1]["occurred_at"], first[1]["event_id"], "older", fingerprint
        )

        self.insert(
            self.event(
                event_id="evt-z",
                occurred_at="2026-08-08T10:05:00+00:00",
                category="state",
                summary="Evento novo",
                fingerprint="fp-z",
            )
        )
        self.db.commit()
        next_page = self.run_query(filters, cursor=older, limit=2)
        self.assertEqual([row["event_id"] for row in next_page[:2]], ["evt-c", "evt-b"])
        self.assertNotIn("evt-z", [row["event_id"] for row in next_page])

        newer = query.encode_cursor(
            "2026-08-08T10:02:00+00:00", "evt-c", "newer", fingerprint
        )
        previous_page = self.run_query(
            filters, cursor=newer, limit=2, direction="newer"
        )
        # For newer pages the extra has-more sentinel sorts first after the
        # ascending inner page is restored to timeline order. The storage layer
        # deliberately discards that first row before returning the page.
        self.assertEqual(
            [row["event_id"] for row in previous_page[-2:]], ["evt-e", "evt-d"]
        )
        with self.assertRaises(query.QueryValidationError):
            self.run_query(filters, cursor=older, direction="newer")
        wrong_filter_cursor = query.encode_cursor(
            first[1]["occurred_at"], first[1]["event_id"], "older", "wrong"
        )
        with self.assertRaises(query.QueryValidationError):
            self.run_query(filters, cursor=wrong_filter_cursor)

    def test_limit_plus_one_is_explicit(self) -> None:
        sql, params = query.compile_event_query({}, limit=2)
        self.assertIn("LIMIT ?", sql)
        self.assertEqual(params[-1], 3)
        self.assertEqual(len(self.db.execute(sql, params).fetchall()), 3)

    def test_sql_injection_and_filter_complexity_are_rejected_or_bound(self) -> None:
        attack = "x%' OR 1=1 --"
        sql, params = query.compile_event_query(
            self.advanced("summary", "contains", attack), include_details=True
        )
        self.assertNotIn(attack, sql)
        self.assertTrue(any("OR 1=1" in str(value) for value in params))
        self.db.execute(sql, params).fetchall()
        self.assertEqual(
            self.db.execute(
                "SELECT COUNT(*) FROM sqlite_master WHERE type='table' AND name='events'"
            ).fetchone()[0],
            1,
        )
        with self.assertRaises(query.QueryValidationError):
            query.compile_event_query(
                self.advanced("summary) OR 1=1 --", "eq", "x")
            )
        with self.assertRaises(query.QueryValidationError):
            query.compile_event_query(self.advanced("summary", "union select", "x"))
        with self.assertRaises(query.QueryValidationError):
            query.compile_event_query({"sql": "1=1"})
        with self.assertRaises(query.QueryValidationError):
            query.decode_cursor("not-a-valid-cursor")

        too_deep: dict = {"field": "category", "operator": "eq", "value": "state"}
        for _ in range(7):
            too_deep = {"logic": "and", "conditions": [too_deep]}
        with self.assertRaises(query.QueryValidationError):
            query.compile_event_query({"advanced": too_deep})
        with self.assertRaises(query.QueryValidationError):
            query.compile_event_query(
                {
                    "advanced": {
                        "logic": "or",
                        "conditions": [
                            {"field": "category", "operator": "eq", "value": "state"}
                            for _ in range(101)
                        ],
                    }
                }
            )
        with self.assertRaises(query.QueryValidationError):
            query.compile_event_query({}, limit=251)


if __name__ == "__main__":
    unittest.main()
