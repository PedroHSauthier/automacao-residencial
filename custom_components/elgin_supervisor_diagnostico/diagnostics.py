"""Home Assistant diagnostic download support."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .const import SENSITIVE_KEYS
from .entity import DiagnosticConfigEntry, manager_from_entry

_DIAGNOSTIC_REDACT_KEYS = set(SENSITIVE_KEYS) | {
    "actor_name",
    "notification_service",
    "user_id",
    "user_name",
}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant,
    entry: DiagnosticConfigEntry,
) -> dict[str, Any]:
    """Return a sanitized snapshot; never include the SQLite content wholesale."""

    manager = manager_from_entry(entry)
    snapshot = await manager.async_get_snapshot(include_recent=False)
    fallback = await manager.storage.async_get_fallback_snapshot()
    snapshot.pop("observations", None)
    snapshot.pop("recent_events", None)
    if isinstance(snapshot.get("settings"), dict):
        snapshot["settings"] = dict(snapshot["settings"])
        snapshot["settings"].pop("saved_filters", None)
        snapshot["settings"].pop("default_saved_filter_id", None)
    options = dict(entry.options)
    options.pop("saved_filters", None)
    options.pop("default_saved_filter_id", None)
    return async_redact_data(
        {
            "entry": {
                "options": options,
            },
            "snapshot": snapshot,
            "fallback_pendente_sanitizado": fallback,
        },
        _DIAGNOSTIC_REDACT_KEYS,
    )
