"""Release guards for Home Assistant and non-regression contracts."""

from __future__ import annotations

import ast
import hashlib
import json
from pathlib import Path
import unittest

import yaml

from _bootstrap import COMPONENT, REPOSITORY


class StaticContractTests(unittest.TestCase):
    def test_protected_esphome_and_aux_files_match_recovery_baseline(self) -> None:
        expected = {
            "esphome/esp8266.yaml": "82916041c4a1cb7574a3177af4b0ecfc3887f771e3bbb12c9adf6192b42c43e0",
            "esphome/components/elgin_aux/elgin_aux.cpp": "6dbc4d2e02ba6e2b77a9263af00b13567fe9a41e08e97feab2b9c04b55f17e5c",
            "esphome/components/elgin_aux/elgin_aux.h": "181cf85f589a35a6e915b87fae2daae07c27593de602e04b22596d9ff2499c93",
            "esphome/components/elgin_aux/elgin_aux_protocol.cpp": "4a9f54ddcca6a5d980519c4ce3ed040df69f724bd0efbd1ff8ae8651b5f77cdb",
            "esphome/components/elgin_aux/elgin_aux_protocol.h": "1c33974fdb92ca485b7debe7cf6668daf8ba5f0fa2b14270607276bdba2bf593",
        }
        for relative, digest in expected.items():
            with self.subTest(path=relative):
                content = (REPOSITORY / relative).read_bytes()
                self.assertEqual(hashlib.sha256(content).hexdigest(), digest)

    def test_supervisor_still_has_one_full_state_action(self) -> None:
        package = (REPOSITORY / "packages/elgin_supervisor_climatico.yaml").read_text()
        self.assertEqual(
            package.count("action: esphome.esp8266_elgin_send_state"), 1
        )

    def test_supervisor_diff_is_diagnostic_only_after_structural_normalization(self) -> None:
        class HALoader(yaml.SafeLoader):
            pass

        HALoader.add_multi_constructor(
            "!",
            lambda loader, _suffix, node: loader.construct_scalar(node)
            if isinstance(node, yaml.ScalarNode)
            else loader.construct_sequence(node)
            if isinstance(node, yaml.SequenceNode)
            else loader.construct_mapping(node),
        )
        current = yaml.load(
            (REPOSITORY / "packages/elgin_supervisor_climatico.yaml").read_text(),
            Loader=HALoader,
        )
        def without_diagnostics(value):
            if isinstance(value, list):
                return [
                    without_diagnostics(item)
                    for item in value
                    if not (
                        isinstance(item, dict)
                        and item.get("event")
                        == "elgin_supervisor_diagnostic_event"
                    )
                ]
            if isinstance(value, dict):
                return {
                    key: without_diagnostics(item)
                    for key, item in value.items()
                    if key != "diagnostico_evaluation_id"
                }
            return value

        normalized = without_diagnostics(current)
        canonical = json.dumps(
            normalized,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        )
        self.assertEqual(
            "24a819d0aadb822fa27ec318a95799155c0feb25395606a90d0002465db0a855",
            hashlib.sha256(canonical.encode()).hexdigest(),
        )

    def test_diagnostic_power_payload_uses_unambiguous_top_level_keys(self) -> None:
        class HALoader(yaml.SafeLoader):
            pass

        HALoader.add_multi_constructor(
            "!",
            lambda loader, _suffix, node: loader.construct_scalar(node)
            if isinstance(node, yaml.ScalarNode)
            else loader.construct_sequence(node)
            if isinstance(node, yaml.SequenceNode)
            else loader.construct_mapping(node),
        )
        package = yaml.load(
            (REPOSITORY / "packages/elgin_supervisor_climatico.yaml").read_text(),
            Loader=HALoader,
        )
        payloads: list[dict] = []

        def collect(value) -> None:
            if isinstance(value, list):
                for item in value:
                    collect(item)
            elif isinstance(value, dict):
                if value.get("event") == "elgin_supervisor_diagnostic_event":
                    payloads.append(value.get("event_data", {}))
                for item in value.values():
                    collect(item)

        collect(package)
        self.assertGreater(len(payloads), 10)
        self.assertTrue(all("power" not in payload for payload in payloads))
        full_state = [
            payload
            for payload in payloads
            if payload.get("stage")
            in {
                "transmission_requested",
                "transmission_suppressed",
                "transmission_accepted_by_software",
            }
            and payload.get("function") == "full_state"
        ]
        self.assertEqual(3, len(full_state))
        self.assertTrue(all("power_state" in payload for payload in full_state))
        self.assertTrue(all("power" in payload.get("desired", {}) for payload in full_state))

    def test_websocket_uses_current_schema_and_admin_contract(self) -> None:
        source = (COMPONENT / "websocket.py").read_text()
        tree = ast.parse(source)
        schema = next(
            node
            for node in tree.body
            if isinstance(node, ast.FunctionDef) and node.name == "_schema"
        )
        self.assertFalse(
            any(
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "Schema"
                for node in ast.walk(schema)
            )
        )
        self.assertNotIn("connection.require_admin", source)
        admin_handlers = {
            "ws_delete_observation",
            "ws_update_settings",
            "ws_clear_events",
            "ws_run_cleanup",
            "ws_reevaluate_anomalies",
        }
        functions = {
            node.name: node
            for node in tree.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        for name in admin_handlers:
            decorators = [ast.unparse(item) for item in functions[name].decorator_list]
            self.assertIn("websocket_api.require_admin", decorators)

    def test_custom_integration_translations_are_self_contained(self) -> None:
        translations = COMPONENT / "translations"
        english = json.loads((translations / "en.json").read_text())
        portuguese = json.loads((translations / "pt-BR.json").read_text())
        self.assertEqual(set(english), set(portuguese))
        self.assertFalse((COMPONENT / "strings.json").exists())

    def test_dashboard_has_one_canonical_diagnostic_view(self) -> None:
        dashboard = (REPOSITORY / "Dashboards/dashboard_supervisor.yaml").read_text()
        self.assertEqual(dashboard.count("path: diagnostico"), 1)
        self.assertEqual(
            dashboard.count("type: custom:elgin-supervisor-diagnostico-card"), 1
        )
        self.assertIn("columns: 48", dashboard)

    def test_runtime_cleanup_and_anomaly_lifecycle_are_not_startup_snapshots(self) -> None:
        manager = (COMPONENT / "manager.py").read_text()
        initializer = (COMPONENT / "__init__.py").read_text()
        self.assertIn("timedelta(minutes=5)", manager)
        self.assertIn("self.storage.async_cleanup_if_due()", manager)
        self.assertIn('if not result.get("skipped")', manager)
        self.assertIn("await self.anomaly.async_start()", manager)
        self.assertIn("await self.anomaly.async_stop()", manager)
        self.assertIn("await self.anomaly.async_apply_settings()", manager)
        self.assertIn("await runtime.manager.anomaly.async_apply_settings()", initializer)

    def test_panorama_reads_canonical_supervisor_entities(self) -> None:
        manager = (COMPONENT / "manager.py").read_text()
        self.assertIn(
            '"sensor.elgin_supervisor_estado_fisico_observado"', manager
        )
        self.assertNotIn('"mode_normalizado"', manager)
        for entity_id in (
            "sensor.elgin_supervisor_preset_efetivo_de_condicao_do_aquecimento",
            "sensor.elgin_supervisor_preset_efetivo_de_condicao_da_refrigeracao",
            "sensor.elgin_supervisor_preset_efetivo_de_condicao_da_desumidificacao",
            "sensor.elgin_supervisor_potencia_efetiva_de_aquecimento",
            "sensor.elgin_supervisor_potencia_efetiva_de_refrigeracao",
            "sensor.elgin_supervisor_potencia_efetiva_de_desumidificacao",
        ):
            self.assertIn(f'"{entity_id}"', manager)

    def test_diagnostic_failure_cannot_call_climate_or_esphome(self) -> None:
        service_call_files = [
            path.name
            for path in COMPONENT.glob("*.py")
            if "services.async_call" in path.read_text(errors="ignore")
        ]
        self.assertEqual(["anomaly.py"], service_call_files)
        anomaly = (COMPONENT / "anomaly.py").read_text()
        self.assertIn('"persistent_notification"', anomaly)
        self.assertIn('"notify"', anomaly)
        self.assertNotIn('"esphome",\n', anomaly)
        self.assertNotIn('"climate",\n', anomaly)
        package = (REPOSITORY / "packages/elgin_supervisor_climatico.yaml").read_text()
        self.assertNotIn("action: elgin_supervisor_diagnostico.", package)
        self.assertGreater(package.count("event: elgin_supervisor_diagnostic_event"), 0)

    def test_every_exposed_setting_has_a_runtime_or_frontend_consumer(self) -> None:
        tree = ast.parse((COMPONENT / "const.py").read_text())
        assignment = next(
            node
            for node in tree.body
            if isinstance(node, ast.AnnAssign)
            and getattr(node.target, "id", "") == "DEFAULT_OPTIONS"
        )
        keys = [ast.literal_eval(item) for item in assignment.value.keys]
        consumers = [
            path.read_text(errors="ignore")
            for path in COMPONENT.rglob("*")
            if path.suffix in {".py", ".js"}
            and path.name not in {"const.py", "models.py", "config_flow.py"}
        ]
        missing = [key for key in keys if not any(key in text for text in consumers)]
        self.assertEqual([], missing)

    def test_yaml_has_no_duplicate_mapping_keys_or_automation_ids(self) -> None:
        files = [
            REPOSITORY / "configuration.yaml",
            *(REPOSITORY / "packages").glob("*.yaml"),
            REPOSITORY / "Dashboards/dashboard_supervisor.yaml",
            COMPONENT / "services.yaml",
        ]

        def inspect(node, ids: list[str]) -> None:
            if isinstance(node, yaml.MappingNode):
                keys: list[str] = []
                for key, value in node.value:
                    if isinstance(key, yaml.ScalarNode):
                        self.assertNotIn(key.value, keys)
                        keys.append(key.value)
                        if key.value in {"id", "unique_id"} and isinstance(
                            value, yaml.ScalarNode
                        ):
                            ids.append(value.value)
                    inspect(value, ids)
            elif isinstance(node, yaml.SequenceNode):
                for value in node.value:
                    inspect(value, ids)

        for path in files:
            with self.subTest(path=path):
                ids: list[str] = []
                inspect(yaml.compose(path.read_text()), ids)
                self.assertEqual(len(ids), len(set(ids)))


if __name__ == "__main__":
    unittest.main()
