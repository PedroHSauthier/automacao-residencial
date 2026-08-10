"""Non-governing runtime manager for Supervisor auditing and diagnostics."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import logging
from types import MappingProxyType
from typing import Any
from uuid import uuid4

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_CALL_SERVICE, EVENT_STATE_CHANGED
from homeassistant.core import Context, Event, HomeAssistant, callback
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

from .anomaly import AnomalyEngine
from .const import DIAGNOSTIC_EVENT, DOMAIN, SELF_ENTITY_PREFIXES, UPDATED_EVENT
from .exporter import DiagnosticExporter, sanitize
from .models import (
    DiagnosticSettings,
    build_operational_flow,
    classify_event_severity,
    is_operational_flow_event,
    normalize_power_level,
    normalize_power_profile,
)
from .origin_resolver import OriginResolver
from .snapshot import build_state_diff, capture_state_snapshot, freeze_json, thaw_json
from .storage import DiagnosticStorage

_LOGGER = logging.getLogger(__name__)

LOCALTUYA_ENTITIES = frozenset(
    {
        "switch.smart_air_conditioner_power_ar_condicionado_id_1",
        "number.smart_air_conditioner_temperatura_alvo_ar_condicionado_id_2",
        "select.smart_air_conditioner_mode_ar_condicionado_id_4",
        "select.smart_air_conditioner_windspeed_ar_condicionado_id_5",
        "switch.smart_air_conditioner_eco_ar_condicionado_id_8",
        "switch.smart_air_conditioner_swing_ar_condicionado_id_33",
        "switch.smart_air_conditioner_sleep_ar_condicionado_id_102",
        "switch.smart_air_conditioner_up_down_wind_ar_condicionado_id_105",
        "switch.smart_air_conditioner_health_ar_condicionado_id_106",
        "sensor.smart_air_conditioner_fault_up_ar_condicionado_id_107",
    }
)

EXPLICIT_ENTITIES = frozenset(
    {
        *LOCALTUYA_ENTITIES,
        "climate.esp8266_elgin_aux_quarto",
        "binary_sensor.esp8266_elgin_aux_estado_base_valido",
        "sensor.sensor_temperatura_sensor_dedicado",
        "sensor.sensor_umidade_sensor_dedicado",
        "weather.forecast_casa",
    }
)
MONITORED_PREFIXES = (
    "sensor.elgin_supervisor_",
    "binary_sensor.elgin_supervisor_",
    "input_boolean.elgin_supervisor_",
    "input_number.elgin_supervisor_",
    "input_select.elgin_supervisor_",
    "input_text.elgin_supervisor_",
    "input_datetime.elgin_supervisor_",
    "select.elgin_supervisor_",
    "timer.elgin_supervisor_",
    "script.elgin_supervisor_",
    "input_boolean.elgin_aux_",
    "sensor.elgin_aux_",
)
RELEVANT_ESPHOME_ACTIONS = frozenset(
    {
        "esp8266_elgin_send_state",
        "esp8266_elgin_update_sensor_temperature",
        "esp8266_elgin_toggle_display",
        "esp8266_elgin_start_clean",
        "esp8266_elgin_import_observed_state",
    }
)
AUDIBLE_REQUEST_TYPES = frozenset(
    {
        "transmission.requested_by_ha",
        "transmission.eco_requested_by_ha",
        "transmission.display_requested_by_ha",
        "transmission.clean_requested_by_ha",
    }
)

MODE_TO_LOCALTUYA = {
    "cool": {"cool", "Frio"},
    "heat": {"heat", "Quente"},
    "dry": {"dry", "Desumidificar"},
    "fan": {"fan", "fan_only", "Ventilar"},
    "auto": {"auto", "Automático"},
}
FAN_TO_LOCALTUYA = {
    "low": {"low", "Baixa"},
    "medium": {"medium", "Média"},
    "high": {"high", "Alta"},
    "auto": {"auto", "Automática"},
    "quiet": {"quiet", "Silencioso"},
}


@dataclass(slots=True)
class PendingTransmission:
    transmission_id: str
    correlation_id: str
    evaluation_id: str | None
    requested_at: datetime
    desired: dict[str, Any]
    expected: dict[str, set[str]]
    matched: dict[str, str] = field(default_factory=dict)
    source_event_id: str | None = None
    timeout_task: asyncio.Task[None] | None = None


def _context_copy(context: Context | None) -> Context | None:
    if context is None:
        return None
    return Context(id=context.id, parent_id=context.parent_id, user_id=context.user_id)


def _iso(value: datetime | None = None) -> str:
    return (value or datetime.now(timezone.utc)).astimezone(timezone.utc).isoformat()


def _enum_text(value: Any, default: str | None = None) -> str | None:
    if value is None:
        return default
    return str(getattr(value, "value", value))


def _optional_bool(value: Any) -> bool | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        return value
    normalized = str(value).strip().casefold()
    if normalized in {"1", "true", "on", "yes", "sim"}:
        return True
    if normalized in {"0", "false", "off", "no", "não", "nao"}:
        return False
    return None


class DiagnosticManager:
    """Observe HA events, persist evidence and never control climate state."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.entry_id = entry.entry_id
        self.settings = DiagnosticSettings.from_options(dict(entry.options))
        self.settings.validate()
        self.storage = DiagnosticStorage(hass, self.settings)
        self.origin = OriginResolver(hass)
        self.anomaly = AnomalyEngine(self)
        self.exporter = DiagnosticExporter(self)
        self._unsubs: list[Callable[[], None]] = []
        self._tasks: set[asyncio.Task[Any]] = set()
        self._listeners: set[Callable[[], None]] = set()
        self._push_listeners: set[Callable[[dict[str, Any]], None]] = set()
        self._event_listeners: set[Callable[[str, dict[str, Any]], None]] = set()
        self._recent: deque[dict[str, Any]] = deque(maxlen=500)
        self._pending: dict[str, PendingTransmission] = {}
        self._context_correlations: dict[str, tuple[str, datetime]] = {}
        self._evaluation_correlations: dict[str, str] = {}
        # Validation permits thresholds up to one million. deque does not
        # preallocate, so this preserves those settings without making a large
        # allocation at startup.
        self._rate_events: deque[datetime] = deque(maxlen=1_000_001)
        self._event_times_24h: deque[datetime] = deque(maxlen=200_000)
        self._last_rate_warning: datetime | None = None
        self._started_at: datetime | None = None
        self._last_event: dict[str, Any] | None = None
        self._last_transmission: dict[str, Any] | None = None
        self._last_esphome: dict[str, Any] | None = None
        self._last_external: dict[str, Any] | None = None
        self._last_decision: dict[str, Any] | None = None
        self._last_confirmation: dict[str, Any] | None = None
        self._last_flow_cache = build_operational_flow([], None)
        self._status = "Inicializando"
        self._instrumentation_seen = False
        self._captured = 0
        self._ignored = 0
        self._cached_health: dict[str, Any] = {}

    @property
    def last_event(self) -> dict[str, Any] | None:
        return dict(self._last_event) if self._last_event else None

    def async_add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.add(listener)
        return lambda: self._listeners.discard(listener)

    def async_add_push_listener(
        self, listener: Callable[[dict[str, Any]], None]
    ) -> Callable[[], None]:
        self._push_listeners.add(listener)
        return lambda: self._push_listeners.discard(listener)

    def async_add_event_listener(
        self, listener: Callable[[str, dict[str, Any]], None]
    ) -> Callable[[], None]:
        self._event_listeners.add(listener)
        return lambda: self._event_listeners.discard(listener)

    @callback
    def _notify(self, event: dict[str, Any] | None = None) -> None:
        for listener in tuple(self._listeners):
            try:
                listener()
            except Exception:
                _LOGGER.exception("Falha ao atualizar entidade de diagnóstico")
        if event:
            public = dict(event)
            for listener in tuple(self._push_listeners):
                try:
                    listener(public)
                except Exception:
                    _LOGGER.exception("Falha ao publicar atualização do diagnóstico")
        self.hass.bus.async_fire(UPDATED_EVENT, {"entry_id": self.entry_id})

    async def async_start(self) -> None:
        await self.storage.async_start()
        self._cached_health = await self.storage.async_health()
        self._started_at = datetime.now(timezone.utc)
        self._unsubs.extend(
            (
                self.hass.bus.async_listen(EVENT_STATE_CHANGED, self._handle_state_changed),
                self.hass.bus.async_listen(EVENT_CALL_SERVICE, self._handle_call_service),
                self.hass.bus.async_listen(DIAGNOSTIC_EVENT, self._handle_diagnostic_event),
                self.hass.bus.async_listen(
                    "elgin_supervisor_agenda_policy_changed", self._handle_agenda_event
                ),
                self.hass.bus.async_listen(
                    "elgin_supervisor_agenda_evaluated", self._handle_agenda_event
                ),
                async_track_time_interval(
                    self.hass,
                    self._async_periodic_cleanup,
                    timedelta(minutes=5),
                ),
                async_track_time_interval(
                    self.hass, self._async_refresh_health, timedelta(minutes=1)
                ),
            )
        )
        await self.anomaly.async_start()
        self._status = "Operacional"
        await self.async_log_event(
            {
                "category": "system",
                "event_type": "diagnostic.started",
                "severity": "success",
                "outcome": "started",
                "summary": "Integração de auditoria iniciada sem atuar no Supervisor.",
                "source_component": DOMAIN,
                "retention_class": "absolute",
                "details_json": {"schema_version": getattr(self.storage, "_schema_version", None)},
            },
            run_anomaly=False,
        )

    async def async_stop(self) -> None:
        self._status = "Encerrando"
        for unsubscribe in self._unsubs:
            try:
                unsubscribe()
            except Exception:
                _LOGGER.debug("Listener já removido", exc_info=True)
        self._unsubs.clear()
        for pending in self._pending.values():
            if pending.timeout_task:
                pending.timeout_task.cancel()
        self._pending.clear()
        await self.anomaly.async_stop()
        for task in tuple(self._tasks):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        await self.storage.async_stop()
        self._status = "Parado"

    def _setting(self, name: str, default: Any = None) -> Any:
        if hasattr(self.settings, name):
            return getattr(self.settings, name)
        values = getattr(self.settings, "values", None)
        if isinstance(values, Mapping):
            return values.get(name, default)
        return default

    def _spawn(self, coro: Any, name: str) -> asyncio.Task[Any]:
        task = self.hass.async_create_background_task(coro, name)
        self._tasks.add(task)

        def _done(completed: asyncio.Task[Any]) -> None:
            self._tasks.discard(completed)
            if completed.cancelled():
                return
            error = completed.exception()
            if error:
                _LOGGER.error("Falha isolada no diagnóstico (%s): %s", name, error, exc_info=error)

        task.add_done_callback(_done)
        return task

    @staticmethod
    def _monitored(entity_id: str) -> bool:
        if any(entity_id.startswith(prefix) for prefix in SELF_ENTITY_PREFIXES):
            return False
        if entity_id == "sensor.elgin_supervisor_diagnostico_de_potencia":
            return False
        return entity_id in EXPLICIT_ENTITIES or entity_id.startswith(MONITORED_PREFIXES)

    def _capture_allowed(self, *, critical: bool = False) -> bool:
        now = datetime.now(timezone.utc)
        window = int(self._setting("rate_window_seconds", 60))
        cutoff = now - timedelta(seconds=window)
        while self._rate_events and self._rate_events[0] < cutoff:
            self._rate_events.popleft()
        self._rate_events.append(now)
        hard = int(self._setting("rate_hard_limit_events", 2_000))
        warning = int(self._setting("rate_warning_events", 500))
        if len(self._rate_events) >= warning and (
            self._last_rate_warning is None or self._last_rate_warning < cutoff
        ):
            self._last_rate_warning = now
            self._spawn(
                self.async_log_event(
                    {
                        "category": "system",
                        "event_type": "capture.high_rate",
                        "severity": "warning",
                        "outcome": "observed",
                        "summary": f"Taxa elevada: {len(self._rate_events)} eventos em {window}s.",
                        "source_component": DOMAIN,
                        "retention_class": "error",
                    },
                    run_anomaly=False,
                ),
                f"{DOMAIN}.rate_warning",
            )
        if len(self._rate_events) > hard and not critical:
            self._ignored += 1
            return False
        return True

    def _state_capture_enabled(self, entity_id: str) -> bool:
        """Apply category switches without weakening the fixed allowlist."""
        if entity_id in LOCALTUYA_ENTITIES:
            return bool(
                self._setting("capture_localtuya", True)
                or self._setting("capture_external_changes", True)
            )
        if entity_id == "climate.esp8266_elgin_aux_quarto":
            return bool(self._setting("capture_climate", True))
        folded = entity_id.casefold()
        if "agenda" in folded:
            return bool(self._setting("capture_agenda", True))
        if "preset" in folded:
            return bool(self._setting("capture_presets", True))
        if "potencia" in folded or "power" in folded:
            return bool(self._setting("capture_power_profiles", True))
        if any(token in folded for token in ("protecao", "pausa_manual", "reconciliacao")):
            return bool(self._setting("capture_protections", True))
        return bool(self._setting("capture_state_changes", True))

    def _diagnostic_capture_enabled(self, stage: str, data: Mapping[str, Any]) -> bool:
        if stage == "error":
            return bool(self._setting("capture_errors", True))
        if stage in {"external_change", "localtuya_confirmed", "localtuya_confirmation"}:
            key = "capture_external_changes" if stage == "external_change" else "capture_localtuya"
            return bool(self._setting(key, True))
        if stage.startswith("transmission_") or stage == "eco_requested":
            return bool(self._setting("capture_service_calls", True))
        if data.get("protection"):
            return bool(
                self._setting("capture_decisions", True)
                or self._setting("capture_protections", True)
            )
        return bool(self._setting("capture_decisions", True))

    @callback
    def _handle_state_changed(self, event: Event) -> None:
        """Capture every mutable object before scheduling any coroutine."""
        try:
            entity_id = str(event.data.get("entity_id") or "")
            if not self._monitored(entity_id):
                return
            critical = entity_id in LOCALTUYA_ENTITIES
            if not self._capture_allowed(critical=critical):
                return
            # The following snapshots and diff are completed synchronously. No
            # State reference crosses the callback boundary.
            before = capture_state_snapshot(entity_id, event.data.get("old_state"))
            after = capture_state_snapshot(entity_id, event.data.get("new_state"))
            diff = build_state_diff(before, after)
            after_state = after.get("state") if isinstance(after, Mapping) else None
            if not self._state_capture_enabled(entity_id) and not (
                self._setting("capture_errors", True)
                and (
                    after is None
                    or str(after_state) in {"unknown", "unavailable"}
                )
            ):
                return
            captured = freeze_json(
                {
                    "entity_id": entity_id,
                    "before": before,
                    "after": after,
                    "diff": diff,
                    "occurred_at": _iso(event.time_fired),
                }
            )
            context = _context_copy(event.context)
            self._spawn(
                self._async_process_state_capture(captured, context),
                f"{DOMAIN}.state.{entity_id}",
            )
        except Exception:
            _LOGGER.exception("Falha isolada ao capturar state_changed")

    @callback
    def _handle_call_service(self, event: Event) -> None:
        try:
            if not bool(self._setting("capture_service_calls", True)):
                return
            domain = str(event.data.get("domain") or "")
            service = str(event.data.get("service") or "")
            service_data = event.data.get("service_data")
            relevant = domain == "esphome" and service in RELEVANT_ESPHOME_ACTIONS
            targets = self._target_entities(service_data)
            eco = domain == "switch" and service in {"turn_on", "turn_off"} and (
                "switch.smart_air_conditioner_eco_ar_condicionado_id_8" in targets
            )
            climate_action = domain == "climate" and (
                "climate.esp8266_elgin_aux_quarto" in targets
            )
            script_action = domain == "script" and (
                service.startswith(("elgin_supervisor_", "elgin_aux_"))
                or any(
                    item.startswith(("script.elgin_supervisor_", "script.elgin_aux_"))
                    for item in targets
                )
            )
            localtuya_action = domain in {"switch", "number", "select"} and bool(
                targets & LOCALTUYA_ENTITIES
            )
            if not (
                relevant
                or eco
                or climate_action
                or script_action
                or localtuya_action
            ):
                return
            audible_action = (
                (relevant and not service.endswith(("update_sensor_temperature", "import_observed_state")))
                or eco
                or service.endswith(("toggle_display", "start_clean"))
            )
            if not self._capture_allowed(critical=audible_action):
                return
            # service_data is copied/frozen here, not in the asynchronous handler.
            captured = freeze_json(
                {
                    "domain": domain,
                    "service": service,
                    "service_data": service_data or {},
                    "occurred_at": _iso(event.time_fired),
                }
            )
            context = _context_copy(event.context)
            self._spawn(
                self._async_process_service_capture(captured, context),
                f"{DOMAIN}.service.{domain}.{service}",
            )
        except Exception:
            _LOGGER.exception("Falha isolada ao capturar call_service")

    @staticmethod
    def _target_entities(service_data: Any) -> set[str]:
        if not isinstance(service_data, Mapping):
            return set()
        target = service_data.get("entity_id")
        if isinstance(target, str):
            return {target}
        if isinstance(target, (list, tuple, set, frozenset)):
            return {str(item) for item in target}
        return set()

    @callback
    def _handle_diagnostic_event(self, event: Event) -> None:
        try:
            raw_data = event.data if isinstance(event.data, Mapping) else {}
            stage = str(raw_data.get("stage") or raw_data.get("event_type") or "")
            critical = bool(
                stage.startswith("transmission_")
                or stage in {
                    "eco_requested",
                    "external_change",
                    "localtuya_confirmed",
                    "localtuya_confirmation",
                    "error",
                }
                or raw_data.get("severity") in {"error", "critical"}
            )
            if not self._capture_allowed(critical=critical):
                return
            captured = freeze_json(
                {
                    "data": event.data,
                    "occurred_at": _iso(event.time_fired),
                }
            )
            context = _context_copy(event.context)
            self._instrumentation_seen = True
            self._spawn(
                self._async_process_diagnostic_capture(captured, context),
                f"{DOMAIN}.instrumented_event",
            )
        except Exception:
            _LOGGER.exception("Falha isolada ao capturar evento instrumentado")

    @callback
    def _handle_agenda_event(self, event: Event) -> None:
        try:
            if not bool(self._setting("capture_agenda", True)):
                return
            if not self._capture_allowed():
                return
            captured = freeze_json(
                {"data": event.data, "event_type": event.event_type, "occurred_at": _iso(event.time_fired)}
            )
            context = _context_copy(event.context)
            self._spawn(
                self._async_process_agenda_capture(captured, context),
                f"{DOMAIN}.agenda",
            )
        except Exception:
            _LOGGER.exception("Falha isolada ao capturar evento da Agenda")

    async def _async_process_state_capture(
        self, frozen_capture: Any, context: Context | None
    ) -> None:
        capture = thaw_json(frozen_capture)
        entity_id = capture["entity_id"]
        before = capture["before"]
        after = capture["after"]
        diff = capture["diff"]
        all_fields = list(diff.get("changed_fields_all", []))
        relevant_fields = list(diff.get("changed_fields_relevant", []))
        if not all_fields:
            return
        entity_removed = after is None
        entity_created = before is None and isinstance(after, Mapping)
        current_state = after.get("state") if isinstance(after, Mapping) else None
        capture_mode = str(self._setting("capture_mode", "normal"))
        if capture_mode == "essential" and entity_id not in LOCALTUYA_ENTITIES:
            essential_state = bool(
                entity_id == "climate.esp8266_elgin_aux_quarto"
                or entity_id.startswith(
                    (
                        "input_boolean.elgin_supervisor_",
                        "input_number.elgin_supervisor_",
                        "input_select.elgin_supervisor_",
                        "input_text.elgin_supervisor_",
                        "input_datetime.elgin_supervisor_",
                    )
                )
                or entity_created
                or entity_removed
                or str(current_state) in {"unknown", "unavailable"}
            )
            if not essential_state:
                return
        if capture_mode == "normal" and not relevant_fields and entity_id not in LOCALTUYA_ENTITIES:
            return
        event_type = (
            "state.removed"
            if entity_removed
            else "state.created"
            if entity_created
            else "state.no_relevant_change"
            if capture_mode != "intensive" and not relevant_fields
            else "state.changed"
        )
        severity = (
            "warning"
            if entity_removed or current_state in {"unknown", "unavailable"}
            else "info"
        )
        is_localtuya = entity_id in LOCALTUYA_ENTITIES
        correlation_id, relation = self._resolve_correlation(
            context=context, evaluation_id=None, occurred_at=_parse_iso(capture["occurred_at"])
        )
        classification: dict[str, Any] = {}
        if is_localtuya:
            classification = await self._classify_localtuya_change(
                entity_id, before, after, context, correlation_id
            )
            event_type = classification.get("event_type", "localtuya.changed")
            severity = classification.get("severity", severity)
            correlation_id = classification.get("correlation_id", correlation_id)
            relation = classification.get("relation", relation)
            if classification.get("is_external"):
                if not bool(self._setting("capture_external_changes", True)):
                    return
            elif not bool(self._setting("capture_localtuya", True)):
                return
            if (
                capture_mode == "essential"
                and not classification.get("is_external")
                and severity not in {"warning", "error", "critical"}
            ):
                return
        origin = await self.origin.async_resolve(
            context,
            source_component="localtuya" if is_localtuya else "state",
            source_entity_id=entity_id,
            external_observation=bool(classification.get("is_external")),
            resolve_user_name=bool(self._setting("privacy_resolve_user_names", True)),
        )
        before_state = before.get("state", "ausente") if before else "ausente"
        after_state = after.get("state", "ausente") if after else "ausente"
        event_data = {
            "occurred_at": capture["occurred_at"],
            "category": "external" if classification.get("is_external") else "state",
            "event_type": event_type,
            "severity": severity,
            "outcome": classification.get("outcome", "observed"),
            "summary": classification.get("summary")
            or f"{entity_id}: {before_state} → {after_state}.",
            "source_component": "localtuya" if is_localtuya else entity_id.split(".", 1)[0],
            "source_entity_id": entity_id,
            "entity_domain": entity_id.split(".", 1)[0],
            "context_id": getattr(context, "id", None),
            "parent_context_id": getattr(context, "parent_id", None),
            "correlation_id": correlation_id,
            "relation_kind": relation.get("kind"),
            "relation_strength": relation.get("strength"),
            "relation_evidence": relation.get("evidence", []),
            "is_external": bool(classification.get("is_external")),
            "before_json": before,
            "after_json": after,
            "diff_json": diff.get("diff", diff),
            "changed_fields_all": all_fields,
            "changed_fields_relevant": relevant_fields,
            "retention_class": "absolute" if is_localtuya else "full",
            "details_json": {"classification": classification.get("classification")},
            **origin.as_dict(),
        }
        await self.async_log_event(event_data, context=context)

    async def _classify_localtuya_change(
        self,
        entity_id: str,
        before: Mapping[str, Any] | None,
        after: Mapping[str, Any] | None,
        context: Context | None,
        fallback_correlation: str,
    ) -> dict[str, Any]:
        if after is None:
            return {
                "event_type": "localtuya.entity_removed",
                "severity": "error",
                "outcome": "removed",
                "summary": f"Entidade LocalTuya removida da máquina de estados: {entity_id}.",
                "classification": "entity_removed",
                "is_external": False,
                "correlation_id": fallback_correlation,
                "relation": {
                    "kind": "state_machine_removal",
                    "strength": "strong",
                    "evidence": ["state_changed.new_state ausente"],
                },
            }
        if before is None:
            return {
                "event_type": "localtuya.entity_created",
                "severity": "info",
                "outcome": "created",
                "summary": f"Entidade LocalTuya entrou na máquina de estados: {entity_id}.",
                "classification": "entity_created",
                "is_external": False,
                "correlation_id": fallback_correlation,
                "relation": {
                    "kind": "state_machine_creation",
                    "strength": "strong",
                    "evidence": ["state_changed.old_state ausente"],
                },
            }
        new_state = str(after.get("state"))
        now = datetime.now(timezone.utc)
        pending = self._best_pending_for(entity_id, new_state, now)
        if pending:
            pending.matched[entity_id] = new_state
            strength = "strong" if self._expected_matches(pending, entity_id, new_state) else "weak"
            event_type = (
                "localtuya.confirmed_expected_field"
                if strength == "strong"
                else "localtuya.observed_during_reconciliation"
            )
            if strength == "strong":
                await self.storage.async_add_relation(
                    {
                        "relation_id": str(uuid4()),
                        "correlation_id": pending.correlation_id,
                        "evaluation_id": pending.evaluation_id,
                        "source_event_id": pending.source_event_id,
                        "target_event_id": None,
                        "relation_kind": "expected_value_match",
                        "relation_strength": "strong",
                        "evidence": [
                            f"entidade={entity_id}",
                            f"valor_observado={new_state}",
                            "valor corresponde ao solicitado dentro da janela",
                        ],
                        "created_at": _iso(),
                    }
                )
            return {
                "event_type": event_type,
                "severity": "success" if strength == "strong" else "info",
                "outcome": "confirmed_by_localtuya" if strength == "strong" else "observed",
                "summary": (
                    f"LocalTuya confirmou {entity_id}={new_state} solicitado pelo HA."
                    if strength == "strong"
                    else f"LocalTuya mudou {entity_id} durante reconciliação; relação não confirmada."
                ),
                "correlation_id": pending.correlation_id,
                "relation": {
                    "kind": "expected_value_match" if strength == "strong" else "temporal_only",
                    "strength": strength,
                    "evidence": ["janela de reconciliação", f"transmission_id={pending.transmission_id}"],
                },
                "classification": "confirmation" if strength == "strong" else "indeterminate",
                "is_external": False,
            }
        if getattr(context, "user_id", None):
            return {
                "event_type": "localtuya.changed_by_ha_user",
                "severity": "info",
                "outcome": "observed",
                "summary": f"Mudança LocalTuya associada a usuário HA: {entity_id}.",
                "classification": "home_assistant_user",
                "is_external": False,
                "correlation_id": fallback_correlation,
                "relation": {
                    "kind": "context_user",
                    "strength": "strong",
                    "evidence": ["context.user_id"],
                },
            }
        divergent = self._latest_pending_for_entity(entity_id, now)
        if divergent:
            expected = sorted(divergent.expected.get(entity_id, set()))
            return {
                "event_type": "localtuya.divergence_or_external",
                "severity": "warning",
                "outcome": "diverged_or_external",
                "summary": (
                    f"LocalTuya publicou {entity_id}={new_state}; o valor não corresponde "
                    "ao solicitado na janela ativa."
                ),
                "correlation_id": divergent.correlation_id,
                "relation": {
                    "kind": "temporal_value_mismatch",
                    "strength": "weak",
                    "evidence": [
                        f"transmission_id={divergent.transmission_id}",
                        f"observado={new_state}",
                        f"esperado={expected}",
                        "pode ser atraso, divergência ou ação externa",
                    ],
                },
                "classification": "divergence_or_external",
                "is_external": True,
            }
        return {
            "event_type": "localtuya.external_or_indeterminate",
            "severity": "warning",
            "outcome": "observed",
            "summary": f"Mudança LocalTuya sem solicitação HA correspondente: {entity_id}.",
            "classification": "external_or_indeterminate",
            "is_external": True,
            "correlation_id": fallback_correlation,
            "relation": {
                "kind": "unmatched_observation",
                "strength": "none",
                "evidence": ["sem context.user_id", "sem valor solicitado correspondente"],
            },
        }

    async def _async_process_service_capture(
        self, frozen_capture: Any, context: Context | None
    ) -> None:
        capture = thaw_json(frozen_capture)
        domain = capture["domain"]
        service = capture["service"]
        service_data = capture["service_data"]
        is_import = service.endswith("import_observed_state")
        is_sensor_update = service.endswith("update_sensor_temperature")
        is_full = service.endswith("send_state")
        is_display = service.endswith("toggle_display")
        is_clean = service.endswith("start_clean")
        targets = self._target_entities(service_data)
        is_eco = domain == "switch" and (
            "switch.smart_air_conditioner_eco_ar_condicionado_id_8" in targets
        )
        is_climate_action = domain == "climate"
        is_script_action = domain == "script"
        is_localtuya_action = domain in {"switch", "number", "select"} and bool(
            targets & LOCALTUYA_ENTITIES
        )
        audibility = (
            "no_transmission" if is_import else
            "silent_expected" if is_sensor_update else
            "audible_expected"
            if is_full or is_eco or is_display or is_clean
            else "no_transmission"
            if is_climate_action or is_script_action
            else "unknown"
        )
        evaluation_id = str(service_data.get("evaluation_id") or "") or None
        correlation_id, relation = self._resolve_correlation(
            context=context,
            evaluation_id=evaluation_id,
            occurred_at=_parse_iso(capture["occurred_at"]),
        )
        semantic = next(
            (
                item
                for item in reversed(self._recent)
                if item.get("correlation_id") == correlation_id
                and item.get("source_component") != "esphome"
            ),
            {},
        )
        evaluation_id = evaluation_id or semantic.get("evaluation_id")
        request_id = str(uuid4())
        # SensorUpdate and passive import are intentionally silent and do not
        # represent an IR transmission. ``request_id`` still traces those calls.
        transmission_id = (
            str(uuid4()) if (is_full or is_display or is_clean or is_eco) else None
        )
        summary = (
            f"Home Assistant solicitou {domain}.{service}; "
            + (
                "importação passiva, sem transmissão IR."
                if is_import
                else "atualização SensorUpdate esperada silenciosa."
                if is_sensor_update
                else "comando potencialmente audível; emissão física não confirmada."
                if transmission_id
                else "ação lógica observada; eventual transmissão deve aparecer em evento correlacionado."
            )
        )
        event_data = {
            "occurred_at": capture["occurred_at"],
            "category": (
                "state_import" if is_import
                else "transmission" if transmission_id
                else "action"
            ),
            "event_type": (
                "state.passive_import_requested_by_ha" if is_import
                else "transmission.sensor_update_requested_by_ha" if is_sensor_update
                else "transmission.eco_requested_by_ha" if is_eco
                else "transmission.display_requested_by_ha" if is_display
                else "transmission.clean_requested_by_ha" if is_clean
                else "action.climate_requested_by_ha" if is_climate_action
                else "action.script_requested_by_ha" if is_script_action
                else "action.localtuya_requested_by_ha" if is_localtuya_action
                else "transmission.requested_by_ha"
            ),
            "severity": "info",
            "outcome": "requested_by_ha",
            "summary": summary,
            "source_component": domain,
            "action_domain": domain,
            "action_name": service,
            "evaluation_id": evaluation_id,
            "correlation_id": correlation_id,
            "relation_kind": relation["kind"],
            "relation_strength": relation["strength"],
            "relation_evidence": relation["evidence"],
            "context_id": getattr(context, "id", None),
            "parent_context_id": getattr(context, "parent_id", None),
            "transmission_id": transmission_id,
            "request_id": request_id,
            "source_entity_id": sorted(targets)[0] if targets else None,
            "entity_domain": (
                sorted(targets)[0].split(".", 1)[0] if targets else None
            ),
            "expected_audibility": audibility,
            "climate_mode": service_data.get("mode") or semantic.get("climate_mode"),
            "treatment": semantic.get("treatment"),
            "preset": semantic.get("preset"),
            "power_profile": semantic.get("power_profile"),
            "agenda_state": semantic.get("agenda_state"),
            "protection": semantic.get("protection"),
            "trigger_model": semantic.get("trigger_model"),
            "desired_json": service_data,
            "retention_class": "absolute",
            "function": (
                "eco" if is_eco
                else "sensor_update" if is_sensor_update
                else "passive_import" if is_import
                else "display" if is_display
                else "clean" if is_clean
                else "climate" if is_climate_action
                else "script" if is_script_action
                else "localtuya" if is_localtuya_action
                else "full_state"
            ),
            "details_json": {
                "evidence_limit": "EVENT_CALL_SERVICE comprova solicitação HA, não emissão física",
                "service_data": service_data if self._setting("privacy_capture_service_data", True) else None,
                "temperature": service_data.get("current_temperature"),
                "target_temperature": service_data.get("target_temperature"),
            },
        }
        event = await self.async_log_event(event_data, context=context)
        expected = (
            self._expected_localtuya(service_data)
            if is_full
            else {
                "switch.smart_air_conditioner_eco_ar_condicionado_id_8": {
                    "on" if service == "turn_on" else "off"
                }
            }
            if is_eco
            else {}
        )
        if transmission_id and expected:
            pending = PendingTransmission(
                transmission_id=transmission_id,
                correlation_id=correlation_id,
                evaluation_id=evaluation_id,
                requested_at=_parse_iso(capture["occurred_at"]),
                desired=dict(service_data),
                expected=expected,
                source_event_id=event["event_id"],
            )
            self._pending[transmission_id] = pending
            pending.timeout_task = self.hass.async_create_background_task(
                self._async_confirmation_timeout(transmission_id),
                f"{DOMAIN}.confirmation_timeout.{transmission_id}",
            )

    @staticmethod
    def _expected_localtuya(data: Mapping[str, Any]) -> dict[str, set[str]]:
        expected: dict[str, set[str]] = {}
        if "power" in data:
            expected["switch.smart_air_conditioner_power_ar_condicionado_id_1"] = {
                "on" if bool(data["power"]) else "off"
            }
        mode = str(data.get("mode") or "")
        if mode in MODE_TO_LOCALTUYA:
            expected["select.smart_air_conditioner_mode_ar_condicionado_id_4"] = MODE_TO_LOCALTUYA[mode]
        fan = str(data.get("fan") or "")
        if fan in FAN_TO_LOCALTUYA:
            expected["select.smart_air_conditioner_windspeed_ar_condicionado_id_5"] = FAN_TO_LOCALTUYA[fan]
        if "target_temperature" in data:
            target = float(data["target_temperature"])
            expected["number.smart_air_conditioner_temperatura_alvo_ar_condicionado_id_2"] = {
                str(int(target)), str(float(target)), str(int(target * 10)), str(float(target * 10))
            }
        if "swing_vertical" in data:
            expected["switch.smart_air_conditioner_up_down_wind_ar_condicionado_id_105"] = {
                "on" if bool(data["swing_vertical"]) else "off"
            }
        if "swing_horizontal" in data:
            expected["switch.smart_air_conditioner_swing_ar_condicionado_id_33"] = {
                "on" if bool(data["swing_horizontal"]) else "off"
            }
        if "sleep_enabled" in data:
            expected["switch.smart_air_conditioner_sleep_ar_condicionado_id_102"] = {
                "on" if bool(data["sleep_enabled"]) else "off"
            }
        if "health" in data:
            expected["switch.smart_air_conditioner_health_ar_condicionado_id_106"] = {
                "on" if bool(data["health"]) else "off"
            }
        return expected

    def _best_pending_for(
        self, entity_id: str, new_state: str, now: datetime
    ) -> PendingTransmission | None:
        window = float(self._setting("localtuya_confirmation_window_seconds", 30))
        candidates = [
            pending
            for pending in self._pending.values()
            if (now - pending.requested_at).total_seconds() <= window
            and entity_id in pending.expected
        ]
        matches = [item for item in candidates if self._expected_matches(item, entity_id, new_state)]
        return max(matches, key=lambda item: item.requested_at) if matches else None

    def _latest_pending_for_entity(
        self, entity_id: str, now: datetime
    ) -> PendingTransmission | None:
        window = float(self._setting("localtuya_confirmation_window_seconds", 30))
        candidates = [
            pending
            for pending in self._pending.values()
            if 0 <= (now - pending.requested_at).total_seconds() <= window
            and entity_id in pending.expected
        ]
        return max(candidates, key=lambda item: item.requested_at) if candidates else None

    @staticmethod
    def _expected_matches(pending: PendingTransmission, entity_id: str, value: str) -> bool:
        expected = pending.expected.get(entity_id, set())
        return value in expected or value.casefold() in {item.casefold() for item in expected}

    async def _async_confirmation_timeout(self, transmission_id: str) -> None:
        await asyncio.sleep(float(self._setting("localtuya_confirmation_window_seconds", 30)))
        pending = self._pending.pop(transmission_id, None)
        if pending is None:
            return
        matched = set(pending.matched)
        expected = set(pending.expected)
        if expected and matched >= expected:
            return
        await self.async_log_event(
            {
                "category": "transmission",
                "event_type": "transmission.confirmation_timeout",
                "severity": "warning",
                "outcome": "not_confirmed",
                "summary": "Janela encerrada sem confirmação completa do LocalTuya.",
                "source_component": DOMAIN,
                "evaluation_id": pending.evaluation_id,
                "correlation_id": pending.correlation_id,
                "transmission_id": pending.transmission_id,
                "expected_audibility": "unknown",
                "retention_class": "error",
                "details_json": {
                    "expected_entities": sorted(expected),
                    "matched_entities": sorted(matched),
                    "evidence_limit": "ausência de confirmação não prova ausência de emissão IR",
                },
            }
        )

    async def _async_process_diagnostic_capture(
        self, frozen_capture: Any, context: Context | None
    ) -> None:
        capture = thaw_json(frozen_capture)
        data = dict(capture["data"])
        stage = str(data.get("stage") or data.get("event_type") or "logical_event")
        if not self._diagnostic_capture_enabled(stage, data):
            return
        evaluation_id = str(data.get("evaluation_id") or "") or None
        correlation_id, relation = self._resolve_correlation(
            context=context,
            evaluation_id=evaluation_id,
            occurred_at=_parse_iso(capture["occurred_at"]),
        )
        category, event_type, severity, outcome, audibility = self._stage_semantics(stage, data)
        snapshot = data.get("snapshot") if isinstance(data.get("snapshot"), Mapping) else {}
        inputs = snapshot.get("inputs") if isinstance(snapshot.get("inputs"), Mapping) else {}
        desired = data.get("desired") if isinstance(data.get("desired"), Mapping) else {}
        event_data = {
            "occurred_at": capture["occurred_at"],
            "category": category,
            "event_type": event_type,
            "severity": severity,
            "outcome": outcome,
            "summary": str(data.get("summary") or data.get("reason") or stage.replace("_", " ").capitalize()),
            "technical_message": data.get("technical_message"),
            "source_component": "elgin_supervisor_climatico",
            "source_entity_id": data.get("source_entity_id") or "script.elgin_supervisor_aplicar_decisao",
            "evaluation_id": evaluation_id,
            "correlation_id": correlation_id,
            "relation_kind": relation["kind"],
            "relation_strength": relation["strength"],
            "relation_evidence": relation["evidence"],
            "context_id": getattr(context, "id", None),
            "parent_context_id": getattr(context, "parent_id", None),
            "trigger_model": data.get("trigger_model"),
            "trigger_entity_id": data.get("trigger_entity_id"),
            "climate_mode": data.get("mode") or data.get("climate_mode"),
            "treatment": data.get("treatment") or data.get("tratamento"),
            "preset": data.get("preset"),
            "power_state": _optional_bool(data.get("power_state")),
            "power_profile": normalize_power_profile(
                data.get("power_profile")
                if data.get("power_profile") is not None
                else data.get("potencia")
            ),
            "power_level": normalize_power_level(data.get("power_level")),
            "agenda_state": data.get("agenda_action") or data.get("agenda_state"),
            "protection": data.get("protection"),
            "function": data.get("function"),
            "expected_audibility": audibility,
            "transmission_id": data.get("transmission_id"),
            "confirmation_state": (
                "confirmed_by_localtuya" if stage in {"localtuya_confirmed", "localtuya_confirmation"}
                else "requested_by_ha" if stage in {"transmission_requested", "eco_requested"}
                else None
            ),
            "is_external": category == "external",
            "desired_json": data.get("desired") or data.get("desired_json"),
            "confirmed_json": data.get("confirmed") or data.get("confirmed_json"),
            "retention_class": "absolute" if category in {"transmission", "external", "error"} else "full",
            "details_json": {
                "stage": stage,
                "temperature": data.get("temperature", inputs.get("temperature")),
                "humidity": data.get("humidity", inputs.get("humidity")),
                "target_temperature": data.get(
                    "target_temperature", desired.get("target_temperature")
                ),
                "power_state": _optional_bool(data.get("power_state")),
                "power_level": normalize_power_level(data.get("power_level")),
                "rule": data.get("rule"),
                "reason": data.get("reason"),
                "payload": data
                if self._setting("privacy_capture_raw_events", True)
                else None,
            },
        }
        if not self._stage_timeline_enabled(stage, data):
            synthetic = {
                "event_id": None,
                "occurred_at": capture["occurred_at"],
                "outcome": outcome,
            }
            if evaluation_id:
                await self._async_update_evaluation(
                    stage, data, synthetic, correlation_id, context
                )
            if stage == "decision_calculated":
                # Normal mode stores one terminal evaluation row, but the
                # oscillation detector still needs every calculated decision.
                await self.anomaly.async_process(event_data)
            self._finish_pending_confirmation(
                stage, data, evaluation_id, correlation_id
            )
            return
        event = await self.async_log_event(event_data, context=context)
        if evaluation_id:
            await self._async_update_evaluation(stage, data, event, correlation_id, context)
        self._finish_pending_confirmation(stage, data, evaluation_id, correlation_id)

    def _stage_timeline_enabled(
        self, stage: str, data: Mapping[str, Any]
    ) -> bool:
        """Group verbose instrumentation into evaluations outside Intensive."""
        mode = str(self._setting("capture_mode", "normal"))
        if mode == "intensive":
            return True
        if stage in {
            "transmission_requested",
            "transmission_accepted_by_software",
            "transmission_suppressed",
            "eco_requested",
            "localtuya_confirmed",
            "localtuya_confirmation",
            "external_change",
            "error",
            "decision_blocked",
        }:
            return True
        if stage == "evaluation_no_change":
            return mode == "normal"
        if stage == "evaluation_completed":
            result = data.get("result") if isinstance(data.get("result"), Mapping) else {}
            action = str(result.get("action") or "")
            return mode == "normal" or action not in {"", "no_action", "already_off"}
        return False

    def _finish_pending_confirmation(
        self,
        stage: str,
        data: Mapping[str, Any],
        evaluation_id: str | None,
        correlation_id: str,
    ) -> None:
        if stage not in {"localtuya_confirmed", "localtuya_confirmation"}:
            return
        confirmed = data.get("confirmed") or data.get("confirmed_json") or {}
        confirmed_signatures: set[str] = set()
        if isinstance(confirmed, Mapping):
            confirmed_signatures = {
                str(value)
                for value in (
                    confirmed.get("signature"),
                    confirmed.get("observed_signature"),
                    confirmed.get("expected_signature"),
                )
                if value
            }
        for pending in list(self._pending.values()):
            requested_signatures = {
                str(value)
                for value in (
                    pending.desired.get("signature"),
                    pending.desired.get("localtuya_signature"),
                )
                if value
            }
            if pending.correlation_id == correlation_id or (
                evaluation_id and pending.evaluation_id == evaluation_id
            ) or bool(confirmed_signatures & requested_signatures):
                if pending.timeout_task:
                    pending.timeout_task.cancel()
                self._pending.pop(pending.transmission_id, None)

    @staticmethod
    def _stage_semantics(stage: str, data: Mapping[str, Any]) -> tuple[str, str, str, str, str]:
        mapping = {
            "trigger_received": ("evaluation", "evaluation.triggered", "debug", "started", "no_transmission"),
            "evaluation_started": ("evaluation", "evaluation.started", "debug", "started", "no_transmission"),
            "decision_calculated": ("decision", "decision.calculated", "info", "calculated", "no_transmission"),
            "decision_blocked": ("decision", "decision.blocked", "warning", "blocked", "no_transmission"),
            "evaluation_no_change": ("evaluation", "evaluation.no_change", "debug", "no_action", "no_transmission"),
            "evaluation_completed": ("evaluation", "evaluation.completed", "success", "completed", "no_transmission"),
            "transmission_requested": ("transmission", "transmission.logical_request", "info", "requested", "audible_expected"),
            "transmission_accepted_by_software": ("transmission", "transmission.accepted_by_software", "success", "accepted_by_software", "audible_expected"),
            "transmission_suppressed": ("transmission", "transmission.duplicate_suppressed", "success", "suppressed", "no_transmission"),
            "eco_requested": ("transmission", "transmission.eco_logical_request", "info", "requested", "audible_expected"),
            "localtuya_confirmed": ("state", "localtuya.confirmed_full_state", "success", "confirmed_by_localtuya", "unknown"),
            "localtuya_confirmation": ("state", "localtuya.confirmed_full_state", "success", "confirmed_by_localtuya", "unknown"),
            "external_change": ("external", "localtuya.external_or_indeterminate", "warning", "observed", "unknown"),
            "error": ("error", "supervisor.error", "error", "failed", "unknown"),
        }
        result = mapping.get(stage, ("logical", f"supervisor.{stage}", "info", "observed", "unknown"))
        if data.get("audibility"):
            return (*result[:4], str(data["audibility"]))
        return result

    async def _async_update_evaluation(
        self,
        stage: str,
        data: Mapping[str, Any],
        event: Mapping[str, Any],
        correlation_id: str,
        context: Context | None,
    ) -> None:
        now = str(event["occurred_at"])
        terminal = stage in {
            "decision_blocked", "evaluation_no_change", "evaluation_completed", "error"
        }
        status = (
            "blocked" if stage == "decision_blocked" else
            "no_change" if stage == "evaluation_no_change" else
            "failed" if stage == "error" else
            "completed" if stage == "evaluation_completed" else "started"
        )
        snapshot = data.get("snapshot") if isinstance(data.get("snapshot"), Mapping) else {}
        record = {
            "evaluation_id": str(data["evaluation_id"]),
            "started_at": str(data.get("started_at") or now),
            "completed_at": now if terminal else None,
            "status": status,
            "summary": data.get("summary") or data.get("reason"),
            "trigger_json": data.get("trigger") or snapshot.get("trigger"),
            "actor_json": {"context_id": getattr(context, "id", None), "user_id": getattr(context, "user_id", None)},
            "inputs_json": data.get("inputs") or snapshot.get("inputs"),
            "prior_decision_json": snapshot.get("prior_decision"),
            "demands_json": data.get("demands") or snapshot.get("demands"),
            "priorities_json": snapshot.get("priorities"),
            "agenda_json": data.get("agenda") or snapshot.get("agenda"),
            "presets_json": data.get("presets") or snapshot.get("presets"),
            "powers_json": data.get("powers") or snapshot.get("powers"),
            "limits_json": data.get("limits") or snapshot.get("limits"),
            "protections_json": data.get("protections") or snapshot.get("protections"),
            "desired_json": data.get("desired") or snapshot.get("desired"),
            "action_json": data.get("action"),
            "result_json": data.get("result") or {"stage": stage, "outcome": event.get("outcome")},
            "reason_json": {"reason": data.get("reason"), "protection": data.get("protection")},
            "related_event_ids": [event["event_id"]]
            if event.get("event_id")
            else [],
            "correlation_id": correlation_id,
            "context_id": getattr(context, "id", None),
        }
        await self.storage.async_upsert_evaluation(record)

    async def _async_process_agenda_capture(
        self, frozen_capture: Any, context: Context | None
    ) -> None:
        capture = thaw_json(frozen_capture)
        data = capture["data"]
        await self.async_log_event(
            {
                "occurred_at": capture["occurred_at"],
                "category": "agenda",
                "event_type": "agenda.evaluated",
                "severity": "debug",
                "outcome": "calculated",
                "summary": "Agenda do Supervisor recalculou a política temporal.",
                "source_component": "elgin_supervisor_agenda",
                "evaluation_id": data.get("evaluation_id"),
                "agenda_state": data.get("global_action") or data.get("state"),
                "details_json": data,
                "retention_class": "full",
            },
            context=context,
            run_anomaly=False,
        )

    def _resolve_correlation(
        self,
        *,
        context: Context | None,
        evaluation_id: str | None,
        occurred_at: datetime,
    ) -> tuple[str, dict[str, Any]]:
        self._prune_correlations(occurred_at)
        if evaluation_id:
            correlation = self._evaluation_correlations.get(evaluation_id)
            if not correlation:
                correlation = str(uuid4())
                self._evaluation_correlations[evaluation_id] = correlation
            if context:
                self._context_correlations[context.id] = (correlation, occurred_at)
            return correlation, {
                "kind": "evaluation_id", "strength": "strong", "evidence": [f"evaluation_id={evaluation_id}"]
            }
        if context:
            for context_id in (context.id, context.parent_id):
                if context_id and context_id in self._context_correlations:
                    correlation = self._context_correlations[context_id][0]
                    self._context_correlations[context.id] = (correlation, occurred_at)
                    return correlation, {
                        "kind": "home_assistant_context",
                        "strength": "strong" if context_id == context.id else "medium",
                        "evidence": ["context.id" if context_id == context.id else "context.parent_id"],
                    }
            correlation = str(uuid4())
            self._context_correlations[context.id] = (correlation, occurred_at)
            return correlation, {"kind": "new_context", "strength": "medium", "evidence": ["novo context.id"]}
        correlation = str(uuid4())
        return correlation, {
            "kind": "unbound", "strength": "none", "evidence": ["sem contexto/evaluation_id"]
        }

    def _prune_correlations(self, now: datetime) -> None:
        window = int(self._setting("correlation_window_seconds", 30))
        cutoff = now - timedelta(seconds=max(window * 4, 120))
        self._context_correlations = {
            key: value for key, value in self._context_correlations.items() if value[1] >= cutoff
        }

    def _apply_privacy(self, event: dict[str, Any]) -> dict[str, Any]:
        """Apply persisted privacy choices before data reaches any queue/listener."""
        if not bool(self._setting("privacy_store_user_ids", True)):
            event["user_id"] = None
        if not bool(self._setting("privacy_store_user_names", True)):
            event["user_name"] = None
            if event.get("actor_type") == "home_assistant_user":
                event["actor_name"] = "Usuário do Home Assistant"
        if bool(self._setting("privacy_redact_sensitive_values", True)):
            sanitized = sanitize(event)
            if isinstance(sanitized, dict):
                event = sanitized
        return event

    async def async_log_event(
        self,
        data: Mapping[str, Any],
        *,
        context: Context | None = None,
        run_anomaly: bool = True,
    ) -> dict[str, Any]:
        event = dict(data)
        occurred_at = str(event.get("occurred_at") or _iso())
        occurred_dt = _parse_iso(occurred_at)
        event.setdefault("event_id", str(uuid4()))
        event["occurred_at"] = occurred_at
        event.setdefault("occurred_at_local", dt_util.as_local(occurred_dt).isoformat())
        event.setdefault("received_at", _iso())
        event.setdefault("category", "logical")
        event.setdefault("event_type", "diagnostic.event")
        event["severity"] = _enum_text(event.get("severity"), "info")
        event["outcome"] = _enum_text(event.get("outcome"), "observed")
        event.setdefault("summary", event["event_type"])
        event.setdefault("source_component", DOMAIN)
        event.setdefault("retention_class", "trace")
        event["retention_class"] = {
            "absolute": "essential",
            "full": "trace",
        }.get(str(event["retention_class"]), str(event["retention_class"]))
        event.setdefault("changed_fields_all", [])
        event.setdefault("changed_fields_relevant", [])
        if not event.get("correlation_id"):
            correlation_id, relation = self._resolve_correlation(
                context=context,
                evaluation_id=event.get("evaluation_id"),
                occurred_at=occurred_dt,
            )
            event["correlation_id"] = correlation_id
            event.setdefault("relation_kind", relation["kind"])
            event.setdefault("relation_strength", relation["strength"])
            event.setdefault("relation_evidence", relation["evidence"])
        if not event.get("actor_name"):
            origin = await self.origin.async_resolve(
                context,
                source_component=str(event.get("source_component") or ""),
                source_entity_id=event.get("source_entity_id"),
                external_observation=bool(event.get("is_external")),
                resolve_user_name=bool(self._setting("privacy_resolve_user_names", True)),
            )
            event.update(origin.as_dict())
        event = self._apply_privacy(event)
        event.setdefault("entity_id", event.get("source_entity_id"))
        event.setdefault("domain", event.get("entity_domain"))
        event.setdefault("mode", event.get("climate_mode"))
        event.setdefault("agenda", event.get("agenda_state"))
        event.setdefault("audibility", event.get("expected_audibility"))
        event["power_profile"] = normalize_power_profile(event.get("power_profile"))
        event["power_level"] = normalize_power_level(event.get("power_level"))
        event["severity"] = classify_event_severity(event)
        event["has_error"] = event["severity"] in {"error", "critical"}
        critical = bool(
            event.get("transmission_id")
            or event.get("is_external")
            or event.get("is_anomaly")
            or event.get("category") in {"transmission", "external", "error", "observation"}
            or event.get("severity") in {"error", "critical"}
        )
        queued = self.storage.enqueue(event, critical=critical)
        if not queued:
            self._ignored += 1
        else:
            self._captured += 1
        self._recent.append(event)
        self._event_times_24h.append(occurred_dt)
        cutoff_24h = datetime.now(timezone.utc) - timedelta(hours=24)
        while self._event_times_24h and self._event_times_24h[0] < cutoff_24h:
            self._event_times_24h.popleft()
        self._last_event = event
        if event.get("transmission_id"):
            self._last_transmission = event
        if event.get("source_component") == "esphome" and str(
            event.get("event_type", "")
        ).endswith("requested_by_ha"):
            self._last_esphome = event
        if event.get("is_external"):
            self._last_external = event
        if event.get("category") in {"decision", "evaluation"}:
            self._last_decision = event
        if event.get("confirmation_state") == "confirmed_by_localtuya" or str(
            event.get("event_type", "")
        ).startswith("localtuya.confirmed"):
            self._last_confirmation = event
        self._emit_entity_event(event)
        self._notify(event)
        if run_anomaly and not str(event.get("event_type", "")).startswith("anomaly."):
            self._spawn(
                self.anomaly.async_process(event), f"{DOMAIN}.anomaly.{event['event_id']}"
            )
        return event

    def _emit_entity_event(self, event: Mapping[str, Any]) -> None:
        if event.get("is_anomaly"):
            event_type = "anomaly"
        elif event.get("category") == "transmission":
            event_type = "transmission"
        elif event.get("is_external"):
            event_type = "external_change"
        elif event.get("category") == "observation":
            event_type = "observation"
        elif event.get("severity") in {"error", "critical"}:
            event_type = "error"
        else:
            return
        attributes = {
            key: event.get(key)
            for key in ("event_id", "event_type", "summary", "severity", "correlation_id", "transmission_id")
        }
        for listener in tuple(self._event_listeners):
            try:
                listener(event_type, attributes)
            except Exception:
                _LOGGER.exception("Falha ao atualizar event entity")

    async def async_emit_anomaly(
        self, anomaly: Mapping[str, Any], *, source_event: Mapping[str, Any]
    ) -> None:
        await self.async_log_event(
            {
                "category": "anomaly",
                "event_type": "anomaly.detected",
                "severity": anomaly.get("severity", "warning"),
                "outcome": "detected",
                "summary": anomaly.get("title") or anomaly.get("explanation"),
                "source_component": DOMAIN,
                "correlation_id": source_event.get("correlation_id"),
                "evaluation_id": source_event.get("evaluation_id"),
                "is_anomaly": True,
                "anomaly_type": anomaly.get("anomaly_type"),
                "retention_class": "absolute",
                "details_json": dict(anomaly),
            },
            run_anomaly=False,
        )

    async def async_register_observation(
        self,
        data: Mapping[str, Any],
        *,
        context: Context | None = None,
    ) -> dict[str, Any]:
        observation_type = str(data.get("observation_type") or "note")
        if observation_type not in {"beep", "note", "manual_action", "environment", "other"}:
            raise ValueError("Tipo de observação inválido")
        occurred_at = str(data.get("occurred_at") or _iso())
        origin = await self.origin.async_resolve(
            context,
            source_component=DOMAIN,
            actor_hint="Usuário observador",
            origin_hint="Observação inserida manualmente",
            resolve_user_name=bool(self._setting("privacy_resolve_user_names", True)),
        )
        candidates = await self._observation_candidates(occurred_at, observation_type)
        correlation_id = candidates[0].get("correlation_id") if candidates else str(uuid4())
        raw_count = data.get("expected_count")
        numeric_count = raw_count if isinstance(raw_count, int) and not isinstance(raw_count, bool) else None
        input_metadata = dict(data.get("metadata") or {})
        label_hint = str(
            input_metadata.get("beep_count")
            or input_metadata.get("expected_count_label")
            or ""
        )
        if label_hint == "many":
            label_hint = "multiple"
        count_label = (
            str(numeric_count) if numeric_count is not None
            else "multiple"
            if raw_count == "multiple" or label_hint == "multiple"
            else "uncertain"
        ) if observation_type == "beep" else None
        observation = {
            "observation_id": str(uuid4()),
            "observation_type": observation_type,
            "occurred_at": occurred_at,
            "created_at": _iso(),
            "user_id": origin.user_id
            if self._setting("privacy_store_user_ids", True)
            else None,
            "user_name": origin.user_name
            if self._setting("privacy_store_user_names", True)
            else None,
            "note": str(data.get("note") or "")[:4096],
            "expected_count": numeric_count,
            "metadata": {
                **input_metadata,
                "beep_count": count_label,
                "candidate_relations": [
                    {
                        "event_id": item.get("event_id"),
                        "relation_strength": item.get("candidate_strength"),
                        "reason": item.get("candidate_reason"),
                    }
                    for item in candidates[:20]
                ],
                "causality_notice": "proximidade temporal isolada não confirma a causa do bip",
            },
            "correlation_id": correlation_id,
            "related_event_ids": [item["event_id"] for item in candidates[:20]],
        }
        if self._setting("privacy_redact_sensitive_values", True):
            safe_observation = sanitize(observation)
            if isinstance(safe_observation, dict):
                observation = safe_observation
        saved = await self.storage.async_add_observation(observation)
        await self.async_log_event(
            {
                "occurred_at": occurred_at,
                "category": "observation",
                "event_type": f"observation.{observation_type}",
                "severity": "info",
                "outcome": "observed_by_user",
                "summary": (
                    f"Usuário observou {numeric_count} bip(s)."
                    if observation_type == "beep" and numeric_count is not None
                    else "Usuário observou vários bips."
                    if observation_type == "beep" and count_label == "multiple"
                    else "Usuário observou bip(s), quantidade incerta."
                    if observation_type == "beep"
                    else "Usuário registrou uma observação."
                ),
                "source_component": DOMAIN,
                "correlation_id": correlation_id,
                "expected_audibility": "observed_by_user" if observation_type == "beep" else "unknown",
                "retention_class": "absolute",
                "details_json": saved,
                **origin.as_dict(),
            },
            context=context,
            run_anomaly=True,
        )
        return saved

    async def _observation_candidates(
        self, occurred_at: str, observation_type: str
    ) -> list[dict[str, Any]]:
        """Find persisted and not-yet-flushed evidence around an observation."""

        center = _parse_iso(occurred_at)
        before = float(self._setting("beep_window_before_seconds", 120))
        after = float(self._setting("beep_window_after_seconds", 120))
        start = (center - timedelta(seconds=before)).isoformat()
        end = (center + timedelta(seconds=after)).isoformat()
        filters: dict[str, Any] = {"start": start, "end": end}
        if observation_type == "beep":
            filters["audibilities"] = ["audible_expected"]

        by_id: dict[str, dict[str, Any]] = {}
        cursor: str | None = None
        # Four bounded pages cover 1,000 audible candidates without ever
        # loading an unbounded interval into HA or the browser.
        for _page in range(4):
            page = await self.storage.async_list_events(
                filters,
                cursor=cursor,
                limit=250,
                direction="older",
                include_details=False,
            )
            for item in page.get("items", []):
                if item.get("event_id"):
                    by_id[str(item["event_id"])] = dict(item)
            if not page.get("has_more") or not page.get("next_cursor"):
                break
            cursor = str(page["next_cursor"])

        # The writer batches asynchronously. Merge the in-memory tail so a bip
        # registered immediately after a command still sees that command.
        for recent in self._recent:
            event_id = recent.get("event_id")
            if not event_id:
                continue
            event_time = _parse_iso(str(recent["occurred_at"]))
            if not center - timedelta(seconds=before) <= event_time <= center + timedelta(seconds=after):
                continue
            if observation_type == "beep" and recent.get("expected_audibility") != "audible_expected":
                continue
            by_id[str(event_id)] = dict(recent)

        candidates: list[dict[str, Any]] = []
        for event in by_id.values():
            delta = (center - _parse_iso(str(event["occurred_at"]))).total_seconds()
            if delta < -after or delta > before:
                continue
            if observation_type == "beep":
                if event.get("expected_audibility") != "audible_expected" and event.get(
                    "audibility"
                ) != "audible_expected":
                    continue
            item = dict(event)
            if event.get("event_type") in AUDIBLE_REQUEST_TYPES:
                item["candidate_strength"] = "strong"
                item["candidate_reason"] = "chamada HA de ação potencialmente audível dentro da janela"
            elif event.get("evaluation_id") and event.get("correlation_id"):
                item["candidate_strength"] = "medium"
                item["candidate_reason"] = "evidência audível estruturada dentro da janela"
            else:
                item["candidate_strength"] = "weak"
                item["candidate_reason"] = "somente proximidade temporal"
            item["distance_seconds"] = abs(delta)
            candidates.append(item)
        return sorted(candidates, key=lambda item: item["distance_seconds"])

    async def async_delete_observation(
        self, observation_id: str, *, context: Context | None = None
    ) -> bool:
        deleted = await self.storage.async_delete_observation(observation_id)
        if deleted:
            await self.async_log_event(
                {
                    "category": "maintenance",
                    "event_type": "observation.deleted",
                    "severity": "info",
                    "outcome": "deleted",
                    "summary": "Uma observação manual foi excluída por administrador.",
                    "source_component": DOMAIN,
                    "retention_class": "essential",
                    "details_json": {"observation_id": observation_id},
                },
                context=context,
                run_anomaly=False,
            )
        return deleted

    async def async_acknowledge_anomaly(
        self, anomaly_id: str, *, context: Context | None, note: str | None = None
    ) -> bool:
        origin = await self.origin.async_resolve(
            context,
            source_component=DOMAIN,
            resolve_user_name=bool(self._setting("privacy_resolve_user_names", True)),
        )
        result = await self.storage.async_set_anomaly_status(
            anomaly_id,
            "acknowledged",
            origin.actor_name
            if self._setting("privacy_store_user_names", True)
            else "Usuário do Home Assistant",
            note,
        )
        if result:
            await self.async_log_event(
                {
                    "category": "anomaly",
                    "event_type": "anomaly.acknowledged",
                    "severity": "info",
                    "outcome": "acknowledged",
                    "summary": f"Anomalia {anomaly_id} reconhecida.",
                    "source_component": DOMAIN,
                    "retention_class": "absolute",
                },
                context=context,
                run_anomaly=False,
            )
        return result

    async def async_resolve_anomaly(
        self, anomaly_id: str, *, context: Context | None, note: str | None = None
    ) -> bool:
        origin = await self.origin.async_resolve(
            context,
            source_component=DOMAIN,
            resolve_user_name=bool(self._setting("privacy_resolve_user_names", True)),
        )
        result = await self.storage.async_set_anomaly_status(
            anomaly_id,
            "resolved",
            origin.actor_name
            if self._setting("privacy_store_user_names", True)
            else "Usuário do Home Assistant",
            note,
        )
        if result:
            await self.async_log_event(
                {
                    "category": "anomaly",
                    "event_type": "anomaly.resolved",
                    "severity": "success",
                    "outcome": "resolved",
                    "summary": f"Anomalia {anomaly_id} resolvida.",
                    "source_component": DOMAIN,
                    "retention_class": "absolute",
                },
                context=context,
                run_anomaly=False,
            )
        return result

    async def async_run_cleanup(self, *, actor: str = "Usuário") -> dict[str, Any]:
        result = await self.storage.async_cleanup()
        await self._async_log_cleanup(result, actor=actor)
        return result

    async def _async_periodic_cleanup(self, _now: datetime) -> None:
        try:
            result = await self.storage.async_cleanup_if_due()
            if not result.get("skipped"):
                await self._async_log_cleanup(
                    result, actor="Manutenção automática"
                )
        except Exception:
            _LOGGER.exception("Falha isolada na limpeza periódica do diagnóstico")

    async def _async_log_cleanup(
        self, result: Mapping[str, Any], *, actor: str
    ) -> None:
        """Record a cleanup that actually ran, never a not-due poll."""

        await self.async_log_event(
            {
                "category": "maintenance",
                "event_type": "maintenance.cleanup",
                "severity": "success",
                "outcome": "completed",
                "summary": "Limpeza do banco de diagnóstico concluída.",
                "actor_name": actor,
                "source_component": DOMAIN,
                "retention_class": "absolute",
                "details_json": dict(result),
            },
            run_anomaly=False,
        )

    async def _async_refresh_health(self, _now: datetime) -> None:
        try:
            self._cached_health = await self.storage.async_health()
            self._notify()
        except Exception:
            _LOGGER.exception("Falha isolada ao atualizar saúde do diagnóstico")

    async def async_reevaluate_anomalies(self) -> dict[str, Any]:
        result = await self.anomaly.async_reevaluate()
        await self.async_log_event(
            {
                "category": "maintenance",
                "event_type": "anomaly.reevaluated",
                "severity": "success",
                "outcome": "completed",
                "summary": "Anomalias foram reavaliadas sobre a janela configurada.",
                "source_component": DOMAIN,
                "retention_class": "essential",
                "details_json": result,
            },
            run_anomaly=False,
        )
        return result

    async def async_update_settings(self, values: Mapping[str, Any]) -> dict[str, Any]:
        current = self.settings.as_dict()
        unknown = set(values) - set(current)
        if unknown:
            raise ValueError(f"Opções desconhecidas: {', '.join(sorted(unknown))}")
        updated = DiagnosticSettings.from_options({**current, **dict(values)})
        updated.validate()
        self.settings = updated
        self.storage.settings = updated
        await self.anomaly.async_apply_settings()
        self.hass.config_entries.async_update_entry(self.entry, options=updated.as_dict())
        await self.async_log_event(
            {
                "category": "configuration",
                "event_type": "configuration.changed",
                "severity": "success",
                "outcome": "accepted",
                "summary": "Configurações do diagnóstico atualizadas e persistidas.",
                "source_component": DOMAIN,
                "retention_class": "absolute",
                "details_json": {"changed_keys": sorted(values)},
            },
            run_anomaly=False,
        )
        await self._async_periodic_cleanup(datetime.now(timezone.utc))
        return updated.as_dict()

    async def async_get_snapshot(self, *, include_recent: bool = True) -> dict[str, Any]:
        health, statistics, anomalies, observations, persisted_flow = await asyncio.gather(
            self.storage.async_health(),
            self.storage.async_get_statistics(),
            self.storage.async_list_anomalies("active", 50),
            self.storage.async_list_observations(50),
            self.storage.async_get_latest_operational_correlation(),
        )
        self._cached_health = dict(health)
        self._last_flow_cache = await self._async_build_latest_flow(persisted_flow)
        snapshot = self.status_snapshot()
        snapshot["storage"] = health
        snapshot["database"] = health
        snapshot["statistics"] = statistics
        snapshot["active_anomalies"] = len(anomalies)
        snapshot["anomaly_items"] = anomalies
        snapshot["observations"] = observations
        snapshot["recent_events"] = list(self._recent)[-100:] if include_recent else []
        snapshot["settings"] = self.settings.as_dict()
        snapshot["counters"].update(
            {
                "active_anomalies": len(anomalies),
                "total_events": statistics.get("total_events", 0),
                "database_size_bytes": health.get("database_size_bytes", 0),
                "compacted": health.get("compacted_events", 0),
                "events_per_day": health.get("events_per_day", 0),
                "top_producer": health.get("top_producer"),
            }
        )
        return snapshot

    async def _async_build_latest_flow(
        self, persisted: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Merge the newest persisted correlation with the unflushed tail."""

        persisted_id = str(persisted.get("correlation_id") or "") or None
        persisted_anchor = str(persisted.get("anchor_occurred_at") or "") or None
        memory_candidates = [
            item
            for item in self._recent
            if item.get("correlation_id") and is_operational_flow_event(item)
        ]
        memory_anchor = max(
            memory_candidates,
            key=lambda item: (
                str(item.get("occurred_at") or ""),
                str(item.get("event_id") or ""),
            ),
            default=None,
        )
        memory_id = (
            str(memory_anchor.get("correlation_id")) if memory_anchor else None
        )
        use_memory = bool(
            memory_anchor
            and (
                not persisted_anchor
                or _parse_iso(str(memory_anchor.get("occurred_at")))
                >= _parse_iso(persisted_anchor)
            )
        )
        correlation_id = memory_id if use_memory else persisted_id
        base_events = list(persisted.get("events") or []) if correlation_id == persisted_id else []
        if correlation_id and correlation_id != persisted_id:
            stored = await self.storage.async_get_correlation(correlation_id)
            base_events = list(stored.get("events") or [])
        if correlation_id:
            base_events.extend(
                item
                for item in self._recent
                if item.get("correlation_id") == correlation_id
            )
        by_id = {
            str(item.get("event_id")): dict(item)
            for item in base_events
            if item.get("event_id")
        }
        return build_operational_flow(list(by_id.values()), correlation_id)

    def _last_flow(self) -> list[dict[str, Any]]:
        """Compatibility accessor for entity consumers of the former helper."""

        return list(self._last_flow_cache.get("steps") or [])

    def _current_supervisor_state(self) -> dict[str, Any]:
        def state(entity_id: str) -> str | None:
            current = self.hass.states.get(entity_id)
            if current is None or current.state in {"unknown", "unavailable"}:
                return None
            return str(current.state)

        def attribute(entity_id: str, name: str) -> Any:
            current = self.hass.states.get(entity_id)
            return current.attributes.get(name) if current is not None else None

        treatment = state("input_select.elgin_supervisor_tratamento_ativo")
        effective_entities = {
            "Aquecimento": (
                "sensor.elgin_supervisor_preset_efetivo_de_condicao_do_aquecimento",
                "sensor.elgin_supervisor_potencia_efetiva_de_aquecimento",
            ),
            "Refrigeração": (
                "sensor.elgin_supervisor_preset_efetivo_de_condicao_da_refrigeracao",
                "sensor.elgin_supervisor_potencia_efetiva_de_refrigeracao",
            ),
            "Desumidificação": (
                "sensor.elgin_supervisor_preset_efetivo_de_condicao_da_desumidificacao",
                "sensor.elgin_supervisor_potencia_efetiva_de_desumidificacao",
            ),
        }
        preset_entity_id, power_entity_id = effective_entities.get(
            treatment, (None, None)
        )
        preset = state(preset_entity_id) if preset_entity_id else None
        power_profile = state(power_entity_id) if power_entity_id else None
        enabled = state("input_boolean.elgin_supervisor_habilitado")
        active_protections = [
            label
            for entity_id, label in (
                ("timer.elgin_supervisor_pausa_manual", "Pausa manual"),
                ("timer.elgin_supervisor_protecao_troca_modo", "Troca de modo"),
                ("timer.elgin_supervisor_janela_reconciliacao", "Reconciliação"),
                ("timer.elgin_supervisor_classificacao_fisica", "Classificação física"),
            )
            if state(entity_id) == "active"
        ]
        return {
            "supervisor_state": (
                "Habilitado" if enabled == "on" else "Desabilitado" if enabled == "off" else "Indisponível"
            ),
            "treatment": treatment,
            "physical_mode": state("sensor.elgin_supervisor_estado_fisico_observado"),
            "effective_configuration_applicable": treatment in effective_entities,
            "preset": preset,
            "power_profile": power_profile,
            "agenda": attribute("sensor.elgin_supervisor_agenda_politica", "global_action")
            or state("sensor.elgin_supervisor_agenda_politica"),
            "protection": ", ".join(active_protections) if active_protections else "Nenhuma",
        }

    def status_snapshot(self) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        cutoff_minute = now - timedelta(minutes=1)
        cutoff_hour = now - timedelta(hours=1)
        cutoff_day = now - timedelta(hours=24)
        events_per_minute = sum(1 for stamp in self._rate_events if stamp >= cutoff_minute)
        events_last_hour = sum(1 for stamp in self._event_times_24h if stamp >= cutoff_hour)
        events_last_day = sum(1 for stamp in self._event_times_24h if stamp >= cutoff_day)
        storm_active = events_per_minute >= int(self._setting("rate_warning_events", 500))
        persistence_healthy = bool(self.storage.healthy)
        current = self._current_supervisor_state()
        return {
            "status": self._status,
            "healthy": self._status == "Operacional" and persistence_healthy,
            "persistence_healthy": persistence_healthy,
            "entry_id": self.entry_id,
            "started_at": _iso(self._started_at) if self._started_at else None,
            "instrumentation_complete": self.instrumentation_complete(),
            "capture_mode": self._setting("capture_mode", "normal"),
            **current,
            "events_24h": events_last_day,
            "event_rate_per_minute": events_per_minute,
            "storm_protection_active": storm_active,
            "database_size_bytes": int(self._cached_health.get("database_size_bytes", 0)),
            "storage": dict(self._cached_health),
            "last_action": dict(self._last_transmission) if self._last_transmission else None,
            "last_esphome": dict(self._last_esphome) if self._last_esphome else None,
            "last_external_change": dict(self._last_external) if self._last_external else None,
            "last_decision": dict(self._last_decision) if self._last_decision else None,
            "last_confirmation": dict(self._last_confirmation) if self._last_confirmation else None,
            "last_complete_flow": dict(self._last_flow_cache),
            "counters": {
                "captured": self._captured,
                "ignored": self._ignored,
                "queued": self.storage.queue_size,
                "dropped": self.storage.dropped_events,
                "pending_confirmations": len(self._pending),
                "last_hour": events_last_hour,
                "last_24h": events_last_day,
                "current_rate": events_per_minute,
                "events_per_minute": events_per_minute,
                "database_size_bytes": int(
                    self._cached_health.get("database_size_bytes", 0)
                ),
            },
            "last_event": dict(self._last_event) if self._last_event else None,
            "last_transmission": dict(self._last_transmission) if self._last_transmission else None,
            "correlation": {
                "contexts": len(self._context_correlations),
                "evaluations": len(self._evaluation_correlations),
            },
        }

    def instrumentation_complete(self) -> bool:
        required = (
            "climate.esp8266_elgin_aux_quarto",
            "sensor.elgin_supervisor_potencias",
            "sensor.elgin_supervisor_configuracao_desejada",
            *LOCALTUYA_ENTITIES,
        )
        return self._instrumentation_seen and all(
            self.hass.states.get(entity_id) is not None for entity_id in required
        )


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)
