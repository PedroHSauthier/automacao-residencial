"""Button platform for Elgin Supervisor Agenda."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
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
    async_add_entities([AgendaEvaluateButton(manager), AgendaCancelExceptionsButton(manager)])


class AgendaEvaluateButton(AgendaEntity, ButtonEntity):
    _attr_icon = "mdi:calendar-refresh"

    def __init__(self, manager: AgendaManager) -> None:
        super().__init__(manager, "evaluate", "Reavaliar agora")

    async def async_press(self) -> None:
        await self.manager.async_manual_evaluate()


class AgendaCancelExceptionsButton(AgendaEntity, ButtonEntity):
    _attr_icon = "mdi:calendar-remove"

    def __init__(self, manager: AgendaManager) -> None:
        super().__init__(manager, "cancel_exceptions", "Cancelar exceções únicas ativas")

    async def async_press(self) -> None:
        await self.manager.async_cancel_active_once_rules()
