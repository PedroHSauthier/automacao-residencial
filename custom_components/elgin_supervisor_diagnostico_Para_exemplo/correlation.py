"""Correlation helpers for multi-stage Elgin Supervisor flows."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import uuid4

from homeassistant.core import Context


@dataclass(slots=True)
class CorrelationEntry:
    correlation_id: str
    started_at: datetime
    context_id: str | None
    parent_context_id: str | None
    user_id: str | None
    source_entity_id: str | None
    actor: str


class CorrelationManager:
    """Resolve explicit IDs first, then HA context, then a narrow temporal match."""

    def __init__(self) -> None:
        self._by_context: dict[str, CorrelationEntry] = {}
        self._recent: deque[CorrelationEntry] = deque(maxlen=500)

    def begin(
        self,
        *,
        context: Context | None = None,
        source_entity_id: str | None = None,
        actor: str = "Sistema",
        correlation_id: str | None = None,
    ) -> CorrelationEntry:
        entry = CorrelationEntry(
            correlation_id=correlation_id or str(uuid4()),
            started_at=datetime.now(timezone.utc),
            context_id=context.id if context else None,
            parent_context_id=context.parent_id if context else None,
            user_id=context.user_id if context else None,
            source_entity_id=source_entity_id,
            actor=actor,
        )
        if entry.context_id:
            self._by_context[entry.context_id] = entry
        self._recent.append(entry)
        self._prune()
        return entry

    def resolve(
        self,
        *,
        explicit_id: str | None = None,
        context: Context | None = None,
        source_entity_id: str | None = None,
        max_age_seconds: int = 30,
    ) -> tuple[str, bool]:
        """Return correlation id and whether correlation is partial."""
        if explicit_id:
            if context and context.id:
                existing = self._by_context.get(context.id)
                if existing is None:
                    self._by_context[context.id] = CorrelationEntry(
                        correlation_id=explicit_id,
                        started_at=datetime.now(timezone.utc),
                        context_id=context.id,
                        parent_context_id=context.parent_id,
                        user_id=context.user_id,
                        source_entity_id=source_entity_id,
                        actor="Explícito",
                    )
            return explicit_id, False
        if context:
            if context.id and context.id in self._by_context:
                return self._by_context[context.id].correlation_id, False
            if context.parent_id and context.parent_id in self._by_context:
                parent = self._by_context[context.parent_id]
                if context.id:
                    self._by_context[context.id] = parent
                return parent.correlation_id, False
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=max_age_seconds)
        for entry in reversed(self._recent):
            if entry.started_at < cutoff:
                break
            if source_entity_id and entry.source_entity_id == source_entity_id:
                return entry.correlation_id, True
        return self.begin(context=context, source_entity_id=source_entity_id).correlation_id, True

    def bind_context(self, context: Context | None, correlation_id: str) -> None:
        if not context or not context.id:
            return
        self._by_context[context.id] = CorrelationEntry(
            correlation_id=correlation_id,
            started_at=datetime.now(timezone.utc),
            context_id=context.id,
            parent_context_id=context.parent_id,
            user_id=context.user_id,
            source_entity_id=None,
            actor="Contexto vinculado",
        )

    def snapshot(self) -> dict[str, Any]:
        self._prune()
        return {
            "active_contexts": len(self._by_context),
            "recent_roots": [
                {
                    "correlation_id": entry.correlation_id,
                    "started_at": entry.started_at.isoformat(),
                    "source_entity_id": entry.source_entity_id,
                    "actor": entry.actor,
                }
                for entry in list(self._recent)[-20:]
            ],
        }

    def _prune(self) -> None:
        cutoff = datetime.now(timezone.utc) - timedelta(hours=2)
        stale = [
            key for key, value in self._by_context.items() if value.started_at < cutoff
        ]
        for key in stale:
            self._by_context.pop(key, None)
