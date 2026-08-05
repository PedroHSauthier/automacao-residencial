"""Event entity for important Elgin Supervisor diagnostic events."""

from __future__ import annotations

from homeassistant.components.event import EventEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import EVENT_ENTITY_TYPES
from .entity import DiagnosticEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    async_add_entities([DiagnosticEventEntity(entry.runtime_data.manager)])


class DiagnosticEventEntity(DiagnosticEntity, EventEntity):
    _attr_icon = "mdi:timeline-alert"
    _attr_event_types = list(EVENT_ENTITY_TYPES)

    def __init__(self, manager) -> None:
        super().__init__(manager, "event", "Evento")
        self._unsub_event = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._unsub_event = self.manager.async_add_event_listener(self._handle_event)

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub_event:
            self._unsub_event()
            self._unsub_event = None
        await super().async_will_remove_from_hass()

    @callback
    def _handle_event(self, event_type: str, attributes: dict) -> None:
        self._trigger_event(event_type, attributes)
        self.async_write_ha_state()
