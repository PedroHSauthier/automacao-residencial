"""Transient, continuous proximity windows; never sends commands or stores timers."""

from __future__ import annotations

from datetime import datetime, timedelta
from math import ceil, isfinite
from typing import Any


def finite_number(value: Any) -> float | None:
    """Unavailable readings must break a window, never become zero."""
    try:
        number = float(value)
        return number if isfinite(number) else None
    except (TypeError, ValueError):
        return None


class ProximityTracker:
    """Keep one independent window for each mode's existing start criterion."""

    def __init__(self) -> None:
        self._windows: dict[str, dict[str, Any]] = {}

    def reset(self, mode: str | None = None) -> None:
        if mode is None:
            self._windows.clear()
        else:
            self._windows.pop(mode, None)

    @property
    def next_deadline(self) -> float | None:
        deadlines = [w["due"] for w in self._windows.values() if not w["ready"]]
        return min(deadlines) if deadlines else None

    def observe(self, metric: str, value: Any) -> None:
        """Process every sensor event, including short excursions between evaluations."""
        value = finite_number(value)
        for mode, window in tuple(self._windows.items()):
            if metric == window["metric"]:
                inside = value is not None and (
                    window["lower"] < value <= window["upper"] if mode == "heat"
                    else window["lower"] <= value < window["upper"]
                )
                if not inside:
                    self.reset(mode)
            if mode == "dry" and metric == "temperature":
                if value is None or value < window["minimum_temperature"]:
                    self.reset(mode)

    def evaluate(
        self, mode: str, preset: dict[str, Any], limits: dict[str, Any],
        value: Any, temperature: Any, allowed: bool, active: bool,
        now: datetime, monotonic_now: float,
    ) -> dict[str, Any]:
        """Return readiness without bypassing normal start, hysteresis or protections."""
        config = preset.get("proximity") or {}
        metric = "humidity" if mode == "dry" else "temperature"
        margin = finite_number(config.get(f"{metric}_margin"))
        minutes = finite_number(config.get("minutes"))
        start, stop = finite_number(limits.get("start")), finite_number(limits.get("stop"))
        minimum = finite_number(limits.get("minimum_temperature")) if mode == "dry" else None
        value, temperature = finite_number(value), finite_number(temperature)
        lower = round(start if mode == "heat" else start - margin, 6) if start is not None and margin is not None else None
        upper = round(start + margin if mode == "heat" else start, 6) if start is not None and margin is not None else None
        result = {
            "enabled": config.get("enabled", False) is True,
            "preset_id": preset.get("effective_id"),
            "metric": metric, "margin": margin, "minutes": minutes,
            "threshold": start, "stop": stop, "minimum_temperature": minimum,
            "lower": lower, "upper": upper,
            "ready": False, "started_at": None, "deadline": None,
            "remaining_seconds": None,
        }

        def finish(status: str, reason: str) -> dict[str, Any]:
            self.reset(mode)
            return {**result, "status": status, "reason": reason}

        if not result["enabled"]:
            return finish("disabled", "Antecipação desabilitada neste preset.")
        if not allowed:
            return finish("blocked", "Contagem suspensa: Supervisor, modo ou partida bloqueados.")
        if active:
            return finish("active", "Ciclo ativo; vale a condição normal de encerramento.")
        if value is None or start is None or stop is None:
            return finish("invalid", "Leitura ou limites indisponíveis; contagem zerada.")
        if mode == "dry" and (temperature is None or minimum is None or temperature < minimum):
            return finish("blocked", "Dry sem temperatura mínima válida; contagem zerada.")
        if (mode == "heat" and value <= start) or (mode != "heat" and value >= start):
            return finish("normal", "Limite normal atingido; não é necessário esperar a antecipação.")
        hysteresis = round(stop - start if mode == "heat" else start - stop, 6)
        if (margin is None or not 0 < margin < hysteresis
                or minutes is None or not 1 <= minutes <= 1440):
            return finish("invalid", "Faixa deve caber entre início e fim efetivos; contagem zerada.")
        inside = lower < value <= upper if mode == "heat" else lower <= value < upper
        if not inside:
            return finish("outside", "Fora da faixa de proximidade; contagem zerada.")

        identity = (preset.get("effective_id"), start, stop, minimum, margin, minutes)
        window = self._windows.get(mode)
        if window is None or window["identity"] != identity:
            duration = minutes * 60
            window = self._windows[mode] = {
                "identity": identity, "metric": metric, "lower": lower, "upper": upper,
                "minimum_temperature": minimum, "due": monotonic_now + duration,
                "started_at": now.isoformat(),
                "deadline": (now + timedelta(seconds=duration)).isoformat(), "ready": False,
            }
        remaining = max(0.0, window["due"] - monotonic_now)
        window["ready"] = remaining == 0
        result.update({
            "ready": window["ready"], "started_at": window["started_at"],
            "deadline": window["deadline"], "remaining_seconds": ceil(remaining),
            "status": "ready" if window["ready"] else "counting",
            "reason": "Tempo de proximidade cumprido; partida sujeita às proteções do Supervisor."
                if window["ready"] else "Permanência contínua na faixa de proximidade em contagem.",
        })
        return result
