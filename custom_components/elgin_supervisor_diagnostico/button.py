"""Safe observation and maintenance buttons for diagnostics."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import DiagnosticConfigEntry, DiagnosticEntity, manager_from_entry

DESCRIPTIONS = (
    ButtonEntityDescription(
        key="register_beep",
        translation_key="register_beep",
        icon="mdi:volume-high",
    ),
    ButtonEntityDescription(
        key="register_observation",
        translation_key="register_observation",
        icon="mdi:note-plus-outline",
    ),
    ButtonEntityDescription(
        key="reevaluate_anomalies",
        translation_key="reevaluate_anomalies",
        icon="mdi:alert-decagram-outline",
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: DiagnosticConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up safe action buttons."""

    manager = manager_from_entry(entry)
    async_add_entities(DiagnosticButton(manager, description) for description in DESCRIPTIONS)


class DiagnosticButton(DiagnosticEntity, ButtonEntity):
    """Invoke diagnostic-only operations; never call Climate or ESPHome."""

    entity_description: ButtonEntityDescription

    async def async_press(self) -> None:
        key = self.entity_description.key
        if key == "register_beep":
            await self.manager.async_register_observation(
                {
                    "observation_type": "beep",
                    "expected_count": "uncertain",
                    "note": "Registro rápido pela entidade button.",
                    "metadata": {
                        "title": "Bip observado",
                        "tags": ["bip", "registro_rapido"],
                    },
                },
                context=self._context,
            )
            return
        if key == "register_observation":
            await self.manager.async_register_observation(
                {
                    "observation_type": "note",
                    "note": "Registro rápido pela entidade button; edite detalhes pelo card.",
                    "metadata": {
                        "title": "Observação rápida",
                        "tags": ["registro_rapido"],
                    },
                },
                context=self._context,
            )
            return
        if key == "reevaluate_anomalies":
            await self.manager.async_reevaluate_anomalies()
