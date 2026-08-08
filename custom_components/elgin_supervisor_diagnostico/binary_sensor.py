"""Health indicators for Elgin Supervisor diagnostics."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import (
    DiagnosticConfigEntry,
    DiagnosticEntity,
    manager_from_entry,
    nested_value,
)

DESCRIPTIONS = (
    BinarySensorEntityDescription(
        key="healthy",
        translation_key="healthy",
        icon="mdi:heart-pulse",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BinarySensorEntityDescription(
        key="persistence_healthy",
        translation_key="persistence_healthy",
        icon="mdi:database-check-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BinarySensorEntityDescription(
        key="instrumentation_complete",
        translation_key="instrumentation_complete",
        icon="mdi:connection",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
    BinarySensorEntityDescription(
        key="storm_protection",
        translation_key="storm_protection",
        icon="mdi:shield-alert-outline",
        device_class=BinarySensorDeviceClass.PROBLEM,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DiagnosticConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up diagnostic health indicators."""

    manager = manager_from_entry(entry)
    async_add_entities(
        DiagnosticBinarySensor(manager, description) for description in DESCRIPTIONS
    )


class DiagnosticBinarySensor(DiagnosticEntity, BinarySensorEntity):
    """Expose cached subsystem health without polling or governing HVAC."""

    entity_description: BinarySensorEntityDescription

    @property
    def is_on(self) -> bool:
        snapshot = self.manager_snapshot()
        key = self.entity_description.key
        if key == "healthy":
            return bool(nested_value(snapshot, "healthy", "health.healthy", default=False))
        if key == "persistence_healthy":
            return bool(
                nested_value(
                    snapshot,
                    "persistence_healthy",
                    "health.persistence_healthy",
                    "storage.healthy",
                    default=False,
                )
            )
        if key == "instrumentation_complete":
            return bool(
                nested_value(
                    snapshot,
                    "instrumentation_complete",
                    "health.instrumentation_complete",
                    default=False,
                )
            )
        if key == "storm_protection":
            return bool(
                nested_value(
                    snapshot,
                    "storm_protection_active",
                    "health.storm_protection_active",
                    "rate.protection_active",
                    default=False,
                )
            )
        return False
