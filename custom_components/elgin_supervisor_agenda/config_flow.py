"""Config flow for Elgin Supervisor Agenda."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult

from .const import DOMAIN, NAME


class ElginSupervisorAgendaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the agenda."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create the single agenda instance."""
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()

        if user_input is not None:
            return self.async_create_entry(
                title=user_input.get("name", NAME),
                data={"name": user_input.get("name", NAME)},
            )

        schema = vol.Schema({vol.Optional("name", default=NAME): str})
        return self.async_show_form(step_id="user", data_schema=schema)
