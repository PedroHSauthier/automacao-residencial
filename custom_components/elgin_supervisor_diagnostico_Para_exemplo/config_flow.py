"""Config and options flows for Elgin Supervisor diagnostics."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult

from .const import DOMAIN, NAME
from .models import DiagnosticSettings


class ElginSupervisorDiagnosticoConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Create the single diagnostics instance."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            return self.async_create_entry(title=NAME, data={})
        return self.async_show_form(step_id="user", data_schema=vol.Schema({}))

    @staticmethod
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        return DiagnosticOptionsFlow(config_entry)


class DiagnosticOptionsFlow(config_entries.OptionsFlow):
    """Fallback native options editor; the custom card exposes the full editor."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        current = DiagnosticSettings.from_options(dict(self.config_entry.options))
        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                settings = DiagnosticSettings.from_options(user_input)
                settings.validate()
            except ValueError:
                errors["base"] = "invalid_options"
            else:
                return self.async_create_entry(title="", data=settings.as_dict())
        schema = vol.Schema(
            {
                vol.Required("intensive_mode", default=current.intensive_mode): bool,
                vol.Required("retention_absolute_days", default=current.retention_absolute_days): vol.All(vol.Coerce(int), vol.Range(min=1, max=365)),
                vol.Required("retention_error_days", default=current.retention_error_days): vol.All(vol.Coerce(int), vol.Range(min=1, max=180)),
                vol.Required("retention_full_days", default=current.retention_full_days): vol.All(vol.Coerce(int), vol.Range(min=1, max=30)),
                vol.Required("beep_window_before_seconds", default=current.beep_window_before_seconds): vol.All(vol.Coerce(int), vol.Range(min=10, max=1800)),
                vol.Required("beep_window_after_seconds", default=current.beep_window_after_seconds): vol.All(vol.Coerce(int), vol.Range(min=10, max=1800)),
                vol.Required("notifications_enabled", default=current.notifications_enabled): bool,
                vol.Required("notification_min_severity", default=current.notification_min_severity): vol.In(["debug", "info", "success", "warning", "error", "critical"]),
                vol.Required("notification_cooldown_seconds", default=current.notification_cooldown_seconds): vol.All(vol.Coerce(int), vol.Range(min=60, max=86400)),
            }
        )
        return self.async_show_form(step_id="init", data_schema=schema, errors=errors)
