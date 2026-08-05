"""In-memory sanitized exports for Elgin Supervisor diagnostics."""

from __future__ import annotations

import base64
import csv
from datetime import datetime, timezone
from io import BytesIO, StringIO
import json
from typing import TYPE_CHECKING, Any
from zipfile import ZIP_DEFLATED, ZipFile

from .const import SENSITIVE_KEYS

if TYPE_CHECKING:
    from .manager import DiagnosticManager


REDACTED = "**REDACTED**"


def sanitize(value: Any, key: str | None = None) -> Any:
    """Recursively redact credentials, location and private URL-like fields."""
    if key and key.casefold() in SENSITIVE_KEYS:
        return REDACTED
    if isinstance(value, dict):
        return {str(item_key): sanitize(item, str(item_key)) for item_key, item in value.items()}
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize(item) for item in value]
    if isinstance(value, str):
        lowered = value.casefold()
        if any(marker in lowered for marker in ("bearer ", "api_key=", "access_token=", "password=")):
            return REDACTED
        if value.startswith(("http://192.168.", "https://192.168.", "http://10.", "https://10.")):
            return "**PRIVATE_URL_REDACTED**"
    return value


class DiagnosticExporter:
    def __init__(self, manager: DiagnosticManager) -> None:
        self.manager = manager

    async def async_create(
        self,
        export_type: str,
        filters: dict[str, Any] | None = None,
        *,
        limit: int = 5_000,
    ) -> dict[str, Any]:
        requested_limit = min(max(int(limit), 1), 5_000)
        events_raw: list[dict[str, Any]] = []
        cursor: str | None = None
        while len(events_raw) < requested_limit:
            page = await self.manager.storage.async_list_events(
                filters or {},
                cursor=cursor,
                limit=min(250, requested_limit - len(events_raw)),
                include_details=True,
            )
            events_raw.extend(page["events"])
            cursor = page.get("next_cursor")
            if not cursor:
                break
        events = sanitize(events_raw)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        if export_type == "csv":
            content = self._csv(events).encode("utf-8-sig")
            return self._response(f"elgin-auditoria-{timestamp}.csv", "text/csv", content)
        if export_type == "json":
            content = json.dumps(
                {"generated_at": datetime.now(timezone.utc).isoformat(), "events": events},
                ensure_ascii=False,
                indent=2,
            ).encode()
            return self._response(f"elgin-auditoria-{timestamp}.json", "application/json", content)
        if export_type == "problem_report":
            text = self._problem_report(events)
            return self._response(f"elgin-relatorio-{timestamp}.txt", "text/plain", text.encode())
        if export_type == "diagnostic_package":
            content = await self._package(events)
            return self._response(f"elgin-diagnostico-{timestamp}.zip", "application/zip", content)
        raise ValueError("Tipo de exportação inválido.")

    @staticmethod
    def _response(filename: str, mime_type: str, content: bytes) -> dict[str, Any]:
        return {
            "filename": filename,
            "mime_type": mime_type,
            "size_bytes": len(content),
            "content_base64": base64.b64encode(content).decode(),
        }

    @staticmethod
    def _csv(events: list[dict[str, Any]]) -> str:
        output = StringIO()
        columns = [
            "occurred_at_local",
            "category",
            "event_type",
            "severity",
            "outcome",
            "summary",
            "actor_name",
            "origin_class",
            "correlation_id",
            "transmission_id",
            "frame_kind",
            "frame_hash",
            "expected_audibility",
            "is_external",
            "is_anomaly",
        ]
        writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(events)
        return output.getvalue()

    async def _package(self, events: list[dict[str, Any]]) -> bytes:
        snapshot = sanitize(await self.manager.async_get_snapshot(include_recent=False))
        anomalies = sanitize(await self.manager.storage.async_list_anomalies(limit=500))
        human = self._problem_report(events)
        buffer = BytesIO()
        with ZipFile(buffer, "w", ZIP_DEFLATED) as archive:
            archive.writestr(
                "diagnostico.json",
                json.dumps(
                    {
                        "generated_at": datetime.now(timezone.utc).isoformat(),
                        "snapshot": snapshot,
                        "anomalies": anomalies,
                        "events": events,
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            )
            archive.writestr("relatorio.txt", human)
            transmissions = [item for item in events if item.get("transmission_id")]
            archive.writestr(
                "transmissoes.json",
                json.dumps(transmissions, ensure_ascii=False, indent=2),
            )
        return buffer.getvalue()

    @staticmethod
    def _problem_report(events: list[dict[str, Any]]) -> str:
        if not events:
            return "Nenhum evento foi encontrado para a consulta selecionada."
        beeps = [event for event in events if event.get("event_type") == "user.beep_observed"]
        sensor_updates = [
            event for event in events if str(event.get("event_type", "")).startswith("ir.sensor_update")
        ]
        full_frames = [event for event in events if str(event.get("event_type", "")).startswith("ir.full")]
        externals = [event for event in events if event.get("is_external")]
        lines = [
            "Relatório humano — Elgin Supervisor Auditoria e Diagnóstico",
            f"Eventos analisados: {len(events)}.",
            f"Bips observados: {len(beeps)}.",
            f"Eventos SensorUpdate: {len(sensor_updates)}.",
            f"Eventos de frame completo: {len(full_frames)}.",
            f"Mudanças externas: {len(externals)}.",
            "",
        ]
        if beeps:
            beep = beeps[0]
            quantity = (beep.get("details_json") or {}).get("quantity", "não informada")
            related = (beep.get("details_json") or {}).get("correlation_analysis", {})
            lines.append(
                f"Às {beep.get('occurred_at_local')} foi registrada a observação de {quantity}."
            )
            if related:
                lines.append(
                    "A correlação encontrou "
                    f"{related.get('sensor_update_count', 0)} SensorUpdate, "
                    f"{related.get('full_frame_count', 0)} frame(s) completo(s) e "
                    f"{related.get('external_change_count', 0)} mudança(s) externa(s)."
                )
                lines.append(
                    f"Classificação: {related.get('relation', 'sem evidência suficiente')} "
                    f"(confiança {related.get('confidence', 'baixa')})."
                )
        else:
            lines.append("Nenhuma observação manual de bip foi incluída nesta consulta.")
        lines.extend(
            [
                "",
                "Limite probatório: proximidade temporal indica correlação possível; não confirma emissão física nem causalidade.",
                "O status transmitted_by_software confirma somente que o software chamou o Remote Transmitter.",
            ]
        )
        return "\n".join(lines)
