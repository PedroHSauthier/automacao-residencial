"""Shared entity helpers for Elgin Supervisor diagnostics."""

from __future__ import annotations

from collections.abc import Callable, Mapping
import logging
from typing import Any, Protocol, TYPE_CHECKING, TypeAlias

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import callback
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import Entity, EntityDescription

from .const import DOMAIN, NAME, VERSION

if TYPE_CHECKING:
    from .manager import DiagnosticManager

    class DiagnosticRuntimeData(Protocol):
        """Runtime contract supplied by the integration setup."""

        manager: DiagnosticManager

    DiagnosticConfigEntry: TypeAlias = ConfigEntry[DiagnosticRuntimeData]
else:
    DiagnosticConfigEntry = ConfigEntry

_LOGGER = logging.getLogger(__name__)

OBJECT_IDS = {
    "status": "elgin_supervisor_diagnostico_status",
    "last_event": "elgin_supervisor_diagnostico_ultimo_evento",
    "last_action": "elgin_supervisor_diagnostico_ultima_acao",
    "events_24h": "elgin_supervisor_diagnostico_eventos_24h",
    "database_size": "elgin_supervisor_diagnostico_tamanho_banco",
    "event_rate": "elgin_supervisor_diagnostico_taxa_eventos",
    "healthy": "elgin_supervisor_diagnostico_saudavel",
    "persistence_healthy": "elgin_supervisor_diagnostico_persistencia_saudavel",
    "instrumentation_complete": "elgin_supervisor_diagnostico_instrumentacao_completa",
    "storm_protection": "elgin_supervisor_diagnostico_protecao_volume",
    "register_beep": "elgin_supervisor_diagnostico_registrar_bip",
    "register_observation": "elgin_supervisor_diagnostico_registrar_observacao",
    "reevaluate_anomalies": "elgin_supervisor_diagnostico_reavaliar_anomalias",
    "important_event": "elgin_supervisor_diagnostico_evento",
}

ENTITY_DOMAINS = {
    "status": "sensor",
    "last_event": "sensor",
    "last_action": "sensor",
    "events_24h": "sensor",
    "database_size": "sensor",
    "event_rate": "sensor",
    "healthy": "binary_sensor",
    "persistence_healthy": "binary_sensor",
    "instrumentation_complete": "binary_sensor",
    "storm_protection": "binary_sensor",
    "register_beep": "button",
    "register_observation": "button",
    "reevaluate_anomalies": "button",
    "important_event": "event",
}


def canonical_entity_id(key: str) -> str:
    """Return the stable entity id requested by the project contract."""

    return f"{ENTITY_DOMAINS[key]}.{OBJECT_IDS[key]}"


def manager_from_entry(entry: DiagnosticConfigEntry) -> DiagnosticManager:
    """Get typed runtime manager without importing it at runtime."""

    runtime = entry.runtime_data
    return runtime.manager


def nested_value(data: Mapping[str, Any], *paths: str, default: Any = None) -> Any:
    """Return the first existing dotted path from a status snapshot."""

    for path in paths:
        current: Any = data
        found = True
        for part in path.split("."):
            if not isinstance(current, Mapping) or part not in current:
                found = False
                break
            current = current[part]
        if found:
            return current
    return default


def event_as_dict(event: Any) -> dict[str, Any]:
    """Convert a manager event to a bounded public mapping when available."""

    if event is None:
        return {}
    if isinstance(event, Mapping):
        return dict(event)
    for method_name in ("as_public_dict", "as_dict"):
        method = getattr(event, method_name, None)
        if callable(method):
            try:
                value = method()
            except TypeError:
                value = method(include_details=False)
            if isinstance(value, Mapping):
                return dict(value)
    result: dict[str, Any] = {}
    for key in (
        "event_id",
        "occurred_at",
        "category",
        "event_type",
        "severity",
        "summary",
        "entity_id",
        "source_entity_id",
        "actor_name",
        "outcome",
        "correlation_id",
        "evaluation_id",
        "is_external",
        "is_anomaly",
    ):
        if hasattr(event, key):
            result[key] = getattr(event, key)
    return result


class DiagnosticEntity(Entity):
    """Base push entity backed by a diagnostic manager snapshot."""

    _attr_has_entity_name = True
    _attr_should_poll = False

    def __init__(
        self,
        manager: DiagnosticManager,
        description: EntityDescription,
    ) -> None:
        self.manager = manager
        self.entity_description = description
        self._attr_unique_id = f"{DOMAIN}_{description.key}"
        self.entity_id = canonical_entity_id(description.key)
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, DOMAIN)},
            name=NAME,
            manufacturer="Projeto Elgin AUX",
            model="Observabilidade local do Supervisor",
            sw_version=VERSION,
        )
        self._remove_manager_listener: Callable[[], None] | None = None

    def manager_snapshot(self) -> dict[str, Any]:
        """Read the manager's non-blocking cached status snapshot."""

        try:
            value = self.manager.status_snapshot()
        except Exception:  # noqa: BLE001
            _LOGGER.exception("Falha ao ler snapshot da entidade de diagnóstico")
            return {}
        return dict(value) if isinstance(value, Mapping) else {}

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self._remove_manager_listener = self.manager.async_add_listener(
            self._handle_manager_update
        )

    async def async_will_remove_from_hass(self) -> None:
        if self._remove_manager_listener is not None:
            self._remove_manager_listener()
            self._remove_manager_listener = None
        await super().async_will_remove_from_hass()

    @callback
    def _handle_manager_update(self, *_args: Any) -> None:
        self.async_write_ha_state()
