"""Elgin Supervisor — Audit and Diagnostics integration."""

from __future__ import annotations

from pathlib import Path
import logging
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_NAME
from homeassistant.core import Context, HomeAssistant, ServiceCall, SupportsResponse
from homeassistant.exceptions import ConfigEntryNotReady, HomeAssistantError
from homeassistant.helpers import issue_registry as ir
from homeassistant.helpers import config_validation as cv

from .const import (
    DATA_FRONTEND_REGISTERED,
    DATA_MANAGERS,
    DATA_WEBSOCKET_REGISTERED,
    DOMAIN,
    FRONTEND_RESOURCE_BASE,
    FRONTEND_RESOURCE_URL,
    FRONTEND_STATIC_URL,
    NAME,
    PLATFORMS,
)
from .manager import DiagnosticManager, DiagnosticRuntimeData

SERVICE_BEGIN_TRACE = "begin_trace"
SERVICE_LOG_EVENT = "log_event"
SERVICE_REGISTER_BEEP = "register_beep"
SERVICE_RUN_CLEANUP = "run_cleanup"

_LOGGER = logging.getLogger(__name__)


def _manager(hass: HomeAssistant, entry_id: str | None = None) -> DiagnosticManager:
    managers: dict[str, DiagnosticManager] = hass.data[DOMAIN][DATA_MANAGERS]
    if entry_id:
        manager = managers.get(entry_id)
        if manager:
            return manager
    if not managers:
        raise HomeAssistantError("A integração de diagnóstico não está configurada.")
    return next(iter(managers.values()))


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    hass.data.setdefault(DOMAIN, {DATA_MANAGERS: {}})
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    domain_data = hass.data.setdefault(DOMAIN, {DATA_MANAGERS: {}})
    manager = DiagnosticManager(hass, entry)
    try:
        await manager.async_start()
    except Exception as err:  # noqa: BLE001
        ir.async_create_issue(
            hass,
            DOMAIN,
            "database_unavailable",
            is_fixable=False,
            is_persistent=True,
            severity=ir.IssueSeverity.ERROR,
            translation_key="database_unavailable",
        )
        raise ConfigEntryNotReady(
            f"O banco exclusivo da auditoria não pôde ser iniciado: {err}"
        ) from err
    ir.async_delete_issue(hass, DOMAIN, "database_unavailable")
    entry.runtime_data = DiagnosticRuntimeData(manager=manager, storage=manager.storage)
    domain_data[DATA_MANAGERS][entry.entry_id] = manager
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    await _async_register_frontend(hass)
    _async_register_websocket(hass)
    _async_register_services(hass)
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Apply externally changed options without writing the entry again."""
    manager = entry.runtime_data.manager
    await manager.async_apply_entry_options(dict(entry.options))


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unloaded:
        return False
    runtime: DiagnosticRuntimeData = entry.runtime_data
    await runtime.manager.async_stop()
    managers = hass.data[DOMAIN][DATA_MANAGERS]
    managers.pop(entry.entry_id, None)
    if not managers:
        for service in (
            SERVICE_BEGIN_TRACE,
            SERVICE_LOG_EVENT,
            SERVICE_REGISTER_BEEP,
            SERVICE_RUN_CLEANUP,
        ):
            hass.services.async_remove(DOMAIN, service)
    return True


async def _async_register_frontend(hass: HomeAssistant) -> None:
    """Serve and register the diagnostic card as a Lovelace module.

    ``ResourceStorageCollection.async_items`` is a callback and returns the
    resource list synchronously. Awaiting it raises ``TypeError`` and prevents
    automatic resource registration, so it must be called without ``await``.
    """
    domain_data = hass.data[DOMAIN]

    # Static paths can only be registered once per Home Assistant process.
    # Resource registration is retried on every setup so a transient Lovelace
    # initialization failure can be corrected by reloading the integration.
    if not domain_data.get(DATA_FRONTEND_REGISTERED):
        frontend_path = Path(__file__).parent / "frontend"
        await hass.http.async_register_static_paths(
            [StaticPathConfig(FRONTEND_STATIC_URL, str(frontend_path), True)]
        )
        domain_data[DATA_FRONTEND_REGISTERED] = True

    try:
        lovelace = hass.data.get("lovelace")
        resources = getattr(lovelace, "resources", None)
        if resources is None and isinstance(lovelace, dict):
            resources = lovelace.get("resources")
        if resources is None:
            raise HomeAssistantError(
                "A coleção de recursos Lovelace ainda não está disponível."
            )

        if hasattr(resources, "async_load") and not getattr(resources, "loaded", False):
            await resources.async_load()

        # async_items() is intentionally synchronous in Home Assistant Core.
        items = resources.async_items() or []
        matching = [
            item
            for item in items
            if str(item.get("url", "")).split("?", 1)[0]
            == FRONTEND_RESOURCE_BASE
        ]

        if matching:
            item = matching[0]
            if item.get("url") != FRONTEND_RESOURCE_URL or item.get("type") != "module":
                await resources.async_update_item(
                    item["id"],
                    {"url": FRONTEND_RESOURCE_URL, "res_type": "module"},
                )
        else:
            if not hasattr(resources, "async_create_item"):
                raise HomeAssistantError(
                    "Os recursos Lovelace estão em modo YAML; registre o módulo "
                    "na seção lovelace.resources."
                )
            await resources.async_create_item(
                {"url": FRONTEND_RESOURCE_URL, "res_type": "module"}
            )

        domain_data["frontend_resource_error"] = False
        ir.async_delete_issue(hass, DOMAIN, "frontend_not_registered")
        _LOGGER.info(
            "Recurso Lovelace do diagnóstico registrado: %s",
            FRONTEND_RESOURCE_URL,
        )
    except Exception as err:  # noqa: BLE001
        # Static serving remains functional; Repairs/system health expose the
        # registration problem and the user can still use manual registration.
        domain_data["frontend_resource_error"] = True
        ir.async_create_issue(
            hass,
            DOMAIN,
            "frontend_not_registered",
            is_fixable=False,
            is_persistent=True,
            severity=ir.IssueSeverity.WARNING,
            translation_key="frontend_not_registered",
        )
        _LOGGER.exception(
            "Falha ao registrar automaticamente o recurso Lovelace do diagnóstico: %s",
            err,
        )


def _async_register_services(hass: HomeAssistant) -> None:
    if hass.services.has_service(DOMAIN, SERVICE_BEGIN_TRACE):
        return

    async def begin_trace(call: ServiceCall) -> dict[str, Any]:
        return await _manager(hass).async_begin_trace(
            context=call.context,
            actor=call.data.get("actor"),
            source_entity_id=call.data.get("source_entity_id"),
            category=call.data.get("category", "evaluation"),
            summary=call.data.get("summary", "Fluxo de auditoria iniciado"),
        )

    async def log_event(call: ServiceCall) -> dict[str, Any]:
        event = await _manager(hass).async_log_event(dict(call.data), context=call.context)
        return {"event_id": event.event_id, "correlation_id": event.correlation_id}

    async def register_beep(call: ServiceCall) -> dict[str, Any]:
        return await _manager(hass).async_register_beep(
            quantity=call.data.get("quantity", "não tenho certeza"),
            note=call.data.get("note"),
            occurred_at=call.data.get("occurred_at"),
            context=call.context,
        )

    async def run_cleanup(call: ServiceCall) -> dict[str, Any]:
        return await _manager(hass).async_run_cleanup(actor="Serviço Home Assistant")

    hass.services.async_register(
        DOMAIN,
        SERVICE_BEGIN_TRACE,
        begin_trace,
        schema=vol.Schema(
            {
                vol.Optional("actor"): cv.string,
                vol.Optional("source_entity_id"): cv.string,
                vol.Optional("category", default="evaluation"): cv.string,
                vol.Optional("summary", default="Fluxo de auditoria iniciado"): cv.string,
            }
        ),
        supports_response=SupportsResponse.ONLY,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_LOG_EVENT,
        log_event,
        schema=vol.Schema(
            {
                vol.Optional("correlation_id"): cv.string,
                vol.Required("category"): cv.string,
                vol.Required("event_type"): cv.string,
                vol.Optional("severity", default="info"): cv.string,
                vol.Required("summary"): cv.string,
                vol.Optional("outcome", default="unknown"): cv.string,
                vol.Optional("retention_class", default="full"): cv.string,
                vol.Optional("source"): cv.string,
                vol.Optional("source_component"): cv.string,
                vol.Optional("source_entity_id"): cv.string,
                vol.Optional("technical_message"): cv.string,
                vol.Optional("transmission_id"): cv.string,
                vol.Optional("frame_kind"): cv.string,
                vol.Optional("frame_hash"): cv.string,
                vol.Optional("expected_audibility", default="unknown"): cv.string,
                vol.Optional("is_external", default=False): cv.boolean,
                vol.Optional("is_anomaly", default=False): cv.boolean,
                vol.Optional("anomaly_type"): cv.string,
                vol.Optional("details"): dict,
                vol.Optional("before"): dict,
                vol.Optional("desired"): dict,
                vol.Optional("confirmed"): dict,
            },
            extra=vol.ALLOW_EXTRA,
        ),
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_REGISTER_BEEP,
        register_beep,
        schema=vol.Schema(
            {
                vol.Required("quantity"): vol.In(["1 bip", "2 bips", "vários bips", "não tenho certeza"]),
                vol.Optional("note"): cv.string,
                vol.Optional("occurred_at"): cv.string,
            }
        ),
        supports_response=SupportsResponse.OPTIONAL,
    )
    hass.services.async_register(
        DOMAIN,
        SERVICE_RUN_CLEANUP,
        run_cleanup,
        supports_response=SupportsResponse.OPTIONAL,
    )


def _async_register_websocket(hass: HomeAssistant) -> None:
    if hass.data[DOMAIN].get(DATA_WEBSOCKET_REGISTERED):
        return
    hass.data[DOMAIN][DATA_WEBSOCKET_REGISTERED] = True

    @websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/get_snapshot", vol.Optional("entry_id"): str})
    @websocket_api.async_response
    async def ws_get_snapshot(hass, connection, msg):
        connection.require_admin()
        connection.send_result(msg["id"], await _manager(hass, msg.get("entry_id")).async_get_snapshot())

    @websocket_api.websocket_command(
        {
            vol.Required("type"): f"{DOMAIN}/list_events",
            vol.Optional("entry_id"): str,
            vol.Optional("filters", default={}): dict,
            vol.Optional("cursor"): str,
            vol.Optional("limit", default=50): vol.All(vol.Coerce(int), vol.Range(min=1, max=250)),
            vol.Optional("include_details", default=False): bool,
        }
    )
    @websocket_api.async_response
    async def ws_list_events(hass, connection, msg):
        connection.require_admin()
        result = await _manager(hass, msg.get("entry_id")).storage.async_list_events(
            msg.get("filters"), cursor=msg.get("cursor"), limit=msg["limit"], include_details=msg["include_details"]
        )
        connection.send_result(msg["id"], result)

    @websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/get_event", vol.Required("event_id"): str, vol.Optional("entry_id"): str})
    @websocket_api.async_response
    async def ws_get_event(hass, connection, msg):
        connection.require_admin()
        event = await _manager(hass, msg.get("entry_id")).storage.async_get_event(msg["event_id"])
        if event is None:
            connection.send_error(msg["id"], "not_found", "Evento não encontrado.")
            return
        connection.send_result(msg["id"], event)

    @websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/get_correlation", vol.Required("correlation_id"): str, vol.Optional("entry_id"): str})
    @websocket_api.async_response
    async def ws_get_correlation(hass, connection, msg):
        connection.require_admin()
        events = await _manager(hass, msg.get("entry_id")).storage.async_get_correlation(msg["correlation_id"])
        connection.send_result(msg["id"], {"events": events})

    @websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/list_anomalies", vol.Optional("status"): str, vol.Optional("entry_id"): str})
    @websocket_api.async_response
    async def ws_list_anomalies(hass, connection, msg):
        connection.require_admin()
        anomalies = await _manager(hass, msg.get("entry_id")).storage.async_list_anomalies(msg.get("status"), limit=500)
        connection.send_result(msg["id"], {"anomalies": anomalies})

    @websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/update_settings", vol.Required("settings"): dict, vol.Optional("entry_id"): str})
    @websocket_api.async_response
    async def ws_update_settings(hass, connection, msg):
        connection.require_admin()
        context = Context(user_id=connection.user.id)
        settings = await _manager(hass, msg.get("entry_id")).async_update_settings(msg["settings"], context=context)
        connection.send_result(msg["id"], {"settings": settings})

    @websocket_api.websocket_command(
        {
            vol.Required("type"): f"{DOMAIN}/register_beep",
            vol.Required("quantity"): vol.In(["1 bip", "2 bips", "vários bips", "não tenho certeza"]),
            vol.Optional("note"): str,
            vol.Optional("occurred_at"): str,
            vol.Optional("entry_id"): str,
        }
    )
    @websocket_api.async_response
    async def ws_register_beep(hass, connection, msg):
        connection.require_admin()
        result = await _manager(hass, msg.get("entry_id")).async_register_beep(
            quantity=msg["quantity"], note=msg.get("note"), occurred_at=msg.get("occurred_at"), context=Context(user_id=connection.user.id)
        )
        connection.send_result(msg["id"], result)

    @websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/acknowledge_anomaly", vol.Required("anomaly_id"): str, vol.Optional("entry_id"): str})
    @websocket_api.async_response
    async def ws_acknowledge_anomaly(hass, connection, msg):
        connection.require_admin()
        changed = await _manager(hass, msg.get("entry_id")).storage.async_acknowledge_anomaly(msg["anomaly_id"])
        connection.send_result(msg["id"], {"acknowledged": changed})

    @websocket_api.websocket_command(
        {
            vol.Required("type"): f"{DOMAIN}/create_export",
            vol.Required("export_type"): vol.In(["csv", "json", "diagnostic_package", "problem_report"]),
            vol.Optional("filters", default={}): dict,
            vol.Optional("entry_id"): str,
        }
    )
    @websocket_api.async_response
    async def ws_create_export(hass, connection, msg):
        connection.require_admin()
        result = await _manager(hass, msg.get("entry_id")).exporter.async_create(msg["export_type"], msg.get("filters"))
        connection.send_result(msg["id"], result)

    @websocket_api.websocket_command(
        {
            vol.Required("type"): f"{DOMAIN}/clear_events",
            vol.Optional("before"): str,
            vol.Optional("entry_id"): str,
        }
    )
    @websocket_api.async_response
    async def ws_clear_events(hass, connection, msg):
        connection.require_admin()
        count = await _manager(hass, msg.get("entry_id")).storage.async_clear_events(before=msg.get("before"))
        connection.send_result(msg["id"], {"deleted": count})

    @websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/run_cleanup", vol.Optional("entry_id"): str})
    @websocket_api.async_response
    async def ws_run_cleanup(hass, connection, msg):
        connection.require_admin()
        result = await _manager(hass, msg.get("entry_id")).async_run_cleanup(actor=connection.user.name or "Administrador")
        connection.send_result(msg["id"], result)

    @websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/reevaluate_anomalies", vol.Optional("entry_id"): str})
    @websocket_api.async_response
    async def ws_reevaluate_anomalies(hass, connection, msg):
        connection.require_admin()
        result = await _manager(hass, msg.get("entry_id")).anomaly.async_reevaluate()
        connection.send_result(msg["id"], result)

    for command in (
        ws_get_snapshot,
        ws_list_events,
        ws_get_event,
        ws_get_correlation,
        ws_list_anomalies,
        ws_update_settings,
        ws_register_beep,
        ws_acknowledge_anomaly,
        ws_create_export,
        ws_clear_events,
        ws_run_cleanup,
        ws_reevaluate_anomalies,
    ):
        websocket_api.async_register_command(hass, command)
