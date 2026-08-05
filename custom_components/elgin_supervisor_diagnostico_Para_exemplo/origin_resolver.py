"""Actor and origin resolution for diagnostic events."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.core import Context, HomeAssistant

from .models import OriginConfidence


@dataclass(slots=True)
class Origin:
    user_id: str | None
    user_name: str | None
    actor_type: str
    actor_name: str
    origin_class: str
    origin_confidence: str


class OriginResolver:
    """Resolve Home Assistant users without inventing identities."""

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass
        self._user_cache: dict[str, str] = {}

    async def async_user_name(self, user_id: str | None) -> str | None:
        if not user_id:
            return None
        if user_id in self._user_cache:
            return self._user_cache[user_id]
        user = await self.hass.auth.async_get_user(user_id)
        if user is None:
            return None
        name = user.name or "Usuário do Home Assistant"
        self._user_cache[user_id] = name
        return name

    async def async_resolve(
        self,
        context: Context | None,
        *,
        source_component: str | None = None,
        is_external: bool = False,
        actor_hint: str | None = None,
        origin_hint: str | None = None,
    ) -> Origin:
        user_id = context.user_id if context else None
        user_name = await self.async_user_name(user_id)
        if user_name:
            return Origin(
                user_id=user_id,
                user_name=user_name,
                actor_type="home_assistant_user",
                actor_name=actor_hint or user_name,
                origin_class=origin_hint or "Interface do Home Assistant",
                origin_confidence=OriginConfidence.HIGH,
            )
        if is_external:
            return Origin(
                user_id=None,
                user_name=None,
                actor_type="external_physical_or_cloud",
                actor_name="Usuário físico/externo",
                origin_class="Origem exata não determinável pelo LocalTuya",
                origin_confidence=OriginConfidence.MEDIUM,
            )
        if actor_hint:
            return Origin(
                user_id=None,
                user_name=None,
                actor_type="system_component",
                actor_name=actor_hint,
                origin_class=origin_hint or "Automação local",
                origin_confidence=OriginConfidence.HIGH,
            )
        if source_component == "elgin_supervisor_agenda":
            return Origin(
                user_id=None,
                user_name=None,
                actor_type="agenda",
                actor_name="Agenda do Supervisor",
                origin_class="Regra temporal",
                origin_confidence=OriginConfidence.MEDIUM,
            )
        if source_component in {"elgin_supervisor", "yaml"}:
            return Origin(
                user_id=None,
                user_name=None,
                actor_type="supervisor",
                actor_name="Elgin Supervisor",
                origin_class="Automação local",
                origin_confidence=OriginConfidence.HIGH,
            )
        return Origin(
            user_id=None,
            user_name=None,
            actor_type="unknown",
            actor_name="Desconhecido",
            origin_class="Origem não determinada",
            origin_confidence=OriginConfidence.UNKNOWN,
        )

    def diagnostics(self) -> dict[str, Any]:
        return {"cached_users": len(self._user_cache)}
