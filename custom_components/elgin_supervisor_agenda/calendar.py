"""Calendar platform for Elgin Supervisor Agenda."""

from __future__ import annotations

from datetime import datetime

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import AgendaEntity
from .const import MODE_NAMES
from .manager import AgendaManager


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    async_add_entities([AgendaCalendar(entry.runtime_data)])


class AgendaCalendar(AgendaEntity, CalendarEntity):
    """Expanded recurring schedule as a native Home Assistant calendar."""

    _attr_icon = "mdi:calendar-clock"
    _attr_initial_color = "#00A6C8"

    def __init__(self, manager: AgendaManager) -> None:
        super().__init__(manager, "calendar", "Agenda")

    @property
    def event(self) -> CalendarEvent | None:
        occurrence = self.manager.current_or_next_occurrence()
        return self._to_event(occurrence) if occurrence else None

    @callback
    def _handle_update(self) -> None:
        """Update state and every active calendar subscription after CRUD."""
        super()._handle_update()
        self.async_update_event_listeners()

    async def async_get_events(
        self,
        hass: HomeAssistant,
        start_date: datetime,
        end_date: datetime,
    ) -> list[CalendarEvent]:
        return [
            self._to_event(occurrence)
            for occurrence in self.manager.occurrences_between(start_date, end_date)
        ]

    @staticmethod
    def _to_event(occurrence: dict) -> CalendarEvent:
        modes = ", ".join(
            MODE_NAMES.get(mode, mode) for mode in occurrence.get("modes", [])
        )
        effects = occurrence.get("effects") or []
        effects_text = "\n".join(f"• {effect}" for effect in effects) or "Nenhum"
        description = (
            f"Prioridade: {occurrence.get('priority')}\n"
            f"Modos: {modes}\n"
            f"Efeitos:\n{effects_text}"
        )
        if occurrence.get("notes"):
            description += f"\nNotas: {occurrence['notes']}"
        start = occurrence["start"]
        end = occurrence["end"]
        if occurrence.get("all_day"):
            start = start.date()
            end = end.date()
        return CalendarEvent(
            start=start,
            end=end,
            summary=f"P{occurrence.get('priority', 0)} · {occurrence['name']}",
            description=description,
            location="Supervisor climático Elgin",
            uid=occurrence["rule_id"],
            recurrence_id=occurrence["start"].isoformat(),
        )
