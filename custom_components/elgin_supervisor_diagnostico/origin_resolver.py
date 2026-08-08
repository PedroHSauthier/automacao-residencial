"""Conservative actor and origin resolution for Supervisor diagnostics."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from homeassistant.core import Context, HomeAssistant


@dataclass(frozen=True, slots=True)
class Origin:
    """Resolved origin without claiming more certainty than HA provides."""

    user_id: str | None
    user_name: str | None
    actor_type: str
    actor_name: str
    origin_class: str
    confidence: str
    evidence: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "user_name": self.user_name,
            "actor_type": self.actor_type,
            "actor_name": self.actor_name,
            "origin_class": self.origin_class,
            "origin_confidence": self.confidence,
            "origin_evidence": list(self.evidence),
        }


class OriginResolver:
    """Resolve HA users and classify system/external origins conservatively."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._users: dict[str, str | None] = {}

    async def async_user_name(self, user_id: str | None) -> str | None:
        if not user_id:
            return None
        if user_id in self._users:
            return self._users[user_id]
        try:
            user = await self.hass.auth.async_get_user(user_id)
            name = user.name if user else None
        except Exception:  # Diagnostic enrichment must never break collection.
            name = None
        self._users[user_id] = name
        return name

    async def async_resolve(
        self,
        context: Context | None,
        *,
        source_component: str | None = None,
        source_entity_id: str | None = None,
        actor_hint: str | None = None,
        origin_hint: str | None = None,
        external_observation: bool = False,
        resolve_user_name: bool = True,
    ) -> Origin:
        user_id = getattr(context, "user_id", None)
        user_name = await self.async_user_name(user_id) if resolve_user_name else None
        if user_id:
            return Origin(
                user_id,
                user_name,
                "home_assistant_user",
                user_name or "Usuário do Home Assistant",
                origin_hint or "Ação autenticada no Home Assistant",
                "high",
                ("context.user_id",),
            )

        if external_observation:
            return Origin(
                None,
                None,
                "external_or_indeterminate",
                actor_hint or "Origem externa ou indeterminada",
                origin_hint or "Mudança observada pelo LocalTuya",
                "low",
                ("sem context.user_id", "estado observado; não prova controle físico"),
            )

        source = source_component or "unknown"
        if source in {"automation", "script", "elgin_supervisor_climatico", "yaml"}:
            return Origin(
                None,
                None,
                "automation",
                actor_hint or "Supervisor climático",
                origin_hint or "Automação local",
                "high" if source in {"yaml", "elgin_supervisor_climatico"} else "medium",
                (f"source_component={source}",),
            )
        if source == "elgin_supervisor_agenda":
            return Origin(
                None,
                None,
                "integration",
                actor_hint or "Agenda do Supervisor",
                origin_hint or "Política temporal local",
                "high",
                ("evento da integração Agenda",),
            )
        if source == "elgin_supervisor_diagnostico":
            return Origin(
                None,
                None,
                "diagnostic",
                actor_hint or "Auditoria e diagnóstico",
                origin_hint or "Processamento interno do diagnóstico",
                "high",
                ("evento interno autoexcluído da captura de estado",),
            )
        return Origin(
            None,
            None,
            "system_or_indeterminate",
            actor_hint or (source_entity_id or source or "Sistema"),
            origin_hint or "Contexto sem usuário identificável",
            "low",
            tuple(item for item in (f"source_component={source}" if source else None,) if item),
        )

    def diagnostics(self) -> dict[str, Any]:
        return {"cached_users": len(self._users)}
