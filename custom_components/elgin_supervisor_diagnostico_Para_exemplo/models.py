"""Typed models for Elgin Supervisor diagnostics."""

from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field, fields
from datetime import datetime, timezone
from enum import StrEnum
import json
from typing import Any, Self
from uuid import uuid4

from homeassistant.util import dt as dt_util

from .const import DEFAULT_OPTIONS, MAX_JSON_DEPTH, MAX_PAYLOAD_BYTES, MAX_TEXT_LENGTH


class Severity(StrEnum):
    DEBUG = "debug"
    INFO = "info"
    SUCCESS = "success"
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"


class Outcome(StrEnum):
    STARTED = "started"
    CALCULATED = "calculated"
    UNCHANGED = "unchanged"
    REQUESTED = "requested"
    ACCEPTED = "accepted"
    TRANSMITTED_BY_SOFTWARE = "transmitted_by_software"
    CONFIRMED = "confirmed"
    SUPPRESSED = "suppressed"
    BLOCKED = "blocked"
    REJECTED = "rejected"
    FAILED = "failed"
    EXTERNAL = "external"
    UNKNOWN = "unknown"


class RetentionClass(StrEnum):
    ABSOLUTE = "absolute"
    ERROR = "error"
    FULL = "full"


class ExpectedAudibility(StrEnum):
    AUDIBLE_EXPECTED = "audible_expected"
    SILENT_EXPECTED = "silent_expected"
    NO_TRANSMISSION = "no_transmission"
    UNKNOWN = "unknown"


class OriginConfidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


def _truncate_text(value: Any, limit: int = MAX_TEXT_LENGTH) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _sanitize_json(value: Any, *, depth: int = 0) -> Any:
    """Convert arbitrary HA data into bounded JSON-safe immutable values."""
    if depth >= MAX_JSON_DEPTH:
        return "<profundidade limitada>"
    if value is None or isinstance(value, (bool, int, float, str)):
        return _truncate_text(value) if isinstance(value, str) else value
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, dict):
        return {
            _truncate_text(key, 160) or "": _sanitize_json(item, depth=depth + 1)
            for key, item in list(value.items())[:250]
        }
    if isinstance(value, (list, tuple, set)):
        return [_sanitize_json(item, depth=depth + 1) for item in list(value)[:250]]
    if hasattr(value, "as_dict"):
        try:
            return _sanitize_json(value.as_dict(), depth=depth + 1)
        except Exception:  # noqa: BLE001
            pass
    return _truncate_text(value)


def bounded_json(value: Any) -> dict[str, Any] | list[Any] | None:
    if value in (None, ""):
        return None
    sanitized = _sanitize_json(deepcopy(value))
    raw = json.dumps(sanitized, ensure_ascii=False, separators=(",", ":"))
    if len(raw.encode("utf-8")) <= MAX_PAYLOAD_BYTES:
        return sanitized
    return {
        "truncated": True,
        "reason": "payload_exceeded_limit",
        "preview": raw[: MAX_PAYLOAD_BYTES // 2],
    }


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def local_iso(value: datetime) -> str:
    return dt_util.as_local(value).isoformat()


@dataclass(slots=True)
class AuditEvent:
    event_id: str = field(default_factory=lambda: str(uuid4()))
    occurred_at: str = field(default_factory=lambda: utc_now().isoformat())
    occurred_at_local: str = field(default_factory=lambda: local_iso(utc_now()))
    received_at: str = field(default_factory=lambda: utc_now().isoformat())
    category: str = "system"
    event_type: str = "system.unknown"
    severity: str = Severity.INFO
    retention_class: str = RetentionClass.FULL
    summary: str = "Evento sem resumo"
    technical_message: str | None = None
    outcome: str = Outcome.UNKNOWN
    source_component: str | None = None
    source_entity_id: str | None = None
    source_automation_id: str | None = None
    source_script_id: str | None = None
    action_domain: str | None = None
    action_name: str | None = None
    correlation_id: str | None = None
    parent_correlation_id: str | None = None
    context_id: str | None = None
    parent_context_id: str | None = None
    user_id: str | None = None
    user_name: str | None = None
    actor_type: str | None = None
    actor_name: str | None = None
    origin_class: str | None = None
    origin_confidence: str = OriginConfidence.UNKNOWN
    trigger_platform: str | None = None
    trigger_entity_id: str | None = None
    from_state: str | None = None
    to_state: str | None = None
    climate_mode: str | None = None
    treatment: str | None = None
    expected_audibility: str = ExpectedAudibility.UNKNOWN
    observed_audibility: str | None = None
    expected_beep_count: int | None = None
    transmission_id: str | None = None
    frame_kind: str | None = None
    frame_hash: str | None = None
    is_external: bool = False
    is_anomaly: bool = False
    anomaly_type: str | None = None
    compacted_count: int = 1
    details_json: dict[str, Any] | list[Any] | None = None
    before_json: dict[str, Any] | list[Any] | None = None
    desired_json: dict[str, Any] | list[Any] | None = None
    confirmed_json: dict[str, Any] | list[Any] | None = None

    def normalized(self) -> Self:
        """Return a bounded, JSON-safe copy suitable for queueing."""
        data = asdict(self)
        for key in (
            "summary",
            "technical_message",
            "source_component",
            "source_entity_id",
            "source_automation_id",
            "source_script_id",
            "action_domain",
            "action_name",
            "correlation_id",
            "parent_correlation_id",
            "context_id",
            "parent_context_id",
            "user_id",
            "user_name",
            "actor_type",
            "actor_name",
            "origin_class",
            "trigger_platform",
            "trigger_entity_id",
            "from_state",
            "to_state",
            "climate_mode",
            "treatment",
            "observed_audibility",
            "transmission_id",
            "frame_kind",
            "frame_hash",
            "anomaly_type",
        ):
            data[key] = _truncate_text(data.get(key))
        data["details_json"] = bounded_json(data.get("details_json"))
        data["before_json"] = bounded_json(data.get("before_json"))
        data["desired_json"] = bounded_json(data.get("desired_json"))
        data["confirmed_json"] = bounded_json(data.get("confirmed_json"))
        data["summary"] = _truncate_text(data.get("summary"), 1_000) or "Evento sem resumo"
        return type(self)(**data)

    def as_public_dict(self, *, include_details: bool = True) -> dict[str, Any]:
        data = asdict(self)
        if not include_details:
            for key in ("technical_message", "details_json", "before_json", "desired_json", "confirmed_json"):
                data.pop(key, None)
        return data

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> Self:
        allowed = {item.name for item in fields(cls)}
        values = {key: value for key, value in data.items() if key in allowed}
        now = utc_now()
        occurred = values.get("occurred_at")
        if isinstance(occurred, datetime):
            if occurred.tzinfo is None:
                occurred = occurred.replace(tzinfo=timezone.utc)
            values["occurred_at"] = occurred.astimezone(timezone.utc).isoformat()
            values.setdefault("occurred_at_local", local_iso(occurred))
        elif not occurred:
            values["occurred_at"] = now.isoformat()
            values.setdefault("occurred_at_local", local_iso(now))
        values.setdefault("received_at", now.isoformat())
        return cls(**values).normalized()


@dataclass(slots=True)
class AnomalyRecord:
    anomaly_id: str = field(default_factory=lambda: str(uuid4()))
    anomaly_type: str = "unknown"
    severity: str = Severity.WARNING
    first_seen: str = field(default_factory=lambda: utc_now().isoformat())
    last_seen: str = field(default_factory=lambda: utc_now().isoformat())
    count: int = 1
    status: str = "active"
    related_event_ids: list[str] = field(default_factory=list)
    explanation: str = "Anomalia detectada"
    recommendation: str = "Revise a linha do tempo correlacionada."
    acknowledged_at: str | None = None
    resolved_at: str | None = None
    notified_at: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class DiagnosticSettings:
    intensive_mode: bool = False
    retention_absolute_days: int = 60
    retention_error_days: int = 30
    retention_full_days: int = 7
    beep_window_before_seconds: int = 120
    beep_window_after_seconds: int = 120
    multiple_full_frames_limit: int = 2
    multiple_full_frames_window_seconds: int = 300
    close_transmissions_seconds: int = 2
    identical_frame_window_seconds: int = 300
    logical_concurrency_seconds: int = 5
    external_reaction_window_seconds: int = 60
    oscillation_window_seconds: int = 600
    oscillation_min_changes: int = 4
    localtuya_confirmation_seconds: int = 30
    notifications_enabled: bool = True
    notification_min_severity: str = "warning"
    notification_cooldown_seconds: int = 900
    notify_service: str = ""
    compaction_enabled: bool = True
    max_database_mb: int = 250
    default_page_size: int = 50
    technical_details_enabled: bool = True
    visible_categories: list[str] = field(default_factory=list)
    enabled_anomaly_types: list[str] = field(default_factory=list)

    @classmethod
    def from_options(cls, options: dict[str, Any]) -> Self:
        merged = {**DEFAULT_OPTIONS, **(options or {})}
        for key in ("visible_categories", "enabled_anomaly_types"):
            value = merged.get(key, [])
            if isinstance(value, str):
                value = [item.strip() for item in value.split(",") if item.strip()]
            elif not isinstance(value, list):
                value = []
            merged[key] = [str(item)[:120] for item in value[:100]]
        allowed = {item.name for item in fields(cls)}
        return cls(**{key: merged[key] for key in allowed})

    def validate(self) -> None:
        if not 1 <= self.retention_absolute_days <= 365:
            raise ValueError("A retenção Absoluto deve ficar entre 1 e 365 dias.")
        if not 1 <= self.retention_error_days <= 180:
            raise ValueError("A retenção Erros deve ficar entre 1 e 180 dias.")
        if not 1 <= self.retention_full_days <= 30:
            raise ValueError("A retenção completa deve ficar entre 1 e 30 dias.")
        for field_name in ("beep_window_before_seconds", "beep_window_after_seconds"):
            value = int(getattr(self, field_name))
            if not 10 <= value <= 1_800:
                raise ValueError("As janelas do bip devem ficar entre 10 segundos e 30 minutos.")
        if not 1 <= self.multiple_full_frames_limit <= 20:
            raise ValueError("O limite de frames completos deve ficar entre 1 e 20.")
        if not 1 <= self.multiple_full_frames_window_seconds <= 3_600:
            raise ValueError("A janela de frames deve ficar entre 1 segundo e 1 hora.")
        if not 1 <= self.close_transmissions_seconds <= 60:
            raise ValueError("A proximidade de transmissões deve ficar entre 1 e 60 segundos.")
        if not 1 <= self.identical_frame_window_seconds <= 3_600:
            raise ValueError("A janela de frame idêntico deve ficar entre 1 segundo e 1 hora.")
        if not 1 <= self.logical_concurrency_seconds <= 300:
            raise ValueError("A janela de concorrência lógica deve ficar entre 1 e 300 segundos.")
        if not 1 <= self.external_reaction_window_seconds <= 1_800:
            raise ValueError("A janela de reação externa deve ficar entre 1 segundo e 30 minutos.")
        if not 10 <= self.oscillation_window_seconds <= 7_200:
            raise ValueError("A janela de oscilação deve ficar entre 10 segundos e 2 horas.")
        if not 4 <= self.oscillation_min_changes <= 20:
            raise ValueError("A oscilação deve exigir entre 4 e 20 mudanças.")
        if not 1 <= self.localtuya_confirmation_seconds <= 600:
            raise ValueError("O prazo de confirmação LocalTuya deve ficar entre 1 e 600 segundos.")
        if not 10 <= self.max_database_mb <= 4_096:
            raise ValueError("O tamanho máximo do banco deve ficar entre 10 e 4096 MB.")
        if not 10 <= self.default_page_size <= 250:
            raise ValueError("A página padrão deve conter entre 10 e 250 eventos.")
        if self.notification_min_severity not in {item.value for item in Severity}:
            raise ValueError("Severidade mínima de notificação inválida.")

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
