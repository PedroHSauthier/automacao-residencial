"""System Health integration for Elgin Supervisor diagnostics."""

from __future__ import annotations

from typing import Any

from homeassistant.components import system_health
from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant, callback

from .const import DOMAIN
from .entity import nested_value


@callback
def async_register(
    hass: HomeAssistant,
    register: system_health.SystemHealthRegistration,
) -> None:
    """Register diagnostic health information."""

    register.async_register_info(system_health_info)


async def system_health_info(hass: HomeAssistant) -> dict[str, Any]:
    """Return a small, non-sensitive cached health summary."""

    entry = next(
        (
            item
            for item in hass.config_entries.async_entries(DOMAIN)
            if item.state is ConfigEntryState.LOADED
        ),
        None,
    )
    if entry is None or getattr(entry, "runtime_data", None) is None:
        return {"configured": bool(hass.config_entries.async_entries(DOMAIN)), "loaded": False}
    manager = entry.runtime_data.manager
    snapshot = manager.status_snapshot()
    return {
        "configured": True,
        "loaded": True,
        "status": nested_value(snapshot, "status", "health.status", default="unknown"),
        "persistence_healthy": nested_value(
            snapshot,
            "persistence_healthy",
            "health.persistence_healthy",
            "storage.healthy",
            default=False,
        ),
        "instrumentation_complete": nested_value(
            snapshot,
            "instrumentation_complete",
            "health.instrumentation_complete",
            default=False,
        ),
        "schema_version": nested_value(
            snapshot, "schema_version", "storage.schema_version"
        ),
        "queue_size": nested_value(snapshot, "queue_size", "storage.queue_size"),
        "dropped_events": nested_value(
            snapshot, "dropped_events", "storage.dropped_events"
        ),
        "storm_protection_active": nested_value(
            snapshot,
            "storm_protection_active",
            "health.storm_protection_active",
            "rate.protection_active",
            default=False,
        ),
    }
