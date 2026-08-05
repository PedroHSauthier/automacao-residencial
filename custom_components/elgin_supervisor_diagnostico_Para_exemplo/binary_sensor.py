"""Binary sensors for Elgin Supervisor diagnostics."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import DiagnosticEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    manager = entry.runtime_data.manager
    async_add_entities(
        [
            ActiveAnomalySensor(manager),
            PersistenceHealthySensor(manager),
            InstrumentationCompleteSensor(manager),
        ]
    )


class ActiveAnomalySensor(DiagnosticEntity, BinarySensorEntity):
    _attr_icon = "mdi:alert-circle"
    _attr_should_poll = True

    def __init__(self, manager) -> None:
        super().__init__(manager, "active_anomaly", "Anomalia ativa")
        self._active = 0

    @property
    def is_on(self):
        return self._active > 0

    @property
    def extra_state_attributes(self):
        return {"quantidade": self._active}

    async def async_update(self) -> None:
        self._active = len(await self.manager.storage.async_list_anomalies(status="active", limit=500))

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        await self.async_update()


class PersistenceHealthySensor(DiagnosticEntity, BinarySensorEntity):
    _attr_icon = "mdi:database-check"

    def __init__(self, manager) -> None:
        super().__init__(manager, "persistence_healthy", "Persistência saudável")

    @property
    def is_on(self):
        return self.manager.storage.healthy


class InstrumentationCompleteSensor(DiagnosticEntity, BinarySensorEntity):
    _attr_icon = "mdi:connection"

    def __init__(self, manager) -> None:
        super().__init__(manager, "instrumentation_complete", "Instrumentação completa")

    @property
    def is_on(self):
        return self.manager.instrumentation_complete()
