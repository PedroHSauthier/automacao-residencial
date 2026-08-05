"""System health information for Elgin Supervisor diagnostics."""

from __future__ import annotations

from homeassistant.components import system_health
from homeassistant.core import HomeAssistant, callback

from .const import DATA_MANAGERS, DOMAIN


@callback
def async_register(hass: HomeAssistant, register: system_health.SystemHealthRegistration) -> None:
    register.async_register_info(system_health_info)


async def system_health_info(hass: HomeAssistant) -> dict:
    managers = hass.data.get(DOMAIN, {}).get(DATA_MANAGERS, {})
    if not managers:
        return {"configured": False}
    manager = next(iter(managers.values()))
    stats = await manager.storage.async_stats()
    return {
        "configured": True,
        "status": "healthy" if manager.storage.healthy else "degraded",
        "schema_version": stats.get("schema_version"),
        "writer_state": stats.get("writer_state"),
        "queue_size": stats.get("queue_size"),
        "dropped_events": stats.get("dropped_events"),
        "database_size_bytes": stats.get("database_size_bytes"),
        "instrumentation_complete": manager.instrumentation_complete(),
    }
