"""Pure correlation engine with explicit evidence and conservative causality."""

from __future__ import annotations

from collections import deque
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from .models import CorrelationRelation, normalize_datetime, utc_now_iso
from .snapshot import freeze_json, thaw_json


def _read(source: Any, key: str, default: Any = None) -> Any:
    if source is None:
        return default
    if isinstance(source, Mapping):
        return source.get(key, default)
    return getattr(source, key, default)


def _as_datetime(value: Any | None) -> datetime:
    normalized = normalize_datetime(value) or utc_now_iso()
    return datetime.fromisoformat(normalized).astimezone(timezone.utc)


@dataclass(frozen=True, slots=True)
class CorrelationResult:
    correlation_id: str
    relation: str
    strength: float
    causality_asserted: bool
    partial: bool
    evidence: tuple[str, ...] = ()
    evaluation_id: str | None = None
    root_context_id: str | None = None
    root_started_at: str | None = None
    temporal_distance_seconds: float | None = None
    candidate_count: int = 1

    def as_dict(self) -> dict[str, Any]:
        return {
            "correlation_id": self.correlation_id,
            "relation": self.relation,
            "strength": self.strength,
            "causality_asserted": self.causality_asserted,
            "partial": self.partial,
            "evidence": list(self.evidence),
            "evaluation_id": self.evaluation_id,
            "root_context_id": self.root_context_id,
            "root_started_at": self.root_started_at,
            "temporal_distance_seconds": self.temporal_distance_seconds,
            "candidate_count": self.candidate_count,
        }


@dataclass(slots=True)
class _CorrelationRoot:
    correlation_id: str
    started_at: datetime
    context_id: str | None = None
    parent_context_id: str | None = None
    user_id: str | None = None
    evaluation_id: str | None = None
    source_entity_id: str | None = None
    action: str | None = None
    actor: str | None = None
    metadata: Any = None
    completed_at: datetime | None = None
    result: Any = None
    contexts: set[str] = field(default_factory=set)

    def as_dict(self) -> dict[str, Any]:
        return {
            "correlation_id": self.correlation_id,
            "started_at": self.started_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "context_id": self.context_id,
            "parent_context_id": self.parent_context_id,
            "user_id": self.user_id,
            "evaluation_id": self.evaluation_id,
            "source_entity_id": self.source_entity_id,
            "action": self.action,
            "actor": self.actor,
            "metadata": thaw_json(self.metadata),
            "result": thaw_json(self.result),
            "contexts": sorted(self.contexts),
        }


class CorrelationEngine:
    """Correlate observations without inferring causality from time alone.

    Context and evaluation matches establish a strong relationship, but
    ``causality_asserted`` is still false.  It becomes true only when the caller
    supplies explicit causal evidence (for example, a propagated diagnostic
    stage saying that one action directly produced the next one).
    """

    def __init__(self, *, max_roots: int = 2_000, retention_seconds: int = 7_200) -> None:
        if max_roots < 10:
            raise ValueError("max_roots deve ser ao menos 10")
        if retention_seconds < 60:
            raise ValueError("retention_seconds deve ser ao menos 60")
        self._max_roots = max_roots
        self._retention = timedelta(seconds=retention_seconds)
        self._roots: dict[str, _CorrelationRoot] = {}
        self._order: deque[str] = deque()
        self._by_context: dict[str, str] = {}
        self._by_evaluation: dict[str, str] = {}

    def begin(
        self,
        *,
        context: Any = None,
        context_id: str | None = None,
        parent_context_id: str | None = None,
        user_id: str | None = None,
        evaluation_id: str | None = None,
        source_entity_id: str | None = None,
        action: str | None = None,
        actor: str | None = None,
        correlation_id: str | None = None,
        started_at: Any = None,
        metadata: Any = None,
    ) -> CorrelationResult:
        self._prune(_as_datetime(started_at))
        context_id = context_id or _read(context, "id")
        parent_context_id = parent_context_id or _read(context, "parent_id")
        user_id = user_id or _read(context, "user_id")
        correlation_id = str(correlation_id or uuid4())
        if correlation_id in self._roots:
            root = self._roots[correlation_id]
            return self._result(
                root,
                CorrelationRelation.EXPLICIT,
                1.0,
                evidence=("correlation_id já registrado",),
            )
        root = _CorrelationRoot(
            correlation_id=correlation_id,
            started_at=_as_datetime(started_at),
            context_id=str(context_id) if context_id else None,
            parent_context_id=str(parent_context_id) if parent_context_id else None,
            user_id=str(user_id) if user_id else None,
            evaluation_id=str(evaluation_id) if evaluation_id else None,
            source_entity_id=str(source_entity_id) if source_entity_id else None,
            action=str(action) if action else None,
            actor=str(actor) if actor else None,
            metadata=freeze_json(metadata) if metadata is not None else None,
        )
        if root.context_id:
            root.contexts.add(root.context_id)
            self._by_context[root.context_id] = correlation_id
        if root.evaluation_id:
            self._by_evaluation[root.evaluation_id] = correlation_id
        self._roots[correlation_id] = root
        self._order.append(correlation_id)
        self._enforce_capacity()
        return self._result(
            root,
            CorrelationRelation.NONE,
            0.0,
            evidence=("nova correlação sem relação anterior determinada",),
        )

    def resolve(
        self,
        *,
        explicit_id: str | None = None,
        correlation_id: str | None = None,
        context: Any = None,
        context_id: str | None = None,
        parent_context_id: str | None = None,
        user_id: str | None = None,
        evaluation_id: str | None = None,
        source_entity_id: str | None = None,
        action: str | None = None,
        occurred_at: Any = None,
        temporal_window_seconds: int = 30,
        allow_temporal: bool = True,
        allow_temporal_proximity: bool = True,
        create_if_missing: bool = True,
        causal_evidence: str | None = None,
    ) -> CorrelationResult | None:
        when = _as_datetime(occurred_at)
        self._prune(when)
        context_id = context_id or _read(context, "id")
        parent_context_id = parent_context_id or _read(context, "parent_id")
        user_id = user_id or _read(context, "user_id")
        explicit_id = explicit_id or correlation_id

        if explicit_id:
            root = self._roots.get(str(explicit_id))
            if root is None:
                self.begin(
                    correlation_id=str(explicit_id),
                    context_id=context_id,
                    parent_context_id=parent_context_id,
                    user_id=user_id,
                    evaluation_id=evaluation_id,
                    source_entity_id=source_entity_id,
                    action=action,
                    started_at=when,
                )
                root = self._roots[str(explicit_id)]
            self._bind_values(
                root, context_id, parent_context_id, evaluation_id, user_id
            )
            relation = (
                CorrelationRelation.DIRECT_CAUSALITY
                if causal_evidence
                else CorrelationRelation.EXPLICIT
            )
            return self._result(
                root,
                relation,
                1.0,
                causality=bool(causal_evidence),
                evidence=(causal_evidence or "correlation_id propagado explicitamente",),
            )

        if evaluation_id and (root_id := self._by_evaluation.get(str(evaluation_id))):
            root = self._roots[root_id]
            self._bind_values(
                root, context_id, parent_context_id, evaluation_id, user_id
            )
            return self._result(
                root,
                CorrelationRelation.DIRECT_CAUSALITY
                if causal_evidence
                else CorrelationRelation.EVALUATION,
                1.0 if causal_evidence else 0.98,
                causality=bool(causal_evidence),
                evidence=(causal_evidence or "evaluation_id idêntico",),
            )

        if context_id and (root_id := self._by_context.get(str(context_id))):
            root = self._roots[root_id]
            self._bind_values(
                root, context_id, parent_context_id, evaluation_id, user_id
            )
            return self._result(
                root,
                CorrelationRelation.DIRECT_CAUSALITY
                if causal_evidence
                else CorrelationRelation.SAME_CONTEXT,
                1.0 if causal_evidence else 0.95,
                causality=bool(causal_evidence),
                evidence=(causal_evidence or "context.id idêntico",),
            )

        if parent_context_id and (root_id := self._by_context.get(str(parent_context_id))):
            root = self._roots[root_id]
            self._bind_values(
                root, context_id, parent_context_id, evaluation_id, user_id
            )
            return self._result(
                root,
                CorrelationRelation.DIRECT_CAUSALITY
                if causal_evidence
                else CorrelationRelation.DESCENDANT_CONTEXT,
                1.0 if causal_evidence else 0.90,
                causality=bool(causal_evidence),
                evidence=(causal_evidence or "context.parent_id aponta para contexto correlacionado",),
            )

        if allow_temporal and temporal_window_seconds > 0:
            window_seconds = min(int(temporal_window_seconds), 3_600)
            cutoff = when - timedelta(seconds=window_seconds)
            candidates: list[tuple[float, _CorrelationRoot, int]] = []
            for root_id in reversed(self._order):
                root = self._roots.get(root_id)
                if root is None:
                    continue
                if root.started_at < cutoff:
                    # Roots normally arrive chronologically, but replay/import
                    # callers may bind historical items out of order.
                    continue
                distance = abs((when - root.started_at).total_seconds())
                if distance > window_seconds:
                    continue
                matches = int(bool(source_entity_id and root.source_entity_id == source_entity_id))
                matches += int(bool(action and root.action == action))
                matches += int(bool(user_id and root.user_id == str(user_id)))
                candidates.append((distance, root, matches))
            if candidates:
                matched = [item for item in candidates if item[2] > 0]
                pool = matched or (candidates if allow_temporal_proximity else [])
                if pool:
                    distance, root, match_count = min(pool, key=lambda item: item[0])
                    if match_count:
                        relation = CorrelationRelation.PROBABLY_RELATED
                        strength = 0.75 if match_count > 2 else 0.65 if match_count > 1 else 0.50
                        evidence = ["dentro da janela temporal configurada"]
                        if source_entity_id and root.source_entity_id == source_entity_id:
                            evidence.append("mesma entidade de origem")
                        if action and root.action == action:
                            evidence.append("mesma ação")
                        if user_id and root.user_id == str(user_id):
                            evidence.append("mesmo usuário")
                    else:
                        relation = CorrelationRelation.TEMPORAL_PROXIMITY
                        strength = 0.20
                        evidence = [
                            "apenas proximidade temporal; não estabelece causalidade"
                        ]
                    return self._result(
                        root,
                        relation,
                        strength,
                        causality=False,
                        evidence=tuple(evidence),
                        temporal_distance=distance,
                        candidate_count=len(pool),
                    )

        if not create_if_missing:
            return None
        return self.begin(
            context=context,
            context_id=context_id,
            parent_context_id=parent_context_id,
            user_id=user_id,
            evaluation_id=evaluation_id,
            source_entity_id=source_entity_id,
            action=action,
            started_at=when,
        )

    def bind_context(
        self,
        context: Any = None,
        correlation_id: str | None = None,
        *,
        context_id: str | None = None,
        parent_context_id: str | None = None,
        user_id: str | None = None,
        evaluation_id: str | None = None,
    ) -> CorrelationResult:
        if not correlation_id:
            raise ValueError("correlation_id é obrigatório")
        context_id = context_id or _read(context, "id")
        parent_context_id = parent_context_id or _read(context, "parent_id")
        user_id = user_id or _read(context, "user_id")
        root = self._roots.get(str(correlation_id))
        if root is None:
            self.begin(
                correlation_id=str(correlation_id),
                context_id=context_id,
                parent_context_id=parent_context_id,
                user_id=user_id,
                evaluation_id=evaluation_id,
            )
            root = self._roots[str(correlation_id)]
        self._bind_values(root, context_id, parent_context_id, evaluation_id, user_id)
        return self._result(
            root,
            CorrelationRelation.DESCENDANT_CONTEXT,
            0.90,
            evidence=("contexto vinculado explicitamente",),
        )

    def complete(
        self,
        correlation_id: str,
        *,
        completed_at: Any = None,
        result: Any = None,
    ) -> dict[str, Any] | None:
        root = self._roots.get(str(correlation_id))
        if root is None:
            return None
        root.completed_at = _as_datetime(completed_at)
        root.result = freeze_json(result) if result is not None else None
        return root.as_dict()

    def snapshot(self) -> dict[str, Any]:
        self._prune(datetime.now(timezone.utc))
        roots = [
            self._roots[root_id].as_dict()
            for root_id in self._order
            if root_id in self._roots
        ]
        return {
            "active_count": sum(1 for item in roots if item["completed_at"] is None),
            "total_retained": len(roots),
            "roots": roots,
        }

    def _bind_values(
        self,
        root: _CorrelationRoot,
        context_id: Any,
        parent_context_id: Any,
        evaluation_id: Any,
        user_id: Any = None,
    ) -> None:
        if context_id:
            context_text = str(context_id)
            root.contexts.add(context_text)
            self._by_context[context_text] = root.correlation_id
        if parent_context_id and str(parent_context_id) not in self._by_context:
            # Retain the relationship as metadata but never claim that an unknown
            # parent proves ancestry to this correlation.
            root.parent_context_id = str(parent_context_id)
        if evaluation_id:
            evaluation_text = str(evaluation_id)
            root.evaluation_id = root.evaluation_id or evaluation_text
            self._by_evaluation[evaluation_text] = root.correlation_id
        if user_id and not root.user_id:
            root.user_id = str(user_id)

    @staticmethod
    def _result(
        root: _CorrelationRoot,
        relation: CorrelationRelation,
        strength: float,
        *,
        causality: bool = False,
        evidence: tuple[str, ...] = (),
        temporal_distance: float | None = None,
        candidate_count: int = 1,
    ) -> CorrelationResult:
        return CorrelationResult(
            correlation_id=root.correlation_id,
            relation=relation.value,
            strength=max(0.0, min(1.0, float(strength))),
            causality_asserted=bool(causality),
            partial=relation
            in {
                CorrelationRelation.PROBABLY_RELATED,
                CorrelationRelation.TEMPORAL_PROXIMITY,
                CorrelationRelation.NONE,
            },
            evidence=tuple(str(item) for item in evidence),
            evaluation_id=root.evaluation_id,
            root_context_id=root.context_id,
            root_started_at=root.started_at.isoformat(),
            temporal_distance_seconds=(
                round(float(temporal_distance), 6)
                if temporal_distance is not None
                else None
            ),
            candidate_count=max(1, int(candidate_count)),
        )

    def _remove(self, correlation_id: str) -> None:
        root = self._roots.pop(correlation_id, None)
        if root is None:
            return
        for context_id in tuple(root.contexts):
            if self._by_context.get(context_id) == correlation_id:
                self._by_context.pop(context_id, None)
        if root.evaluation_id and self._by_evaluation.get(root.evaluation_id) == correlation_id:
            self._by_evaluation.pop(root.evaluation_id, None)

    def _prune(self, now: datetime) -> None:
        cutoff = now - self._retention
        while self._order:
            root = self._roots.get(self._order[0])
            if root is None:
                self._order.popleft()
                continue
            reference = root.completed_at or root.started_at
            if reference >= cutoff:
                break
            self._order.popleft()
            self._remove(root.correlation_id)
        self._enforce_capacity()

    def _enforce_capacity(self) -> None:
        while len(self._roots) > self._max_roots and self._order:
            self._remove(self._order.popleft())


__all__ = ["CorrelationEngine", "CorrelationResult"]
