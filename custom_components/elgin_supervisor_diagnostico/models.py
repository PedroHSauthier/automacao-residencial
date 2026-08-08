"""Pure, immutable data models for Elgin Supervisor diagnostics."""

from __future__ import annotations

from dataclasses import dataclass, field, fields
from datetime import datetime, timezone
from enum import StrEnum
import hashlib
import json
import math
from typing import Any, Self
from uuid import uuid4

from .snapshot import FrozenDict, FrozenList, freeze_json, thaw_json


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
    OBSERVED = "observed"
    OBSERVED_BY_USER = "observed_by_user"
    CONFIRMED = "confirmed"
    DIVERGED = "diverged"
    SUPPRESSED = "suppressed"
    BLOCKED = "blocked"
    REJECTED = "rejected"
    FAILED = "failed"
    EXTERNAL = "external"
    COMPLETED = "completed"
    UNKNOWN = "unknown"


class RetentionClass(StrEnum):
    ESSENTIAL = "essential"
    ERROR = "error"
    TRACE = "trace"


class CaptureMode(StrEnum):
    ESSENTIAL = "essential"
    NORMAL = "normal"
    INTENSIVE = "intensive"


class Audibility(StrEnum):
    AUDIBLE_EXPECTED = "audible_expected"
    SILENT_EXPECTED = "silent_expected"
    NO_IR_TRANSMISSION = "no_ir_transmission"
    NOT_DETERMINED = "not_determined"


class AnomalyStatus(StrEnum):
    ACTIVE = "active"
    ACKNOWLEDGED = "acknowledged"
    RESOLVED = "resolved"


class CorrelationRelation(StrEnum):
    DIRECT_CAUSALITY = "direct_causality"
    EXPLICIT = "explicit_correlation"
    SAME_CONTEXT = "same_context"
    DESCENDANT_CONTEXT = "descendant_context"
    EVALUATION = "correlated_by_evaluation"
    PROBABLY_RELATED = "probably_related"
    TEMPORAL_PROXIMITY = "temporal_proximity_only"
    NONE = "no_determined_relation"


_MAX_SUMMARY = 2_000
_MAX_TEXT = 16_384


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def normalize_datetime(value: Any, *, default_now: bool = True) -> str | None:
    if value is None or value == "":
        return utc_now_iso() if default_now else None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError as err:
            raise ValueError(f"Data/hora inválida: {value!r}") from err
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc).isoformat()


def _text(value: Any, *, limit: int = _MAX_TEXT) -> str | None:
    if value is None:
        return None
    result = str(value)
    return result if len(result) <= limit else result[: limit - 1] + "…"


def _enum_value(enum_type: type[StrEnum], value: Any, default: StrEnum) -> str:
    if isinstance(value, enum_type):
        return value.value
    candidate = str(value if value is not None else default.value).strip().casefold()
    aliases = {
        "absolute": "essential",
        "full": "trace",
        "unknown": "not_determined" if enum_type is Audibility else "unknown",
        "no_transmission": "no_ir_transmission",
    }
    candidate = aliases.get(candidate, candidate)
    try:
        return enum_type(candidate).value
    except ValueError:
        return default.value


def _bool(value: Any, default: bool = False) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    normalized = str(value).strip().casefold()
    if normalized in {"1", "true", "yes", "on", "sim"}:
        return True
    if normalized in {"0", "false", "no", "off", "não", "nao", ""}:
        return False
    return default


def _integer(value: Any, default: int) -> int:
    try:
        return int(value)
    except (TypeError, ValueError, OverflowError):
        return default


def _number(value: Any) -> float | None:
    if value is None or value == "":
        return None
    try:
        result = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if math.isfinite(result) else None


def _first(data: dict[str, Any], *names: str, default: Any = None) -> Any:
    """Return the first present key, preserving explicit ``None`` values."""

    for name in names:
        if name in data:
            return data[name]
    return default


def _strength(value: Any) -> float:
    """Normalize persisted textual strengths to a stable 0..1 score."""

    numeric = _number(value)
    if numeric is not None:
        return max(0.0, min(1.0, numeric))
    return {
        "none": 0.0,
        "weak": 0.25,
        "low": 0.25,
        "medium": 0.60,
        "probable": 0.65,
        "strong": 0.90,
        "direct": 1.0,
    }.get(str(value or "").strip().casefold(), 0.0)


def _relation(value: Any) -> str:
    """Keep known semantic relations and losslessly retain legacy relation kinds."""

    candidate = _text(value, limit=180)
    if not candidate:
        return CorrelationRelation.NONE.value
    normalized = candidate.strip().casefold()
    aliases = {
        "direct": CorrelationRelation.DIRECT_CAUSALITY.value,
        "explicit": CorrelationRelation.EXPLICIT.value,
        "context": CorrelationRelation.SAME_CONTEXT.value,
        "parent_context": CorrelationRelation.DESCENDANT_CONTEXT.value,
        "evaluation_id": CorrelationRelation.EVALUATION.value,
        "temporal_only": CorrelationRelation.TEMPORAL_PROXIMITY.value,
        "unbound": CorrelationRelation.NONE.value,
    }
    return aliases.get(normalized, normalized)


def _outcome(value: Any) -> str:
    """Normalize known outcomes without erasing richer persisted result labels."""

    candidate = _text(value, limit=120)
    if not candidate:
        return Outcome.UNKNOWN.value
    normalized = candidate.strip().casefold()
    try:
        return Outcome(normalized).value
    except ValueError:
        return normalized


def _string_tuple(value: Any, *, maximum: int = 500) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        stripped = value.strip()
        if stripped.startswith("["):
            try:
                decoded = json.loads(stripped)
            except json.JSONDecodeError:
                decoded = None
            values = (
                [str(item).strip() for item in decoded]
                if isinstance(decoded, list)
                else [item.strip() for item in value.split(",")]
            )
        else:
            values = [item.strip() for item in value.split(",")]
    elif isinstance(value, (set, frozenset)):
        values = [str(item).strip() for item in sorted(value, key=repr)]
    elif isinstance(value, (list, tuple)):
        values = [str(item).strip() for item in value]
    else:
        values = [str(value).strip()]
    return tuple(dict.fromkeys(item[:240] for item in values if item))[:maximum]


def _json(value: Any) -> Any:
    return None if value is None else freeze_json(value)


def _model_dict(instance: Any) -> dict[str, Any]:
    return {
        item.name: thaw_json(getattr(instance, item.name))
        for item in fields(instance)
    }


def _fingerprint(payload: dict[str, Any]) -> str:
    raw = json.dumps(thaw_json(freeze_json(payload)), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class AuditEvent:
    """One immutable persisted fact observed by the diagnostic integration."""

    event_id: str = field(default_factory=lambda: str(uuid4()))
    occurred_at: str = field(default_factory=utc_now_iso)
    occurred_at_local: str | None = None
    received_at: str = field(default_factory=utc_now_iso)
    category: str = "system"
    event_type: str = "system.unknown"
    severity: str = Severity.INFO
    summary: str = "Evento sem resumo"
    technical_message: str | None = None
    entity_id: str | None = None
    domain: str | None = None
    source_component: str | None = None
    actor_type: str | None = None
    actor_name: str | None = None
    user_id: str | None = None
    user_name: str | None = None
    context_id: str | None = None
    parent_context_id: str | None = None
    correlation_id: str | None = None
    parent_correlation_id: str | None = None
    evaluation_id: str | None = None
    correlation_relation: str = CorrelationRelation.NONE
    correlation_strength: float = 0.0
    relation_evidence: tuple[str, ...] = ()
    causality_asserted: bool = False
    origin_class: str | None = None
    origin_confidence: str | float | None = None
    mode: str | None = None
    treatment: str | None = None
    preset: str | None = None
    power_profile: str | None = None
    agenda: str | None = None
    rule: str | None = None
    protection: str | None = None
    activation_model: str | None = None
    trigger_entity_id: str | None = None
    function: str | None = None
    temperature: float | None = None
    target_temperature: float | None = None
    humidity: float | None = None
    outcome: str = Outcome.UNKNOWN
    reason: str | None = None
    blocked_by: tuple[str, ...] = ()
    action_domain: str | None = None
    action_name: str | None = None
    transmission_id: str | None = None
    request_id: str | None = None
    confirmation_state: str | None = None
    audibility: str = Audibility.NOT_DETERMINED
    is_external: bool = False
    is_anomaly: bool = False
    anomaly_type: str | None = None
    has_error: bool = False
    before_json: Any = None
    after_json: Any = None
    diff_json: Any = None
    desired_json: Any = None
    confirmed_json: Any = None
    details_json: Any = None
    raw_event_json: Any = None
    changed_fields_all: tuple[str, ...] = ()
    changed_fields_relevant: tuple[str, ...] = ()
    retention_class: str = RetentionClass.TRACE
    compacted_count: int = 1
    fingerprint: str = ""
    legacy_semantics: str | None = None

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> Self:
        event_id = _text(data.get("event_id"), limit=128) or str(uuid4())
        occurred_at = normalize_datetime(data.get("occurred_at")) or utc_now_iso()
        received_at = normalize_datetime(data.get("received_at")) or utc_now_iso()
        entity_id = _text(_first(data, "entity_id", "source_entity_id"), limit=255)
        domain = _text(_first(data, "domain", "entity_domain"), limit=80)
        if domain is None and entity_id and "." in entity_id:
            domain = entity_id.split(".", 1)[0]

        diff_value = data.get("diff_json", data.get("diff"))
        diff_mapping = diff_value if isinstance(diff_value, dict) else {}
        persisted_diff = (
            diff_mapping.get("diff")
            if isinstance(diff_mapping.get("diff"), dict)
            and (
                "changed_fields_all" in diff_mapping
                or "changed_fields_relevant" in diff_mapping
            )
            else diff_value
        )
        frozen_diff = _json(persisted_diff)
        changed_all = _string_tuple(
            data.get("changed_fields_all", diff_mapping.get("changed_fields_all"))
        )
        changed_relevant = _string_tuple(
            data.get(
                "changed_fields_relevant",
                diff_mapping.get("changed_fields_relevant", diff_mapping.get("changed_fields")),
            )
        )

        severity = _enum_value(Severity, data.get("severity"), Severity.INFO)
        retention = _enum_value(
            RetentionClass,
            data.get("retention_class"),
            RetentionClass.TRACE,
        )
        has_error = _bool(data.get("has_error"), severity in {Severity.ERROR, Severity.CRITICAL})
        # ``relation_kind`` is intentionally open-ended in the existing SQLite
        # schema, so retain legacy evidence labels instead of collapsing them.
        relation = _relation(_first(data, "correlation_relation", "relation_kind"))
        strength = _strength(_first(data, "correlation_strength", "relation_strength"))

        details_value = _first(data, "details_json", "details")
        details_mapping = details_value if isinstance(details_value, dict) else {}

        values: dict[str, Any] = {
            "event_id": event_id,
            "occurred_at": occurred_at,
            "occurred_at_local": _text(data.get("occurred_at_local"), limit=80),
            "received_at": received_at,
            "category": _text(data.get("category"), limit=120) or "system",
            "event_type": _text(data.get("event_type"), limit=180) or "system.unknown",
            "severity": severity,
            "summary": _text(data.get("summary"), limit=_MAX_SUMMARY) or "Evento sem resumo",
            "technical_message": _text(data.get("technical_message")),
            "entity_id": entity_id,
            "domain": domain,
            "source_component": _text(data.get("source_component"), limit=180),
            "actor_type": _text(data.get("actor_type"), limit=120),
            "actor_name": _text(data.get("actor_name"), limit=255),
            "user_id": _text(data.get("user_id"), limit=128),
            "user_name": _text(data.get("user_name"), limit=255),
            "context_id": _text(data.get("context_id"), limit=128),
            "parent_context_id": _text(data.get("parent_context_id"), limit=128),
            "correlation_id": _text(data.get("correlation_id"), limit=128),
            "parent_correlation_id": _text(data.get("parent_correlation_id"), limit=128),
            "evaluation_id": _text(data.get("evaluation_id"), limit=128),
            "correlation_relation": relation,
            "correlation_strength": strength,
            "relation_evidence": _string_tuple(
                _first(data, "relation_evidence", "evidence"), maximum=500
            ),
            "causality_asserted": _bool(data.get("causality_asserted")),
            "origin_class": _text(data.get("origin_class"), limit=120),
            "origin_confidence": freeze_json(data.get("origin_confidence"))
            if data.get("origin_confidence") is not None
            else None,
            "mode": _text(data.get("mode", data.get("climate_mode")), limit=80),
            "treatment": _text(data.get("treatment"), limit=120),
            "preset": _text(data.get("preset"), limit=180),
            "power_profile": _text(data.get("power_profile", data.get("power")), limit=180),
            "agenda": _text(_first(data, "agenda", "agenda_state"), limit=255),
            "rule": _text(_first(data, "rule", default=details_mapping.get("rule")), limit=255),
            "protection": _text(data.get("protection"), limit=255),
            "activation_model": _text(
                _first(data, "activation_model", "trigger_model"), limit=180
            ),
            "trigger_entity_id": _text(data.get("trigger_entity_id"), limit=255),
            "function": _text(data.get("function"), limit=180),
            "temperature": _number(
                _first(data, "temperature", default=details_mapping.get("temperature"))
            ),
            "target_temperature": _number(
                _first(
                    data,
                    "target_temperature",
                    default=details_mapping.get("target_temperature"),
                )
            ),
            "humidity": _number(
                _first(data, "humidity", default=details_mapping.get("humidity"))
            ),
            "outcome": _outcome(data.get("outcome")),
            "reason": _text(_first(data, "reason", default=details_mapping.get("reason"))),
            "blocked_by": _string_tuple(
                _first(data, "blocked_by", default=details_mapping.get("blocked_by"))
            ),
            "action_domain": _text(data.get("action_domain"), limit=80),
            "action_name": _text(data.get("action_name", data.get("action")), limit=180),
            "transmission_id": _text(data.get("transmission_id"), limit=128),
            "request_id": _text(data.get("request_id"), limit=128),
            "confirmation_state": _text(data.get("confirmation_state"), limit=120),
            "audibility": _enum_value(
                Audibility,
                data.get("audibility", data.get("expected_audibility")),
                Audibility.NOT_DETERMINED,
            ),
            "is_external": _bool(data.get("is_external")),
            "is_anomaly": _bool(data.get("is_anomaly")),
            "anomaly_type": _text(data.get("anomaly_type"), limit=180),
            "has_error": has_error,
            "before_json": _json(data.get("before_json", data.get("before"))),
            "after_json": _json(data.get("after_json", data.get("after"))),
            "diff_json": frozen_diff,
            "desired_json": _json(_first(data, "desired_json", "desired")),
            "confirmed_json": _json(_first(data, "confirmed_json", "confirmed")),
            "details_json": _json(details_value),
            "raw_event_json": _json(data.get("raw_event_json", data.get("raw_event"))),
            "changed_fields_all": changed_all,
            "changed_fields_relevant": changed_relevant,
            "retention_class": retention,
            "compacted_count": max(1, _integer(data.get("compacted_count"), 1)),
            "legacy_semantics": _text(data.get("legacy_semantics"), limit=255),
        }
        fingerprint = _text(data.get("fingerprint"), limit=128)
        values["fingerprint"] = fingerprint or _fingerprint(
            {
                "category": values["category"],
                "event_type": values["event_type"],
                "entity_id": entity_id,
                "outcome": values["outcome"],
                "mode": values["mode"],
                "treatment": values["treatment"],
                "before": values["before_json"],
                "after": values["after_json"],
                "diff": frozen_diff,
                "details": values["details_json"],
            }
        )
        return cls(**values)

    def as_dict(self) -> dict[str, Any]:
        result = _model_dict(self)
        details = result.get("details_json")
        if not isinstance(details, dict):
            details = {}
        else:
            details = dict(details)
        for key, value in {
            "rule": self.rule,
            "reason": self.reason,
            "blocked_by": list(self.blocked_by) if self.blocked_by else None,
            "temperature": self.temperature,
            "target_temperature": self.target_temperature,
            "humidity": self.humidity,
            "causality_asserted": self.causality_asserted,
        }.items():
            if value is not None and key not in details:
                details[key] = value
        if self.raw_event_json is not None and "raw_event" not in details:
            details["raw_event"] = thaw_json(self.raw_event_json)
        result["details_json"] = details or None
        result["retention_class_canonical"] = self.retention_class
        result["retention_class"] = {
            RetentionClass.ESSENTIAL.value: "absolute",
            RetentionClass.TRACE.value: "full",
        }.get(self.retention_class, self.retention_class)
        # Canonical UI names and current persisted SQLite names coexist at this
        # boundary. Storage consumes the latter and public APIs may use either.
        result.update(
            {
                "source_entity_id": self.entity_id,
                "entity_domain": self.domain,
                "climate_mode": self.mode,
                "agenda_state": self.agenda,
                "expected_audibility": self.audibility,
                "trigger_model": self.activation_model,
                "relation_kind": self.correlation_relation,
                "relation_strength": self.correlation_strength,
            }
        )
        return result


@dataclass(frozen=True, slots=True)
class EvaluationRecord:
    """One consolidated Supervisor evaluation, not one row per internal stage."""

    evaluation_id: str = field(default_factory=lambda: str(uuid4()))
    correlation_id: str = field(default_factory=lambda: str(uuid4()))
    context_id: str | None = None
    started_at: str = field(default_factory=utc_now_iso)
    finished_at: str | None = None
    status: str = "started"
    summary: str | None = None
    trigger: Any = None
    actor: Any = None
    input_snapshot: Any = None
    previous_decision: Any = None
    demands: Any = None
    priorities: Any = None
    agenda: Any = None
    presets: Any = None
    powers: Any = None
    limits: Any = None
    protections: Any = None
    desired_configuration: Any = None
    previous_desired_configuration: Any = None
    action: Any = None
    result: Any = None
    reason: str | None = None
    blocked_by: tuple[str, ...] = ()
    mode: str | None = None
    treatment: str | None = None
    related_events: tuple[str, ...] = ()
    stages: Any = None
    complete: bool = False
    duration_ms: float | None = None
    revision: int = 1

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> Self:
        started = normalize_datetime(data.get("started_at")) or utc_now_iso()
        finished = normalize_datetime(
            _first(data, "finished_at", "completed_at"), default_now=False
        )
        duration = _number(data.get("duration_ms"))
        if duration is None and finished:
            duration = max(
                0.0,
                (
                    datetime.fromisoformat(finished)
                    - datetime.fromisoformat(started)
                ).total_seconds()
                * 1_000,
            )
        reason_value = _first(data, "reason", "reason_json")
        reason_mapping = reason_value if isinstance(reason_value, dict) else {}
        reason_text = reason_mapping.get("reason") if reason_mapping else reason_value
        blocked_value = _first(
            data, "blocked_by", default=reason_mapping.get("blocked_by")
        )
        return cls(
            evaluation_id=_text(data.get("evaluation_id"), limit=128) or str(uuid4()),
            correlation_id=_text(data.get("correlation_id"), limit=128) or str(uuid4()),
            context_id=_text(data.get("context_id"), limit=128),
            started_at=started,
            finished_at=finished,
            status=_text(data.get("status"), limit=80)
            or ("completed" if finished else "started"),
            summary=_text(data.get("summary"), limit=_MAX_SUMMARY),
            trigger=_json(_first(data, "trigger", "trigger_json")),
            actor=_json(_first(data, "actor", "actor_json")),
            input_snapshot=_json(_first(data, "input_snapshot", "inputs_json")),
            previous_decision=_json(
                _first(data, "previous_decision", "prior_decision_json")
            ),
            demands=_json(_first(data, "demands", "demands_json")),
            priorities=_json(_first(data, "priorities", "priorities_json")),
            agenda=_json(_first(data, "agenda", "agenda_json")),
            presets=_json(_first(data, "presets", "presets_json")),
            powers=_json(_first(data, "powers", "powers_json")),
            limits=_json(_first(data, "limits", "limits_json")),
            protections=_json(_first(data, "protections", "protections_json")),
            desired_configuration=_json(
                _first(data, "desired_configuration", "desired_json")
            ),
            previous_desired_configuration=_json(
                data.get("previous_desired_configuration")
            ),
            action=_json(_first(data, "action", "action_json")),
            result=_json(_first(data, "result", "result_json")),
            reason=_text(reason_text),
            blocked_by=_string_tuple(blocked_value),
            mode=_text(
                _first(data, "mode", default=reason_mapping.get("mode")), limit=80
            ),
            treatment=_text(
                _first(data, "treatment", default=reason_mapping.get("treatment")),
                limit=120,
            ),
            related_events=_string_tuple(
                _first(data, "related_events", "related_event_ids"), maximum=2_000
            ),
            stages=_json(
                _first(data, "stages", default=reason_mapping.get("stages"))
            ),
            complete=_bool(
                data.get("complete"),
                bool(finished) or str(data.get("status", "")).casefold() == "completed",
            ),
            duration_ms=duration,
            revision=max(1, _integer(data.get("revision"), 1)),
        )

    def as_dict(self) -> dict[str, Any]:
        result = _model_dict(self)
        reason_payload = {
            "reason": self.reason,
            "blocked_by": list(self.blocked_by),
            "mode": self.mode,
            "treatment": self.treatment,
            "previous_desired_configuration": thaw_json(
                self.previous_desired_configuration
            ),
            "stages": thaw_json(self.stages),
            "duration_ms": self.duration_ms,
        }
        result.update(
            {
                "completed_at": self.finished_at,
                "trigger_json": thaw_json(self.trigger),
                "actor_json": thaw_json(self.actor),
                "inputs_json": thaw_json(self.input_snapshot),
                "prior_decision_json": thaw_json(self.previous_decision),
                "demands_json": thaw_json(self.demands),
                "priorities_json": thaw_json(self.priorities),
                "agenda_json": thaw_json(self.agenda),
                "presets_json": thaw_json(self.presets),
                "powers_json": thaw_json(self.powers),
                "limits_json": thaw_json(self.limits),
                "protections_json": thaw_json(self.protections),
                "desired_json": thaw_json(self.desired_configuration),
                "action_json": thaw_json(self.action),
                "result_json": thaw_json(self.result),
                "reason_json": {
                    key: value for key, value in reason_payload.items() if value is not None
                },
                "related_event_ids": list(self.related_events),
            }
        )
        return result


@dataclass(frozen=True, slots=True)
class AnomalyRecord:
    anomaly_id: str = field(default_factory=lambda: str(uuid4()))
    anomaly_type: str = "unknown"
    severity: str = Severity.WARNING
    status: str = AnomalyStatus.ACTIVE
    first_occurred_at: str = field(default_factory=utc_now_iso)
    last_occurred_at: str = field(default_factory=utc_now_iso)
    occurrence_count: int = 1
    summary: str = "Anomalia detectada"
    explanation: str = ""
    recommendation: str | None = None
    related_event_ids: tuple[str, ...] = ()
    correlation_id: str | None = None
    acknowledged_by_user_id: str | None = None
    acknowledged_by_user_name: str | None = None
    acknowledged_at: str | None = None
    acknowledgment_note: str | None = None
    resolved_by_user_id: str | None = None
    resolved_by_user_name: str | None = None
    resolved_at: str | None = None
    resolution_note: str | None = None
    notified_at: str | None = None
    fingerprint: str = ""
    details_json: Any = None

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> Self:
        anomaly_type = _text(data.get("anomaly_type", data.get("type")), limit=180) or "unknown"
        summary = _text(_first(data, "summary", "title"), limit=_MAX_SUMMARY) or "Anomalia detectada"
        fingerprint = _text(data.get("fingerprint"), limit=128) or _fingerprint(
            {"type": anomaly_type, "scope": data.get("scope"), "summary": summary}
        )
        status = _enum_value(AnomalyStatus, data.get("status"), AnomalyStatus.ACTIVE)
        return cls(
            anomaly_id=_text(data.get("anomaly_id", data.get("id")), limit=128) or str(uuid4()),
            anomaly_type=anomaly_type,
            severity=_enum_value(Severity, data.get("severity"), Severity.WARNING),
            status=status,
            first_occurred_at=normalize_datetime(
                data.get("first_occurred_at", data.get("first_seen"))
            ) or utc_now_iso(),
            last_occurred_at=normalize_datetime(
                data.get("last_occurred_at", data.get("last_seen"))
            ) or utc_now_iso(),
            occurrence_count=max(1, _integer(data.get("occurrence_count", data.get("count")), 1)),
            summary=summary,
            explanation=_text(data.get("explanation")) or "",
            recommendation=_text(data.get("recommendation")),
            related_event_ids=_string_tuple(data.get("related_event_ids"), maximum=2_000),
            correlation_id=_text(data.get("correlation_id"), limit=128),
            acknowledged_by_user_id=_text(data.get("acknowledged_by_user_id"), limit=128),
            acknowledged_by_user_name=_text(
                _first(data, "acknowledged_by_user_name", "acknowledged_by"), limit=255
            ),
            acknowledged_at=normalize_datetime(data.get("acknowledged_at"), default_now=False),
            acknowledgment_note=_text(
                _first(
                    data,
                    "acknowledgment_note",
                    "acknowledgement_note",
                    "note",
                )
            ),
            resolved_by_user_id=_text(data.get("resolved_by_user_id"), limit=128),
            resolved_by_user_name=_text(
                _first(data, "resolved_by_user_name", "resolved_by"), limit=255
            ),
            resolved_at=normalize_datetime(data.get("resolved_at"), default_now=False),
            resolution_note=_text(data.get("resolution_note")),
            notified_at=normalize_datetime(data.get("notified_at"), default_now=False),
            fingerprint=fingerprint,
            details_json=_json(data.get("details_json", data.get("details"))),
        )

    def as_dict(self) -> dict[str, Any]:
        result = _model_dict(self)
        result.update(
            {
                "title": self.summary,
                "first_seen": self.first_occurred_at,
                "last_seen": self.last_occurred_at,
                "count": self.occurrence_count,
                "acknowledged_by": self.acknowledged_by_user_name
                or self.acknowledged_by_user_id,
                "acknowledgement_note": self.acknowledgment_note,
                "resolved_by": self.resolved_by_user_name or self.resolved_by_user_id,
                "details": thaw_json(self.details_json),
            }
        )
        return result


@dataclass(frozen=True, slots=True)
class ObservationRecord:
    observation_id: str = field(default_factory=lambda: str(uuid4()))
    occurred_at: str = field(default_factory=utc_now_iso)
    received_at: str = field(default_factory=utc_now_iso)
    observation_type: str = "note"
    beep_count: str | None = None
    title: str = "Observação"
    text: str = ""
    tags: tuple[str, ...] = ()
    user_id: str | None = None
    user_name: str | None = None
    context_id: str | None = None
    correlation_id: str | None = None
    evaluation_id: str | None = None
    outcome: str = Outcome.OBSERVED_BY_USER
    snapshot_json: Any = None
    details_json: Any = None
    related_event_ids: tuple[str, ...] = ()

    @classmethod
    def from_mapping(cls, data: dict[str, Any]) -> Self:
        observation_type = _text(data.get("observation_type", data.get("type")), limit=80) or "note"
        metadata_value = _first(
            data, "metadata", "metadata_json", "details_json", "details"
        )
        metadata_mapping = metadata_value if isinstance(metadata_value, dict) else {}
        beep_count = _text(
            _first(
                data,
                "beep_count",
                "expected_count",
                default=metadata_mapping.get("beep_count"),
            ),
            limit=32,
        )
        valid_numeric_count = bool(
            beep_count and beep_count.isdigit() and int(beep_count) > 0
        )
        if observation_type == "beep" and not (
            valid_numeric_count or beep_count in {"multiple", "uncertain"}
        ):
            beep_count = "uncertain"
        return cls(
            observation_id=_text(data.get("observation_id", data.get("id")), limit=128) or str(uuid4()),
            occurred_at=normalize_datetime(data.get("occurred_at")) or utc_now_iso(),
            received_at=normalize_datetime(
                _first(data, "received_at", "created_at")
            ) or utc_now_iso(),
            observation_type=observation_type,
            beep_count=beep_count,
            title=_text(
                _first(data, "title", default=metadata_mapping.get("title")), limit=255
            ) or ("Bip observado" if observation_type == "beep" else "Observação"),
            text=_text(data.get("text", data.get("note"))) or "",
            tags=_string_tuple(
                _first(data, "tags", default=metadata_mapping.get("tags")), maximum=50
            ),
            user_id=_text(data.get("user_id"), limit=128),
            user_name=_text(data.get("user_name"), limit=255),
            context_id=_text(
                _first(data, "context_id", default=metadata_mapping.get("context_id")),
                limit=128,
            ),
            correlation_id=_text(data.get("correlation_id"), limit=128),
            evaluation_id=_text(
                _first(
                    data,
                    "evaluation_id",
                    default=metadata_mapping.get("evaluation_id"),
                ),
                limit=128,
            ),
            outcome=Outcome.OBSERVED_BY_USER,
            snapshot_json=_json(
                _first(
                    data,
                    "snapshot_json",
                    "snapshot",
                    default=metadata_mapping.get("snapshot"),
                )
            ),
            details_json=_json(metadata_value),
            related_event_ids=_string_tuple(data.get("related_event_ids"), maximum=2_000),
        )

    def as_dict(self) -> dict[str, Any]:
        result = _model_dict(self)
        metadata = result.get("details_json")
        if not isinstance(metadata, dict):
            metadata = {}
        else:
            metadata = dict(metadata)
        metadata.setdefault("beep_count", self.beep_count)
        metadata.setdefault("title", self.title)
        metadata.setdefault("tags", list(self.tags))
        metadata.setdefault("context_id", self.context_id)
        metadata.setdefault("evaluation_id", self.evaluation_id)
        metadata.setdefault("snapshot", thaw_json(self.snapshot_json))
        expected_count = (
            int(self.beep_count)
            if self.beep_count and self.beep_count.isdigit()
            else None
        )
        result.update(
            {
                "created_at": self.received_at,
                "note": self.text,
                "expected_count": expected_count,
                "metadata": metadata,
                "metadata_json": metadata,
                "related_event_ids": list(self.related_event_ids),
            }
        )
        return result


@dataclass(frozen=True, slots=True)
class DiagnosticSettings:
    """Persisted ConfigEntry options covering every card settings section."""

    capture_mode: str = CaptureMode.NORMAL
    capture_decisions: bool = True
    capture_state_changes: bool = True
    capture_service_calls: bool = True
    capture_localtuya: bool = True
    capture_climate: bool = True
    capture_agenda: bool = True
    capture_presets: bool = True
    capture_power_profiles: bool = True
    capture_protections: bool = True
    capture_errors: bool = True
    capture_external_changes: bool = True
    retention_essential_days: int = 60
    retention_error_days: int = 30
    retention_trace_days: int = 7
    compaction_enabled: bool = True
    compaction_window_seconds: int = 60
    compact_identical_evaluations: bool = True
    compact_no_change: bool = True
    compact_identical_states: bool = True
    compact_repeated_blocks: bool = True
    compact_repeated_unavailable: bool = True
    rate_window_seconds: int = 60
    rate_warning_events: int = 500
    rate_hard_limit_events: int = 2_000
    queue_limit: int = 5_000
    critical_queue_limit: int = 2_000
    batch_size: int = 100
    flush_interval_seconds: float = 0.25
    correlation_window_seconds: int = 30
    localtuya_confirmation_window_seconds: int = 30
    external_observation_window_seconds: int = 60
    beep_window_before_seconds: int = 120
    beep_window_after_seconds: int = 120
    anomaly_enabled_types: tuple[str, ...] = (
        "commands_too_close",
        "repeated_commands",
        "decision_oscillation",
        "desired_state_divergence",
        "localtuya_not_confirmed",
        "external_change_reaction",
        "excessive_volume",
        "repeated_error",
        "critical_entity_unavailable",
    )
    anomalies_enabled: bool = True
    anomaly_close_commands_seconds: int = 2
    anomaly_repeated_command_window_seconds: int = 300
    anomaly_oscillation_window_seconds: int = 600
    anomaly_oscillation_min_changes: int = 4
    anomaly_divergence_seconds: int = 60
    anomaly_volume_window_seconds: int = 60
    anomaly_volume_event_limit: int = 1_000
    anomaly_repeated_error_window_seconds: int = 300
    anomaly_repeated_error_count: int = 3
    anomaly_unavailable_seconds: int = 120
    anomaly_no_change_threshold: int = 100
    anomaly_duplicate_window_seconds: int = 10
    anomaly_audible_burst_seconds: int = 20
    anomaly_audible_burst_count: int = 3
    anomaly_window_minutes: int = 15
    notifications_enabled: bool = False
    notification_min_severity: str = Severity.WARNING
    notification_types: tuple[str, ...] = (
        "commands_too_close",
        "repeated_commands",
        "decision_oscillation",
        "desired_state_divergence",
        "localtuya_not_confirmed",
        "external_change_reaction",
        "excessive_volume",
        "repeated_error",
        "critical_entity_unavailable",
    )
    notification_cooldown_seconds: int = 900
    notification_persistent: bool = True
    notification_service: str = ""
    interface_items_per_page: int = 50
    interface_auto_refresh: bool = True
    interface_columns: tuple[str, ...] = (
        "occurred_at",
        "severity",
        "category",
        "summary",
        "actor",
        "origin",
        "entity_id",
        "before",
        "after",
        "outcome",
        "correlation_id",
    )
    interface_density: str = "comfortable"
    interface_show_technical_codes: bool = False
    interface_show_unchanged_attributes: bool = False
    interface_date_format: str = "locale"
    interface_detail_mode: str = "panel"
    saved_filters: Any = field(default_factory=tuple)
    default_saved_filter_id: str = ""
    privacy_resolve_user_names: bool = True
    privacy_store_user_ids: bool = True
    privacy_store_user_names: bool = True
    privacy_capture_raw_events: bool = True
    privacy_capture_service_data: bool = True
    privacy_redact_sensitive_values: bool = True
    maintenance_database_limit_mb: int = 250
    maintenance_cleanup_interval_hours: int = 6
    maintenance_export_max_rows: int = 50_000
    anonymize_entity_ids: bool = False

    @classmethod
    def from_options(cls, options: dict[str, Any] | None) -> Self:
        source = dict(options or {})
        # Compatibility is read-only: old option names are migrated into the
        # current semantic model and are never emitted again by ``as_dict``.
        if "capture_mode" not in source and "intensive_mode" in source:
            source["capture_mode"] = (
                CaptureMode.INTENSIVE if _bool(source.get("intensive_mode")) else CaptureMode.NORMAL
            )
        aliases = {
            "retention_absolute_days": "retention_essential_days",
            "retention_full_days": "retention_trace_days",
            "retention_observations_days": "retention_essential_days",
            "capture_state_changed": "capture_state_changes",
            "capture_power": "capture_power_profiles",
            "localtuya_confirmation_seconds": "localtuya_confirmation_window_seconds",
            "external_observation_seconds": "external_observation_window_seconds",
            "enabled_anomaly_types": "anomaly_enabled_types",
            "notification_minimum_severity": "notification_min_severity",
            "persistent_notifications": "notification_persistent",
            "notify_service": "notification_service",
            "default_page_size": "interface_items_per_page",
            "page_size": "interface_items_per_page",
            "live_updates": "interface_auto_refresh",
            "visible_columns": "interface_columns",
            "density": "interface_density",
            "technical_details_enabled": "interface_show_technical_codes",
            "show_technical_codes": "interface_show_technical_codes",
            "show_unchanged_attributes": "interface_show_unchanged_attributes",
            "date_format": "interface_date_format",
            "detail_presentation": "interface_detail_mode",
            "max_database_mb": "maintenance_database_limit_mb",
            "cleanup_interval_hours": "maintenance_cleanup_interval_hours",
            "export_max_events": "maintenance_export_max_rows",
            "normal_queue_max": "queue_limit",
            "rate_limit_per_minute": "rate_hard_limit_events",
        }
        for old, new in aliases.items():
            if new not in source and old in source:
                source[new] = source[old]

        defaults = cls()
        bool_fields = {
            item.name
            for item in fields(cls)
            if isinstance(getattr(defaults, item.name), bool)
        }
        int_fields = {
            item.name
            for item in fields(cls)
            if isinstance(getattr(defaults, item.name), int)
            and not isinstance(getattr(defaults, item.name), bool)
        }
        tuple_fields = {
            item.name
            for item in fields(cls)
            if isinstance(getattr(defaults, item.name), tuple)
        }
        values: dict[str, Any] = {}
        for item in fields(cls):
            name = item.name
            default = getattr(defaults, name)
            value = source.get(name, default)
            if name in bool_fields:
                value = _bool(value, default)
            elif name in int_fields:
                value = _integer(value, default)
            elif name in tuple_fields:
                value = _string_tuple(value)
            elif isinstance(default, float):
                try:
                    value = float(value)
                except (TypeError, ValueError, OverflowError):
                    value = default
            elif isinstance(default, str):
                value = _text(value, limit=255) or default
            values[name] = value

        saved_filters = source.get("saved_filters", defaults.saved_filters)
        if not isinstance(saved_filters, (list, tuple)):
            saved_filters = []
        values["saved_filters"] = freeze_json(list(saved_filters)[:100])

        values["capture_mode"] = _enum_value(
            CaptureMode, values["capture_mode"], CaptureMode.NORMAL
        )
        values["notification_min_severity"] = _enum_value(
            Severity,
            values["notification_min_severity"],
            Severity.WARNING,
        )
        settings = cls(**values)
        settings.validate()
        return settings

    def validate(self) -> None:
        errors: list[str] = []

        def between(name: str, minimum: int, maximum: int) -> None:
            value = getattr(self, name)
            if not minimum <= value <= maximum:
                errors.append(f"{name} deve ficar entre {minimum} e {maximum}")

        between("retention_essential_days", 1, 3_650)
        between("retention_error_days", 1, 365)
        between("retention_trace_days", 1, 90)
        between("compaction_window_seconds", 1, 3_600)
        between("correlation_window_seconds", 1, 600)
        between("localtuya_confirmation_window_seconds", 1, 600)
        between("external_observation_window_seconds", 1, 1_800)
        between("beep_window_before_seconds", 10, 1_800)
        between("beep_window_after_seconds", 10, 1_800)
        between("anomaly_close_commands_seconds", 1, 60)
        between("anomaly_repeated_command_window_seconds", 1, 3_600)
        between("anomaly_oscillation_window_seconds", 10, 7_200)
        between("anomaly_oscillation_min_changes", 4, 50)
        between("anomaly_divergence_seconds", 1, 3_600)
        between("anomaly_volume_window_seconds", 1, 3_600)
        between("anomaly_volume_event_limit", 10, 1_000_000)
        between("anomaly_repeated_error_window_seconds", 1, 86_400)
        between("anomaly_repeated_error_count", 2, 1_000)
        between("anomaly_unavailable_seconds", 1, 86_400)
        between("anomaly_no_change_threshold", 2, 1_000_000)
        between("anomaly_duplicate_window_seconds", 1, 3_600)
        between("anomaly_audible_burst_seconds", 1, 3_600)
        between("anomaly_audible_burst_count", 2, 1_000)
        between("anomaly_window_minutes", 1, 1_440)
        between("notification_cooldown_seconds", 10, 86_400)
        between("interface_items_per_page", 10, 250)
        between("maintenance_database_limit_mb", 10, 4_096)
        between("maintenance_cleanup_interval_hours", 1, 168)
        between("maintenance_export_max_rows", 100, 1_000_000)
        between("rate_window_seconds", 1, 3_600)
        between("rate_warning_events", 10, 1_000_000)
        between("rate_hard_limit_events", 100, 1_000_000)
        between("queue_limit", 100, 100_000)
        between("critical_queue_limit", 100, 100_000)
        between("batch_size", 1, 5_000)
        if not 0.01 <= self.flush_interval_seconds <= 60:
            errors.append("flush_interval_seconds deve ficar entre 0.01 e 60")
        if self.rate_warning_events > self.rate_hard_limit_events:
            errors.append("rate_warning_events não pode exceder rate_hard_limit_events")
        if (
            self.anomaly_duplicate_window_seconds
            > self.anomaly_repeated_command_window_seconds
        ):
            errors.append(
                "anomaly_duplicate_window_seconds não pode exceder a janela de repetição"
            )
        if self.interface_density not in {"compact", "comfortable"}:
            errors.append("interface_density inválida")
        if self.interface_date_format not in {"locale", "iso", "relative"}:
            errors.append("interface_date_format inválido")
        if self.interface_detail_mode not in {"panel", "modal"}:
            errors.append("interface_detail_mode inválido")
        if self.notification_service:
            domain, separator, service = self.notification_service.partition(".")
            if (
                separator != "."
                or domain != "notify"
                or not service
                or any(
                    character not in "abcdefghijklmnopqrstuvwxyz0123456789_"
                    for character in service
                )
            ):
                errors.append(
                    "notification_service deve usar notify.servico com caracteres seguros"
                )
        supported_anomalies = set(type(self)().anomaly_enabled_types)
        unknown_anomalies = set(self.anomaly_enabled_types) - supported_anomalies
        unknown_notifications = set(self.notification_types) - supported_anomalies
        if unknown_anomalies:
            errors.append(
                "anomaly_enabled_types contém tipos desconhecidos: "
                + ", ".join(sorted(unknown_anomalies))
            )
        if unknown_notifications:
            errors.append(
                "notification_types contém tipos desconhecidos: "
                + ", ".join(sorted(unknown_notifications))
            )
        if errors:
            raise ValueError("; ".join(errors))

    def as_dict(self) -> dict[str, Any]:
        return _model_dict(self)

    # Runtime compatibility properties. They are intentionally absent from
    # ``as_dict`` so ConfigEntry.options has one canonical key per setting.
    @property
    def retention_absolute_days(self) -> int:
        return self.retention_essential_days

    @property
    def retention_full_days(self) -> int:
        return self.retention_trace_days

    @property
    def retention_observations_days(self) -> int:
        return self.retention_essential_days

    @property
    def notification_minimum_severity(self) -> str:
        return self.notification_min_severity

    @property
    def export_max_events(self) -> int:
        return self.maintenance_export_max_rows

    @property
    def capture_power(self) -> bool:
        return self.capture_power_profiles

    @property
    def localtuya_confirmation_seconds(self) -> int:
        return self.localtuya_confirmation_window_seconds

    @property
    def external_observation_seconds(self) -> int:
        return self.external_observation_window_seconds

    @property
    def enabled_anomaly_types(self) -> tuple[str, ...]:
        return self.anomaly_enabled_types

    @property
    def persistent_notifications(self) -> bool:
        return self.notification_persistent

    @property
    def notify_service(self) -> str:
        return self.notification_service

    @property
    def page_size(self) -> int:
        return self.interface_items_per_page

    @property
    def max_database_mb(self) -> int:
        return self.maintenance_database_limit_mb

    @property
    def cleanup_interval_hours(self) -> int:
        return self.maintenance_cleanup_interval_hours

    @property
    def normal_queue_max(self) -> int:
        return self.queue_limit


# Compatibility export used by storage and older callers. ``query`` depends only
# on ``snapshot``, therefore importing it here does not create a cycle.
from .query import decode_cursor, encode_cursor  # noqa: E402


__all__ = [
    "AnomalyRecord",
    "AnomalyStatus",
    "AuditEvent",
    "Audibility",
    "CaptureMode",
    "CorrelationRelation",
    "DiagnosticSettings",
    "EvaluationRecord",
    "ObservationRecord",
    "Outcome",
    "RetentionClass",
    "Severity",
    "decode_cursor",
    "encode_cursor",
    "normalize_datetime",
    "utc_now_iso",
]
