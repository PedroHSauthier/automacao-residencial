"""Render the actual HA demand templates against normal and anticipated cycles."""

from copy import deepcopy
from itertools import product
import math
import unittest

from jinja2 import Environment
import yaml

from _agenda_bootstrap import REPOSITORY


class HALoader(yaml.SafeLoader):
    pass


HALoader.add_multi_constructor("!", lambda loader, suffix, node: loader.construct_scalar(node))

MODE_DATA = {
    "heat": ("aquecimento", "Aquecimento", "aquecimento_habilitado", "aquecimento", 18.0, 20.2, 18.5),
    "cool": ("refrigeracao", "Refrigeração", "refrigeracao_habilitada", "refrigeracao", 26.0, 23.0, 25.5),
    "dry": ("desumidificacao", "Desumidificação", "desumidificacao_habilitada", "desumidificacao", 63, 57, 60),
}


def mappings(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from mappings(child)
    elif isinstance(value, list):
        for child in value:
            yield from mappings(child)


class DemandTemplateTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        package = yaml.load((REPOSITORY / "packages/elgin_supervisor_climatico.yaml").read_text(encoding="utf-8"), Loader=HALoader)
        by_id = {item.get("default_entity_id"): item for item in mappings(package)}
        cls.templates = {
            mode: by_id[f"binary_sensor.elgin_supervisor_demanda_{data[0]}"]
            for mode, data in MODE_DATA.items()
        }
        cls.environment = Environment()

    def ready(self, mode):
        _, _, _, _, start, stop, near = MODE_DATA[mode]
        return {"ready": True, "threshold": start, "stop": stop,
                "lower": start if mode == "heat" else near,
                "upper": near if mode == "heat" else start,
                "minimum_temperature": 19.0}

    def render(self, mode, value, *, active=False, proximity=None, enabled=True, agenda_allowed=True, power="Normal", temperature=25):
        _, treatment, control, power_name, start, stop, _ = MODE_DATA[mode]
        state_values = {
            "sensor.sensor_temperatura_sensor_dedicado": str(temperature if mode == "dry" else value),
            "sensor.sensor_umidade_sensor_dedicado": str(value if mode == "dry" else 55),
            "input_select.elgin_supervisor_tratamento_ativo": treatment if active else "Nenhum",
            f"input_boolean.elgin_supervisor_{control}": "on" if enabled else "off",
            f"sensor.elgin_supervisor_potencia_efetiva_de_{power_name}": power,
        }
        attrs = {
            "sensor.elgin_supervisor_limites_efetivos": {
                f"{power_name}_inicio": start, f"{power_name}_fim": stop,
                "desumidificacao_temperatura_minima": 19.0,
            },
            "sensor.elgin_supervisor_agenda_politica": {"modes": {mode: agenda_allowed}},
            "sensor.elgin_supervisor_presets_de_condicao": {"modes": {mode: {"proximity_state": proximity or {}}}},
        }
        def is_number(value):
            try:
                return math.isfinite(float(value))
            except (TypeError, ValueError):
                return False
        context = {
            "states": lambda entity_id: state_values.get(entity_id, "unknown"),
            "state_attr": lambda entity_id, attribute: attrs.get(entity_id, {}).get(attribute),
            "is_state": lambda entity_id, expected: state_values.get(entity_id) == expected,
            "is_number": is_number,
        }
        node = self.templates[mode]
        available = self.environment.from_string(node["availability"]).render(context).strip() == "True"
        if not available:
            return None
        return self.environment.from_string(node["state"]).render(context).strip() == "True"

    def test_disabled_or_missing_proximity_preserves_every_normal_and_hysteresis_boundary(self):
        for mode, (_, _, _, _, start, stop, near) in MODE_DATA.items():
            values = {start - 0.1, start, start + 0.1, stop - 0.1, stop, stop + 0.1, near}
            for value, active, enabled, agenda_allowed, power in product(values, (False, True), (False, True), (False, True), ("Normal", "Desativado")):
                with self.subTest(mode=mode, value=value, active=active, enabled=enabled, agenda=agenda_allowed, power=power):
                    normal = value < stop if active else value <= start
                    if mode != "heat":
                        normal = value > stop if active else value >= start
                    expected = enabled and agenda_allowed and power != "Desativado" and normal
                    for proximity in (None, {"enabled": False, "ready": False}):
                        self.assertEqual(expected, self.render(mode, value, active=active, enabled=enabled, agenda_allowed=agenda_allowed, power=power, proximity=proximity))

    def test_ready_starts_only_while_inside_the_current_band(self):
        for mode, (_, _, _, _, start, _, near) in MODE_DATA.items():
            with self.subTest(mode=mode):
                p = self.ready(mode)
                self.assertFalse(self.render(mode, near, proximity={**p, "ready": False}))
                self.assertTrue(self.render(mode, near, proximity=p))
                outside = near + 0.1 if mode == "heat" else near - 0.1
                self.assertFalse(self.render(mode, outside, proximity=p))
                self.assertTrue(self.render(mode, start, proximity={**p, "ready": False}))

    def test_ready_never_overrides_mode_agenda_or_power_permission(self):
        for mode, data in MODE_DATA.items():
            for overrides in ({"enabled": False}, {"agenda_allowed": False}, {"power": "Desativado"}):
                with self.subTest(mode=mode, overrides=overrides):
                    self.assertFalse(self.render(mode, data[-1], proximity=self.ready(mode), **overrides))

    def test_stale_threshold_stop_or_floor_cannot_use_readiness_from_old_limits(self):
        for mode, data in MODE_DATA.items():
            keys = ("threshold", "stop", "minimum_temperature") if mode == "dry" else ("threshold", "stop")
            for key in keys:
                with self.subTest(mode=mode, key=key):
                    stale = self.ready(mode)
                    stale[key] += 0.1
                    self.assertFalse(self.render(mode, data[-1], proximity=stale))

    def test_ready_never_extends_an_active_cycle_past_its_normal_stop(self):
        for mode, data in MODE_DATA.items():
            stop = data[-2]
            for value in (stop, stop + 0.1 if mode == "heat" else stop - 0.1):
                with self.subTest(mode=mode, value=value):
                    p = self.ready(mode)
                    # Even a stale snapshot whose band contains this reading
                    # must not enter the start branch for an active cycle.
                    p.update(lower=value - 1, upper=value + 1)
                    self.assertFalse(self.render(mode, value, active=True, proximity=p))

    def test_dry_floor_and_sensor_availability_remain_mandatory(self):
        for active in (False, True):
            self.assertFalse(self.render("dry", 60, active=active, proximity=self.ready("dry"), temperature=18.9))
            self.assertIsNone(self.render("dry", 60, active=active, proximity=self.ready("dry"), temperature="unavailable"))
        for mode in MODE_DATA:
            self.assertIsNone(self.render(mode, "unavailable", proximity=self.ready(mode)))


if __name__ == "__main__":
    unittest.main()
