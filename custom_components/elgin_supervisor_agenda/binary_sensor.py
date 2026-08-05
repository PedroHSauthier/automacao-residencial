"""Binary sensors for Elgin Supervisor Agenda."""

from __future__ import annotations

from homeassistant.components.binary_sensor import BinarySensorEntity
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
    manager: AgendaManager = entry.runtime_data
    async_add_entities([AgendaActiveBinarySensor(manager), AgendaBlockingBinarySensor(manager)])


class AgendaActiveBinarySensor(AgendaEntity, BinarySensorEntity):
    _attr_icon = "mdi:calendar-check"

    def __init__(self, manager: AgendaManager) -> None:
        super().__init__(manager, "active", "Em ação")

    @property
    def is_on(self):
        return self.manager.enabled and self.manager.policy.get("active_count", 0) > 0


class AgendaBlockingBinarySensor(AgendaEntity, BinarySensorEntity):
    _attr_icon = "mdi:calendar-lock"

    def __init__(self, manager: AgendaManager) -> None:
        super().__init__(manager, "blocking", "Bloqueando operação")

    @property
    def is_on(self):
        return self.manager.policy.get("global_action") in {
            "disable_supervisor",
            "power_off_block",
            "suspend",
        }

    @property
    def extra_state_attributes(self):
        return {"acao": self.manager.policy.get("global_action", "normal")}
