"""Switch platform for Elgin Supervisor Agenda."""

from __future__ import annotations

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import AgendaEntity
from .manager import AgendaManager


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([AgendaEnabledSwitch(entry.runtime_data)])


class AgendaEnabledSwitch(AgendaEntity, SwitchEntity):
    _attr_icon = "mdi:calendar-sync"

    def __init__(self, manager: AgendaManager) -> None:
        super().__init__(manager, "enabled", "Habilitada")

    @property
    def is_on(self):
        return self.manager.enabled

    async def async_turn_on(self, **kwargs) -> None:
        await self.manager.async_set_enabled(True)

    async def async_turn_off(self, **kwargs) -> None:
        await self.manager.async_set_enabled(False)
