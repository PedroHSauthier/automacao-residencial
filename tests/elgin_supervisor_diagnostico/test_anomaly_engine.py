"""Behavior tests for all configurable anomaly families."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import unittest

from _bootstrap import load


anomaly_module = load("anomaly")


ANOMALY_TYPES = (
    "commands_too_close",
    "repeated_commands",
    "decision_oscillation",
    "desired_state_divergence",
    "localtuya_not_confirmed",
    "external_change_reaction",
    "excessive_volume",
    "repeated_error",
    "critical_entity_unavailable",
)


class _Storage:
    def __init__(self) -> None:
        self.saved: list[dict] = []
        self.by_id: dict[str, dict] = {}

    async def async_upsert_anomaly(self, anomaly):
        item = dict(anomaly)
        self.saved.append(item)
        self.by_id[item["anomaly_id"]] = item
        return item

    async def async_get_anomaly(self, anomaly_id):
        item = self.by_id.get(anomaly_id)
        return dict(item) if item else None

    async def async_mark_anomaly_notified(self, anomaly_id, notified_at):
        if anomaly_id not in self.by_id:
            return False
        self.by_id[anomaly_id]["notified_at"] = notified_at
        return True

    async def async_count_by_types(self, _types, _since):
        return {}


class _Services:
    def __init__(self) -> None:
        self.calls: list[tuple] = []
        self.fail_domain: str | None = None

    async def async_call(self, domain, service, data, **kwargs):
        if domain == self.fail_domain:
            raise RuntimeError(f"falha simulada em {domain}")
        self.calls.append((domain, service, data, kwargs))


class _States:
    def __init__(self) -> None:
        self.values = {}

    def get(self, entity_id):
        return self.values.get(entity_id)


class _Manager:
    def __init__(self) -> None:
        self.settings = SimpleNamespace(
            anomalies_enabled=True,
            anomaly_enabled_types=ANOMALY_TYPES,
            anomaly_close_commands_seconds=2,
            anomaly_repeated_command_window_seconds=300,
            anomaly_oscillation_window_seconds=600,
            anomaly_oscillation_min_changes=4,
            anomaly_divergence_seconds=0.01,
            anomaly_volume_window_seconds=60,
            anomaly_volume_event_limit=1_000,
            anomaly_repeated_error_window_seconds=300,
            anomaly_repeated_error_count=3,
            anomaly_unavailable_seconds=0.01,
            anomaly_no_change_threshold=100,
            anomaly_duplicate_window_seconds=10,
            anomaly_audible_burst_seconds=20,
            anomaly_audible_burst_count=3,
            external_observation_window_seconds=60,
            anomaly_window_minutes=15,
            notifications_enabled=False,
            notification_types=ANOMALY_TYPES,
            notification_min_severity="warning",
            notification_cooldown_seconds=900,
            notification_persistent=True,
            notification_service="",
        )
        self.storage = _Storage()
        self.emitted: list[dict] = []
        self.tasks: set[asyncio.Task] = set()
        self.hass = SimpleNamespace(states=_States(), services=_Services())

    async def async_emit_anomaly(self, anomaly, *, source_event):
        self.emitted.append({"anomaly": anomaly, "source": source_event})

    def _spawn(self, coroutine, _name):
        task = asyncio.create_task(coroutine)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return task


def _event(index: int, **changes) -> dict:
    occurred = datetime(2026, 8, 8, 12, 0, tzinfo=timezone.utc) + timedelta(
        seconds=index
    )
    event = {
        "event_id": f"event-{index}",
        "occurred_at": occurred.isoformat(),
        "event_type": "state.changed",
        "severity": "info",
        "category": "state",
        "summary": "Evento",
        "correlation_id": "corr-1",
    }
    event.update(changes)
    return event


class AnomalyEngineTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self) -> None:
        self.manager = _Manager()
        self.engine = anomaly_module.AnomalyEngine(self.manager)

    async def asyncTearDown(self) -> None:
        await self.engine.async_stop()
        for task in tuple(self.manager.tasks):
            task.cancel()
        if self.manager.tasks:
            await asyncio.gather(*self.manager.tasks, return_exceptions=True)

    async def test_close_repeated_command_and_external_reaction_are_distinct(self) -> None:
        await self.engine.async_process(
            _event(0, is_external=True, event_type="localtuya.external_or_indeterminate")
        )
        first = _event(
            1,
            event_type="transmission.requested_by_ha",
            category="transmission",
            action_domain="esphome",
            action_name="esp8266_elgin_send_state",
            desired_json={"mode": "dry", "target_temperature": 22},
        )
        second = _event(2, **{key: value for key, value in first.items() if key not in {"event_id", "occurred_at"}})
        await self.engine.async_process(first)
        result = await self.engine.async_process(second)
        types = {item["anomaly_type"] for item in result}
        self.assertEqual(
            {"commands_too_close", "repeated_commands", "external_change_reaction"},
            types,
        )

    async def test_oscillation_divergence_timeout_and_repeated_error(self) -> None:
        found: list[dict] = []
        for index, mode in enumerate(("cool", "dry", "cool", "dry")):
            found.extend(
                await self.engine.async_process(
                    _event(
                        index,
                        event_type="decision.calculated",
                        category="decision",
                        climate_mode=mode,
                        treatment=mode,
                    )
                )
            )
        found.extend(
            await self.engine.async_process(
                _event(5, event_type="localtuya.divergence_or_external", is_external=True)
            )
        )
        await asyncio.sleep(0.03)
        found.extend(self.manager.storage.saved)
        found.extend(
            await self.engine.async_process(
                _event(6, event_type="transmission.confirmation_timeout", category="transmission")
            )
        )
        for index in range(7, 10):
            found.extend(
                await self.engine.async_process(
                    _event(index, event_type="supervisor.error", severity="error", category="error")
                )
            )
        types = {item["anomaly_type"] for item in found}
        self.assertTrue(
            {
                "decision_oscillation",
                "desired_state_divergence",
                "localtuya_not_confirmed",
                "repeated_error",
            }
            <= types
        )

    async def test_excessive_volume_has_cooldown(self) -> None:
        self.manager.settings.anomaly_volume_event_limit = 3
        results = []
        for index in range(6):
            results.extend(await self.engine.async_process(_event(index)))
        self.assertEqual(
            1,
            sum(item["anomaly_type"] == "excessive_volume" for item in results),
        )

    async def test_critical_unavailable_waits_and_recovery_cancels(self) -> None:
        entity_id = "sensor.sensor_umidade_sensor_dedicado"
        unavailable = SimpleNamespace(state="unavailable")
        self.manager.hass.states.values[entity_id] = unavailable
        await self.engine.async_process(
            _event(
                0,
                source_entity_id=entity_id,
                after_json={"state": "unavailable"},
            )
        )
        await asyncio.sleep(0.03)
        self.assertIn(
            "critical_entity_unavailable",
            {item["anomaly_type"] for item in self.manager.storage.saved},
        )

        before = len(self.manager.storage.saved)
        self.manager.hass.states.values[entity_id] = SimpleNamespace(state="74")
        await self.engine.async_process(
            _event(1, source_entity_id=entity_id, after_json={"state": "74"})
        )
        await asyncio.sleep(0.02)
        self.assertEqual(before, len(self.manager.storage.saved))

    async def test_divergence_requires_duration_and_recovery_cancels(self) -> None:
        event = _event(
            0,
            event_type="localtuya.divergence_or_external",
            source_entity_id="select.smart_air_conditioner_mode_ar_condicionado_id_4",
        )
        immediate = await self.engine.async_process(event)
        self.assertNotIn(
            "desired_state_divergence",
            {item["anomaly_type"] for item in immediate},
        )
        await self.engine.async_process(
            _event(
                1,
                event_type="localtuya.confirmed_expected_field",
                source_entity_id=event["source_entity_id"],
                confirmation_state="confirmed_by_localtuya",
            )
        )
        await asyncio.sleep(0.03)
        self.assertNotIn(
            "desired_state_divergence",
            {item["anomaly_type"] for item in self.manager.storage.saved},
        )

        await self.engine.async_process(event)
        await asyncio.sleep(0.03)
        self.assertIn(
            "desired_state_divergence",
            {item["anomaly_type"] for item in self.manager.storage.saved},
        )

    async def test_unavailable_timer_is_stable_and_disable_is_revalidated(self) -> None:
        entity_id = "sensor.sensor_umidade_sensor_dedicado"
        self.manager.settings.anomaly_unavailable_seconds = 0.04
        self.manager.hass.states.values[entity_id] = SimpleNamespace(
            state="unavailable"
        )
        event = _event(
            0,
            source_entity_id=entity_id,
            after_json={"state": "unavailable"},
        )
        await self.engine.async_process(event)
        first_task = self.engine._unavailable_tasks[entity_id]
        await asyncio.sleep(0.02)
        await self.engine.async_process(_event(1, **{key: value for key, value in event.items() if key not in {"event_id", "occurred_at"}}))
        self.assertIs(first_task, self.engine._unavailable_tasks[entity_id])
        await asyncio.sleep(0.03)
        self.assertIn(entity_id, self.engine._unavailable_alerted)

        other = "sensor.sensor_temperatura_sensor_dedicado"
        self.manager.hass.states.values[other] = SimpleNamespace(state="unavailable")
        await self.engine.async_process(
            _event(2, source_entity_id=other, after_json={"state": "unavailable"})
        )
        self.manager.settings.anomalies_enabled = False
        await asyncio.sleep(0.05)
        matches = [
            item
            for item in self.manager.storage.saved
            if (item.get("details") or {}).get("entity_id") == other
        ]
        self.assertEqual([], matches)

    async def test_startup_scans_already_unavailable_critical_entity(self) -> None:
        for entity_id in anomaly_module.CRITICAL_ENTITIES:
            self.manager.hass.states.values[entity_id] = SimpleNamespace(state="ok")
        target = "sensor.sensor_umidade_sensor_dedicado"
        self.manager.hass.states.values[target] = SimpleNamespace(state="unknown")
        await self.engine.async_start()
        await asyncio.sleep(0.03)
        self.assertIn(
            target,
            {
                (item.get("details") or {}).get("entity_id")
                for item in self.manager.storage.saved
            },
        )

    async def test_all_four_secondary_controls_change_detection(self) -> None:
        self.manager.settings.anomaly_no_change_threshold = 2
        self.assertEqual([], await self.engine.async_process(_event(0, event_type="evaluation.no_change")))
        no_change = await self.engine.async_process(
            _event(1, event_type="evaluation.no_change")
        )
        self.assertEqual(
            "no_change_sequence", no_change[0]["details"]["variant"]
        )

        command = {
            "event_type": "transmission.requested_by_ha",
            "category": "transmission",
            "action_domain": "esphome",
            "action_name": "esp8266_elgin_send_state",
            "desired_json": {"mode": "dry"},
        }
        self.manager.settings.anomaly_duplicate_window_seconds = 1
        await self.engine.async_process(_event(10, **command))
        outside = await self.engine.async_process(_event(12, **command))
        repeated = next(
            item for item in outside if item["anomaly_type"] == "repeated_commands"
        )
        self.assertEqual("repeated_command", repeated["details"]["variant"])
        self.manager.settings.anomaly_duplicate_window_seconds = 3
        duplicate = await self.engine.async_process(_event(14, **command))
        exact = next(
            item for item in duplicate if item["anomaly_type"] == "repeated_commands"
        )
        self.assertEqual("exact_duplicate", exact["details"]["variant"])

        fresh = anomaly_module.AnomalyEngine(self.manager)
        self.manager.settings.anomaly_audible_burst_seconds = 5
        self.manager.settings.anomaly_audible_burst_count = 4
        for index in range(3):
            result = await fresh.async_process(_event(20 + index, **command))
        self.assertNotIn(
            "audible_burst",
            {(item.get("details") or {}).get("variant") for item in result},
        )
        self.manager.settings.anomaly_audible_burst_count = 3
        burst = await fresh.async_process(_event(23, **command))
        self.assertIn(
            "audible_burst",
            {(item.get("details") or {}).get("variant") for item in burst},
        )
        await fresh.async_stop()

    async def test_notification_cooldown_persists_and_failure_retries(self) -> None:
        self.manager.settings.notifications_enabled = True
        anomaly = self.engine._build(
            "repeated_commands",
            "warning",
            "Teste",
            "Explicação",
            "Recomendação",
            _event(0),
            {"variant": "notification_test"},
        )
        saved = await self.manager.storage.async_upsert_anomaly(anomaly)
        await self.engine._async_notify(saved)
        self.assertEqual(1, len(self.manager.hass.services.calls))
        self.assertTrue(self.manager.storage.by_id[saved["anomaly_id"]]["notified_at"])

        restarted = anomaly_module.AnomalyEngine(self.manager)
        await restarted._async_notify(saved)
        self.assertEqual(1, len(self.manager.hass.services.calls))

        failed = self.engine._build(
            "repeated_commands",
            "warning",
            "Falha",
            "Explicação",
            "Recomendação",
            _event(1),
            {"variant": "notification_failure"},
        )
        failed = await self.manager.storage.async_upsert_anomaly(failed)
        self.manager.hass.services.fail_domain = "persistent_notification"
        with self.assertLogs(anomaly_module._LOGGER.name, level="ERROR"):
            await self.engine._async_notify(failed)
        self.assertIsNone(
            self.manager.storage.by_id[failed["anomaly_id"]].get("notified_at")
        )
        self.manager.hass.services.fail_domain = None
        await self.engine._async_notify(failed)
        self.assertIsNotNone(
            self.manager.storage.by_id[failed["anomaly_id"]].get("notified_at")
        )
        await restarted.async_stop()


if __name__ == "__main__":
    unittest.main()
