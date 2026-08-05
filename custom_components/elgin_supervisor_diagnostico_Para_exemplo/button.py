"""Button platform for Elgin Supervisor diagnostics."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import DiagnosticEntity


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry, async_add_entities: AddEntitiesCallback) -> None:
    manager = entry.runtime_data.manager
    async_add_entities(
        [RegisterBeepButton(manager), ForceCleanupButton(manager), ReevaluateAnomaliesButton(manager)]
    )


class RegisterBeepButton(DiagnosticEntity, ButtonEntity):
    _attr_icon = "mdi:volume-high"

    def __init__(self, manager) -> None:
        super().__init__(manager, "register_beep", "Registrar bip")

    async def async_press(self) -> None:
        await self.manager.async_register_beep(
            quantity="não tenho certeza",
            note="Registro rápido pela entidade button; use o card para informar a quantidade.",
            occurred_at=None,
            context=self._context,
        )


class ForceCleanupButton(DiagnosticEntity, ButtonEntity):
    _attr_icon = "mdi:database-refresh"

    def __init__(self, manager) -> None:
        super().__init__(manager, "force_cleanup", "Forçar limpeza")

    async def async_press(self) -> None:
        await self.manager.async_run_cleanup(actor="Botão de entidade")


class ReevaluateAnomaliesButton(DiagnosticEntity, ButtonEntity):
    _attr_icon = "mdi:alert-decagram-outline"

    def __init__(self, manager) -> None:
        super().__init__(manager, "reevaluate_anomalies", "Reavaliar anomalias")

    async def async_press(self) -> None:
        await self.manager.anomaly.async_reevaluate()
