"""Compatibility and validation for opt-in proximity settings on existing presets."""

from copy import deepcopy
from types import SimpleNamespace
import unittest

from _agenda_bootstrap import load


presets = load("presets")


class PresetProximityTests(unittest.TestCase):
    def preset(self, mode="cool", **changes):
        base = {
            "id": f"{mode}_example", "name": "Example", "mode": mode, "level": 0,
            "start": 18 if mode == "heat" else 63 if mode == "dry" else 26,
            "stop": 20.2 if mode == "heat" else 57 if mode == "dry" else 23,
            "power_modifier": 1,
        }
        return presets.normalize_preset({**base, **changes})

    def test_old_presets_migrate_with_feature_disabled_and_values_preserved(self) -> None:
        for mode in ("heat", "cool", "dry"):
            with self.subTest(mode=mode):
                result = self.preset(mode)
                self.assertFalse(result["proximity"]["enabled"])
                self.assertEqual(1, result["power_modifier"])
                self.assertEqual(f"{mode}_example", result["id"])
                presets.validate_preset(result, [])
        hass = SimpleNamespace(states=SimpleNamespace(get=lambda _: None))
        catalog = presets.default_presets(hass)
        self.assertEqual(15, len(catalog))
        self.assertTrue(all(not item["proximity"]["enabled"] for item in catalog))

    def test_enable_is_independent_per_preset_and_mode(self) -> None:
        enabled = self.preset(proximity={"enabled": True})
        disabled = self.preset("heat")
        self.assertTrue(enabled["proximity"]["enabled"])
        self.assertFalse(disabled["proximity"]["enabled"])
        enabled["proximity"]["minutes"] = 99
        self.assertEqual(10, disabled["proximity"]["minutes"])

    def test_partial_old_client_update_keeps_existing_proximity_configuration(self) -> None:
        original = self.preset(proximity={"enabled": True, "temperature_margin": 0.7, "humidity_margin": 4, "minutes": 12})
        payload = {key: value for key, value in original.items() if key != "proximity"}
        payload["name"] = "Renamed"
        result = presets.normalize_preset(payload, existing=original)
        self.assertEqual(original["proximity"], result["proximity"])
        result = presets.normalize_preset({**payload, "proximity": {"minutes": 13}}, existing=original)
        self.assertEqual({**original["proximity"], "minutes": 13}, result["proximity"])
        self.assertEqual(12, original["proximity"]["minutes"])

    def test_temperature_tenths_humidity_and_minutes_integers_are_accepted(self) -> None:
        result = self.preset(proximity={"enabled": True, "temperature_margin": "0.1", "humidity_margin": "1", "minutes": "1"})
        presets.validate_preset(result, [])
        self.assertEqual({"enabled": True, "temperature_margin": 0.1, "humidity_margin": 1, "minutes": 1}, result["proximity"])

    def test_invalid_steps_ranges_nonfinite_and_types_are_rejected(self) -> None:
        invalid = (
            ("temperature_margin", 0.15), ("temperature_margin", -0.1), ("temperature_margin", 10.1),
            ("humidity_margin", 1.5), ("humidity_margin", -1), ("humidity_margin", 31),
            ("minutes", 1.5), ("minutes", 0), ("minutes", 1441),
            ("temperature_margin", float("nan")), ("humidity_margin", float("inf")),
            ("minutes", "invalid"), ("minutes", None), ("enabled", "unknown"),
        )
        for key, value in invalid:
            with self.subTest(key=key, value=value):
                with self.assertRaises(presets.PresetValidationError):
                    self.preset(proximity={key: value})
        for value in (None, [], "yes"):
            with self.subTest(proximity=value):
                with self.assertRaises(presets.PresetValidationError):
                    self.preset(proximity=value)

    def test_enabled_band_must_be_positive_and_inside_hysteresis(self) -> None:
        for mode, key, hysteresis in (("heat", "temperature_margin", 2.2), ("cool", "temperature_margin", 3), ("dry", "humidity_margin", 6)):
            for margin in (0, hysteresis, hysteresis + 1):
                with self.subTest(mode=mode, margin=margin):
                    preset = self.preset(mode, proximity={"enabled": True, key: margin})
                    with self.assertRaises(presets.PresetValidationError):
                        presets.validate_preset(preset, [])

    def test_disabled_does_not_restrict_existing_small_hysteresis(self) -> None:
        preset = self.preset(start=26, stop=25.8)
        presets.validate_preset(preset, [])
        self.assertFalse(preset["proximity"]["enabled"])

    def test_catalog_and_effective_snapshot_expose_copies_of_selected_settings(self) -> None:
        hass = SimpleNamespace(states=SimpleNamespace(get=lambda _: None))
        catalog = presets.default_presets(hass)
        selected = next(item for item in catalog if item["id"] == "cool_equilibrio")
        selected["proximity"] = {"enabled": True, "temperature_margin": 0.5, "humidity_margin": 3, "minutes": 7}
        bases = {mode: f"{mode}_equilibrio" for mode in ("heat", "cool", "dry")}
        before = deepcopy(catalog)
        snapshot = presets.calculate_preset_state(hass, catalog, bases, {}, 1)
        self.assertEqual(selected["proximity"], snapshot["modes"]["cool"]["proximity"])
        self.assertFalse(snapshot["modes"]["heat"]["proximity"]["enabled"])
        snapshot["modes"]["cool"]["proximity"]["minutes"] = 80
        exported = presets.public_catalog(catalog, bases)
        exported["presets"]["cool"][0]["proximity"]["minutes"] = 99
        self.assertEqual(before, catalog)


if __name__ == "__main__":
    unittest.main()
