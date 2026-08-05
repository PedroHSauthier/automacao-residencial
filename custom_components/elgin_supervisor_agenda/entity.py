"""Base entity for Elgin Supervisor Agenda."""

from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, NAME
from .manager import AgendaManager


OBJECT_IDS = {
    "calendar": "elgin_supervisor_agenda",
    "policy": "elgin_supervisor_agenda_politica",
    "active_rules": "elgin_supervisor_agenda_regras_ativas",
    "next_transition": "elgin_supervisor_agenda_proxima_transicao",
    "conflicts": "elgin_supervisor_agenda_conflitos",
    "catalog": "elgin_supervisor_agenda_catalogo",
    "presets": "elgin_supervisor_presets_de_condicao",
    "powers": "elgin_supervisor_potencias",
    "preset_base_heat": "elgin_supervisor_preset_base_aquecimento",
    "preset_base_cool": "elgin_supervisor_preset_base_refrigeracao",
    "preset_base_dry": "elgin_supervisor_preset_base_desumidificacao",
    "power_base_heat": "elgin_supervisor_potencia_base_aquecimento",
    "power_base_cool": "elgin_supervisor_potencia_base_refrigeracao",
    "power_base_dry": "elgin_supervisor_potencia_base_desumidificacao",
    "active": "elgin_supervisor_agenda_em_acao",
    "blocking": "elgin_supervisor_agenda_bloqueando_operacao",
    "enabled": "elgin_supervisor_agenda_habilitada",
    "evaluate": "elgin_supervisor_agenda_reavaliar_agora",
    "cancel_exceptions": "elgin_supervisor_agenda_cancelar_excecoes_unicas_ativas",
}

ENTITY_DOMAINS = {
    "calendar": "calendar",
    "policy": "sensor",
    "active_rules": "sensor",
    "next_transition": "sensor",
    "conflicts": "sensor",
    "catalog": "sensor",
    "presets": "sensor",
    "powers": "sensor",
    "preset_base_heat": "select",
    "preset_base_cool": "select",
    "preset_base_dry": "select",
    "power_base_heat": "select",
    "power_base_cool": "select",
    "power_base_dry": "select",
    "active": "binary_sensor",
    "blocking": "binary_sensor",
    "enabled": "switch",
    "evaluate": "button",
    "cancel_exceptions": "button",
}


def canonical_entity_id(key: str) -> str:
    """Return the stable entity ID required by packages and dashboards."""
    return f"{ENTITY_DOMAINS[key]}.{OBJECT_IDS[key]}"


class AgendaEntity(Entity):
    """Base entity tied directly to one manager."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, manager: AgendaManager, key: str, name: str) -> None:
        self.manager = manager
        self._attr_unique_id = f"{manager.entry_id}_{key}"
        self._attr_name = name
        # Set a matching-domain entity_id before registration. This becomes the
        # integration suggestion and prevents global area/device naming settings
        # from prefixing IDs that are API contracts for packages and dashboards.
        self.entity_id = canonical_entity_id(key)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, manager.entry_id)},
            name=manager.name or NAME,
            manufacturer="Projeto Elgin AUX",
            model="Motor local de políticas temporais",
        )
        self._unsub_manager = None

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._unsub_manager = self.manager.async_add_listener(self._handle_update)

    async def async_will_remove_from_hass(self) -> None:
        if self._unsub_manager:
            self._unsub_manager()
            self._unsub_manager = None
        await super().async_will_remove_from_hass()

    @callback
    def _handle_update(self) -> None:
        """Write the manager snapshot immediately to Home Assistant."""
        self.async_write_ha_state()
