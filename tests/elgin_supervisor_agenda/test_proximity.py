"""Behavioral coverage for continuous windows and their reset boundaries."""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timedelta, timezone
import unittest

from _agenda_bootstrap import load


ProximityTracker = load("proximity").ProximityTracker
EPOCH = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)
LIMITS = {
    "heat": {"start": 18.0, "stop": 20.2},
    "cool": {"start": 26.0, "stop": 23.0},
    "dry": {"start": 63, "stop": 57, "minimum_temperature": 19.0},
}


class ProximityWindowTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tracker = ProximityTracker()
        self.preset = {
            "effective_id": "cool_example",
            "proximity": {"enabled": True, "temperature_margin": 0.5, "humidity_margin": 3, "minutes": 10},
        }

    def evaluate(self, mode="cool", value=25.5, seconds=0, **changes):
        arguments = {
            "mode": mode, "preset": self.preset, "limits": LIMITS[mode],
            "value": value, "temperature": 25, "allowed": True, "active": False,
            "now": EPOCH + timedelta(seconds=seconds), "monotonic_now": 1000 + seconds,
        }
        arguments.update(changes)
        return self.tracker.evaluate(**arguments)

    def test_cool_example_requires_the_entire_ten_minutes(self) -> None:
        initial = self.evaluate()
        self.assertEqual("counting", initial["status"])
        self.assertEqual((25.5, 26.0), (initial["lower"], initial["upper"]))
        self.assertEqual(600, initial["remaining_seconds"])
        self.assertEqual(EPOCH.isoformat(), initial["started_at"])
        self.assertEqual((EPOCH + timedelta(minutes=10)).isoformat(), initial["deadline"])
        pending = self.evaluate(value=25.9, seconds=599)
        self.assertFalse(pending["ready"])
        self.assertEqual(1, pending["remaining_seconds"])
        ready = self.evaluate(value=25.6, seconds=600)
        self.assertTrue(ready["ready"])
        self.assertEqual("ready", ready["status"])
        self.assertEqual(0, ready["remaining_seconds"])
        self.assertIsNone(self.tracker.next_deadline)

    def test_each_mode_uses_its_correct_open_and_closed_boundaries(self) -> None:
        cases = (
            ("cool", 25.499, "outside"), ("cool", 25.5, "counting"),
            ("cool", 25.999, "counting"), ("cool", 26.0, "normal"),
            ("heat", 18.501, "outside"), ("heat", 18.5, "counting"),
            ("heat", 18.001, "counting"), ("heat", 18.0, "normal"),
            ("dry", 59.999, "outside"), ("dry", 60, "counting"),
            ("dry", 62.999, "counting"), ("dry", 63, "normal"),
        )
        for mode, value, expected in cases:
            with self.subTest(mode=mode, value=value):
                self.tracker.reset()
                self.assertEqual(expected, self.evaluate(mode=mode, value=value)["status"])

    def test_normal_start_wins_before_timer_expires(self) -> None:
        for mode, near, threshold in (("cool", 25.5, 26), ("heat", 18.5, 18), ("dry", 60, 63)):
            with self.subTest(mode=mode):
                self.evaluate(mode=mode, value=near)
                normal = self.evaluate(mode=mode, value=threshold, seconds=1)
                self.assertEqual("normal", normal["status"])
                self.assertIsNone(normal["started_at"])
                restarted = self.evaluate(mode=mode, value=near, seconds=2)
                self.assertEqual(600, restarted["remaining_seconds"])

    def test_leaving_then_returning_restarts_the_full_window(self) -> None:
        self.evaluate()
        self.assertEqual("outside", self.evaluate(value=25.4, seconds=599)["status"])
        restarted = self.evaluate(seconds=600)
        self.assertFalse(restarted["ready"])
        self.assertEqual(600, restarted["remaining_seconds"])
        self.assertTrue(self.evaluate(seconds=1200)["ready"])

    def test_sensor_events_catch_short_excursions_between_evaluations(self) -> None:
        for excursion in (25.4, 26, "unavailable", None, float("nan"), float("inf")):
            with self.subTest(excursion=excursion):
                self.tracker.reset()
                self.evaluate()
                self.tracker.observe("temperature", excursion)
                self.tracker.observe("temperature", 25.5)
                result = self.evaluate(seconds=600)
                self.assertFalse(result["ready"])
                self.assertEqual(600, result["remaining_seconds"])

    def test_event_inside_band_preserves_the_window_and_unrelated_sensor_is_ignored(self) -> None:
        self.evaluate()
        self.tracker.observe("temperature", 25.9)
        self.tracker.observe("humidity", "unavailable")
        self.assertTrue(self.evaluate(seconds=600)["ready"])

    def test_heat_and_dry_can_complete_their_own_windows(self) -> None:
        for mode, value, metric in (("heat", 18.5, "temperature"), ("dry", 60, "humidity")):
            with self.subTest(mode=mode):
                first = self.evaluate(mode=mode, value=value)
                self.assertEqual(metric, first["metric"])
                self.assertTrue(self.evaluate(mode=mode, value=value, seconds=600)["ready"])

    def test_dry_floor_is_required_even_when_humidity_is_at_normal_start(self) -> None:
        for value in (60, 63):
            with self.subTest(value=value):
                self.assertEqual("blocked", self.evaluate(mode="dry", value=value, temperature=18.9)["status"])
                expected = "counting" if value == 60 else "normal"
                self.assertEqual(expected, self.evaluate(mode="dry", value=value, temperature=19)["status"])

    def test_dry_floor_excursion_and_humidity_excursion_reset_independently(self) -> None:
        for metric, excursion in (("temperature", 18.9), ("temperature", "unknown"), ("humidity", 59), ("humidity", 63)):
            with self.subTest(metric=metric, excursion=excursion):
                self.tracker.reset()
                self.evaluate(mode="dry", value=60)
                self.tracker.observe(metric, excursion)
                self.tracker.observe(metric, 25 if metric == "temperature" else 60)
                self.assertEqual(600, self.evaluate(mode="dry", value=60, seconds=600)["remaining_seconds"])

    def test_block_active_disable_invalid_or_outside_discards_elapsed_time(self) -> None:
        cases = (
            ({"allowed": False}, "blocked"), ({"active": True}, "active"),
            ({"value": "unknown"}, "invalid"), ({"value": float("nan")}, "invalid"),
            ({"value": float("inf")}, "invalid"), ({"value": 25.4}, "outside"),
            ({"preset": {"effective_id": "legacy"}}, "disabled"),
        )
        for changes, status in cases:
            with self.subTest(status=status, changes=changes):
                self.tracker.reset()
                self.evaluate()
                self.assertEqual(status, self.evaluate(seconds=599, **changes)["status"])
                result = self.evaluate(seconds=600)
                self.assertFalse(result["ready"])
                self.assertEqual(600, result["remaining_seconds"])

    def test_new_preset_limits_margin_or_duration_do_not_reuse_elapsed_time(self) -> None:
        cases = (
            {"preset": {**self.preset, "effective_id": "another_preset"}},
            {"limits": {"start": 25.9, "stop": 23}},
            {"limits": {"start": 26, "stop": 23.1}},
            {"preset": {**self.preset, "proximity": {**self.preset["proximity"], "temperature_margin": 0.6}}},
            {"preset": {**self.preset, "proximity": {**self.preset["proximity"], "minutes": 11}}},
        )
        for changes in cases:
            with self.subTest(changes=changes):
                self.tracker.reset()
                self.evaluate()
                result = self.evaluate(seconds=599, **changes)
                duration = changes.get("preset", self.preset)["proximity"]["minutes"] * 60
                self.assertEqual(duration, result["remaining_seconds"])
                self.assertFalse(result["ready"])

    def test_dry_floor_change_restarts_window(self) -> None:
        self.evaluate(mode="dry", value=60)
        changed = self.evaluate(mode="dry", value=60, seconds=599, limits={**LIMITS["dry"], "minimum_temperature": 20})
        self.assertEqual(600, changed["remaining_seconds"])

    def test_invalid_effective_band_never_starts_counting(self) -> None:
        for margin in (0, -1, 3, 4, float("nan")):
            with self.subTest(margin=margin):
                preset = deepcopy(self.preset)
                preset["proximity"]["temperature_margin"] = margin
                self.assertEqual("invalid", self.evaluate(preset=preset)["status"])
        for minutes in (0, 1441, float("inf")):
            with self.subTest(minutes=minutes):
                preset = deepcopy(self.preset)
                preset["proximity"]["minutes"] = minutes
                self.assertEqual("invalid", self.evaluate(preset=preset)["status"])

    def test_restart_loses_timer_and_never_restores_ready_from_persistence(self) -> None:
        self.evaluate()
        self.assertTrue(self.evaluate(seconds=600)["ready"])
        self.tracker = ProximityTracker()
        fresh = self.evaluate(seconds=700)
        self.assertEqual("counting", fresh["status"])
        self.assertEqual(600, fresh["remaining_seconds"])

    def test_windows_are_independent_and_reset_supports_one_or_all_modes(self) -> None:
        self.evaluate()
        self.evaluate(mode="dry", value=60, seconds=100)
        self.assertEqual(1600, self.tracker.next_deadline)
        self.tracker.reset("cool")
        self.assertEqual(1700, self.tracker.next_deadline)
        self.assertTrue(self.evaluate(mode="dry", value=60, seconds=700)["ready"])
        self.assertFalse(self.evaluate(seconds=700)["ready"])
        self.tracker.reset()
        self.assertIsNone(self.tracker.next_deadline)

    def test_wall_clock_adjustment_cannot_complete_window_early(self) -> None:
        self.evaluate()
        jumped = self.evaluate(seconds=60, now=EPOCH + timedelta(days=1))
        self.assertFalse(jumped["ready"])
        self.assertEqual(540, jumped["remaining_seconds"])
        ready = self.evaluate(seconds=600, now=EPOCH - timedelta(days=1))
        self.assertTrue(ready["ready"])


if __name__ == "__main__":
    unittest.main()
