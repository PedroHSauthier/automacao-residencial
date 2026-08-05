"""Switch platform for Elgin Supervisor diagnostics."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import DiagnosticEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([IntensiveSwitch(entry.runtime_data.manager)])


class IntensiveSwitch(DiagnosticEntity, SwitchEntity):
    _attr_icon = "mdi:timeline-plus"

    def __init__(self, manager) -> None:
        super().__init__(manager, "intensive", "Intensivo")

    @property
    def is_on(self):
        return self.manager.intensive_mode

    async def async_turn_on(self, **kwargs) -> None:
        await self.manager.async_set_intensive(True, self._context)

    async def async_turn_off(self, **kwargs) -> None:
        await self.manager.async_set_intensive(False, self._context)
