"""Event entity for important diagnostic occurrences."""

from __future__ import annotations

from typing import Any

from homeassistant.components.event import EventEntity, EventEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import (
    DiagnosticConfigEntry,
    DiagnosticEntity,
    event_as_dict,
    manager_from_entry,
)

EVENT_TYPES = (
    "decision",
    "action",
    "external_change",
    "anomaly",
    "observation",
    "error",
    "health",
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DiagnosticConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up one event entity for important occurrences."""

    async_add_entities([DiagnosticEvent(manager_from_entry(entry))])


class DiagnosticEvent(DiagnosticEntity, EventEntity):
    """Publish important rows without exposing large raw payloads as attributes."""

    _attr_event_types = list(EVENT_TYPES)

    def __init__(self, manager) -> None:
        super().__init__(
            manager,
            EventEntityDescription(
                key="important_event",
                translation_key="important_event",
                icon="mdi:timeline-alert-outline",
                entity_category=EntityCategory.DIAGNOSTIC,
            ),
        )
        self._last_event_id: str | None = None

    @callback
    def _handle_manager_update(self, *_args: Any) -> None:
        event = event_as_dict(getattr(self.manager, "last_event", None))
        event_id = str(event.get("event_id") or "")
        if event_id and event_id != self._last_event_id:
            public_type = self._public_type(event)
            if public_type is not None:
                self._last_event_id = event_id
                allowed = {
                    "event_id",
                    "occurred_at",
                    "severity",
                    "summary",
                    "entity_id",
                    "source_entity_id",
                    "actor_name",
                    "outcome",
                    "correlation_id",
                    "evaluation_id",
                }
                attributes = {
                    key: value for key, value in event.items() if key in allowed
                }
                attributes["diagnostic_event_type"] = event.get("event_type")
                self._trigger_event(
                    public_type,
                    attributes,
                )
        self.async_write_ha_state()

    @staticmethod
    def _public_type(event: dict[str, Any]) -> str | None:
        category = str(event.get("category") or "")
        event_type = str(event.get("event_type") or "")
        severity = str(event.get("severity") or "")
        if event.get("is_anomaly") or category == "anomaly":
            return "anomaly"
        if event.get("is_external") or category == "external_change":
            return "external_change"
        if category in {"observation", "user"}:
            return "observation"
        if severity in {"error", "critical"}:
            return "error"
        if category in {"decision", "evaluation"}:
            return "decision"
        if category in {"action", "transmission"}:
            return "action"
        if category in {"health", "storage", "system"}:
            return "health"
        if event_type.startswith("anomaly."):
            return "anomaly"
        return None
