"""Elgin Supervisor Agenda integration."""

from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path

import voluptuous as vol

from homeassistant.components import websocket_api
from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ID, CONF_URL, EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers.event import async_call_later
from homeassistant.util import dt as dt_util

from .const import (
    DOMAIN,
    FRONTEND_RESOURCE_BASE,
    FRONTEND_RESOURCE_URL,
    FRONTEND_STATIC_URL,
    PLATFORMS,
)
from .entity import ENTITY_DOMAINS, OBJECT_IDS, canonical_entity_id
from .manager import AgendaManager

DATA_MANAGERS = "managers"
DATA_CORE_REGISTERED = "core_registered"
DATA_FRONTEND_PATH_REGISTERED = "frontend_path_registered"
DATA_RESOURCE_RETRY_SCHEDULED = "resource_retry_scheduled"

FRONTEND_DIRECTORY = Path(__file__).parent / "frontend"
RESOURCE_RETRY_SECONDS = 2
RESOURCE_RETRY_LIMIT = 15

_LOGGER = logging.getLogger(__name__)


def _manager(hass: HomeAssistant, entry_id: str | None = None) -> AgendaManager:
    managers: dict[str, AgendaManager] = hass.data[DOMAIN][DATA_MANAGERS]
    if entry_id and entry_id in managers:
        return managers[entry_id]
    if not managers:
        raise ValueError("Nenhuma agenda configurada")
    return next(iter(managers.values()))


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up integration-wide services and the embedded frontend module."""
    hass.data.setdefault(DOMAIN, {}).setdefault(DATA_MANAGERS, {})
    await _async_register_frontend_path(hass)
    _register_core_once(hass)

    if hass.state is CoreState.running:
        await _async_register_lovelace_resource(hass)
    else:
        async def _after_started(_event) -> None:
            await _async_register_lovelace_resource(hass)

        hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STARTED, _after_started)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {}).setdefault(DATA_MANAGERS, {})
    await _async_register_frontend_path(hass)
    _register_core_once(hass)
    await _async_register_lovelace_resource(hass)

    manager = AgendaManager(hass, entry.entry_id, entry.data.get("name", entry.title))
    entry.runtime_data = manager
    hass.data[DOMAIN][DATA_MANAGERS][entry.entry_id] = manager
    await manager.async_load()

    # The package and dashboard use stable IDs as an internal API. Migrate any
    # IDs generated with area/device prefixes before loading the entity platforms.
    _async_migrate_entity_ids(hass, entry)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # Fresh entities only enter the registry after the platforms are forwarded.
    # Normalize immediately and retry after the registry/UI settles.
    _async_migrate_entity_ids(hass, entry)

    async def _retry_entity_ids(_now) -> None:
        _async_migrate_entity_ids(hass, entry)

    async_call_later(hass, 1, _retry_entity_ids)
    async_call_later(hass, 5, _retry_entity_ids)
    return True


def _register_core_once(hass: HomeAssistant) -> None:
    data = hass.data.setdefault(DOMAIN, {})
    if data.get(DATA_CORE_REGISTERED):
        return
    _register_websocket_commands(hass)
    _register_services(hass)
    data[DATA_CORE_REGISTERED] = True


async def _async_register_frontend_path(hass: HomeAssistant) -> None:
    """Serve the card from the integration so backend and frontend stay atomic."""
    data = hass.data.setdefault(DOMAIN, {})
    if data.get(DATA_FRONTEND_PATH_REGISTERED):
        return
    try:
        await hass.http.async_register_static_paths(
            [StaticPathConfig(FRONTEND_STATIC_URL, str(FRONTEND_DIRECTORY), False)]
        )
    except RuntimeError:
        # A reload can encounter a path registered by the previous entry setup.
        _LOGGER.debug("Caminho estático da Agenda já estava registrado")
    data[DATA_FRONTEND_PATH_REGISTERED] = True


@callback
def _schedule_resource_retry(hass: HomeAssistant, attempt: int) -> None:
    """Retry after Lovelace finishes loading without creating duplicate timers."""
    if attempt >= RESOURCE_RETRY_LIMIT:
        _LOGGER.error(
            "Não foi possível registrar o recurso Lovelace após %s tentativas; "
            "registre manualmente %s como módulo",
            RESOURCE_RETRY_LIMIT,
            FRONTEND_RESOURCE_URL,
        )
        return

    data = hass.data.setdefault(DOMAIN, {})
    if data.get(DATA_RESOURCE_RETRY_SCHEDULED):
        return
    data[DATA_RESOURCE_RETRY_SCHEDULED] = True

    async def _retry(_now) -> None:
        data[DATA_RESOURCE_RETRY_SCHEDULED] = False
        await _async_register_lovelace_resource(hass, attempt + 1)

    async_call_later(hass, RESOURCE_RETRY_SECONDS, _retry)


async def _async_register_lovelace_resource(
    hass: HomeAssistant, attempt: int = 0
) -> bool:
    """Register one canonical module and remove every obsolete Agenda resource."""
    try:
        from homeassistant.components.lovelace.const import (
            CONF_RESOURCE_TYPE_WS,
            LOVELACE_DATA,
            MODE_STORAGE,
        )

        lovelace_data = hass.data.get(LOVELACE_DATA)
        if lovelace_data is None:
            _schedule_resource_retry(hass, attempt)
            return False
        if lovelace_data.resource_mode != MODE_STORAGE:
            _LOGGER.warning(
                "Os recursos Lovelace não estão em modo storage. Registre "
                "manualmente %s como módulo",
                FRONTEND_RESOURCE_URL,
            )
            return False

        resources = lovelace_data.resources
        await resources.async_get_info()
        items = list(resources.async_items())
        managed_prefixes = (
            "/local/elgin_supervisor_agenda/",
            f"{FRONTEND_STATIC_URL}/",
        )
        managed = [
            item
            for item in items
            if any(
                str(item.get(CONF_URL, "")).split("?", 1)[0].startswith(prefix)
                for prefix in managed_prefixes
            )
        ]
        canonical = next(
            (
                item
                for item in managed
                if str(item.get(CONF_URL, "")).split("?", 1)[0]
                == FRONTEND_RESOURCE_BASE
            ),
            None,
        )
        resource_data = {
            CONF_RESOURCE_TYPE_WS: "module",
            CONF_URL: FRONTEND_RESOURCE_URL,
        }

        if canonical is None:
            canonical = await resources.async_create_item(resource_data)
            _LOGGER.info("Recurso Lovelace canônico da Agenda registrado: %s", FRONTEND_RESOURCE_URL)
        elif (
            canonical.get(CONF_URL) != FRONTEND_RESOURCE_URL
            or canonical.get(CONF_RESOURCE_TYPE_WS) != "module"
        ):
            canonical = await resources.async_update_item(canonical[CONF_ID], resource_data)
            _LOGGER.info("Recurso Lovelace canônico da Agenda atualizado: %s", FRONTEND_RESOURCE_URL)

        canonical_id = canonical.get(CONF_ID)
        for item in managed:
            if item.get(CONF_ID) != canonical_id:
                await resources.async_delete_item(item[CONF_ID])
                _LOGGER.info("Recurso Lovelace antigo removido: %s", item.get(CONF_URL))
        return True
    except Exception:  # noqa: BLE001
        if attempt + 1 < RESOURCE_RETRY_LIMIT:
            _LOGGER.debug(
                "Lovelace ainda não pronto para o recurso da Agenda; nova tentativa",
                exc_info=True,
            )
            _schedule_resource_retry(hass, attempt)
        else:
            _LOGGER.exception("Falha definitiva ao registrar o recurso Lovelace da Agenda")
        return False


@callback
def _async_migrate_entity_ids(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Normalize area-prefixed entity IDs to the stable integration contract."""
    registry = er.async_get(hass)
    for key in OBJECT_IDS:
        domain = ENTITY_DOMAINS[key]
        unique_id = f"{entry.entry_id}_{key}"
        current_entity_id = registry.async_get_entity_id(domain, DOMAIN, unique_id)
        target_entity_id = canonical_entity_id(key)
        if current_entity_id is None or current_entity_id == target_entity_id:
            continue

        occupied = registry.async_get(target_entity_id)
        if occupied is not None and occupied.unique_id != unique_id:
            # Previous failed migrations can leave a disabled/orphan registry
            # entry at the canonical ID. Remove only entries owned by this same
            # config entry and platform; never touch unrelated entities.
            if occupied.config_entry_id == entry.entry_id and occupied.platform == DOMAIN:
                registry.async_remove(target_entity_id)
                _LOGGER.warning("Registro órfão removido antes da migração: %s", target_entity_id)
            else:
                _LOGGER.error(
                    "Não foi possível migrar %s para %s: o destino pertence a outra entidade",
                    current_entity_id,
                    target_entity_id,
                )
                continue
        try:
            registry.async_update_entity(
                current_entity_id,
                new_entity_id=target_entity_id,
            )
            _LOGGER.info("Entity ID da Agenda normalizado: %s -> %s", current_entity_id, target_entity_id)
        except ValueError:
            _LOGGER.exception(
                "Falha ao normalizar Entity ID da Agenda: %s -> %s",
                current_entity_id,
                target_entity_id,
            )


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        manager: AgendaManager = entry.runtime_data
        await manager.async_unload()
        hass.data[DOMAIN][DATA_MANAGERS].pop(entry.entry_id, None)
    return unloaded


def _register_services(hass: HomeAssistant) -> None:
    async def create_or_update(call: ServiceCall) -> None:
        await _manager(hass, call.data.get("entry_id")).async_upsert_rule(call.data["rule"])

    async def delete(call: ServiceCall) -> None:
        await _manager(hass, call.data.get("entry_id")).async_delete_rule(call.data["rule_id"])

    async def set_enabled(call: ServiceCall) -> None:
        await _manager(hass, call.data.get("entry_id")).async_set_rule_enabled(
            call.data["rule_id"], call.data["enabled"]
        )

    async def evaluate(call: ServiceCall) -> None:
        await _manager(hass, call.data.get("entry_id")).async_manual_evaluate()

    async def clear(call: ServiceCall) -> None:
        await _manager(hass, call.data.get("entry_id")).async_clear_rules()

    async def cancel(call: ServiceCall) -> None:
        await _manager(hass, call.data.get("entry_id")).async_cancel_active_once_rules()

    async def save_preset(call: ServiceCall) -> None:
        await _manager(hass, call.data.get("entry_id")).async_upsert_preset(call.data["preset"])

    async def delete_preset(call: ServiceCall) -> None:
        await _manager(hass, call.data.get("entry_id")).async_delete_preset(call.data["preset_id"])

    async def set_base_preset(call: ServiceCall) -> None:
        await _manager(hass, call.data.get("entry_id")).async_set_base_preset(
            call.data["mode"], call.data["preset_id"]
        )

    async def save_power_profile(call: ServiceCall) -> None:
        await _manager(hass, call.data.get("entry_id")).async_upsert_power_profile(call.data["profile"])

    async def delete_power_profile(call: ServiceCall) -> None:
        await _manager(hass, call.data.get("entry_id")).async_delete_power_profile(call.data["profile_id"])

    async def set_base_power_profile(call: ServiceCall) -> None:
        await _manager(hass, call.data.get("entry_id")).async_set_base_power_profile(
            call.data["mode"], call.data["profile_id"]
        )

    async def save_power_rule(call: ServiceCall) -> None:
        await _manager(hass, call.data.get("entry_id")).async_upsert_power_rule(call.data["rule"])

    async def delete_power_rule(call: ServiceCall) -> None:
        await _manager(hass, call.data.get("entry_id")).async_delete_power_rule(call.data["rule_id"])

    async def set_power_rule_enabled(call: ServiceCall) -> None:
        await _manager(hass, call.data.get("entry_id")).async_set_power_rule_enabled(
            call.data["rule_id"], call.data["enabled"]
        )

    async def update_power_settings(call: ServiceCall) -> None:
        await _manager(hass, call.data.get("entry_id")).async_update_power_settings(call.data["settings"])

    async def restore_default_power_profiles(call: ServiceCall) -> None:
        await _manager(hass, call.data.get("entry_id")).async_restore_default_power_profiles()

    optional_entry = {vol.Optional("entry_id"): str}
    hass.services.async_register(
        DOMAIN,
        "create_rule",
        create_or_update,
        schema=vol.Schema({vol.Required("rule"): dict, **optional_entry}),
    )
    hass.services.async_register(
        DOMAIN,
        "update_rule",
        create_or_update,
        schema=vol.Schema({vol.Required("rule"): dict, **optional_entry}),
    )
    hass.services.async_register(
        DOMAIN,
        "delete_rule",
        delete,
        schema=vol.Schema({vol.Required("rule_id"): str, **optional_entry}),
    )
    hass.services.async_register(
        DOMAIN,
        "set_rule_enabled",
        set_enabled,
        schema=vol.Schema(
            {
                vol.Required("rule_id"): str,
                vol.Required("enabled"): bool,
                **optional_entry,
            }
        ),
    )
    hass.services.async_register(DOMAIN, "evaluate", evaluate, schema=vol.Schema(optional_entry))
    hass.services.async_register(DOMAIN, "clear_rules", clear, schema=vol.Schema(optional_entry))
    hass.services.async_register(
        DOMAIN, "cancel_active_once_rules", cancel, schema=vol.Schema(optional_entry)
    )
    hass.services.async_register(
        DOMAIN,
        "save_preset",
        save_preset,
        schema=vol.Schema({vol.Required("preset"): dict, **optional_entry}),
    )
    hass.services.async_register(
        DOMAIN,
        "delete_preset",
        delete_preset,
        schema=vol.Schema({vol.Required("preset_id"): str, **optional_entry}),
    )
    hass.services.async_register(
        DOMAIN,
        "set_base_preset",
        set_base_preset,
        schema=vol.Schema(
            {
                vol.Required("mode"): vol.In(["heat", "cool", "dry"]),
                vol.Required("preset_id"): str,
                **optional_entry,
            }
        ),
    )
    hass.services.async_register(
        DOMAIN, "save_power_profile", save_power_profile,
        schema=vol.Schema({vol.Required("profile"): dict, **optional_entry}),
    )
    hass.services.async_register(
        DOMAIN, "delete_power_profile", delete_power_profile,
        schema=vol.Schema({vol.Required("profile_id"): str, **optional_entry}),
    )
    hass.services.async_register(
        DOMAIN, "set_base_power_profile", set_base_power_profile,
        schema=vol.Schema({
            vol.Required("mode"): vol.In(["heat", "cool", "dry"]),
            vol.Required("profile_id"): str,
            **optional_entry,
        }),
    )
    hass.services.async_register(
        DOMAIN, "save_power_rule", save_power_rule,
        schema=vol.Schema({vol.Required("rule"): dict, **optional_entry}),
    )
    hass.services.async_register(
        DOMAIN, "delete_power_rule", delete_power_rule,
        schema=vol.Schema({vol.Required("rule_id"): str, **optional_entry}),
    )
    hass.services.async_register(
        DOMAIN, "set_power_rule_enabled", set_power_rule_enabled,
        schema=vol.Schema({
            vol.Required("rule_id"): str,
            vol.Required("enabled"): bool,
            **optional_entry,
        }),
    )
    hass.services.async_register(
        DOMAIN, "update_power_settings", update_power_settings,
        schema=vol.Schema({vol.Required("settings"): dict, **optional_entry}),
    )
    hass.services.async_register(
        DOMAIN, "restore_default_power_profiles", restore_default_power_profiles,
        schema=vol.Schema(optional_entry),
    )


def _register_websocket_commands(hass: HomeAssistant) -> None:
    @websocket_api.websocket_command(
        {vol.Required("type"): f"{DOMAIN}/get_snapshot", vol.Optional("entry_id"): str}
    )
    @websocket_api.async_response
    async def ws_get_snapshot(hass, connection, msg):
        manager = _manager(hass, msg.get("entry_id"))
        connection.send_result(msg["id"], manager.public_snapshot())

    @websocket_api.websocket_command(
        {vol.Required("type"): f"{DOMAIN}/list_rules", vol.Optional("entry_id"): str}
    )
    @websocket_api.async_response
    async def ws_list_rules(hass, connection, msg):
        manager = _manager(hass, msg.get("entry_id"))
        connection.send_result(msg["id"], manager.public_snapshot())

    @websocket_api.websocket_command(
        {
            vol.Required("type"): f"{DOMAIN}/save_rule",
            vol.Required("rule"): dict,
            vol.Optional("entry_id"): str,
        }
    )
    @websocket_api.require_admin
    @websocket_api.async_response
    async def ws_save_rule(hass, connection, msg):
        manager = _manager(hass, msg.get("entry_id"))
        try:
            rule = await manager.async_upsert_rule(msg["rule"])
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("Falha ao salvar regra da Agenda")
            detail = str(err) or type(err).__name__
            raise HomeAssistantError(
                f"Não foi possível salvar a regra: {detail}"
            ) from err
        connection.send_result(msg["id"], rule)

    @websocket_api.websocket_command(
        {
            vol.Required("type"): f"{DOMAIN}/delete_rule",
            vol.Required("rule_id"): str,
            vol.Optional("entry_id"): str,
        }
    )
    @websocket_api.require_admin
    @websocket_api.async_response
    async def ws_delete_rule(hass, connection, msg):
        manager = _manager(hass, msg.get("entry_id"))
        try:
            result = await manager.async_delete_rule(msg["rule_id"])
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("Falha ao excluir regra da Agenda")
            detail = str(err) or type(err).__name__
            raise HomeAssistantError(
                f"Não foi possível excluir a regra: {detail}"
            ) from err
        connection.send_result(msg["id"], result)

    @websocket_api.websocket_command(
        {
            vol.Required("type"): f"{DOMAIN}/set_rule_enabled",
            vol.Required("rule_id"): str,
            vol.Required("enabled"): bool,
            vol.Optional("entry_id"): str,
        }
    )
    @websocket_api.require_admin
    @websocket_api.async_response
    async def ws_set_rule_enabled(hass, connection, msg):
        manager = _manager(hass, msg.get("entry_id"))
        try:
            result = await manager.async_set_rule_enabled(
                msg["rule_id"], msg["enabled"]
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("Falha ao alterar regra da Agenda")
            detail = str(err) or type(err).__name__
            raise HomeAssistantError(
                f"Não foi possível alterar a regra: {detail}"
            ) from err
        connection.send_result(msg["id"], result)

    @websocket_api.websocket_command(
        {vol.Required("type"): f"{DOMAIN}/evaluate", vol.Optional("entry_id"): str}
    )
    @websocket_api.async_response
    async def ws_evaluate(hass, connection, msg):
        manager = _manager(hass, msg.get("entry_id"))
        await manager.async_manual_evaluate()
        connection.send_result(msg["id"], manager.policy)

    @websocket_api.websocket_command(
        {vol.Required("type"): f"{DOMAIN}/list_presets", vol.Optional("entry_id"): str}
    )
    @websocket_api.async_response
    async def ws_list_presets(hass, connection, msg):
        manager = _manager(hass, msg.get("entry_id"))
        connection.send_result(
            msg["id"],
            {
                "entry_id": manager.entry_id,
                "presets": manager.public_presets(),
                "base_presets": dict(manager.base_presets),
                "preset_state": manager.preset_state,
                "catalog": manager.catalog,
            },
        )

    @websocket_api.websocket_command(
        {
            vol.Required("type"): f"{DOMAIN}/save_preset",
            vol.Required("preset"): dict,
            vol.Optional("entry_id"): str,
        }
    )
    @websocket_api.require_admin
    @websocket_api.async_response
    async def ws_save_preset(hass, connection, msg):
        manager = _manager(hass, msg.get("entry_id"))
        try:
            preset = await manager.async_upsert_preset(msg["preset"])
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("Falha ao salvar preset de condição")
            raise HomeAssistantError(str(err) or type(err).__name__) from err
        connection.send_result(msg["id"], preset)

    @websocket_api.websocket_command(
        {
            vol.Required("type"): f"{DOMAIN}/delete_preset",
            vol.Required("preset_id"): str,
            vol.Optional("entry_id"): str,
        }
    )
    @websocket_api.require_admin
    @websocket_api.async_response
    async def ws_delete_preset(hass, connection, msg):
        manager = _manager(hass, msg.get("entry_id"))
        try:
            result = await manager.async_delete_preset(msg["preset_id"])
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("Falha ao excluir preset de condição")
            raise HomeAssistantError(str(err) or type(err).__name__) from err
        connection.send_result(msg["id"], result)

    @websocket_api.websocket_command(
        {
            vol.Required("type"): f"{DOMAIN}/set_base_preset",
            vol.Required("mode"): vol.In(["heat", "cool", "dry"]),
            vol.Required("preset_id"): str,
            vol.Optional("entry_id"): str,
        }
    )
    @websocket_api.require_admin
    @websocket_api.async_response
    async def ws_set_base_preset(hass, connection, msg):
        manager = _manager(hass, msg.get("entry_id"))
        try:
            preset = await manager.async_set_base_preset(msg["mode"], msg["preset_id"])
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("Falha ao alterar preset base")
            raise HomeAssistantError(str(err) or type(err).__name__) from err
        connection.send_result(msg["id"], preset)

    @websocket_api.websocket_command(
        {
            vol.Required("type"): f"{DOMAIN}/duplicate_preset",
            vol.Required("preset_id"): str,
            vol.Optional("mode"): vol.In(["heat", "cool", "dry"]),
            vol.Optional("entry_id"): str,
        }
    )
    @websocket_api.require_admin
    @websocket_api.async_response
    async def ws_duplicate_preset(hass, connection, msg):
        manager = _manager(hass, msg.get("entry_id"))
        try:
            preset = await manager.async_duplicate_preset(msg["preset_id"], msg.get("mode"))
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("Falha ao duplicar preset")
            raise HomeAssistantError(str(err) or type(err).__name__) from err
        connection.send_result(msg["id"], preset)


    @websocket_api.websocket_command(
        {vol.Required("type"): f"{DOMAIN}/list_configuration", vol.Optional("entry_id"): str}
    )
    @websocket_api.async_response
    async def ws_list_configuration(hass, connection, msg):
        manager = _manager(hass, msg.get("entry_id"))
        connection.send_result(msg["id"], manager.public_snapshot())

    @websocket_api.websocket_command(
        {
            vol.Required("type"): f"{DOMAIN}/save_power_profile",
            vol.Required("profile"): dict,
            vol.Optional("entry_id"): str,
        }
    )
    @websocket_api.require_admin
    @websocket_api.async_response
    async def ws_save_power_profile(hass, connection, msg):
        try:
            result = await _manager(hass, msg.get("entry_id")).async_upsert_power_profile(msg["profile"])
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("Falha ao salvar perfil de potência")
            raise HomeAssistantError(str(err) or type(err).__name__) from err
        connection.send_result(msg["id"], result)

    @websocket_api.websocket_command(
        {
            vol.Required("type"): f"{DOMAIN}/duplicate_power_profile",
            vol.Required("profile_id"): str,
            vol.Optional("mode"): vol.In(["heat", "cool", "dry"]),
            vol.Optional("entry_id"): str,
        }
    )
    @websocket_api.require_admin
    @websocket_api.async_response
    async def ws_duplicate_power_profile(hass, connection, msg):
        try:
            result = await _manager(hass, msg.get("entry_id")).async_duplicate_power_profile(
                msg["profile_id"], msg.get("mode")
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("Falha ao duplicar perfil de potência")
            raise HomeAssistantError(str(err) or type(err).__name__) from err
        connection.send_result(msg["id"], result)

    @websocket_api.websocket_command(
        {
            vol.Required("type"): f"{DOMAIN}/delete_power_profile",
            vol.Required("profile_id"): str,
            vol.Optional("entry_id"): str,
        }
    )
    @websocket_api.require_admin
    @websocket_api.async_response
    async def ws_delete_power_profile(hass, connection, msg):
        try:
            result = await _manager(hass, msg.get("entry_id")).async_delete_power_profile(msg["profile_id"])
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("Falha ao excluir perfil de potência")
            raise HomeAssistantError(str(err) or type(err).__name__) from err
        connection.send_result(msg["id"], result)

    @websocket_api.websocket_command(
        {
            vol.Required("type"): f"{DOMAIN}/set_base_power_profile",
            vol.Required("mode"): vol.In(["heat", "cool", "dry"]),
            vol.Required("profile_id"): str,
            vol.Optional("entry_id"): str,
        }
    )
    @websocket_api.require_admin
    @websocket_api.async_response
    async def ws_set_base_power_profile(hass, connection, msg):
        try:
            result = await _manager(hass, msg.get("entry_id")).async_set_base_power_profile(
                msg["mode"], msg["profile_id"]
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("Falha ao alterar potência base")
            raise HomeAssistantError(str(err) or type(err).__name__) from err
        connection.send_result(msg["id"], result)

    @websocket_api.websocket_command(
        {
            vol.Required("type"): f"{DOMAIN}/save_power_rule",
            vol.Required("rule"): dict,
            vol.Optional("entry_id"): str,
        }
    )
    @websocket_api.require_admin
    @websocket_api.async_response
    async def ws_save_power_rule(hass, connection, msg):
        try:
            result = await _manager(hass, msg.get("entry_id")).async_upsert_power_rule(msg["rule"])
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("Falha ao salvar regra dinâmica de potência")
            raise HomeAssistantError(str(err) or type(err).__name__) from err
        connection.send_result(msg["id"], result)

    @websocket_api.websocket_command(
        {
            vol.Required("type"): f"{DOMAIN}/delete_power_rule",
            vol.Required("rule_id"): str,
            vol.Optional("entry_id"): str,
        }
    )
    @websocket_api.require_admin
    @websocket_api.async_response
    async def ws_delete_power_rule(hass, connection, msg):
        try:
            result = await _manager(hass, msg.get("entry_id")).async_delete_power_rule(msg["rule_id"])
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("Falha ao excluir regra dinâmica de potência")
            raise HomeAssistantError(str(err) or type(err).__name__) from err
        connection.send_result(msg["id"], result)

    @websocket_api.websocket_command(
        {
            vol.Required("type"): f"{DOMAIN}/set_power_rule_enabled",
            vol.Required("rule_id"): str,
            vol.Required("enabled"): bool,
            vol.Optional("entry_id"): str,
        }
    )
    @websocket_api.require_admin
    @websocket_api.async_response
    async def ws_set_power_rule_enabled(hass, connection, msg):
        try:
            result = await _manager(hass, msg.get("entry_id")).async_set_power_rule_enabled(
                msg["rule_id"], msg["enabled"]
            )
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("Falha ao alterar regra dinâmica de potência")
            raise HomeAssistantError(str(err) or type(err).__name__) from err
        connection.send_result(msg["id"], result)

    @websocket_api.websocket_command(
        {
            vol.Required("type"): f"{DOMAIN}/update_power_settings",
            vol.Required("settings"): dict,
            vol.Optional("entry_id"): str,
        }
    )
    @websocket_api.require_admin
    @websocket_api.async_response
    async def ws_update_power_settings(hass, connection, msg):
        try:
            result = await _manager(hass, msg.get("entry_id")).async_update_power_settings(msg["settings"])
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("Falha ao atualizar limites e prioridades")
            raise HomeAssistantError(str(err) or type(err).__name__) from err
        connection.send_result(msg["id"], result)

    @websocket_api.websocket_command(
        {vol.Required("type"): f"{DOMAIN}/restore_default_power_profiles", vol.Optional("entry_id"): str}
    )
    @websocket_api.require_admin
    @websocket_api.async_response
    async def ws_restore_default_power_profiles(hass, connection, msg):
        try:
            result = await _manager(hass, msg.get("entry_id")).async_restore_default_power_profiles()
        except Exception as err:  # noqa: BLE001
            _LOGGER.exception("Falha ao restaurar perfis padrões")
            raise HomeAssistantError(str(err) or type(err).__name__) from err
        connection.send_result(msg["id"], result)

    @websocket_api.websocket_command(
        {
            vol.Required("type"): f"{DOMAIN}/get_occurrences",
            vol.Required("start"): str,
            vol.Required("end"): str,
            vol.Optional("entry_id"): str,
        }
    )
    @websocket_api.async_response
    async def ws_get_occurrences(hass, connection, msg):
        manager = _manager(hass, msg.get("entry_id"))
        start = dt_util.parse_datetime(msg["start"])
        end = dt_util.parse_datetime(msg["end"])
        if start is None or end is None:
            raise HomeAssistantError("Intervalo de calendário inválido")
        start = dt_util.as_local(start)
        end = dt_util.as_local(end)
        if end <= start:
            raise HomeAssistantError("O fim do intervalo deve ser posterior ao início")
        if end - start > timedelta(days=370):
            raise HomeAssistantError("O intervalo máximo do calendário é de 370 dias")
        connection.send_result(
            msg["id"],
            {
                "entry_id": manager.entry_id,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "occurrences": manager.public_occurrences(
                    start, end, max_events=2500
                ),
            },
        )

    websocket_api.async_register_command(hass, ws_get_snapshot)
    websocket_api.async_register_command(hass, ws_list_rules)
    websocket_api.async_register_command(hass, ws_save_rule)
    websocket_api.async_register_command(hass, ws_delete_rule)
    websocket_api.async_register_command(hass, ws_set_rule_enabled)
    websocket_api.async_register_command(hass, ws_evaluate)
    websocket_api.async_register_command(hass, ws_list_presets)
    websocket_api.async_register_command(hass, ws_save_preset)
    websocket_api.async_register_command(hass, ws_delete_preset)
    websocket_api.async_register_command(hass, ws_set_base_preset)
    websocket_api.async_register_command(hass, ws_duplicate_preset)
    websocket_api.async_register_command(hass, ws_list_configuration)
    websocket_api.async_register_command(hass, ws_save_power_profile)
    websocket_api.async_register_command(hass, ws_duplicate_power_profile)
    websocket_api.async_register_command(hass, ws_delete_power_profile)
    websocket_api.async_register_command(hass, ws_set_base_power_profile)
    websocket_api.async_register_command(hass, ws_save_power_rule)
    websocket_api.async_register_command(hass, ws_delete_power_rule)
    websocket_api.async_register_command(hass, ws_set_power_rule_enabled)
    websocket_api.async_register_command(hass, ws_update_power_settings)
    websocket_api.async_register_command(hass, ws_restore_default_power_profiles)
    websocket_api.async_register_command(hass, ws_get_occurrences)
