"""Incremental release tests for migrations, authorization and Recorder privacy."""

from __future__ import annotations

import ast
from pathlib import Path
import unittest

from _bootstrap import COMPONENT, load


models = load("models")
migrations = load("migrations")

ANOMALY_TYPES = tuple(models.DiagnosticSettings().anomaly_enabled_types)


class MigrationTests(unittest.TestCase):
    def test_complete_v1_options_are_preserved_and_repeatable(self) -> None:
        defaults = models.DiagnosticSettings().as_dict()
        legacy = {
            "intensive_mode": True,
            "retention_absolute_days": 91,
            "retention_error_days": 44,
            "retention_full_days": 13,
            "beep_window_before_seconds": 321,
            "beep_window_after_seconds": 654,
            "multiple_full_frames_limit": 7,
            "multiple_full_frames_window_seconds": 222,
            "close_transmissions_seconds": 9,
            "identical_frame_window_seconds": 111,
            "logical_concurrency_seconds": 17,
            "external_reaction_window_seconds": 88,
            "oscillation_window_seconds": 777,
            "oscillation_min_changes": 9,
            "localtuya_confirmation_seconds": 41,
            "notifications_enabled": True,
            "notification_min_severity": "error",
            "notification_cooldown_seconds": 1_234,
            "notify_service": "notify.mobile_app_quarto",
            "compaction_enabled": False,
            "max_database_mb": 333,
            "default_page_size": 75,
            "technical_details_enabled": True,
            "visible_categories": ["transmission", "external"],
            "enabled_anomaly_types": [
                "ir.identical_frame_retransmitted",
                "decision.oscillation",
            ],
        }
        first = migrations.migrate_options_v1(
            legacy, defaults, ANOMALY_TYPES
        )
        second = migrations.migrate_options_v1(
            first, defaults, ANOMALY_TYPES
        )
        self.assertEqual(first, second)
        self.assertEqual("intensive", first["capture_mode"])
        self.assertEqual(9, first["anomaly_close_commands_seconds"])
        self.assertEqual(111, first["anomaly_repeated_command_window_seconds"])
        self.assertEqual(111, first["anomaly_duplicate_window_seconds"])
        self.assertEqual(7, first["anomaly_audible_burst_count"])
        self.assertEqual(222, first["anomaly_audible_burst_seconds"])
        self.assertEqual(88, first["external_observation_window_seconds"])
        self.assertEqual(777, first["anomaly_oscillation_window_seconds"])
        self.assertEqual(9, first["anomaly_oscillation_min_changes"])
        self.assertEqual(41, first["localtuya_confirmation_window_seconds"])
        self.assertEqual("notify.mobile_app_quarto", first["notification_service"])
        self.assertEqual(75, first["interface_items_per_page"])
        self.assertEqual(
            ["repeated_commands", "decision_oscillation"],
            first["anomaly_enabled_types"],
        )
        self.assertEqual(
            "migrado_categorias_visiveis", first["default_saved_filter_id"]
        )
        models.DiagnosticSettings.from_options(first).validate()

    def test_legacy_empty_anomaly_list_means_all_but_v2_empty_stays_empty(self) -> None:
        defaults = models.DiagnosticSettings().as_dict()
        legacy = migrations.migrate_options_v1(
            {"enabled_anomaly_types": []}, defaults, ANOMALY_TYPES
        )
        current = migrations.migrate_options_v1(
            {"anomaly_enabled_types": []}, defaults, ANOMALY_TYPES
        )
        self.assertEqual(list(ANOMALY_TYPES), legacy["anomaly_enabled_types"])
        self.assertEqual([], current["anomaly_enabled_types"])

    def test_registry_map_is_semantic_and_event_renames_to_important_event(self) -> None:
        self.assertEqual("important_event", migrations.LEGACY_ENTITY_MAP["event"])
        self.assertEqual("last_action", migrations.LEGACY_ENTITY_MAP["last_transmission"])
        self.assertNotIn("counters", migrations.LEGACY_ENTITY_MAP)
        self.assertIn("counters", migrations.LEGACY_RETIRED_KEYS)
        self.assertIn("force_cleanup", migrations.LEGACY_RETIRED_KEYS)
        self.assertEqual(
            set(migrations.LEGACY_ENTITY_DOMAINS),
            set(migrations.LEGACY_ENTITY_MAP) | set(migrations.LEGACY_RETIRED_KEYS),
        )

    def test_registry_migration_runs_before_platform_forward_and_checks_ownership(self) -> None:
        source = (COMPONENT / "__init__.py").read_text()
        self.assertLess(
            source.index("_async_migrate_registries(hass, entry)"),
            source.index("async_forward_entry_setups(entry, PLATFORMS)"),
        )
        self.assertIn("item.platform == DOMAIN", source)
        self.assertIn("item.config_entry_id == entry.entry_id", source)
        self.assertIn("async_get_device_by_identifier", source)
        self.assertIn("new_identifiers=identifiers", source)
        self.assertIn("if occupied is None or occupied.entity_id == current", source)


class SecurityAndPrivacyTests(unittest.TestCase):
    def test_no_destructive_button_or_service_remains(self) -> None:
        button = (COMPONENT / "button.py").read_text()
        services = (COMPONENT / "services.yaml").read_text()
        initializer = (COMPONENT / "__init__.py").read_text()
        self.assertNotIn('key="run_cleanup"', button)
        self.assertNotIn("run_cleanup:", services)
        self.assertNotIn(
            'hass.services.async_register(DOMAIN, "run_cleanup"', initializer
        )

    def test_destructive_websockets_are_admin_only_and_confirmed(self) -> None:
        source = (COMPONENT / "websocket.py").read_text()
        tree = ast.parse(source)
        functions = {
            node.name: node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for name, word in (
            ("ws_clear_events", "APAGAR"),
            ("ws_run_cleanup", "LIMPAR"),
        ):
            decorators = [
                ast.unparse(item) for item in functions[name].decorator_list
            ]
            self.assertIn("websocket_api.require_admin", decorators)
            body = ast.unparse(functions[name])
            self.assertIn(word, body)
        export_body = ast.unparse(functions["ws_create_export"])
        self.assertIn("diagnostic_package", export_body)
        self.assertIn("is_admin", export_body)

    def test_last_action_recorder_attributes_use_exact_allowlist(self) -> None:
        source = (COMPONENT / "sensor.py").read_text()
        tree = ast.parse(source)
        method = next(
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef)
            and node.name == "extra_state_attributes"
        )
        sets = [
            ast.literal_eval(node)
            for node in ast.walk(method)
            if isinstance(node, ast.Set)
            and all(isinstance(item, ast.Constant) for item in node.elts)
        ]
        action_allowlist = next(
            value for value in sets if "transmission_id" in value
        )
        self.assertEqual(
            {
                "event_id",
                "occurred_at",
                "event_type",
                "summary",
                "function",
                "expected_audibility",
                "audibility",
                "correlation_id",
                "transmission_id",
            },
            action_allowlist,
        )
        forbidden = {
            "raw_event",
            "service_data",
            "before_json",
            "after_json",
            "diff_json",
            "details_json",
            "user_id",
            "context_id",
        }
        self.assertTrue(forbidden.isdisjoint(action_allowlist))


if __name__ == "__main__":
    unittest.main()
