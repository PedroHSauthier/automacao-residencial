"""Sensor entities for Elgin Supervisor diagnostics."""

from __future__ import annotations

from homeassistant.components.sensor import SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import DiagnosticEntity
from .manager import DiagnosticRuntimeData


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    manager = entry.runtime_data.manager
    async_add_entities(
        [
            StatusSensor(manager),
            LastEventSensor(manager),
            LastTransmissionSensor(manager),
            CountersSensor(manager),
            DatabaseSensor(manager),
        ]
    )


class StatusSensor(DiagnosticEntity, SensorEntity):
    _attr_icon = "mdi:timeline-check"

    def __init__(self, manager) -> None:
        super().__init__(manager, "status", "Status")

    @property
    def native_value(self):
        return "Operacional" if self.manager.storage.healthy else "Degradado"

    @property
    def extra_state_attributes(self):
        return {
            "modo_intensivo": self.manager.intensive_mode,
            "instrumentacao_completa": self.manager.instrumentation_complete(),
            "fila": self.manager.storage.queue_size,
        }


class LastEventSensor(DiagnosticEntity, SensorEntity):
    _attr_icon = "mdi:timeline-clock"

    def __init__(self, manager) -> None:
        super().__init__(manager, "last_event", "Último evento")

    @property
    def native_value(self):
        return self.manager.last_event.summary if self.manager.last_event else "Nenhum"

    @property
    def extra_state_attributes(self):
        event = self.manager.last_event
        return event.as_public_dict(include_details=False) if event else {}


class LastTransmissionSensor(DiagnosticEntity, SensorEntity):
    _attr_icon = "mdi:remote"

    def __init__(self, manager) -> None:
        super().__init__(manager, "last_transmission", "Última transmissão")

    @property
    def native_value(self):
        event = self.manager.last_transmission
        return event.frame_kind or event.event_type if event else "Nenhuma"

    @property
    def extra_state_attributes(self):
        event = self.manager.last_transmission
        return event.as_public_dict(include_details=False) if event else {}


class CountersSensor(DiagnosticEntity, SensorEntity):
    _attr_icon = "mdi:counter"
    _attr_should_poll = True

    def __init__(self, manager) -> None:
        super().__init__(manager, "counters", "Contadores")
        self._stats = {}

    @property
    def native_value(self):
        return self._stats.get("total_events", 0)

    @property
    def extra_state_attributes(self):
        return {
            "por_classe": self._stats.get("events_by_retention_class", {}),
            "por_categoria": self._stats.get("events_by_category", {}),
            "anomalias_ativas": self._stats.get("active_anomalies", 0),
            "descartados": self._stats.get("dropped_events", 0),
        }

    async def async_update(self) -> None:
        self._stats = await self.manager.storage.async_stats()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._stats = await self.manager.storage.async_stats()


class DatabaseSensor(DiagnosticEntity, SensorEntity):
    _attr_icon = "mdi:database"
    _attr_should_poll = True

    def __init__(self, manager) -> None:
        super().__init__(manager, "database", "Banco")
        self._stats = {}

    @property
    def native_value(self):
        return round((self._stats.get("database_size_bytes", 0) + self._stats.get("wal_size_bytes", 0)) / 1024 / 1024, 2)

    @property
    def native_unit_of_measurement(self):
        return "MB"

    @property
    def extra_state_attributes(self):
        return dict(self._stats)

    async def async_update(self) -> None:
        self._stats = await self.manager.storage.async_stats()

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._stats = await self.manager.storage.async_stats()
