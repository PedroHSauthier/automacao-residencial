"""Rule-based anomaly detection for Elgin Supervisor diagnostics."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta, timezone
import logging
from typing import TYPE_CHECKING, Any

from homeassistant.components import persistent_notification

from .const import SEVERITY_ORDER, TRANSMISSION_EVENT_TYPES
from .models import AnomalyRecord, AuditEvent, Severity

if TYPE_CHECKING:
    from .manager import DiagnosticManager

_LOGGER = logging.getLogger(__name__)


class AnomalyEngine:
    """Detect local, explainable anomalies without blocking event production."""

    def __init__(self, manager: DiagnosticManager) -> None:
        self.manager = manager
        self._transmissions: deque[AuditEvent] = deque(maxlen=500)
        self._full_frames: deque[AuditEvent] = deque(maxlen=200)
        self._sensor_updates: deque[AuditEvent] = deque(maxlen=200)
        self._external_changes: deque[AuditEvent] = deque(maxlen=200)
        self._decisions: deque[AuditEvent] = deque(maxlen=300)
        self._last_notifications: dict[str, datetime] = {}

    async def async_process(self, event: AuditEvent) -> list[AnomalyRecord]:
        anomalies: list[AnomalyRecord] = []
        is_software_transmission = (
            event.event_type in TRANSMISSION_EVENT_TYPES
            and event.outcome == "transmitted_by_software"
        ) or event.event_type in {
            "ir.full.transmitter_called",
            "ir.sensor_update.transmitter_called",
            "ir.display",
            "ir.clean",
        }
        if is_software_transmission:
            anomalies.extend(self._process_transmission(event))
        if event.event_type == "localtuya.external_change":
            self._external_changes.append(event)
        if event.event_type in {
            "cycle.decision",
            "preset.calculated",
            "power.calculated",
            "priority.calculated",
        }:
            anomaly = self._process_decision(event)
            if anomaly:
                anomalies.append(anomaly)
        if event.event_type == "user.beep_observed":
            anomaly = self._process_beep(event)
            if anomaly:
                anomalies.append(anomaly)
        if event.event_type in {"esp.disconnected", "esp.state_base_invalid", "esp.self_test_failed"}:
            anomalies.append(
                self._build(
                    event,
                    f"system.{event.event_type}",
                    Severity.ERROR,
                    "O ESP ou seu estado-base ficou indisponível para comandos confiáveis.",
                    "Verifique conectividade, reinicialização, autoteste e envie um estado completo antes do SensorUpdate.",
                )
            )
        if event.event_type in {"localtuya.timeout", "localtuya.divergence"}:
            anomalies.append(
                self._build(
                    event,
                    "localtuya.confirmation_failed",
                    Severity.WARNING,
                    "Um frame completo aceito pelo ESP não foi confirmado pelo LocalTuya no prazo configurado.",
                    "Compare estado desejado, estado observado e disponibilidade do LocalTuya; isso não prova falha física do IR.",
                )
            )
        if event.event_type in {"storage.queue_overflow", "storage.failure"}:
            anomalies.append(
                self._build(
                    event,
                    "system.persistence",
                    Severity.CRITICAL if event.severity == "critical" else Severity.ERROR,
                    "A persistência da auditoria perdeu capacidade ou ficou indisponível.",
                    "Revise espaço em disco, permissões e saúde do SQLite. O controle climático continua independente.",
                )
            )
        for anomaly in anomalies:
            stored = await self.manager.storage.async_upsert_anomaly(anomaly)
            await self.manager.async_emit_anomaly_event(stored, source_event=event)
            await self._async_notify(stored)
        return anomalies

    def _process_transmission(self, event: AuditEvent) -> list[AnomalyRecord]:
        now = datetime.fromisoformat(event.occurred_at).astimezone(timezone.utc)
        settings = self.manager.settings
        anomalies: list[AnomalyRecord] = []
        self._prune(now)
        previous = self._transmissions[-1] if self._transmissions else None
        if previous:
            previous_time = datetime.fromisoformat(previous.occurred_at).astimezone(timezone.utc)
            delta = (now - previous_time).total_seconds()
            if 0 <= delta < settings.close_transmissions_seconds:
                anomalies.append(
                    self._build(
                        event,
                        "ir.transmissions_too_close",
                        Severity.WARNING,
                        f"Dois comandos IR foram acionados pelo software com intervalo de {delta:.2f} s.",
                        "Abra a correlação dos dois eventos e confirme se partiram de emissores lógicos diferentes.",
                        related=[previous.event_id, event.event_id],
                        details={"interval_seconds": delta},
                    )
                )
            previous_caller = self._logical_emitter(previous)
            current_caller = self._logical_emitter(event)
            if (
                previous_caller != current_caller
                and 0 <= delta < settings.logical_concurrency_seconds
            ):
                anomalies.append(
                    self._build(
                        event,
                        "ir.logical_emitter_concurrency",
                        Severity.WARNING,
                        f"Dois emissores lógicos diferentes transmitiram em sequência: {previous_caller} e {current_caller}.",
                        "Revise Supervisor, Climate, funções avançadas, I Feel, visor, Clean e chamadas diretas ao serviço ESPHome.",
                        related=[previous.event_id, event.event_id],
                        details={
                            "interval_seconds": delta,
                            "previous_emitter": previous_caller,
                            "current_emitter": current_caller,
                        },
                    )
                )
            if (
                event.frame_hash
                and previous.frame_hash == event.frame_hash
                and 0 <= delta < settings.identical_frame_window_seconds
                and not (event.details_json or {}).get("forced", False)
            ):
                anomalies.append(
                    self._build(
                        event,
                        "ir.identical_frame_retransmitted",
                        Severity.WARNING,
                        "O mesmo frame foi retransmitido sem marcação explícita de envio forçado.",
                        "Verifique supressão de IR idêntico, concorrência entre Climate/Supervisor e chamadas diretas ao ESPHome.",
                        related=[previous.event_id, event.event_id],
                        details={"frame_hash": event.frame_hash, "interval_seconds": delta},
                    )
                )
        if not event.correlation_id or (event.details_json or {}).get("partial_correlation"):
            anomalies.append(
                self._build(
                    event,
                    "ir.command_without_correlation",
                    Severity.WARNING,
                    "Uma transmissão foi observada sem correlação completa com o fluxo que a originou.",
                    "Use begin_trace e propague correlation_id/transmission_id até a ação ESPHome.",
                )
            )
        external_cutoff = now - timedelta(seconds=settings.external_reaction_window_seconds)
        recent_external = [
            item
            for item in self._external_changes
            if datetime.fromisoformat(item.occurred_at).astimezone(timezone.utc) >= external_cutoff
        ]
        if recent_external:
            anomalies.append(
                self._build(
                    event,
                    "localtuya.external_change_followed_by_supervisor",
                    Severity.WARNING,
                    "Uma alteração externa foi seguida por reação IR do sistema dentro da janela curta configurada.",
                    "Verifique importação passiva, reforço de I Feel, pausa manual e eventual frame completo corretivo.",
                    related=[*[item.event_id for item in recent_external], event.event_id],
                    details={
                        "window_seconds": settings.external_reaction_window_seconds,
                        "external_count": len(recent_external),
                        "transmission_kind": event.frame_kind,
                    },
                )
            )
        self._transmissions.append(event)
        if event.frame_kind == "full_state" or event.event_type.startswith("ir.full"):
            self._full_frames.append(event)
            cutoff = now - timedelta(seconds=settings.multiple_full_frames_window_seconds)
            recent = [
                item
                for item in self._full_frames
                if datetime.fromisoformat(item.occurred_at).astimezone(timezone.utc) >= cutoff
            ]
            if len(recent) >= settings.multiple_full_frames_limit:
                anomalies.append(
                    self._build(
                        event,
                        "ir.multiple_full_frames",
                        Severity.WARNING,
                        f"Foram observados {len(recent)} frames completos dentro da janela configurada.",
                        "Agrupe por correlation_id e origem para confirmar se houve repetição necessária ou concorrência.",
                        related=[item.event_id for item in recent],
                        details={
                            "count": len(recent),
                            "window_seconds": settings.multiple_full_frames_window_seconds,
                        },
                    )
                )
        if event.frame_kind == "sensor_update" or event.event_type.startswith("ir.sensor_update"):
            self._sensor_updates.append(event)
        return anomalies

    @staticmethod
    def _logical_emitter(event: AuditEvent) -> str:
        details = event.details_json if isinstance(event.details_json, dict) else {}
        response = details.get("esp_response") if isinstance(details.get("esp_response"), dict) else {}
        return str(
            response.get("caller")
            or details.get("caller")
            or event.source_script_id
            or event.source_entity_id
            or event.actor_name
            or event.source_component
            or "desconhecido"
        )

    def _process_decision(self, event: AuditEvent) -> AnomalyRecord | None:
        """Detect an A/B/A/B decision oscillation in a bounded time window."""
        now = datetime.fromisoformat(event.occurred_at).astimezone(timezone.utc)
        cutoff = now - timedelta(seconds=self.manager.settings.oscillation_window_seconds)
        while self._decisions and datetime.fromisoformat(self._decisions[0].occurred_at).astimezone(timezone.utc) < cutoff:
            self._decisions.popleft()
        self._decisions.append(event)
        relevant = [item for item in self._decisions if item.event_type == event.event_type]
        count = self.manager.settings.oscillation_min_changes
        if len(relevant) < count:
            return None
        tail = relevant[-count:]
        values = [
            item.to_state
            or item.treatment
            or item.climate_mode
            or str((item.details_json or {}).get("value") or (item.details_json or {}).get("effective") or "")
            for item in tail
        ]
        if len(set(values)) == 2 and all(values[index] != values[index - 1] for index in range(1, len(values))):
            return self._build(
                event,
                "decision.oscillation",
                Severity.WARNING,
                f"A decisão {event.event_type} alternou repetidamente entre {values[-2]} e {values[-1]}.",
                "Revise histerese, prioridades, presets, potência e fontes que mudam próximas ao limiar.",
                related=[item.event_id for item in tail],
                details={
                    "values": values,
                    "window_seconds": self.manager.settings.oscillation_window_seconds,
                },
            )
        return None

    def _process_beep(self, beep: AuditEvent) -> AnomalyRecord | None:
        when = datetime.fromisoformat(beep.occurred_at).astimezone(timezone.utc)
        before = timedelta(seconds=self.manager.settings.beep_window_before_seconds)
        after = timedelta(seconds=self.manager.settings.beep_window_after_seconds)
        audible = [
            item
            for item in self._transmissions
            if when - before <= datetime.fromisoformat(item.occurred_at).astimezone(timezone.utc) <= when + after
            and item.expected_audibility == "audible_expected"
        ]
        sensor_updates = [
            item
            for item in self._sensor_updates
            if when - before <= datetime.fromisoformat(item.occurred_at).astimezone(timezone.utc) <= when + after
        ]
        if sensor_updates and not audible:
            return self._build(
                beep,
                "ir.sensor_update_possibly_audible",
                Severity.WARNING,
                "Um bip observado ficou próximo de SensorUpdate e não houve outro comando audível mais provável na janela.",
                "Isso é correlação temporal, não causalidade. Compare os frames, quantidades e transmission_id antes de alterar o SensorUpdate.",
                related=[beep.event_id, *[item.event_id for item in sensor_updates]],
                details={
                    "sensor_update_count": len(sensor_updates),
                    "audible_command_count": len(audible),
                    "confidence": "medium" if len(sensor_updates) == 1 else "high",
                },
            )
        return None

    def _build(
        self,
        event: AuditEvent,
        anomaly_type: str,
        severity: Severity,
        explanation: str,
        recommendation: str,
        *,
        related: list[str] | None = None,
        details: dict[str, Any] | None = None,
    ) -> AnomalyRecord:
        return AnomalyRecord(
            anomaly_type=anomaly_type,
            severity=severity,
            first_seen=event.occurred_at,
            last_seen=event.occurred_at,
            related_event_ids=related or [event.event_id],
            explanation=explanation,
            recommendation=recommendation,
            details=details or {},
        )

    async def _async_notify(self, anomaly: AnomalyRecord) -> None:
        settings = self.manager.settings
        if not settings.notifications_enabled:
            return
        enabled = settings.enabled_anomaly_types
        if enabled and anomaly.anomaly_type not in enabled:
            return
        if SEVERITY_ORDER.get(anomaly.severity, 0) < SEVERITY_ORDER.get(settings.notification_min_severity, 3):
            return
        now = datetime.now(timezone.utc)
        previous = self._last_notifications.get(anomaly.anomaly_type)
        if previous and (now - previous).total_seconds() < settings.notification_cooldown_seconds:
            return
        self._last_notifications[anomaly.anomaly_type] = now
        notification_id = f"elgin_supervisor_diagnostico_{anomaly.anomaly_type.replace('.', '_')}"
        message = (
            f"{anomaly.explanation}\n\n"
            f"Ocorrências: {anomaly.count}.\n"
            f"Recomendação: {anomaly.recommendation}\n\n"
            "Abra a view **Auditoria e Logs** do dashboard do Supervisor."
        )
        persistent_notification.async_create(
            self.manager.hass,
            message,
            title=f"Elgin Supervisor — {anomaly.anomaly_type}",
            notification_id=notification_id,
        )
        if settings.notify_service and "." in settings.notify_service:
            domain, service = settings.notify_service.split(".", 1)
            try:
                await self.manager.hass.services.async_call(
                    domain,
                    service,
                    {"title": "Elgin Supervisor", "message": message},
                    blocking=False,
                )
            except Exception:  # noqa: BLE001
                _LOGGER.exception("Falha ao enviar notificação opcional")

    def _prune(self, now: datetime) -> None:
        cutoff = now - timedelta(hours=1)
        for queue in (
            self._transmissions,
            self._full_frames,
            self._sensor_updates,
            self._external_changes,
            self._decisions,
        ):
            while queue and datetime.fromisoformat(queue[0].occurred_at).astimezone(timezone.utc) < cutoff:
                queue.popleft()

    async def async_reevaluate(self) -> dict[str, Any]:
        """Return current in-memory detector state; historical rules remain event-driven."""
        now = datetime.now(timezone.utc)
        self._prune(now)
        return {
            "transmissions_last_hour": len(self._transmissions),
            "full_frames_last_hour": len(self._full_frames),
            "sensor_updates_last_hour": len(self._sensor_updates),
            "external_changes_last_hour": len(self._external_changes),
            "decisions_last_hour": len(self._decisions),
        }
