"""Base entities for Elgin Supervisor diagnostics."""

from __future__ import annotations

from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity

from .const import DOMAIN, NAME
from .manager import DiagnosticManager

OBJECT_IDS = {
    "status": "elgin_supervisor_diagnostico_status",
    "last_event": "elgin_supervisor_diagnostico_ultimo_evento",
    "last_transmission": "elgin_supervisor_diagnostico_ultima_transmissao",
    "counters": "elgin_supervisor_diagnostico_contadores",
    "database": "elgin_supervisor_diagnostico_banco",
    "active_anomaly": "elgin_supervisor_diagnostico_anomalia_ativa",
    "persistence_healthy": "elgin_supervisor_diagnostico_persistencia_saudavel",
    "instrumentation_complete": "elgin_supervisor_diagnostico_instrumentacao_completa",
    "intensive": "elgin_supervisor_diagnostico_intensivo",
    "register_beep": "elgin_supervisor_diagnostico_registrar_bip",
    "force_cleanup": "elgin_supervisor_diagnostico_forcar_limpeza",
    "reevaluate_anomalies": "elgin_supervisor_diagnostico_reavaliar_anomalias",
    "event": "elgin_supervisor_diagnostico_evento",
}

ENTITY_DOMAINS = {
    "status": "sensor",
    "last_event": "sensor",
    "last_transmission": "sensor",
    "counters": "sensor",
    "database": "sensor",
    "active_anomaly": "binary_sensor",
    "persistence_healthy": "binary_sensor",
    "instrumentation_complete": "binary_sensor",
    "intensive": "switch",
    "register_beep": "button",
    "force_cleanup": "button",
    "reevaluate_anomalies": "button",
    "event": "event",
}


def canonical_entity_id(key: str) -> str:
    return f"{ENTITY_DOMAINS[key]}.{OBJECT_IDS[key]}"


class DiagnosticEntity(Entity):
    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(self, manager: DiagnosticManager, key: str, name: str) -> None:
        self.manager = manager
        self._attr_unique_id = f"{manager.entry_id}_{key}"
        self._attr_name = name
        self.entity_id = canonical_entity_id(key)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, manager.entry_id)},
            name=NAME,
            manufacturer="Projeto Elgin AUX",
            model="Auditoria local SQLite e correlação temporal",
            sw_version="1.0.0",
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
        self.async_write_ha_state()
