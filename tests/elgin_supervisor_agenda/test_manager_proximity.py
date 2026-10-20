"""Run the actual Agenda pipeline with a fake HA clock, bus and state registry."""

from copy import deepcopy
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, Mock, patch

from _agenda_bootstrap import load


manager_module = load("manager")
presets_module = load("presets")


class ManagerProximityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.seconds = 0
        self.epoch = datetime(2026, 10, 2, 12, tzinfo=timezone.utc)
        self.state_values = {
            "sensor.sensor_temperatura_sensor_dedicado": "25.5",
            "sensor.sensor_umidade_sensor_dedicado": "60",
            "input_select.elgin_supervisor_tratamento_ativo": "Nenhum",
            "input_boolean.elgin_supervisor_habilitado": "on",
            **{entity: "on" for entity in manager_module.PROXIMITY_MODE_CONTROLS.values()},
            **{entity: "Normal" for entity in manager_module.PROXIMITY_POWER_ENTITIES.values()},
        }
        self.hass = SimpleNamespace(
            states=SimpleNamespace(get=self.state),
            bus=SimpleNamespace(async_fire=Mock(), async_listen=Mock(side_effect=lambda *args: Mock())),
            services=SimpleNamespace(async_call=AsyncMock()),
        )
        self.scheduled = []
        self.clock_patch = patch.object(manager_module, "monotonic", lambda: 1000 + self.seconds)
        self.datetime_patch = patch.object(manager_module.dt_util, "now", lambda: self.epoch + timedelta(seconds=self.seconds))
        self.schedule_patch = patch.object(manager_module, "async_call_later", self.schedule)
        for item in (self.clock_patch, self.datetime_patch, self.schedule_patch):
            item.start()
            self.addCleanup(item.stop)
        self.manager = manager_module.AgendaManager(self.hass, "test", "Test")
        self.manager.presets = presets_module.default_presets(self.hass)
        self.manager.base_presets = {"heat": "heat_equilibrio", "cool": "cool_economia", "dry": "dry_equilibrio"}
        self.cool_preset = next(item for item in self.manager.presets if item["id"] == "cool_economia")
        self.cool_preset["proximity"]["enabled"] = True
        self.manager._power_load({"power_rules": []})
        self.listener = Mock()
        self.manager.async_add_listener(self.listener)

    def state(self, entity_id):
        value = self.state_values.get(entity_id)
        return None if value is None else SimpleNamespace(state=value, attributes={})

    def schedule(self, hass, seconds, callback):
        cancel = Mock()
        self.scheduled.append({"delay": seconds, "callback": callback, "cancel": cancel})
        return cancel

    def proximity(self, mode="cool"):
        return self.manager.preset_state["modes"][mode]["proximity_state"]

    async def test_deadline_wakes_without_sensor_changes_and_does_not_write_or_send_commands(self):
        await self.manager.async_evaluate()
        self.assertEqual("counting", self.proximity()["status"])
        self.assertEqual(1, len(self.scheduled))
        self.assertEqual(600, self.scheduled[0]["delay"])
        self.seconds = 600
        await self.scheduled[0]["callback"](None)
        self.assertTrue(self.proximity()["ready"])
        self.assertIsNone(self.manager._proximity_due)
        self.assertIsNone(self.manager._unsub_proximity)
        self.manager.store.async_save.assert_not_awaited()
        self.hass.services.async_call.assert_not_awaited()

    async def test_periodic_countdown_is_not_a_policy_change_or_an_extra_log(self):
        await self.manager.async_evaluate()
        revision = self.manager._revision
        calls = self.hass.bus.async_fire.call_count
        notified = self.listener.call_count
        self.seconds = 30
        await self.manager.async_evaluate()
        self.assertEqual(570, self.proximity()["remaining_seconds"])
        self.assertEqual(revision, self.manager._revision)
        self.assertEqual(calls, self.hass.bus.async_fire.call_count)
        self.assertEqual(notified, self.listener.call_count)
        self.assertEqual(1, len(self.scheduled))
        self.seconds = 600
        await self.scheduled[0]["callback"](None)
        self.assertGreater(self.manager._revision, revision)
        self.assertEqual(calls + 1, self.hass.bus.async_fire.call_count)

    async def test_event_sample_cancels_brief_excursion_even_after_live_state_has_returned(self):
        await self.manager.async_evaluate()
        original_timer = self.scheduled[0]
        self.seconds = 599
        # Registry already holds 25.5 again; only the event preserves the departure.
        event = SimpleNamespace(data={"entity_id": "sensor.sensor_temperatura_sensor_dedicado", "new_state": SimpleNamespace(state="25.4")})
        await self.manager._async_catalog_changed(event)
        original_timer["cancel"].assert_called_once()
        self.assertEqual(600, self.proximity()["remaining_seconds"])
        self.assertEqual(2199, self.manager._proximity_due)
        self.seconds = 600
        await self.manager.async_evaluate()
        self.assertFalse(self.proximity()["ready"])
        self.seconds = 1199
        await self.scheduled[-1]["callback"](None)
        self.assertTrue(self.proximity()["ready"])

    async def test_unload_cancels_timer_and_discards_all_transient_progress(self):
        await self.manager.async_evaluate()
        cancel = self.scheduled[0]["cancel"]
        self.manager._unsub_interval = Mock()
        self.manager._unsub_states = Mock()
        self.manager._unsub_transition = Mock()
        transition = self.manager._unsub_transition
        await self.manager.async_unload()
        cancel.assert_called_once()
        self.manager._unsub_interval.assert_called_once()
        self.manager._unsub_states.assert_called_once()
        transition.assert_called_once()
        self.assertIsNone(self.manager._proximity.next_deadline)
        self.assertIsNone(self.manager._unsub_proximity)
        self.assertIsNone(self.manager._proximity_due)

    async def test_other_mode_control_change_does_not_restart_cool_window(self):
        await self.manager.async_evaluate()
        self.seconds = 300
        event = SimpleNamespace(data={"entity_id": manager_module.PROXIMITY_MODE_CONTROLS["heat"], "new_state": SimpleNamespace(state="off")})
        await self.manager._async_catalog_changed(event)
        self.assertEqual(300, self.proximity()["remaining_seconds"])
        event = SimpleNamespace(data={"entity_id": manager_module.PROXIMITY_POWER_ENTITIES["dry"], "new_state": SimpleNamespace(state="Desativado")})
        await self.manager._async_catalog_changed(event)
        self.assertEqual(300, self.proximity()["remaining_seconds"])

    async def test_brief_supervisor_disable_cancels_timer_from_event_value(self):
        await self.manager.async_evaluate()
        self.seconds = 500
        # Even if it has already returned to on in the registry, reset first.
        event = SimpleNamespace(data={"entity_id": "input_boolean.elgin_supervisor_habilitado", "new_state": SimpleNamespace(state="off")})
        await self.manager._async_catalog_changed(event)
        self.assertEqual(600, self.proximity()["remaining_seconds"])

    async def test_effective_agenda_offsets_use_same_precision_as_yaml(self):
        await self.manager.async_evaluate()
        self.manager._evaluate_proximity({"start_offset": {"cool": 0.04}, "stop_offset": {"cool": 0.04}}, self.epoch)
        self.assertEqual(26.0, self.proximity()["threshold"])
        self.assertEqual(23.0, self.proximity()["stop"])
        self.seconds = 500
        self.manager._evaluate_proximity({"start_offset": {"cool": 0.14}}, self.epoch + timedelta(seconds=500))
        self.assertEqual(26.1, self.proximity()["threshold"])
        self.assertFalse(self.proximity()["ready"])

    async def test_invalid_limits_update_is_atomic_and_leaves_persisted_presets_valid(self):
        before_settings = deepcopy(self.manager.power_settings)
        before_presets = deepcopy(self.manager.presets)
        revisions = (self.manager._power_revision, self.manager._preset_revision)
        with self.assertRaises(presets_module.PresetValidationError):
            await self.manager.async_update_power_settings({
                "cycle_limits": {"cool": {"start": 26.0, "stop": 25.7}},
                "priorities": {"heat": 888},
            })
        self.assertEqual(before_settings, self.manager.power_settings)
        self.assertEqual(before_presets, self.manager.presets)
        self.assertEqual(revisions, (self.manager._power_revision, self.manager._preset_revision))
        self.manager.store.async_save.assert_not_awaited()

    async def test_valid_limits_update_still_mirrors_into_current_base_preset(self):
        await self.manager.async_update_power_settings({"cycle_limits": {"cool": {"start": 26.0, "stop": 24.8}}})
        self.assertEqual(24.8, self.cool_preset["stop"])
        self.assertTrue(self.cool_preset["proximity"]["enabled"])
        self.manager.store.async_save.assert_awaited_once()
        saved = self.manager.store.async_save.call_args.args[0]
        self.assertNotIn("proximity_state", repr(saved))
        presets_module.validate_preset(self.cool_preset, self.manager.presets)


if __name__ == "__main__":
    unittest.main()
