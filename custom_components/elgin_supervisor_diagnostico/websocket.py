"""WebSocket API for the reactive Supervisor diagnostic card."""

from __future__ import annotations

from collections.abc import Callable
import logging
from typing import Any

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.core import Context, HomeAssistant, callback

from .const import DATA_ENTRIES, DATA_WEBSOCKET_REGISTERED, DOMAIN
from .query import FILTER_FIELDS, OPERATORS

_LOGGER = logging.getLogger(__name__)
PREFIX = DOMAIN


def _manager(hass: HomeAssistant, entry_id: str | None = None):
    entries = hass.data.get(DOMAIN, {}).get(DATA_ENTRIES, {})
    if entry_id:
        if entry_id not in entries:
            raise ValueError("Instância de diagnóstico não encontrada")
        return entries[entry_id].manager
    if not entries:
        raise ValueError("A integração de diagnóstico não está configurada")
    return next(iter(entries.values())).manager


def _context(connection, msg: dict[str, Any]) -> Context:
    return Context(user_id=getattr(connection, "user", None).id if getattr(connection, "user", None) else None)


def _error(connection, msg_id: int, err: Exception) -> None:
    _LOGGER.debug("Falha WebSocket do diagnóstico", exc_info=True)
    connection.send_error(msg_id, "diagnostic_error", str(err))


def _schema(command: str, values: dict[Any, Any] | None = None) -> dict[Any, Any]:
    """Return the raw mapping expected by Home Assistant's WS decorator."""

    return {
        vol.Required("type"): f"{PREFIX}/{command}",
        vol.Optional("entry_id"): str,
        **(values or {}),
    }


def async_register_websocket(hass: HomeAssistant) -> None:
    data = hass.data.setdefault(DOMAIN, {})
    if data.get(DATA_WEBSOCKET_REGISTERED):
        return
    for command in (
        ws_get_snapshot,
        ws_list_events,
        ws_get_event,
        ws_get_evaluation,
        ws_get_correlation,
        ws_get_filter_catalog,
        ws_get_statistics,
        ws_list_anomalies,
        ws_list_observations,
        ws_acknowledge_anomaly,
        ws_resolve_anomaly,
        ws_register_observation,
        ws_delete_observation,
        ws_get_settings,
        ws_update_settings,
        ws_create_export,
        ws_clear_events,
        ws_run_cleanup,
        ws_reevaluate_anomalies,
        ws_subscribe,
    ):
        websocket_api.async_register_command(hass, command)
    data[DATA_WEBSOCKET_REGISTERED] = True


@websocket_api.websocket_command(
    _schema("get_snapshot", {vol.Optional("include_recent", default=True): bool})
)
@websocket_api.async_response
async def ws_get_snapshot(hass, connection, msg):
    try:
        result = await _manager(hass, msg.get("entry_id")).async_get_snapshot(
            include_recent=msg["include_recent"]
        )
        connection.send_result(msg["id"], result)
    except Exception as err:
        _error(connection, msg["id"], err)


@websocket_api.websocket_command(
    _schema(
        "list_events",
        {
            vol.Optional("filters", default={}): dict,
            vol.Optional("cursor"): str,
            vol.Optional("limit", default=50): vol.All(vol.Coerce(int), vol.Range(min=1, max=250)),
            vol.Optional("direction", default="older"): vol.In(("older", "newer")),
            vol.Optional("include_details", default=False): bool,
        },
    )
)
@websocket_api.async_response
async def ws_list_events(hass, connection, msg):
    try:
        result = await _manager(hass, msg.get("entry_id")).storage.async_list_events(
            msg["filters"],
            cursor=msg.get("cursor"),
            limit=msg["limit"],
            direction=msg["direction"],
            include_details=msg["include_details"],
        )
        connection.send_result(msg["id"], result)
    except Exception as err:
        _error(connection, msg["id"], err)


@websocket_api.websocket_command(_schema("get_event", {vol.Required("event_id"): str}))
@websocket_api.async_response
async def ws_get_event(hass, connection, msg):
    try:
        item = await _manager(hass, msg.get("entry_id")).storage.async_get_event(msg["event_id"])
        if item is None:
            connection.send_error(msg["id"], "not_found", "Evento não encontrado")
        else:
            connection.send_result(msg["id"], item)
    except Exception as err:
        _error(connection, msg["id"], err)


@websocket_api.websocket_command(_schema("get_evaluation", {vol.Required("evaluation_id"): str}))
@websocket_api.async_response
async def ws_get_evaluation(hass, connection, msg):
    try:
        item = await _manager(hass, msg.get("entry_id")).storage.async_get_evaluation(msg["evaluation_id"])
        if item is None:
            connection.send_error(msg["id"], "not_found", "Avaliação não encontrada")
        else:
            connection.send_result(msg["id"], item)
    except Exception as err:
        _error(connection, msg["id"], err)


@websocket_api.websocket_command(_schema("get_correlation", {vol.Required("correlation_id"): str}))
@websocket_api.async_response
async def ws_get_correlation(hass, connection, msg):
    try:
        connection.send_result(
            msg["id"], await _manager(hass, msg.get("entry_id")).storage.async_get_correlation(msg["correlation_id"])
        )
    except Exception as err:
        _error(connection, msg["id"], err)


@websocket_api.websocket_command(
    _schema("get_filter_catalog", {vol.Optional("filters", default={}): dict})
)
@websocket_api.async_response
async def ws_get_filter_catalog(hass, connection, msg):
    try:
        manager = _manager(hass, msg.get("entry_id"))
        result = await manager.storage.async_get_filter_catalog(msg["filters"])
        result.update(
            {
                "fields": {
                    name: {"kind": spec.kind}
                    for name, spec in FILTER_FIELDS.items()
                },
                "operators": sorted(OPERATORS),
                "quick_filters": [
                    {"id": "audible", "name": "Pode ter gerado bip", "filters": {"audibility": ["audible_expected"]}},
                    {"id": "transmissions", "name": "Solicitações de transmissão", "filters": {"has_transmission": True}},
                    {"id": "external", "name": "Externos/indeterminados", "filters": {"external": True}},
                    {"id": "errors", "name": "Erros", "filters": {"has_error": True}},
                    {"id": "blocked", "name": "Decisões bloqueadas", "filters": {"outcome": ["blocked"]}},
                    {"id": "no_change", "name": "Sem mudança", "filters": {"event_type": ["evaluation.no_change"]}},
                ],
                "saved_filters": manager.settings.as_dict().get("saved_filters", []),
            }
        )
        connection.send_result(msg["id"], result)
    except Exception as err:
        _error(connection, msg["id"], err)


@websocket_api.websocket_command(_schema("get_statistics", {vol.Optional("filters", default={}): dict}))
@websocket_api.async_response
async def ws_get_statistics(hass, connection, msg):
    try:
        connection.send_result(
            msg["id"], await _manager(hass, msg.get("entry_id")).storage.async_get_statistics(msg["filters"])
        )
    except Exception as err:
        _error(connection, msg["id"], err)


@websocket_api.websocket_command(
    _schema(
        "list_anomalies",
        {
            vol.Optional("status", default="active"): vol.In(("active", "acknowledged", "resolved", "all")),
            vol.Optional("limit", default=200): vol.All(vol.Coerce(int), vol.Range(min=1, max=500)),
        },
    )
)
@websocket_api.async_response
async def ws_list_anomalies(hass, connection, msg):
    try:
        items = await _manager(hass, msg.get("entry_id")).storage.async_list_anomalies(msg["status"], msg["limit"])
        connection.send_result(msg["id"], {"items": items, "anomalies": items})
    except Exception as err:
        _error(connection, msg["id"], err)


@websocket_api.websocket_command(
    _schema("list_observations", {vol.Optional("limit", default=200): vol.All(vol.Coerce(int), vol.Range(min=1, max=500))})
)
@websocket_api.async_response
async def ws_list_observations(hass, connection, msg):
    try:
        items = await _manager(hass, msg.get("entry_id")).storage.async_list_observations(msg["limit"])
        connection.send_result(msg["id"], {"items": items, "observations": items})
    except Exception as err:
        _error(connection, msg["id"], err)


@websocket_api.websocket_command(
    _schema("acknowledge_anomaly", {vol.Required("anomaly_id"): str, vol.Optional("note"): str})
)
@websocket_api.async_response
async def ws_acknowledge_anomaly(hass, connection, msg):
    try:
        result = await _manager(hass, msg.get("entry_id")).async_acknowledge_anomaly(
            msg["anomaly_id"], context=_context(connection, msg), note=msg.get("note")
        )
        connection.send_result(msg["id"], {"success": result})
    except Exception as err:
        _error(connection, msg["id"], err)


@websocket_api.websocket_command(
    _schema("resolve_anomaly", {vol.Required("anomaly_id"): str, vol.Optional("note"): str})
)
@websocket_api.async_response
async def ws_resolve_anomaly(hass, connection, msg):
    try:
        result = await _manager(hass, msg.get("entry_id")).async_resolve_anomaly(
            msg["anomaly_id"], context=_context(connection, msg), note=msg.get("note")
        )
        connection.send_result(msg["id"], {"success": result})
    except Exception as err:
        _error(connection, msg["id"], err)


@websocket_api.websocket_command(
    _schema(
        "register_observation",
        {
            vol.Required("observation_type"): vol.In(("beep", "note", "manual_action", "environment", "other")),
            vol.Optional("occurred_at"): str,
            vol.Optional("note", default=""): str,
            vol.Optional("expected_count"): vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
            vol.Optional("metadata", default={}): dict,
        },
    )
)
@websocket_api.async_response
async def ws_register_observation(hass, connection, msg):
    try:
        payload = {
            key: value
            for key, value in msg.items()
            if key not in {"id", "type", "entry_id"}
        }
        result = await _manager(hass, msg.get("entry_id")).async_register_observation(
            payload, context=_context(connection, msg)
        )
        connection.send_result(msg["id"], result)
    except Exception as err:
        _error(connection, msg["id"], err)


@websocket_api.websocket_command(_schema("delete_observation", {vol.Required("observation_id"): str}))
@websocket_api.require_admin
@websocket_api.async_response
async def ws_delete_observation(hass, connection, msg):
    try:
        result = await _manager(hass, msg.get("entry_id")).async_delete_observation(
            msg["observation_id"], context=_context(connection, msg)
        )
        connection.send_result(msg["id"], {"success": result})
    except Exception as err:
        _error(connection, msg["id"], err)


@websocket_api.websocket_command(_schema("get_settings"))
@websocket_api.async_response
async def ws_get_settings(hass, connection, msg):
    try:
        connection.send_result(msg["id"], {"settings": _manager(hass, msg.get("entry_id")).settings.as_dict()})
    except Exception as err:
        _error(connection, msg["id"], err)


@websocket_api.websocket_command(_schema("update_settings", {vol.Required("settings"): dict}))
@websocket_api.require_admin
@websocket_api.async_response
async def ws_update_settings(hass, connection, msg):
    try:
        result = await _manager(hass, msg.get("entry_id")).async_update_settings(msg["settings"])
        connection.send_result(msg["id"], {"settings": result})
    except Exception as err:
        _error(connection, msg["id"], err)


@websocket_api.websocket_command(
    _schema(
        "create_export",
        {
            vol.Required("format"): vol.In(("csv", "json", "text", "diagnostic_package")),
            vol.Optional("filters", default={}): dict,
            vol.Optional("include_details", default=True): bool,
        },
    )
)
@websocket_api.async_response
async def ws_create_export(hass, connection, msg):
    try:
        if msg["format"] == "diagnostic_package" and not bool(
            getattr(getattr(connection, "user", None), "is_admin", False)
        ):
            raise PermissionError(
                "O pacote de diagnóstico com fallback exige administrador"
            )
        result = await _manager(hass, msg.get("entry_id")).exporter.async_create(
            msg["format"], msg["filters"], include_details=msg["include_details"]
        )
        connection.send_result(msg["id"], result)
    except Exception as err:
        _error(connection, msg["id"], err)


@websocket_api.websocket_command(
    _schema(
        "clear_events",
        {
            vol.Required("confirmation"): str,
            vol.Optional("before"): str,
            vol.Optional("filters", default={}): dict,
        },
    )
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_clear_events(hass, connection, msg):
    try:
        if msg["confirmation"] != "APAGAR":
            _LOGGER.warning(
                "Exclusão de logs negada por confirmação inválida (user_id=%s)",
                getattr(getattr(connection, "user", None), "id", None),
            )
            raise ValueError("Confirmação destrutiva inválida; digite APAGAR")
        count = await _manager(hass, msg.get("entry_id")).storage.async_clear_events(
            before=msg.get("before"), filters=msg["filters"]
        )
        connection.send_result(msg["id"], {"success": True, "deleted": count})
    except Exception as err:
        _error(connection, msg["id"], err)


@websocket_api.websocket_command(
    _schema("run_cleanup", {vol.Required("confirmation"): str})
)
@websocket_api.require_admin
@websocket_api.async_response
async def ws_run_cleanup(hass, connection, msg):
    try:
        if msg["confirmation"] != "LIMPAR":
            _LOGGER.warning(
                "Limpeza manual negada por confirmação inválida (user_id=%s)",
                getattr(getattr(connection, "user", None), "id", None),
            )
            raise ValueError("Confirmação destrutiva inválida; digite LIMPAR")
        connection.send_result(
            msg["id"], await _manager(hass, msg.get("entry_id")).async_run_cleanup(actor="Administrador HA")
        )
    except Exception as err:
        _error(connection, msg["id"], err)


@websocket_api.websocket_command(_schema("reevaluate_anomalies"))
@websocket_api.require_admin
@websocket_api.async_response
async def ws_reevaluate_anomalies(hass, connection, msg):
    try:
        connection.send_result(
            msg["id"],
            await _manager(hass, msg.get("entry_id")).async_reevaluate_anomalies(),
        )
    except Exception as err:
        _error(connection, msg["id"], err)


@websocket_api.websocket_command(_schema("subscribe"))
@callback
def ws_subscribe(hass, connection, msg):
    try:
        manager = _manager(hass, msg.get("entry_id"))

        @callback
        def forward(event: dict[str, Any]) -> None:
            connection.send_event(msg["id"], {"type": "event", "event": event})

        unsubscribe: Callable[[], None] = manager.async_add_push_listener(forward)
        connection.subscriptions[msg["id"]] = unsubscribe
        connection.send_result(msg["id"])
    except Exception as err:
        _error(connection, msg["id"], err)
