"""Elgin Supervisor independent, local-only diagnostic integration."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import logging
from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.components.http import StaticPathConfig
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_ID, CONF_TYPE, CONF_URL
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er

from .const import (
    DATA_ENTRIES,
    DATA_FRONTEND_REGISTERED,
    DOMAIN,
    ANOMALY_TYPES,
    FRONTEND_RESOURCE_BASE,
    FRONTEND_RESOURCE_URL,
    FRONTEND_STATIC_URL,
    PLATFORMS,
    default_options,
    merged_options,
)
from .entity import ENTITY_DOMAINS, OBJECT_IDS, canonical_entity_id
from .manager import DiagnosticManager
from .migrations import (
    LEGACY_ENTITY_DOMAINS as _LEGACY_ENTITY_DOMAINS,
    LEGACY_ENTITY_MAP as _LEGACY_ENTITY_MAP,
    LEGACY_RETIRED_KEYS as _LEGACY_RETIRED_KEYS,
    migrate_options_v1,
)
from .websocket import async_register_websocket

_LOGGER = logging.getLogger(__name__)
FRONTEND_DIRECTORY = Path(__file__).parent / "frontend"
DATA_SERVICES_REGISTERED = "services_registered"


@dataclass(slots=True)
class DiagnosticRuntimeData:
    """Typed state owned by one ConfigEntry."""

    manager: DiagnosticManager

    @property
    def storage(self):
        return self.manager.storage


DiagnosticConfigEntry = ConfigEntry[DiagnosticRuntimeData]


def get_manager(hass: HomeAssistant, entry_id: str | None = None) -> DiagnosticManager:
    entries: dict[str, DiagnosticRuntimeData] = hass.data.get(DOMAIN, {}).get(DATA_ENTRIES, {})
    if entry_id:
        if entry_id not in entries:
            raise ValueError("Instância de diagnóstico não encontrada")
        return entries[entry_id].manager
    if not entries:
        raise ValueError("A integração de diagnóstico não está configurada")
    return next(iter(entries.values())).manager


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Register inert shared API pieces; no HVAC service is ever registered."""
    hass.data.setdefault(DOMAIN, {}).setdefault(DATA_ENTRIES, {})
    await _async_register_frontend(hass)
    async_register_websocket(hass)
    _register_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: DiagnosticConfigEntry) -> bool:
    """Start isolated persistence/capture for the ConfigEntry."""
    hass.data.setdefault(DOMAIN, {}).setdefault(DATA_ENTRIES, {})
    await _async_register_frontend(hass)
    async_register_websocket(hass)
    _register_services(hass)

    manager = DiagnosticManager(hass, entry)
    runtime = DiagnosticRuntimeData(manager)
    entry.runtime_data = runtime
    hass.data[DOMAIN][DATA_ENTRIES][entry.entry_id] = runtime
    try:
        _async_migrate_registries(hass, entry)
        await manager.async_start()
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
        _async_normalize_current_entities(hass, entry)
    except Exception:
        hass.data[DOMAIN][DATA_ENTRIES].pop(entry.entry_id, None)
        try:
            await manager.async_stop()
        except Exception:
            _LOGGER.debug("Falha secundária ao desfazer setup", exc_info=True)
        raise
    entry.async_on_unload(entry.add_update_listener(_async_options_updated))
    return True


async def _async_options_updated(hass: HomeAssistant, entry: DiagnosticConfigEntry) -> None:
    """Apply native options without reloading capture listeners or losing live UI state."""
    runtime = hass.data.get(DOMAIN, {}).get(DATA_ENTRIES, {}).get(entry.entry_id)
    if runtime is None:
        return
    from .models import DiagnosticSettings

    settings = DiagnosticSettings.from_options(dict(entry.options))
    settings.validate()
    runtime.manager.settings = settings
    runtime.manager.storage.settings = settings
    await runtime.manager.anomaly.async_apply_settings()
    await runtime.manager._async_periodic_cleanup(datetime.now(timezone.utc))
    runtime.manager._notify()  # Cached entities only; no climate side effect.


async def async_unload_entry(hass: HomeAssistant, entry: DiagnosticConfigEntry) -> bool:
    """Remove every listener/task and close SQLite cleanly."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if not unloaded:
        return False
    runtime = hass.data.get(DOMAIN, {}).get(DATA_ENTRIES, {}).pop(entry.entry_id, None)
    if runtime:
        await runtime.manager.async_stop()
    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate options from the non-production reference without inventing evidence."""
    if entry.version > 2:
        return False
    migrated = _migrate_options_v1(dict(entry.options))
    hass.config_entries.async_update_entry(
        entry,
        data={},
        options=migrated,
        version=2,
        minor_version=0,
    )
    return True


def _migrate_options_v1(options: dict[str, Any]) -> dict[str, Any]:
    """Return one complete, repeatable v2 options mapping."""
    return merged_options(
        migrate_options_v1(options, default_options(), ANOMALY_TYPES)
    )


async def _async_register_frontend(hass: HomeAssistant) -> None:
    data = hass.data.setdefault(DOMAIN, {})
    if not data.get(DATA_FRONTEND_REGISTERED):
        try:
            await hass.http.async_register_static_paths(
                [StaticPathConfig(FRONTEND_STATIC_URL, str(FRONTEND_DIRECTORY), False)]
            )
        except RuntimeError:
            _LOGGER.debug("Caminho estático do diagnóstico já estava registrado")
        data[DATA_FRONTEND_REGISTERED] = True
    await _async_register_lovelace_resource(hass)


async def _async_register_lovelace_resource(hass: HomeAssistant) -> bool:
    """Register one versioned module when Lovelace uses storage resources."""
    try:
        from homeassistant.components.lovelace.const import (
            CONF_RESOURCE_TYPE_WS,
            LOVELACE_DATA,
            MODE_STORAGE,
        )

        lovelace = hass.data.get(LOVELACE_DATA)
        if lovelace is None:
            _LOGGER.info(
                "Lovelace ainda não carregado; registre manualmente %s se o recurso não aparecer",
                FRONTEND_RESOURCE_URL,
            )
            return False
        if lovelace.resource_mode != MODE_STORAGE:
            _LOGGER.warning(
                "Recursos Lovelace estão em YAML; registre %s como módulo",
                FRONTEND_RESOURCE_URL,
            )
            return False
        resources = lovelace.resources
        await resources.async_get_info()
        items = list(resources.async_items())
        managed_prefixes = (
            f"{FRONTEND_STATIC_URL}/",
            "/local/elgin_supervisor_diagnostico/",
            "/local/elgin-supervisor-diagnostico",
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
                if str(item.get(CONF_URL, "")).split("?", 1)[0] == FRONTEND_RESOURCE_BASE
            ),
            None,
        )
        payload = {CONF_RESOURCE_TYPE_WS: "module", CONF_URL: FRONTEND_RESOURCE_URL}
        if canonical is None:
            canonical = await resources.async_create_item(payload)
        elif canonical.get(CONF_URL) != FRONTEND_RESOURCE_URL or canonical.get(CONF_TYPE) != "module":
            canonical = await resources.async_update_item(canonical[CONF_ID], payload)
        canonical_id = canonical.get(CONF_ID)
        for item in managed:
            if item.get(CONF_ID) != canonical_id:
                await resources.async_delete_item(item[CONF_ID])
                _LOGGER.info("Recurso Lovelace antigo do diagnóstico removido: %s", item.get(CONF_URL))
        return True
    except Exception:
        _LOGGER.exception(
            "Falha isolada ao registrar o card; o Supervisor continua independente. "
            "Registre manualmente %s como módulo.",
            FRONTEND_RESOURCE_URL,
        )
        return False


def _register_services(hass: HomeAssistant) -> None:
    data = hass.data.setdefault(DOMAIN, {})
    if data.get(DATA_SERVICES_REGISTERED):
        return

    async def register_observation(call: ServiceCall) -> None:
        payload = dict(call.data)
        beep_count = payload.pop("beep_count", None)
        note = payload.pop("text", "")
        title = payload.pop("title", "")
        tags = payload.pop("tags", [])
        counts = {"one": 1, "two": 2, "multiple": None, "uncertain": None}
        await get_manager(hass, payload.pop("entry_id", None)).async_register_observation(
            {
                "observation_type": payload.pop("observation_type", "note"),
                "occurred_at": payload.pop("occurred_at", None),
                "note": note,
                "expected_count": counts.get(beep_count, beep_count),
                "metadata": {"title": title, "tags": tags, "beep_count": beep_count, **payload},
            },
            context=call.context,
        )

    async def register_beep(call: ServiceCall) -> None:
        payload = dict(call.data)
        entry_id = payload.pop("entry_id", None)
        beep_count = payload.pop("beep_count", "uncertain")
        counts = {"one": 1, "two": 2, "multiple": None, "uncertain": None}
        await get_manager(hass, entry_id).async_register_observation(
            {
                "observation_type": "beep",
                "occurred_at": payload.pop("occurred_at", None),
                "note": payload.pop("text", ""),
                "expected_count": counts.get(beep_count, beep_count),
                "metadata": {
                    "title": "Bip observado",
                    "tags": payload.pop("tags", []),
                    "beep_count": beep_count,
                    **payload,
                },
            },
            context=call.context,
        )

    async def reevaluate(call: ServiceCall) -> None:
        await get_manager(hass, call.data.get("entry_id")).async_reevaluate_anomalies()

    common = {vol.Optional("entry_id"): str}
    observation_schema = vol.Schema(
        {
            **common,
            vol.Required("observation_type", default="note"): vol.In(
                ("beep", "note", "manual_action", "environment", "other")
            ),
            vol.Optional("title", default=""): str,
            vol.Optional("text", default=""): str,
            vol.Optional("tags", default=[]): [str],
            vol.Optional("beep_count"): vol.Any(
                "one",
                "two",
                "multiple",
                "uncertain",
                vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
            ),
            vol.Optional("occurred_at"): str,
        }
    )
    hass.services.async_register(DOMAIN, "register_observation", register_observation, schema=observation_schema)
    hass.services.async_register(
        DOMAIN,
        "register_beep",
        register_beep,
        schema=vol.Schema(
            {
                **common,
                vol.Optional("beep_count", default="uncertain"): vol.Any(
                    "one",
                    "two",
                    "multiple",
                    "uncertain",
                    vol.All(vol.Coerce(int), vol.Range(min=1, max=100)),
                ),
                vol.Optional("text", default=""): str,
                vol.Optional("tags", default=[]): [str],
                vol.Optional("occurred_at"): str,
            }
        ),
    )
    hass.services.async_register(DOMAIN, "reevaluate_anomalies", reevaluate, schema=vol.Schema(common))
    data[DATA_SERVICES_REGISTERED] = True


def _entry_owns_registry_item(item: Any, entry: ConfigEntry) -> bool:
    return bool(
        item is not None
        and item.platform == DOMAIN
        and item.config_entry_id == entry.entry_id
    )


def _async_migrate_registries(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Upgrade the reference registry entries before platforms are forwarded."""

    registry = er.async_get(hass)
    device_id = _async_migrate_device_identifier(hass, entry)
    for legacy_key, domain in _LEGACY_ENTITY_DOMAINS.items():
        legacy_unique_id = f"{entry.entry_id}_{legacy_key}"
        current = registry.async_get_entity_id(domain, DOMAIN, legacy_unique_id)
        if current is None:
            continue
        item = registry.async_get(current)
        if not _entry_owns_registry_item(item, entry) or item.unique_id != legacy_unique_id:
            _LOGGER.error(
                "Entrada legada ignorada por não pertencer ao ConfigEntry atual: %s",
                current,
            )
            continue
        if legacy_key in _LEGACY_RETIRED_KEYS:
            registry.async_remove(current)
            _LOGGER.info("Entidade legada sem equivalente removida do registro: %s", current)
            continue

        new_key = _LEGACY_ENTITY_MAP[legacy_key]
        new_domain = ENTITY_DOMAINS[new_key]
        new_unique_id = f"{DOMAIN}_{new_key}"
        existing_new = registry.async_get_entity_id(new_domain, DOMAIN, new_unique_id)
        if existing_new and existing_new != current:
            existing_item = registry.async_get(existing_new)
            if _entry_owns_registry_item(existing_item, entry):
                registry.async_remove(current)
                _LOGGER.info(
                    "Entrada legada duplicada retirada; entidade canônica preservada: %s",
                    existing_new,
                )
            else:
                _LOGGER.error(
                    "Unique ID canônico ocupado por entrada alheia; migração manual necessária: %s",
                    new_unique_id,
                )
            continue

        target = canonical_entity_id(new_key)
        occupied = registry.async_get(target)
        update: dict[str, Any] = {"new_unique_id": new_unique_id}
        if device_id:
            update["device_id"] = device_id
        if occupied is None or occupied.entity_id == current:
            update["new_entity_id"] = target
        else:
            _LOGGER.error(
                "Entity ID canônico %s está ocupado por %s; a entidade própria será "
                "migrada sem sobrescrever o ID alheio.",
                target,
                occupied.unique_id,
            )
        try:
            registry.async_update_entity(current, **update)
        except ValueError:
            _LOGGER.exception("Falha ao migrar entidade legada %s", current)


def _async_migrate_device_identifier(
    hass: HomeAssistant, entry: ConfigEntry
) -> str | None:
    """Move only this entry's legacy device identifier to the canonical one."""

    registry = dr.async_get(hass)
    legacy_identifier = (DOMAIN, entry.entry_id)
    canonical_identifier = (DOMAIN, DOMAIN)
    legacy = registry.async_get_device_by_identifier(legacy_identifier, entry.entry_id)
    canonical = registry.async_get_device_by_identifier(
        canonical_identifier, entry.entry_id
    )
    if legacy is None:
        return canonical.id if canonical else None
    if canonical is not None and canonical.id != legacy.id:
        _LOGGER.error(
            "Dispositivo canônico já existe separado do legado; entidades serão "
            "vinculadas ao canônico e o dispositivo legado será preservado para revisão manual."
        )
        return canonical.id
    identifiers = set(legacy.identifiers)
    identifiers.discard(legacy_identifier)
    identifiers.add(canonical_identifier)
    try:
        updated = registry.async_update_device(
            legacy.id, new_identifiers=identifiers
        )
    except ValueError:
        _LOGGER.exception("Falha ao migrar o identificador do dispositivo legado")
        return legacy.id
    return updated.id


def _async_normalize_current_entities(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Normalize new entities after forward without touching foreign occupants."""

    registry = er.async_get(hass)
    device_registry = dr.async_get(hass)
    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, DOMAIN), entry.entry_id
    )
    for key in OBJECT_IDS:
        domain = ENTITY_DOMAINS[key]
        unique_id = f"{DOMAIN}_{key}"
        current = registry.async_get_entity_id(domain, DOMAIN, unique_id)
        item = registry.async_get(current) if current else None
        if not _entry_owns_registry_item(item, entry):
            continue
        target = canonical_entity_id(key)
        occupied = registry.async_get(target)
        update: dict[str, Any] = {}
        if device and item.device_id != device.id:
            update["device_id"] = device.id
        if current != target:
            if occupied is None:
                update["new_entity_id"] = target
            elif occupied.entity_id != current:
                _LOGGER.error(
                    "Entity ID canônico ocupado; %s permanecerá como %s até revisão manual.",
                    target,
                    current,
                )
        if update:
            try:
                registry.async_update_entity(current, **update)
            except ValueError:
                _LOGGER.exception("Falha ao normalizar a entidade %s", current)
