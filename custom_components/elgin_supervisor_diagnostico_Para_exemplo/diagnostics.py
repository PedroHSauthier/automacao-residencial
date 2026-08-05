"""Home Assistant diagnostics support."""

from __future__ import annotations

from typing import Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import SENSITIVE_KEYS
from .manager import DiagnosticRuntimeData


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: ConfigEntry
) -> dict[str, Any]:
    runtime: DiagnosticRuntimeData = entry.runtime_data
    snapshot = await runtime.manager.async_get_snapshot(include_recent=True)
    return async_redact_data(
        {
            "entry": {
                "title": entry.title,
                "data": dict(entry.data),
                "options": dict(entry.options),
            },
            "snapshot": snapshot,
            "origin_resolver": runtime.manager.origin.diagnostics(),
        },
        set(SENSITIVE_KEYS),
    )
