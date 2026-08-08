"""Rule-based, evidence-oriented anomaly detection."""

from __future__ import annotations

import asyncio
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
import hashlib
import json
import logging
import re
from typing import TYPE_CHECKING, Any, Mapping
from uuid import uuid4

if TYPE_CHECKING:
    from .manager import DiagnosticManager

_LOGGER = logging.getLogger(__name__)

AUDIBLE_REQUEST_TYPES = frozenset(
    {
        "transmission.requested_by_ha",
        "transmission.eco_requested_by_ha",
        "transmission.display_requested_by_ha",
        "transmission.clean_requested_by_ha",
    }
)
CRITICAL_ENTITIES = frozenset(
    {
        "climate.esp8266_elgin_aux_quarto",
        "binary_sensor.esp8266_elgin_aux_estado_base_valido",
        "sensor.sensor_temperatura_sensor_dedicado",
        "sensor.sensor_umidade_sensor_dedicado",
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


def _parse_time(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def _semantic_fingerprint(event: Mapping[str, Any]) -> str:
    explicit = event.get("fingerprint")
    if explicit:
        return str(explicit)
    payload = {
        "event_type": event.get("event_type"),
        "action_domain": event.get("action_domain"),
        "action_name": event.get("action_name"),
        "source_entity_id": event.get("source_entity_id"),
        "desired_json": event.get("desired_json"),
        "mode": event.get("climate_mode"),
        "function": event.get("function"),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str)
    return hashlib.sha256(encoded.encode()).hexdigest()[:32]


class AnomalyEngine:
    """Detect all configurable anomaly families without asserting physical causality."""

    def __init__(self, manager: DiagnosticManager) -> None:
        self.manager = manager
        self._audible: deque[dict[str, Any]] = deque(maxlen=2_000)
        self._fingerprints: dict[str, deque[datetime]] = defaultdict(
            lambda: deque(maxlen=500)
        )
        self._decisions: deque[tuple[datetime, str, str | None]] = deque(maxlen=500)
        self._errors: dict[str, deque[datetime]] = defaultdict(lambda: deque(maxlen=1_000))
        self._volume: deque[datetime] = deque(maxlen=100_000)
        self._last_external: dict[str, Any] | None = None
        self._last_volume_anomaly: datetime | None = None
        self._last_audible_burst: datetime | None = None
        self._no_change_count = 0
        self._unavailable_tasks: dict[str, asyncio.Task[Any]] = {}
        self._unavailable_sources: dict[str, dict[str, Any]] = {}
        self._unavailable_alerted: set[str] = set()
        self._divergence_tasks: dict[str, asyncio.Task[Any]] = {}
        self._divergence_sources: dict[str, dict[str, Any]] = {}
        self._notification_lock = asyncio.Lock()
        self._lifecycle_started = False
        self._applied_unavailable_seconds: float | None = None
        self._applied_divergence_seconds: float | None = None
        self._replay_mode = False
        self._skip_group_keys: set[str] = set()
        self._skip_anomaly_types: set[str] = set()

    def _enabled(self, anomaly_type: str) -> bool:
        enabled = set(getattr(self.manager.settings, "anomaly_enabled_types", ()))
        return anomaly_type in enabled

    def _rules_enabled(self, anomaly_type: str) -> bool:
        return bool(getattr(self.manager.settings, "anomalies_enabled", True)) and self._enabled(
            anomaly_type
        )

    async def async_start(self) -> None:
        """Reconcile timer-based rules with states already present at startup."""

        self._lifecycle_started = True
        await self.async_apply_settings()

    async def async_stop(self) -> None:
        """Cancel every timer owned by the anomaly engine."""

        self._lifecycle_started = False
        tasks = tuple(self._unavailable_tasks.values()) + tuple(
            self._divergence_tasks.values()
        )
        for task in tasks:
            task.cancel()
        self._unavailable_tasks.clear()
        self._unavailable_sources.clear()
        self._unavailable_alerted.clear()
        self._divergence_tasks.clear()
        self._divergence_sources.clear()

    async def async_apply_settings(self) -> None:
        """Apply enable flags and timer durations without requiring a reload."""

        if not self._lifecycle_started:
            return
        unavailable_seconds = float(
            getattr(self.manager.settings, "anomaly_unavailable_seconds", 120)
        )
        divergence_seconds = float(
            getattr(self.manager.settings, "anomaly_divergence_seconds", 60)
        )
        if not self._rules_enabled("critical_entity_unavailable"):
            for task in tuple(self._unavailable_tasks.values()):
                task.cancel()
            self._unavailable_tasks.clear()
            self._unavailable_sources.clear()
            self._unavailable_alerted.clear()
        elif self._applied_unavailable_seconds not in {None, unavailable_seconds}:
            for task in tuple(self._unavailable_tasks.values()):
                task.cancel()
            self._unavailable_tasks.clear()
        if not self._rules_enabled("desired_state_divergence"):
            for task in tuple(self._divergence_tasks.values()):
                task.cancel()
            self._divergence_tasks.clear()
            self._divergence_sources.clear()
        elif self._applied_divergence_seconds not in {None, divergence_seconds}:
            sources = tuple(self._divergence_sources.values())
            for task in tuple(self._divergence_tasks.values()):
                task.cancel()
            self._divergence_tasks.clear()
            for source in sources:
                self._track_divergence(source)
        self._applied_unavailable_seconds = unavailable_seconds
        self._applied_divergence_seconds = divergence_seconds

        if self._rules_enabled("critical_entity_unavailable"):
            for entity_id in CRITICAL_ENTITIES:
                state = self.manager.hass.states.get(entity_id)
                current = state.state if state is not None else "unavailable"
                if current not in {"unknown", "unavailable"}:
                    continue
                source = self._unavailable_sources.get(entity_id)
                if source is None:
                    source = {
                        "occurred_at": datetime.now(timezone.utc).isoformat(),
                        "event_type": "state.unavailable_at_startup",
                        "source_entity_id": entity_id,
                        "after_json": {"state": current},
                        "summary": f"{entity_id} indisponível no início do diagnóstico.",
                    }
                    self._unavailable_sources[entity_id] = source
                self._ensure_unavailability_timer(entity_id, source)

    async def async_process(self, event: Mapping[str, Any]) -> list[dict[str, Any]]:
        data = dict(event)
        if not bool(getattr(self.manager.settings, "anomalies_enabled", True)):
            return []
        now = _parse_time(str(data.get("occurred_at") or ""))
        self._prune(now)
        self._volume.append(now)
        found: list[dict[str, Any]] = []

        if data.get("is_external"):
            self._last_external = data

        if data.get("event_type") in AUDIBLE_REQUEST_TYPES:
            found.extend(self._process_command(data, now))
            found.extend(self._process_external_reaction(data, now))
            self._no_change_count = 0

        if data.get("event_type") == "decision.calculated":
            found.extend(self._process_decision(data, now))
            self._no_change_count = 0

        if data.get("event_type") in {
            "evaluation.no_change",
            "evaluation.triggered_without_change",
        }:
            found.extend(self._process_no_change(data))

        if data.get("event_type") == "localtuya.divergence_or_external":
            if self._replay_mode:
                found.append(self._divergence_anomaly(data))
            else:
                self._track_divergence(data)
        elif str(data.get("event_type") or "").startswith("localtuya.confirmed") or data.get(
            "confirmation_state"
        ) == "confirmed_by_localtuya":
            self._cancel_divergence(data)

        if data.get("event_type") == "transmission.confirmation_timeout":
            found.append(
                self._build(
                    "localtuya_not_confirmed",
                    "warning",
                    "Solicitação sem confirmação LocalTuya",
                    "O Home Assistant solicitou uma action, mas a janela terminou sem confirmação observável completa.",
                    "Verifique conectividade, alcance IR e atualização dos DPs. Isso não prova falha física isoladamente.",
                    data,
                )
            )

        if data.get("severity") in {"error", "critical"}:
            found.extend(self._process_error(data, now))

        self._track_unavailability(data)
        found.extend(self._process_volume(data, now))
        return await self._persist(found, data)

    def _process_command(
        self, event: dict[str, Any], now: datetime
    ) -> list[dict[str, Any]]:
        found: list[dict[str, Any]] = []
        close_seconds = float(
            getattr(self.manager.settings, "anomaly_close_commands_seconds", 2)
        )
        if self._audible:
            previous = self._audible[-1]
            delta = (now - _parse_time(str(previous.get("occurred_at") or ""))).total_seconds()
            if 0 <= delta <= close_seconds:
                found.append(
                    self._build(
                        "commands_too_close",
                        "warning",
                        "Comandos potencialmente audíveis muito próximos",
                        f"Duas solicitações HA ocorreram com intervalo de {delta:.3f}s.",
                        "Compare função, assinatura, avaliação e usuário. Isso não confirma quantos frames foram recebidos fisicamente.",
                        event,
                        {"previous_event_id": previous.get("event_id"), "distance_seconds": delta},
                    )
                )

        fingerprint = _semantic_fingerprint(event)
        repeated_window = float(
            getattr(self.manager.settings, "anomaly_repeated_command_window_seconds", 300)
        )
        duplicate_window = float(
            getattr(self.manager.settings, "anomaly_duplicate_window_seconds", 10)
        )
        history = self._fingerprints[fingerprint]
        cutoff = now - timedelta(seconds=repeated_window)
        while history and history[0] < cutoff:
            history.popleft()
        if history:
            distance = (now - history[-1]).total_seconds()
            exact_duplicate = 0 <= distance <= duplicate_window
            found.append(
                self._build(
                    "repeated_commands",
                    "error" if exact_duplicate else "warning",
                    "Comando potencialmente audível duplicado"
                    if exact_duplicate
                    else "Comando potencialmente audível repetido",
                    "A mesma action e configuração desejada reapareceram dentro da janela curta de duplicata."
                    if exact_duplicate
                    else "A mesma action e configuração desejada reapareceram dentro da janela configurada.",
                    "Abra os eventos relacionados para identificar reavaliação, Eco, usuário ou automação repetitiva.",
                    event,
                    {
                        "previous_count": len(history),
                        "window_seconds": duplicate_window
                        if exact_duplicate
                        else repeated_window,
                        "distance_seconds": distance,
                        "variant": "exact_duplicate"
                        if exact_duplicate
                        else "repeated_command",
                    },
                )
            )
        history.append(now)
        self._audible.append(event)
        burst_window = float(
            getattr(self.manager.settings, "anomaly_audible_burst_seconds", 20)
        )
        burst_count = int(
            getattr(self.manager.settings, "anomaly_audible_burst_count", 3)
        )
        burst_cutoff = now - timedelta(seconds=burst_window)
        recent = [
            item
            for item in self._audible
            if _parse_time(str(item.get("occurred_at") or "")) >= burst_cutoff
        ]
        if len(recent) >= burst_count and (
            self._last_audible_burst is None
            or self._last_audible_burst < burst_cutoff
        ):
            self._last_audible_burst = now
            found.append(
                self._build(
                    "commands_too_close",
                    "error",
                    "Rajada de comandos potencialmente audíveis",
                    f"Foram observadas pelo menos {burst_count} solicitações audíveis em {burst_window:g}s.",
                    "Compare os transmission_id e as funções antes de concluir que todos os bips vieram do mesmo fluxo.",
                    event,
                    {
                        "variant": "audible_burst",
                        "count": len(recent),
                        "window_seconds": burst_window,
                        "related_event_ids": [
                            item.get("event_id") for item in recent if item.get("event_id")
                        ],
                    },
                )
            )
        return found

    def _process_no_change(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        """Detect a sustained sequence of evaluations that produce no action."""

        self._no_change_count += 1
        threshold = int(
            getattr(self.manager.settings, "anomaly_no_change_threshold", 100)
        )
        if self._no_change_count < threshold:
            return []
        count = self._no_change_count
        self._no_change_count = 0
        return [
            self._build(
                "excessive_volume",
                "warning",
                "Muitas avaliações consecutivas sem mudança",
                f"O Supervisor registrou {count} avaliações consecutivas sem ação necessária.",
                "Revise o produtor das avaliações e a compactação; isso pode ser normal em sensores ruidosos, mas não deve esconder um loop.",
                event,
                {"variant": "no_change_sequence", "count": count},
            )
        ]

    def _process_decision(
        self, event: dict[str, Any], now: datetime
    ) -> list[dict[str, Any]]:
        key = "|".join(
            str(event.get(name) or "")
            for name in ("treatment", "climate_mode", "power_profile", "preset")
        )
        if not key.strip("|"):
            return []
        if not self._decisions or self._decisions[-1][1] != key:
            self._decisions.append((now, key, event.get("event_id")))
        window = int(getattr(self.manager.settings, "anomaly_oscillation_window_seconds", 600))
        cutoff = now - timedelta(seconds=window)
        while self._decisions and self._decisions[0][0] < cutoff:
            self._decisions.popleft()
        minimum = int(getattr(self.manager.settings, "anomaly_oscillation_min_changes", 4))
        if len(self._decisions) < minimum or len({item[1] for item in self._decisions}) < 2:
            return []
        related = [item[2] for item in self._decisions if item[2]]
        self._decisions.clear()
        return [
            self._build(
                "decision_oscillation",
                "warning",
                "Decisão do Supervisor oscilando",
                f"O estado calculado mudou pelo menos {minimum} vezes em {window}s.",
                "Revise limites, prioridades, preset, potência e sensores próximos às histereses.",
                event,
                {"related_decision_event_ids": related},
            )
        ]

    def _process_external_reaction(
        self, event: dict[str, Any], now: datetime
    ) -> list[dict[str, Any]]:
        if not self._last_external:
            return []
        distance = (
            now - _parse_time(str(self._last_external.get("occurred_at") or ""))
        ).total_seconds()
        window = float(
            getattr(self.manager.settings, "external_observation_window_seconds", 60)
        )
        if not 0 <= distance <= window:
            return []
        return [
            self._build(
                "external_change_reaction",
                "warning",
                "Mudança externa seguida por reação do Supervisor",
                f"Uma solicitação HA ocorreu {distance:.3f}s após mudança externa ou indeterminada.",
                "Verifique se a política de respeito ao controle manual e a pausa estavam corretas. Proximidade temporal não prova causalidade.",
                event,
                {"external_event_id": self._last_external.get("event_id"), "distance_seconds": distance},
            )
        ]

    def _process_error(
        self, event: dict[str, Any], now: datetime
    ) -> list[dict[str, Any]]:
        key = str(event.get("event_type") or event.get("summary") or "error")
        history = self._errors[key]
        window = int(
            getattr(self.manager.settings, "anomaly_repeated_error_window_seconds", 300)
        )
        cutoff = now - timedelta(seconds=window)
        while history and history[0] < cutoff:
            history.popleft()
        history.append(now)
        threshold = int(getattr(self.manager.settings, "anomaly_repeated_error_count", 3))
        if len(history) < threshold:
            return []
        history.clear()
        return [
            self._build(
                "repeated_error",
                "error",
                "Erro repetitivo no fluxo climático",
                f"O mesmo tipo de erro apareceu pelo menos {threshold} vezes em {window}s.",
                "Abra a correlação e verifique a primeira falha antes das repetições.",
                event,
            )
        ]

    def _process_volume(
        self, event: dict[str, Any], now: datetime
    ) -> list[dict[str, Any]]:
        window = int(getattr(self.manager.settings, "anomaly_volume_window_seconds", 60))
        cutoff = now - timedelta(seconds=window)
        while self._volume and self._volume[0] < cutoff:
            self._volume.popleft()
        limit = int(getattr(self.manager.settings, "anomaly_volume_event_limit", 1_000))
        if len(self._volume) < limit:
            return []
        if self._last_volume_anomaly and self._last_volume_anomaly >= cutoff:
            return []
        self._last_volume_anomaly = now
        return [
            self._build(
                "excessive_volume",
                "error",
                "Volume excessivo de eventos",
                f"Foram processados pelo menos {limit} eventos de diagnóstico em {window}s.",
                "Use estatísticas e Top produtores; reduza captura somente depois de identificar a origem.",
                event,
                {"count": len(self._volume), "window_seconds": window},
            )
        ]

    def _track_unavailability(self, event: dict[str, Any]) -> None:
        if self._replay_mode:
            return
        entity_id = str(event.get("source_entity_id") or event.get("entity_id") or "")
        if entity_id not in CRITICAL_ENTITIES:
            return
        after = event.get("after_json") or event.get("after")
        current = after.get("state") if isinstance(after, Mapping) else None
        if after is None and str(event.get("event_type") or "").endswith(".removed"):
            current = "unavailable"
        if current not in {"unknown", "unavailable"}:
            existing = self._unavailable_tasks.pop(entity_id, None)
            if existing:
                existing.cancel()
            self._unavailable_sources.pop(entity_id, None)
            self._unavailable_alerted.discard(entity_id)
            return
        self._unavailable_sources[entity_id] = dict(event)
        self._ensure_unavailability_timer(entity_id, event)

    def _ensure_unavailability_timer(
        self, entity_id: str, source_event: Mapping[str, Any]
    ) -> None:
        if not self._rules_enabled("critical_entity_unavailable"):
            return
        if entity_id in self._unavailable_alerted:
            return
        existing = self._unavailable_tasks.get(entity_id)
        if existing is not None and not existing.done():
            return
        task = self.manager._spawn(
            self._async_unavailable_timeout(entity_id, dict(source_event)),
            f"elgin_supervisor_diagnostico.unavailable.{entity_id}",
        )
        self._unavailable_tasks[entity_id] = task

    async def _async_unavailable_timeout(
        self, entity_id: str, source_event: dict[str, Any]
    ) -> None:
        try:
            await asyncio.sleep(
                float(getattr(self.manager.settings, "anomaly_unavailable_seconds", 120))
            )
            if not self._rules_enabled("critical_entity_unavailable"):
                return
            current = self.manager.hass.states.get(entity_id)
            if current is not None and current.state not in {"unknown", "unavailable"}:
                return
            anomaly = self._build(
                "critical_entity_unavailable",
                "error",
                "Entidade crítica indisponível",
                f"{entity_id} permaneceu unavailable/unknown além da janela configurada.",
                "Restaure a entidade e confira os bloqueios do Supervisor antes de liberar ações.",
                source_event,
                {"entity_id": entity_id},
            )
            await self._persist([anomaly], source_event)
            self._unavailable_alerted.add(entity_id)
        finally:
            current_task = asyncio.current_task()
            if self._unavailable_tasks.get(entity_id) is current_task:
                self._unavailable_tasks.pop(entity_id, None)

    @staticmethod
    def _divergence_key(event: Mapping[str, Any]) -> str:
        return str(
            event.get("source_entity_id")
            or event.get("entity_id")
            or event.get("transmission_id")
            or event.get("correlation_id")
            or "global"
        )

    def _track_divergence(self, event: Mapping[str, Any]) -> None:
        if self._replay_mode or not self._rules_enabled("desired_state_divergence"):
            return
        key = self._divergence_key(event)
        self._divergence_sources[key] = dict(event)
        existing = self._divergence_tasks.get(key)
        if existing is not None and not existing.done():
            return
        self._divergence_tasks[key] = self.manager._spawn(
            self._async_divergence_timeout(key),
            f"elgin_supervisor_diagnostico.divergence.{key}",
        )

    def _cancel_divergence(self, event: Mapping[str, Any]) -> None:
        key = self._divergence_key(event)
        task = self._divergence_tasks.pop(key, None)
        if task:
            task.cancel()
        self._divergence_sources.pop(key, None)

    async def _async_divergence_timeout(self, key: str) -> None:
        try:
            await asyncio.sleep(
                float(getattr(self.manager.settings, "anomaly_divergence_seconds", 60))
            )
            if not self._rules_enabled("desired_state_divergence"):
                return
            source = self._divergence_sources.get(key)
            if source is None:
                return
            await self._persist([self._divergence_anomaly(source)], source)
        finally:
            current_task = asyncio.current_task()
            if self._divergence_tasks.get(key) is current_task:
                self._divergence_tasks.pop(key, None)
                self._divergence_sources.pop(key, None)

    def _divergence_anomaly(self, event: Mapping[str, Any]) -> dict[str, Any]:
        return self._build(
            "desired_state_divergence",
            "warning",
            "Estado observado permaneceu divergente do solicitado",
            "O LocalTuya publicou um valor diferente do esperado e não houve confirmação de recuperação durante a janela configurada.",
            "Abra a correlação para distinguir atraso, comando externo ou divergência real; a relação temporal não prova a causa.",
            event,
            {"variant": "persistent_divergence"},
        )

    async def _persist(
        self,
        anomalies: list[dict[str, Any]],
        source_event: Mapping[str, Any],
    ) -> list[dict[str, Any]]:
        persisted: list[dict[str, Any]] = []
        for anomaly in anomalies:
            if not self._rules_enabled(str(anomaly["anomaly_type"])):
                continue
            group_key = str((anomaly.get("details") or {}).get("group_key") or "")
            if self._replay_mode and (
                group_key in self._skip_group_keys
                or str(anomaly["anomaly_type"]) in self._skip_anomaly_types
            ):
                continue
            try:
                saved = await self.manager.storage.async_upsert_anomaly(anomaly)
                persisted.append(saved)
                await self.manager.async_emit_anomaly(saved, source_event=source_event)
                await self._async_notify(saved)
            except Exception:  # Diagnostic failure must remain isolated.
                _LOGGER.exception("Falha ao persistir anomalia")
        return persisted

    def _build(
        self,
        anomaly_type: str,
        severity: str,
        title: str,
        explanation: str,
        recommendation: str,
        event: Mapping[str, Any],
        details: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        seen_at = _parse_time(str(event.get("occurred_at") or "")).isoformat()
        detail_values = dict(details or {})
        group_basis = {
            "type": anomaly_type,
            "entity": detail_values.get("entity_id")
            or event.get("source_entity_id")
            or event.get("entity_id"),
            "function": event.get("function"),
            "action": event.get("action_name"),
            "mode": event.get("climate_mode"),
            "treatment": event.get("treatment"),
            "error_type": event.get("event_type")
            if anomaly_type == "repeated_error"
            else None,
            "command": _semantic_fingerprint(event)
            if anomaly_type == "repeated_commands"
            else None,
            "variant": detail_values.get("variant"),
        }
        group_key = (
            f"{anomaly_type}:"
            + hashlib.sha256(
                json.dumps(group_basis, sort_keys=True, default=str).encode()
            ).hexdigest()[:20]
        )
        return {
            "anomaly_id": str(uuid4()),
            "anomaly_type": anomaly_type,
            "severity": severity,
            "title": title,
            "explanation": explanation,
            "recommendation": recommendation,
            "first_seen": seen_at,
            "last_seen": seen_at,
            "count": 1,
            "status": "active",
            "related_event_ids": [event.get("event_id")] if event.get("event_id") else [],
            "details": {
                "evaluation_id": event.get("evaluation_id"),
                "correlation_id": event.get("correlation_id"),
                "group_key": group_key,
                **detail_values,
            },
        }

    async def _async_notify(self, anomaly: Mapping[str, Any]) -> None:
        if self._replay_mode:
            return
        if not bool(getattr(self.manager.settings, "notifications_enabled", False)):
            return
        anomaly_type = str(anomaly.get("anomaly_type") or "")
        if anomaly_type not in set(getattr(self.manager.settings, "notification_types", ())):
            return
        minimum = str(getattr(self.manager.settings, "notification_min_severity", "warning"))
        order = {"debug": 0, "info": 1, "success": 1, "warning": 2, "error": 3, "critical": 4}
        if order.get(str(anomaly.get("severity")), 0) < order.get(minimum, 2):
            return
        anomaly_id = str(anomaly.get("anomaly_id") or "")
        if not anomaly_id:
            return
        async with self._notification_lock:
            current = await self.manager.storage.async_get_anomaly(anomaly_id)
            if current is None:
                return
            now = datetime.now(timezone.utc)
            cooldown = int(
                getattr(self.manager.settings, "notification_cooldown_seconds", 900)
            )
            notified_at = current.get("notified_at")
            if notified_at:
                try:
                    previous = _parse_time(str(notified_at))
                except (TypeError, ValueError):
                    previous = None
                if previous and (now - previous).total_seconds() < cooldown:
                    return

            persistent = bool(
                getattr(self.manager.settings, "notification_persistent", True)
            )
            custom = str(
                getattr(self.manager.settings, "notification_service", "") or ""
            ).strip()
            if custom and not re.fullmatch(r"notify\.[a-z0-9_]+", custom):
                _LOGGER.error(
                    "Serviço notify rejeitado por formato/domínio inválido: %s", custom
                )
                return
            if not persistent and not custom:
                return

            message = (
                f"{current.get('explanation', '')}\n\n"
                f"{current.get('recommendation', '')}"
            )
            try:
                if persistent:
                    await self.manager.hass.services.async_call(
                        "persistent_notification",
                        "create",
                        {
                            "notification_id": (
                                "elgin_supervisor_diagnostico_"
                                + hashlib.sha256(
                                    str(
                                        (current.get("details") or {}).get(
                                            "group_key", anomaly_type
                                        )
                                    ).encode()
                                ).hexdigest()[:20]
                            ),
                            "title": current.get("title")
                            or "Anomalia do Supervisor",
                            "message": message,
                        },
                        blocking=True,
                    )
                if custom:
                    _domain, service = custom.split(".", 1)
                    await self.manager.hass.services.async_call(
                        "notify",
                        service,
                        {
                            "title": current.get("title")
                            or "Anomalia do Supervisor",
                            "message": message,
                        },
                        blocking=True,
                    )
            except Exception:
                _LOGGER.exception(
                    "Falha ao enviar notificação; cooldown não foi avançado"
                )
                return
            await self.manager.storage.async_mark_anomaly_notified(
                anomaly_id, now.isoformat()
            )

    def _prune(self, now: datetime) -> None:
        longest = max(
            int(getattr(self.manager.settings, "anomaly_repeated_command_window_seconds", 300)),
            int(getattr(self.manager.settings, "anomaly_oscillation_window_seconds", 600)),
            int(getattr(self.manager.settings, "anomaly_volume_window_seconds", 60)),
            int(getattr(self.manager.settings, "anomaly_repeated_error_window_seconds", 300)),
            int(getattr(self.manager.settings, "anomaly_duplicate_window_seconds", 10)),
            int(getattr(self.manager.settings, "anomaly_audible_burst_seconds", 20)),
        )
        cutoff = now - timedelta(seconds=longest)
        while self._audible and _parse_time(str(self._audible[0].get("occurred_at") or "")) < cutoff:
            self._audible.popleft()

    async def async_reevaluate(self) -> dict[str, Any]:
        since = (
            datetime.now(timezone.utc)
            - timedelta(minutes=int(getattr(self.manager.settings, "anomaly_window_minutes", 15)))
        ).isoformat()
        maximum = min(
            50_000,
            int(getattr(self.manager.settings, "maintenance_export_max_rows", 50_000)),
        )
        events: list[dict[str, Any]] = []
        cursor: str | None = None
        while len(events) < maximum:
            page = await self.manager.storage.async_list_events(
                {"period": {"start": since}},
                cursor=cursor,
                limit=min(250, maximum - len(events)),
                direction="older",
                include_details=True,
            )
            items = list(page.get("items") or [])
            events.extend(items)
            cursor = page.get("next_cursor")
            if not items or not page.get("has_more") or not cursor:
                break

        existing = await self.manager.storage.async_list_anomalies("all", 500)
        replay = AnomalyEngine(self.manager)
        replay._replay_mode = True
        replay._skip_group_keys = {
            str((item.get("details") or {}).get("group_key"))
            for item in existing
            if (item.get("details") or {}).get("group_key")
        }
        replay._skip_anomaly_types = {
            str(item.get("anomaly_type"))
            for item in existing
            if item.get("anomaly_type")
            and not (item.get("details") or {}).get("group_key")
        }
        persisted_ids: set[str] = set()
        matches = 0
        for event in reversed(events):
            if str(event.get("event_type") or "").startswith("anomaly."):
                continue
            saved = await replay.async_process(event)
            matches += len(saved)
            persisted_ids.update(
                str(item["anomaly_id"])
                for item in saved
                if item.get("anomaly_id")
            )
        return {
            "since": since,
            "scanned_events": len(events),
            "matched_occurrences": matches,
            "new_anomaly_groups": len(persisted_ids),
            "truncated": len(events) >= maximum,
        }
