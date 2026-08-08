"""Observational sensors for Elgin Supervisor diagnostics."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.const import EntityCategory, UnitOfInformation
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import (
    DiagnosticEntity,
    DiagnosticConfigEntry,
    event_as_dict,
    manager_from_entry,
    nested_value,
)

DESCRIPTIONS = (
    SensorEntityDescription(
        key="status",
        translation_key="status",
        icon="mdi:timeline-check-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="last_event",
        translation_key="last_event",
        icon="mdi:timeline-clock-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="last_action",
        translation_key="last_action",
        icon="mdi:remote",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="events_24h",
        translation_key="events_24h",
        icon="mdi:counter",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="database_size",
        translation_key="database_size",
        icon="mdi:database",
        native_unit_of_measurement=UnitOfInformation.BYTES,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    SensorEntityDescription(
        key="event_rate",
        translation_key="event_rate",
        icon="mdi:speedometer",
        native_unit_of_measurement="eventos/min",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DiagnosticConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up diagnostic sensors for one config entry."""

    manager = manager_from_entry(entry)
    async_add_entities(DiagnosticSensor(manager, description) for description in DESCRIPTIONS)


class DiagnosticSensor(DiagnosticEntity, SensorEntity):
    """Expose a small cached health summary; detailed data stays in WebSocket."""

    entity_description: SensorEntityDescription

    @property
    def native_value(self) -> Any:
        snapshot = self.manager_snapshot()
        key = self.entity_description.key
        if key == "status":
            return nested_value(
                snapshot,
                "status",
                "health.status",
                default="unknown",
            )
        if key == "last_event":
            event = event_as_dict(getattr(self.manager, "last_event", None))
            return str(event.get("summary") or "none")[:255]
        if key == "last_action":
            value = nested_value(
                snapshot,
                "last_action.summary",
                "overview.last_action.summary",
                "last_action.event_type",
                default="none",
            )
            return str(value)[:255]
        if key == "events_24h":
            return int(
                nested_value(
                    snapshot,
                    "events_24h",
                    "statistics.events_24h",
                    "storage.events_24h",
                    default=0,
                )
                or 0
            )
        if key == "database_size":
            return int(
                nested_value(
                    snapshot,
                    "database_size_bytes",
                    "storage.database_size_bytes",
                    "storage.size_bytes",
                    default=0,
                )
                or 0
            )
        if key == "event_rate":
            return round(
                float(
                    nested_value(
                        snapshot,
                        "event_rate_per_minute",
                        "rate.events_per_minute",
                        "statistics.events_per_minute",
                        default=0,
                    )
                    or 0
                ),
                2,
            )
        return None

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        key = self.entity_description.key
        snapshot = self.manager_snapshot()
        if key == "status":
            return {
                "capture_mode": nested_value(snapshot, "capture_mode", "settings.capture_mode"),
                "queue_size": nested_value(snapshot, "queue_size", "storage.queue_size"),
                "schema_version": nested_value(snapshot, "schema_version", "storage.schema_version"),
                "dropped_events": nested_value(snapshot, "dropped_events", "storage.dropped_events"),
            }
        if key == "last_event":
            event = event_as_dict(getattr(self.manager, "last_event", None))
            allowed = {
                "event_id",
                "occurred_at",
                "category",
                "event_type",
                "severity",
                "entity_id",
                "source_entity_id",
                "actor_name",
                "outcome",
                "correlation_id",
                "evaluation_id",
                "is_external",
                "is_anomaly",
            }
            return {name: value for name, value in event.items() if name in allowed}
        if key == "last_action":
            action = nested_value(snapshot, "last_action", "overview.last_action", default={})
            if not isinstance(action, dict):
                return None
            allowed = {
                "event_id",
                "occurred_at",
                "event_type",
                "summary",
                "function",
                "expected_audibility",
                "audibility",
                "correlation_id",
                "transmission_id",
            }
            return {name: value for name, value in action.items() if name in allowed}
        if key == "database_size":
            storage = nested_value(snapshot, "storage", default={})
            if not isinstance(storage, dict):
                return None
            allowed = {
                "database_size_bytes",
                "wal_size_bytes",
                "schema_version",
                "quick_check",
                "queue_size",
                "normal_queue_size",
                "critical_queue_size",
                "dropped_events",
                "fallback_events",
                "written_events",
                "compacted_events",
                "last_cleanup",
                "last_failure",
                "last_write_latency_ms",
            }
            return {name: value for name, value in storage.items() if name in allowed}
        return None
