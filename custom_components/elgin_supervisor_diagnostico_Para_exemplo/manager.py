"""Runtime manager for Elgin Supervisor auditing and diagnostics."""

from __future__ import annotations

import asyncio
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import logging
from typing import Any
from uuid import uuid4

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EVENT_CALL_SERVICE, EVENT_STATE_CHANGED
from homeassistant.core import Context, Event, HomeAssistant, State, callback
from homeassistant.helpers.event import async_track_state_change_event, async_track_time_interval
from homeassistant.helpers import issue_registry as ir
from homeassistant.util import dt as dt_util

from .anomaly import AnomalyEngine
from .const import (
    ANOMALY_REEVALUATE_INTERVAL,
    CLEANUP_INTERVAL,
    CRITICAL_EVENT_TYPES,
    EVENT_AGENDA_POLICY_CHANGED,
    EVENT_AGENDA_EVALUATED,
    EVENT_DIAGNOSTIC_UPDATED,
    LOCALTUYA_ENTITIES,
    MONITORED_ENTITIES,
    RELEVANT_SERVICE_DOMAINS,
    TRANSMISSION_EVENT_TYPES,
    DOMAIN,
)
from .correlation import CorrelationManager
from .exporter import DiagnosticExporter
from .models import (
    AnomalyRecord,
    AuditEvent,
    DiagnosticSettings,
    ExpectedAudibility,
    Outcome,
    RetentionClass,
    Severity,
)
from .origin_resolver import OriginResolver
from .storage import DiagnosticStorage

_LOGGER = logging.getLogger(__name__)


@dataclass(slots=True)
class DiagnosticRuntimeData:
    """Typed config-entry runtime data."""

    manager: "DiagnosticManager"
    storage: DiagnosticStorage


@dataclass(slots=True)
class PendingConfirmation:
    correlation_id: str | None
    transmission_id: str | None
    created_at: datetime
    desired: dict[str, Any] | None
    event_id: str


class DiagnosticManager:
    """Collect, correlate and expose diagnostic events without controlling HVAC."""

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry
        self.entry_id = entry.entry_id
        self.settings = DiagnosticSettings.from_options(dict(entry.options))
        self.settings.validate()
        self.storage = DiagnosticStorage(hass, self.settings)
        self.correlation = CorrelationManager()
        self.origin = OriginResolver(hass)
        self.anomaly = AnomalyEngine(self)
        self.exporter = DiagnosticExporter(self)
        self._listeners: set[Callable[[], None]] = set()
        self._event_listeners: set[Callable[[str, dict[str, Any]], None]] = set()
        self._unsubs: list[Callable[[], None]] = []
        self._tasks: set[asyncio.Task[Any]] = set()
        self._recent: deque[AuditEvent] = deque(maxlen=300)
        self._pending_confirmations: deque[PendingConfirmation] = deque(maxlen=50)
        self._started_at: datetime | None = None
        self._last_event: AuditEvent | None = None
        self._last_transmission: AuditEvent | None = None
        self._last_anomaly: AnomalyRecord | None = None
        self._status = "Inicializando"
        self._intensive_mode = self.settings.intensive_mode
        self._beep_tasks: dict[str, asyncio.Task[Any]] = {}
        self._internal_service_guard = 0

    @property
    def intensive_mode(self) -> bool:
        return self._intensive_mode

    @property
    def last_event(self) -> AuditEvent | None:
        return self._last_event

    @property
    def last_transmission(self) -> AuditEvent | None:
        return self._last_transmission

    @callback
    def async_add_listener(self, listener: Callable[[], None]) -> Callable[[], None]:
        self._listeners.add(listener)

        @callback
        def remove() -> None:
            self._listeners.discard(listener)

        return remove

    @callback
    def async_add_event_listener(
        self, listener: Callable[[str, dict[str, Any]], None]
    ) -> Callable[[], None]:
        self._event_listeners.add(listener)

        @callback
        def remove() -> None:
            self._event_listeners.discard(listener)

        return remove

    @callback
    def _notify(self) -> None:
        for listener in tuple(self._listeners):
            try:
                listener()
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Falha ao atualizar entidade de diagnóstico")
        self.hass.bus.async_fire(EVENT_DIAGNOSTIC_UPDATED, {"entry_id": self.entry_id})

    @callback
    def _emit_event_entity(self, event_type: str, attributes: dict[str, Any]) -> None:
        for listener in tuple(self._event_listeners):
            try:
                listener(event_type, attributes)
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Falha ao atualizar event entity")

    async def async_start(self) -> None:
        await self.storage.async_start()
        self._started_at = datetime.now(timezone.utc)
        self._status = "Operacional"
        self._unsubs.extend(
            [
                async_track_state_change_event(
                    self.hass, list(MONITORED_ENTITIES), self._async_state_changed
                ),
                self.hass.bus.async_listen(EVENT_CALL_SERVICE, self._handle_call_service),
                self.hass.bus.async_listen(
                    EVENT_AGENDA_POLICY_CHANGED, self._handle_agenda_event
                ),
                self.hass.bus.async_listen(
                    EVENT_AGENDA_EVALUATED, self._handle_agenda_event
                ),
                async_track_time_interval(
                    self.hass, self._async_periodic_cleanup, CLEANUP_INTERVAL
                ),
                async_track_time_interval(
                    self.hass,
                    self._async_periodic_anomaly_reevaluation,
                    ANOMALY_REEVALUATE_INTERVAL,
                ),
            ]
        )
        await self.async_log_event(
            {
                "category": "system",
                "event_type": "configuration.changed",
                "severity": Severity.SUCCESS,
                "retention_class": RetentionClass.ABSOLUTE,
                "summary": "Integração de auditoria iniciada.",
                "outcome": Outcome.ACCEPTED,
                "source_component": "elgin_supervisor_diagnostico",
                "actor_name": "Elgin Supervisor — Auditoria e Diagnóstico",
                "origin_class": "Inicialização da integração",
                "details_json": {
                    "schema_version": 1,
                    "monitored_entity_count": len(MONITORED_ENTITIES),
                    "intensive_mode": self._intensive_mode,
                },
            },
            run_anomaly=False,
        )
        self._spawn(
            self._async_delayed_repairs_check(),
            f"{__package__}.repairs_initial_check",
        )

    async def _async_delayed_repairs_check(self) -> None:
        """Wait for dependent integrations/entities before declaring instrumentation missing."""
        await asyncio.sleep(30)
        await self.async_refresh_repairs()

    async def async_stop(self) -> None:
        self._status = "Encerrando"
        for unsubscribe in self._unsubs:
            try:
                unsubscribe()
            except Exception:  # noqa: BLE001
                _LOGGER.debug("Listener já removido", exc_info=True)
        self._unsubs.clear()
        for task in list(self._tasks):
            task.cancel()
        for task in list(self._beep_tasks.values()):
            task.cancel()
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
        if self._beep_tasks:
            await asyncio.gather(*self._beep_tasks.values(), return_exceptions=True)
        self._tasks.clear()
        self._beep_tasks.clear()
        await self.storage.async_stop()
        self._status = "Parado"

    def _spawn(self, coro: Any, name: str) -> None:
        task = self.hass.async_create_background_task(coro, name)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def async_begin_trace(
        self,
        *,
        context: Context | None,
        actor: str | None = None,
        source_entity_id: str | None = None,
        category: str = "evaluation",
        summary: str = "Fluxo de auditoria iniciado",
    ) -> dict[str, Any]:
        origin = await self.origin.async_resolve(
            context,
            actor_hint=actor or "Elgin Supervisor",
            origin_hint="Automação local" if not context or not context.user_id else None,
        )
        entry = self.correlation.begin(
            context=context,
            source_entity_id=source_entity_id,
            actor=origin.actor_name,
        )
        await self.async_log_event(
            {
                "category": category,
                "event_type": "evaluation.started",
                "severity": Severity.INFO,
                "retention_class": RetentionClass.FULL,
                "summary": summary,
                "outcome": Outcome.STARTED,
                "source_component": "yaml",
                "source_entity_id": source_entity_id,
                "correlation_id": entry.correlation_id,
                "context_id": entry.context_id,
                "parent_context_id": entry.parent_context_id,
                "user_id": origin.user_id,
                "user_name": origin.user_name,
                "actor_type": origin.actor_type,
                "actor_name": origin.actor_name,
                "origin_class": origin.origin_class,
                "origin_confidence": origin.origin_confidence,
            },
            context=context,
            run_anomaly=False,
        )
        return {
            "correlation_id": entry.correlation_id,
            "started_at": entry.started_at.isoformat(),
            "actor": origin.actor_name,
            "root_context_id": entry.context_id,
        }

    async def async_log_event(
        self,
        data: dict[str, Any],
        *,
        context: Context | None = None,
        run_anomaly: bool = True,
    ) -> AuditEvent:
        if data.get("event_type") == "evaluation.no_change" and not self._intensive_mode:
            # Return an ephemeral event so callers keep deterministic behavior.
            return AuditEvent.from_mapping(data)
        source_entity_id = data.get("source_entity_id") or data.get("source")
        correlation_id, partial = self.correlation.resolve(
            explicit_id=data.get("correlation_id"),
            context=context,
            source_entity_id=source_entity_id,
        )
        origin = await self.origin.async_resolve(
            context,
            source_component=data.get("source_component"),
            is_external=bool(data.get("is_external")),
            actor_hint=data.get("actor_name"),
            origin_hint=data.get("origin_class"),
        )
        details = data.get("details_json") or data.get("details") or {}
        if not isinstance(details, dict):
            details = {"value": details}
        if not self.settings.technical_details_enabled:
            details = {
                key: value
                for key, value in details.items()
                if key in {"partial_correlation", "condition", "reason", "forced", "caller"}
            }
        if partial:
            details = {**details, "partial_correlation": True}
        event_data = {
            **data,
            "correlation_id": correlation_id,
            "context_id": data.get("context_id") or (context.id if context else None),
            "parent_context_id": data.get("parent_context_id") or (context.parent_id if context else None),
            "user_id": data.get("user_id") or origin.user_id,
            "user_name": data.get("user_name") or origin.user_name,
            "actor_type": data.get("actor_type") or origin.actor_type,
            "actor_name": data.get("actor_name") or origin.actor_name,
            "origin_class": data.get("origin_class") or origin.origin_class,
            "origin_confidence": data.get("origin_confidence") or origin.origin_confidence,
            "details_json": details,
            "before_json": data.get("before_json") or data.get("before"),
            "desired_json": data.get("desired_json") or data.get("desired"),
            "confirmed_json": data.get("confirmed_json") or data.get("confirmed"),
        }
        event = AuditEvent.from_mapping(event_data)
        critical = (
            event.event_type in CRITICAL_EVENT_TYPES
            or event.severity in {Severity.ERROR, Severity.CRITICAL}
            or event.is_anomaly
            or bool(event.transmission_id)
        )
        queued = self.storage.enqueue(event, critical=critical)
        if not queued and critical:
            _LOGGER.error(
                "Evento crítico foi encaminhado ao journal de emergência: %s",
                event.event_type,
            )
        elif not queued and self.storage.consume_overflow_report():
            overflow = AuditEvent.from_mapping(
                {
                    "category": "storage",
                    "event_type": "storage.queue_overflow",
                    "severity": Severity.ERROR,
                    "retention_class": RetentionClass.ABSOLUTE,
                    "summary": "A fila normal de auditoria atingiu 5.000 eventos; um evento de baixa prioridade foi descartado.",
                    "technical_message": "Eventos críticos, comandos e anomalias continuam usando a fila reservada.",
                    "outcome": Outcome.FAILED,
                    "source_component": "elgin_supervisor_diagnostico",
                    "correlation_id": correlation_id,
                    "is_anomaly": True,
                    "anomaly_type": "system.persistence",
                    "details_json": {
                        "normal_queue_limit": 5000,
                        "dropped_events": self.storage.dropped_events,
                    },
                }
            )
            self.storage.enqueue(overflow, critical=True)
            self._recent.append(overflow)
            self._last_event = overflow
            self._spawn(
                self.anomaly.async_process(overflow),
                f"{__package__}.anomaly.{overflow.event_id}",
            )
        # Error details use their own shorter retention, while an absolute
        # summary survives after those details expire.
        if (
            event.retention_class == RetentionClass.ERROR
            and event.severity in {Severity.ERROR, Severity.CRITICAL}
            and not event.event_type.endswith(".summary")
        ):
            summary_event = AuditEvent.from_mapping(
                {
                    "category": event.category,
                    "event_type": f"{event.event_type}.summary",
                    "severity": event.severity,
                    "retention_class": RetentionClass.ABSOLUTE,
                    "summary": event.summary,
                    "outcome": event.outcome,
                    "source_component": event.source_component,
                    "source_entity_id": event.source_entity_id,
                    "action_domain": event.action_domain,
                    "action_name": event.action_name,
                    "correlation_id": event.correlation_id,
                    "parent_correlation_id": event.parent_correlation_id,
                    "context_id": event.context_id,
                    "parent_context_id": event.parent_context_id,
                    "user_id": event.user_id,
                    "user_name": event.user_name,
                    "actor_type": event.actor_type,
                    "actor_name": event.actor_name,
                    "origin_class": event.origin_class,
                    "origin_confidence": event.origin_confidence,
                    "transmission_id": event.transmission_id,
                    "frame_kind": event.frame_kind,
                    "frame_hash": event.frame_hash,
                    "is_external": event.is_external,
                    "details_json": {"detail_event_id": event.event_id},
                }
            )
            self.storage.enqueue(summary_event, critical=True)
        self._recent.append(event)
        self._last_event = event
        if event.event_type in TRANSMISSION_EVENT_TYPES or event.transmission_id:
            self._last_transmission = event
        if event.event_type in {
            "ir.full.transmitter_called",
            "ir.full.response",
        } and event.outcome in {
            Outcome.TRANSMITTED_BY_SOFTWARE,
            Outcome.ACCEPTED,
        }:
            self._pending_confirmations.append(
                PendingConfirmation(
                    correlation_id=event.correlation_id,
                    transmission_id=event.transmission_id,
                    created_at=datetime.fromisoformat(event.occurred_at).astimezone(timezone.utc),
                    desired=event.desired_json if isinstance(event.desired_json, dict) else None,
                    event_id=event.event_id,
                )
            )
        public_type = self._public_event_type(event)
        if public_type:
            self._emit_event_entity(
                public_type,
                {
                    "event_id": event.event_id,
                    "event_type": event.event_type,
                    "summary": event.summary,
                    "severity": event.severity,
                    "correlation_id": event.correlation_id,
                    "transmission_id": event.transmission_id,
                },
            )
        self._notify()
        if run_anomaly and event.event_type != "anomaly.detected":
            self._spawn(
                self.anomaly.async_process(event),
                f"{__package__}.anomaly.{event.event_id}",
            )
        return event

    @staticmethod
    def _public_event_type(event: AuditEvent) -> str | None:
        if event.is_anomaly or event.event_type.startswith("anomaly."):
            return "anomaly"
        if event.transmission_id or event.event_type.startswith("ir."):
            return "transmission"
        if event.is_external:
            return "external_change"
        if event.event_type.startswith("user."):
            return "user_observation"
        if event.severity in {Severity.ERROR, Severity.CRITICAL}:
            return "error"
        return None

    async def async_emit_anomaly_event(
        self, anomaly: AnomalyRecord, *, source_event: AuditEvent
    ) -> None:
        self._last_anomaly = anomaly
        await self.async_log_event(
            {
                "category": "anomaly",
                "event_type": "anomaly.detected",
                "severity": anomaly.severity,
                "retention_class": RetentionClass.ABSOLUTE,
                "summary": anomaly.explanation,
                "technical_message": anomaly.recommendation,
                "outcome": Outcome.CALCULATED,
                "source_component": "elgin_supervisor_diagnostico",
                "correlation_id": source_event.correlation_id,
                "parent_correlation_id": source_event.correlation_id,
                "is_anomaly": True,
                "anomaly_type": anomaly.anomaly_type,
                "details_json": {
                    "anomaly_id": anomaly.anomaly_id,
                    "count": anomaly.count,
                    "related_event_ids": anomaly.related_event_ids,
                    "recommendation": anomaly.recommendation,
                    **anomaly.details,
                },
            },
            run_anomaly=False,
        )

    async def async_register_beep(
        self,
        *,
        quantity: str,
        note: str | None,
        occurred_at: str | None,
        context: Context | None,
    ) -> dict[str, Any]:
        when = dt_util.parse_datetime(occurred_at) if occurred_at else dt_util.now()
        if when is None:
            raise ValueError("Horário do bip inválido.")
        if when.tzinfo is None:
            when = when.replace(tzinfo=dt_util.DEFAULT_TIME_ZONE)
        now = dt_util.now()
        if abs((now - dt_util.as_local(when)).total_seconds()) > 30:
            raise ValueError("O horário do bip só pode ser ajustado em até 30 segundos.")
        correlation = self.correlation.begin(context=context, actor="Observação manual")
        climate_snapshot = self._climate_snapshot()
        event = await self.async_log_event(
            {
                "occurred_at": dt_util.as_utc(when).isoformat(),
                "occurred_at_local": dt_util.as_local(when).isoformat(),
                "category": "user",
                "event_type": "user.beep_observed",
                "severity": Severity.INFO,
                "retention_class": RetentionClass.ABSOLUTE,
                "summary": f"Usuário registrou {quantity}.",
                "technical_message": note,
                "outcome": Outcome.UNKNOWN,
                "source_component": "elgin_supervisor_diagnostico",
                "correlation_id": correlation.correlation_id,
                "expected_audibility": ExpectedAudibility.UNKNOWN,
                "observed_audibility": quantity,
                "details_json": {
                    "quantity": quantity,
                    "note": note or "",
                    "window_before_seconds": self.settings.beep_window_before_seconds,
                    "window_after_seconds": self.settings.beep_window_after_seconds,
                    "snapshot": climate_snapshot,
                    "correlation_status": "window_open",
                },
            },
            context=context,
        )
        task = self.hass.async_create_background_task(
            self._async_finish_beep_window(event),
            f"{__package__}.beep_window.{event.event_id}",
        )
        self._beep_tasks[event.event_id] = task
        task.add_done_callback(lambda _task: self._beep_tasks.pop(event.event_id, None))
        return {
            "event_id": event.event_id,
            "correlation_id": event.correlation_id,
            "window_closes_at": (
                dt_util.as_utc(when)
                + timedelta(seconds=self.settings.beep_window_after_seconds)
            ).isoformat(),
        }

    async def _async_finish_beep_window(self, beep: AuditEvent) -> None:
        delay = max(
            0.0,
            (
                datetime.fromisoformat(beep.occurred_at).astimezone(timezone.utc)
                + timedelta(seconds=self.settings.beep_window_after_seconds)
                - datetime.now(timezone.utc)
            ).total_seconds(),
        )
        await asyncio.sleep(delay)
        start = (
            datetime.fromisoformat(beep.occurred_at).astimezone(timezone.utc)
            - timedelta(seconds=self.settings.beep_window_before_seconds)
        ).isoformat()
        end = (
            datetime.fromisoformat(beep.occurred_at).astimezone(timezone.utc)
            + timedelta(seconds=self.settings.beep_window_after_seconds)
        ).isoformat()
        events = (
            await self.storage.async_list_events(
                {"start": start, "end": end}, limit=250, include_details=True
            )
        )["events"]
        sensor_updates = [item for item in events if str(item["event_type"]).startswith("ir.sensor_update")]
        full_frames = [item for item in events if str(item["event_type"]).startswith("ir.full")]
        externals = [item for item in events if item.get("is_external")]
        audible = [item for item in events if item.get("expected_audibility") == "audible_expected"]
        silent = [item for item in events if item.get("expected_audibility") == "silent_expected"]
        if audible:
            relation, confidence = "provavelmente relacionado", "high"
        elif sensor_updates:
            relation, confidence = "possível relação", "medium"
        elif externals:
            relation, confidence = "possível relação externa", "medium"
        else:
            relation, confidence = "sem evidência suficiente", "low"
        analysis = {
            "sensor_update_count": len(sensor_updates),
            "full_frame_count": len(full_frames),
            "external_change_count": len(externals),
            "audible_expected_count": len(audible),
            "silent_expected_count": len(silent),
            "relation": relation,
            "confidence": confidence,
            "related_event_ids": [item["event_id"] for item in events if item["event_id"] != beep.event_id],
        }
        await self.storage.async_update_event_details(
            beep.event_id,
            {**(beep.details_json or {}), "correlation_status": "completed", "correlation_analysis": analysis},
        )
        await self.async_log_event(
            {
                "category": "user",
                "event_type": "user.note",
                "severity": Severity.INFO,
                "retention_class": RetentionClass.ABSOLUTE,
                "summary": f"Correlação do bip concluída: {relation}.",
                "outcome": Outcome.CALCULATED,
                "source_component": "elgin_supervisor_diagnostico",
                "correlation_id": beep.correlation_id,
                "parent_correlation_id": beep.correlation_id,
                "details_json": analysis,
            },
            run_anomaly=False,
        )

    @callback
    def _handle_call_service(self, event: Event) -> None:
        domain = str(event.data.get("domain") or "")
        service = str(event.data.get("service") or "")
        if domain not in RELEVANT_SERVICE_DOMAINS:
            return
        if self._internal_service_guard:
            return
        self._spawn(
            self._async_record_service_call(event, domain, service),
            f"{__package__}.service.{domain}.{service}",
        )

    async def _async_record_service_call(
        self, event: Event, domain: str, service: str
    ) -> None:
        service_data = event.data.get("service_data") or {}
        target = service_data.get("entity_id")
        if isinstance(target, list):
            target_text = ", ".join(str(item) for item in target[:5])
        else:
            target_text = str(target or "")
        is_esphome_ir = (
            domain == "esphome"
            and service.startswith("esp8266_elgin_")
            and not service.endswith("get_last_report")
        )
        event_type = "action.requested"
        retention = RetentionClass.ABSOLUTE if is_esphome_ir else RetentionClass.FULL
        await self.async_log_event(
            {
                "category": "action",
                "event_type": event_type,
                "severity": Severity.INFO,
                "retention_class": retention,
                "summary": f"Ação {domain}.{service} solicitada{f' para {target_text}' if target_text else ''}.",
                "outcome": Outcome.REQUESTED,
                "source_component": domain,
                "source_entity_id": target_text or None,
                "action_domain": domain,
                "action_name": service,
                "expected_audibility": (
                    ExpectedAudibility.SILENT_EXPECTED
                    if service.endswith("update_sensor_temperature")
                    else ExpectedAudibility.AUDIBLE_EXPECTED
                    if is_esphome_ir and not service.endswith("import_observed_state")
                    else ExpectedAudibility.NO_TRANSMISSION
                    if service.endswith("import_observed_state")
                    else ExpectedAudibility.UNKNOWN
                ),
                "details_json": {"service_data": service_data},
            },
            context=event.context,
            run_anomaly=False,
        )

    @callback
    def _handle_agenda_event(self, event: Event) -> None:
        self._spawn(
            self.async_log_event(
                {
                    "category": "agenda",
                    "event_type": "agenda.evaluation",
                    "severity": Severity.INFO,
                    "retention_class": RetentionClass.FULL,
                    "summary": f"Agenda avaliada: {event.data.get('state', 'estado não informado')}.",
                    "outcome": Outcome.CALCULATED,
                    "source_component": "elgin_supervisor_agenda",
                    "actor_name": "Agenda do Supervisor",
                    "origin_class": "Regra temporal",
                    "details_json": dict(event.data),
                },
                context=event.context,
                run_anomaly=False,
            ),
            f"{__package__}.agenda",
        )

    async def _async_state_changed(self, event: Event) -> None:
        entity_id = str(event.data.get("entity_id") or "")
        old_state: State | None = event.data.get("old_state")
        new_state: State | None = event.data.get("new_state")
        if new_state is None or (old_state and old_state.state == new_state.state and old_state.attributes == new_state.attributes):
            return
        if entity_id in LOCALTUYA_ENTITIES:
            await self._async_localtuya_changed(event, entity_id, old_state, new_state)
            return
        if entity_id == "binary_sensor.esp8266_elgin_aux_estado_base_valido":
            event_type = "esp.state_base_valid" if new_state.state == "on" else "esp.state_base_invalid"
            severity = Severity.SUCCESS if new_state.state == "on" else Severity.WARNING
            retention = RetentionClass.ABSOLUTE
        elif entity_id == "climate.esp8266_elgin_aux_quarto" and new_state.state == "unavailable":
            event_type = "esp.disconnected"
            severity = Severity.ERROR
            retention = RetentionClass.ABSOLUTE
        elif entity_id == "climate.esp8266_elgin_aux_quarto" and old_state and old_state.state == "unavailable":
            event_type = "esp.connected"
            severity = Severity.SUCCESS
            retention = RetentionClass.ABSOLUTE
        elif new_state.state in {"unknown", "unavailable"}:
            event_type = "input.unavailable"
            severity = Severity.WARNING
            retention = RetentionClass.ERROR
        else:
            event_type = "input.state_changed"
            severity = Severity.INFO
            retention = RetentionClass.FULL
        await self.async_log_event(
            {
                "category": "input" if not event_type.startswith("esp.") else "esp",
                "event_type": event_type,
                "severity": severity,
                "retention_class": retention,
                "summary": f"{entity_id} mudou de {old_state.state if old_state else 'inexistente'} para {new_state.state}.",
                "outcome": Outcome.CALCULATED,
                "source_component": entity_id.split(".", 1)[0],
                "source_entity_id": entity_id,
                "trigger_platform": "state",
                "trigger_entity_id": entity_id,
                "from_state": old_state.state if old_state else None,
                "to_state": new_state.state,
                "before_json": old_state.as_dict() if old_state else None,
                "confirmed_json": new_state.as_dict(),
            },
            context=new_state.context,
            run_anomaly=event_type.startswith("esp."),
        )

    async def _async_localtuya_changed(
        self,
        event: Event,
        entity_id: str,
        old_state: State | None,
        new_state: State,
    ) -> None:
        now = datetime.now(timezone.utc)
        cutoff = now - timedelta(seconds=self.settings.localtuya_confirmation_seconds)
        while self._pending_confirmations and self._pending_confirmations[0].created_at < cutoff:
            expired = self._pending_confirmations.popleft()
            await self.async_log_event(
                {
                    "category": "localtuya",
                    "event_type": "localtuya.timeout",
                    "severity": Severity.WARNING,
                    "retention_class": RetentionClass.ERROR,
                    "summary": "O LocalTuya não confirmou o último frame completo dentro do prazo.",
                    "outcome": Outcome.FAILED,
                    "source_component": "localtuya",
                    "correlation_id": expired.correlation_id,
                    "transmission_id": expired.transmission_id,
                    "details_json": {"source_event_id": expired.event_id, "timeout_seconds": self.settings.localtuya_confirmation_seconds},
                },
                run_anomaly=True,
            )
        context_has_user = bool(new_state.context.user_id)
        pending = self._pending_confirmations[-1] if self._pending_confirmations else None
        is_confirmation = bool(pending and pending.created_at >= cutoff and not context_has_user)
        is_external = not is_confirmation and not context_has_user
        if is_confirmation:
            event_type = "localtuya.state_confirmed"
            outcome = Outcome.CONFIRMED
            severity = Severity.SUCCESS
            correlation_id = pending.correlation_id
            transmission_id = pending.transmission_id
            actor_name = "LocalTuya"
            origin_class = "Confirmação de estado observado"
        elif is_external:
            event_type = "localtuya.external_change"
            outcome = Outcome.EXTERNAL
            severity = Severity.WARNING
            correlation_id = None
            transmission_id = None
            actor_name = None
            origin_class = None
        else:
            event_type = "input.state_changed"
            outcome = Outcome.REQUESTED
            severity = Severity.INFO
            correlation_id = None
            transmission_id = None
            actor_name = None
            origin_class = "Interface do Home Assistant"
        await self.async_log_event(
            {
                "category": "localtuya",
                "event_type": event_type,
                "severity": severity,
                "retention_class": RetentionClass.ABSOLUTE,
                "summary": (
                    f"LocalTuya confirmou {entity_id}: {new_state.state}."
                    if is_confirmation
                    else f"Alteração externa observada em {entity_id}: {old_state.state if old_state else '—'} → {new_state.state}."
                    if is_external
                    else f"Usuário alterou {entity_id}: {new_state.state}."
                ),
                "outcome": outcome,
                "source_component": "localtuya",
                "source_entity_id": entity_id,
                "correlation_id": correlation_id,
                "transmission_id": transmission_id,
                "actor_name": actor_name,
                "origin_class": origin_class,
                "trigger_platform": "state",
                "trigger_entity_id": entity_id,
                "from_state": old_state.state if old_state else None,
                "to_state": new_state.state,
                "is_external": is_external,
                "before_json": old_state.as_dict() if old_state else None,
                "confirmed_json": new_state.as_dict(),
            },
            context=new_state.context,
            run_anomaly=is_external,
        )

    async def _async_periodic_cleanup(self, _now: datetime) -> None:
        await self.async_run_cleanup(actor="Limpeza automática")

    async def _async_periodic_anomaly_reevaluation(self, _now: datetime) -> None:
        await self.anomaly.async_reevaluate()
        await self.async_refresh_repairs()

    async def async_refresh_repairs(self) -> None:
        """Create or clear persistent Repair issues for the integration itself."""
        domain_data = self.hass.data.get(DOMAIN, {})
        checks = {
            "database_unavailable": (
                not self.storage.healthy,
                ir.IssueSeverity.ERROR,
            ),
            "frontend_not_registered": (
                bool(domain_data.get("frontend_resource_error")),
                ir.IssueSeverity.WARNING,
            ),
            "instrumentation_incomplete": (
                not self.instrumentation_complete(),
                ir.IssueSeverity.ERROR,
            ),
            "critical_fallback_used": (
                self.storage.critical_fallback_events > 0,
                ir.IssueSeverity.ERROR,
            ),
        }
        for issue_id, (active, severity) in checks.items():
            if active:
                ir.async_create_issue(
                    self.hass,
                    DOMAIN,
                    issue_id,
                    is_fixable=False,
                    is_persistent=True,
                    severity=severity,
                    translation_key=issue_id,
                )
            else:
                ir.async_delete_issue(self.hass, DOMAIN, issue_id)

    async def async_run_cleanup(self, *, actor: str = "Usuário") -> dict[str, Any]:
        result = await self.storage.async_cleanup()
        await self.async_log_event(
            {
                "category": "storage",
                "event_type": "storage.cleanup",
                "severity": Severity.SUCCESS,
                "retention_class": RetentionClass.ABSOLUTE,
                "summary": "Limpeza do banco de auditoria concluída.",
                "outcome": Outcome.CONFIRMED,
                "source_component": "elgin_supervisor_diagnostico",
                "actor_name": actor,
                "details_json": result,
            },
            run_anomaly=False,
        )
        return result

    async def async_set_intensive(self, enabled: bool, context: Context | None = None) -> None:
        if self._intensive_mode == enabled:
            return
        before = self.settings.as_dict()
        self._intensive_mode = enabled
        self.settings.intensive_mode = enabled
        await self.async_update_settings(
            {**self.settings.as_dict(), "intensive_mode": enabled}, context=context, before=before
        )

    async def async_apply_entry_options(self, values: dict[str, Any]) -> None:
        """Apply options from the config entry update listener without recursion."""
        new_settings = DiagnosticSettings.from_options(values)
        new_settings.validate()
        self.settings = new_settings
        self.storage.settings = new_settings
        self._intensive_mode = new_settings.intensive_mode
        self._notify_listeners()

    async def async_update_settings(
        self,
        values: dict[str, Any],
        *,
        context: Context | None,
        before: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        old = before or self.settings.as_dict()
        new_settings = DiagnosticSettings.from_options(values)
        new_settings.validate()
        self.hass.config_entries.async_update_entry(self.entry, options=new_settings.as_dict())
        self.settings = new_settings
        self.storage.settings = new_settings
        self._intensive_mode = new_settings.intensive_mode
        await self.async_log_event(
            {
                "category": "configuration",
                "event_type": "configuration.changed",
                "severity": Severity.INFO,
                "retention_class": RetentionClass.ABSOLUTE,
                "summary": "Configurações da auditoria foram alteradas.",
                "outcome": Outcome.CONFIRMED,
                "source_component": "elgin_supervisor_diagnostico",
                "before_json": old,
                "confirmed_json": new_settings.as_dict(),
            },
            context=context,
            run_anomaly=False,
        )
        return new_settings.as_dict()

    async def async_get_snapshot(self, *, include_recent: bool = True) -> dict[str, Any]:
        stats = await self.storage.async_stats()
        anomalies = await self.storage.async_list_anomalies(status="active", limit=50)
        return {
            "entry_id": self.entry_id,
            "name": self.entry.title,
            "status": self._status,
            "started_at": self._started_at.isoformat() if self._started_at else None,
            "settings": self.settings.as_dict(),
            "health": {
                "persistence_healthy": self.storage.healthy,
                "instrumentation_complete": self.instrumentation_complete(),
                "intensive_mode": self._intensive_mode,
            },
            "storage": stats,
            "active_anomalies": anomalies,
            "last_event": self._last_event.as_public_dict(include_details=False) if self._last_event else None,
            "last_transmission": self._last_transmission.as_public_dict(include_details=False) if self._last_transmission else None,
            "correlation": self.correlation.snapshot(),
            "climate": self._climate_snapshot(),
            "recent_events": [item.as_public_dict(include_details=False) for item in list(self._recent)[-25:]] if include_recent else [],
        }

    def instrumentation_complete(self) -> bool:
        required_entities = (
            "climate.esp8266_elgin_aux_quarto",
            "binary_sensor.esp8266_elgin_aux_estado_base_valido",
            "sensor.elgin_supervisor_configuracao_desejada",
        )
        required_services = (
            ("esphome", "esp8266_elgin_send_state"),
            ("esphome", "esp8266_elgin_update_sensor_temperature"),
        )
        return all(self.hass.states.get(entity_id) is not None for entity_id in required_entities) and all(
            self.hass.services.has_service(domain, service) for domain, service in required_services
        )

    def _climate_snapshot(self) -> dict[str, Any]:
        entity_ids = (
            "climate.esp8266_elgin_aux_quarto",
            "binary_sensor.esp8266_elgin_aux_estado_base_valido",
            "sensor.elgin_supervisor_tratamento_desejado",
            "input_select.elgin_supervisor_tratamento_ativo",
            "binary_sensor.elgin_supervisor_ifeel_efetivo",
            "binary_sensor.elgin_supervisor_eco_efetivo",
            "switch.smart_air_conditioner_power_ar_condicionado_id_1",
            "select.smart_air_conditioner_mode_ar_condicionado_id_4",
            "number.smart_air_conditioner_temperatura_alvo_ar_condicionado_id_2",
        )
        return {
            entity_id: self.hass.states.get(entity_id).as_dict()
            if self.hass.states.get(entity_id)
            else None
            for entity_id in entity_ids
        }
