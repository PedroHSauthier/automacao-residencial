"""Sanitized CSV, JSON, human report and diagnostic package exports."""

from __future__ import annotations

import asyncio
import base64
import csv
from datetime import datetime, timezone
from io import BytesIO, StringIO
import json
import re
from typing import TYPE_CHECKING, Any, Mapping
from zipfile import ZIP_DEFLATED, ZipFile

from .const import SENSITIVE_KEYS

if TYPE_CHECKING:
    from .manager import DiagnosticManager

REDACTED = "**REDACTED**"
ENTITY_RE = re.compile(r"\b([a-z_]+)\.([a-z0-9_]+)\b", re.IGNORECASE)


def sanitize(value: Any, key: str | None = None, *, anonymize_entities: bool = False) -> Any:
    """Recursively redact secrets and optionally anonymize entity object IDs."""
    normalized = (key or "").lower().replace("-", "_")
    if any(secret in normalized for secret in SENSITIVE_KEYS):
        return REDACTED
    if isinstance(value, Mapping):
        return {
            str(item_key): sanitize(
                item_value, str(item_key), anonymize_entities=anonymize_entities
            )
            for item_key, item_value in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [sanitize(item, key, anonymize_entities=anonymize_entities) for item in value]
    if isinstance(value, str):
        text = value
        if anonymize_entities:
            text = ENTITY_RE.sub(lambda match: f"{match.group(1)}.entidade_{abs(hash(match.group(0))) % 100000:05d}", text)
        return text
    return value


class DiagnosticExporter:
    def __init__(self, manager: DiagnosticManager) -> None:
        self.manager = manager

    async def async_create(
        self,
        export_format: str,
        filters: Mapping[str, Any] | None = None,
        *,
        include_details: bool = True,
    ) -> dict[str, Any]:
        if export_format not in {"csv", "json", "text", "diagnostic_package"}:
            raise ValueError("Formato de exportação inválido")
        maximum = int(getattr(self.manager.settings, "export_max_events", 10_000))
        events = await self._async_collect(filters or {}, maximum, include_details)
        anonymize = bool(getattr(self.manager.settings, "anonymize_entity_ids", False))
        safe_events = sanitize(events, anonymize_entities=anonymize)
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        if export_format == "csv":
            content = await asyncio.to_thread(self._csv, safe_events)
            return self._response(f"elgin-diagnostico-{timestamp}.csv", "text/csv", content.encode())
        if export_format == "json":
            content = json.dumps(
                {"exported_at": datetime.now(timezone.utc).isoformat(), "events": safe_events},
                ensure_ascii=False,
                indent=2,
            ).encode()
            return self._response(f"elgin-diagnostico-{timestamp}.json", "application/json", content)
        if export_format == "text":
            content = self._human_report(safe_events).encode()
            return self._response(f"elgin-diagnostico-{timestamp}.txt", "text/plain", content)
        fallback = sanitize(
            await self.manager.storage.async_get_fallback_snapshot(),
            anonymize_entities=anonymize,
        )
        package = await asyncio.to_thread(self._package, safe_events, fallback)
        return self._response(f"elgin-diagnostico-{timestamp}.zip", "application/zip", package)

    async def _async_collect(
        self, filters: Mapping[str, Any], maximum: int, include_details: bool
    ) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        cursor: str | None = None
        while len(result) < maximum:
            page = await self.manager.storage.async_list_events(
                filters,
                cursor=cursor,
                limit=min(250, maximum - len(result)),
                include_details=include_details,
            )
            items = page.get("items", [])
            result.extend(items)
            cursor = page.get("next_cursor")
            if not items or not page.get("has_more") or not cursor:
                break
        return result

    @staticmethod
    def _response(filename: str, mime_type: str, content: bytes) -> dict[str, Any]:
        return {
            "filename": filename,
            "mime_type": mime_type,
            "size_bytes": len(content),
            "content_base64": base64.b64encode(content).decode("ascii"),
        }

    @staticmethod
    def _csv(events: list[dict[str, Any]]) -> str:
        output = StringIO()
        columns = [
            "occurred_at_local", "event_id", "evaluation_id", "correlation_id",
            "category", "event_type", "severity", "outcome", "summary",
            "actor_name", "user_name", "origin_class", "source_entity_id",
            "climate_mode", "treatment", "preset", "power_profile", "agenda_state",
            "protection", "function", "expected_audibility", "transmission_id",
            "confirmation_state", "is_external", "changed_fields_relevant",
            "before_json", "after_json", "diff_json", "desired_json", "confirmed_json",
        ]
        writer = csv.DictWriter(output, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for event in events:
            row = dict(event)
            for key in columns:
                if isinstance(row.get(key), (dict, list)):
                    row[key] = json.dumps(row[key], ensure_ascii=False, separators=(",", ":"))
            writer.writerow(row)
        return output.getvalue()

    def _package(
        self, events: list[dict[str, Any]], fallback: Mapping[str, Any]
    ) -> bytes:
        output = BytesIO()
        snapshot = sanitize(self.manager.status_snapshot())
        with ZipFile(output, "w", ZIP_DEFLATED) as archive:
            archive.writestr(
                "manifest.json",
                json.dumps(
                    {
                        "format": "elgin_supervisor_diagnostico",
                        "version": 2,
                        "exported_at": datetime.now(timezone.utc).isoformat(),
                        "event_count": len(events),
                        "privacy": "segredos removidos; causalidade física não presumida",
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            )
            archive.writestr("eventos.json", json.dumps(events, ensure_ascii=False, indent=2))
            archive.writestr("eventos.csv", self._csv(events))
            archive.writestr("relatorio.txt", self._human_report(events))
            archive.writestr("saude.json", json.dumps(snapshot, ensure_ascii=False, indent=2))
            if (fallback.get("status") or {}).get("degraded"):
                archive.writestr(
                    "fallback_pendente_sanitizado.json",
                    json.dumps(fallback, ensure_ascii=False, indent=2),
                )
        return output.getvalue()

    @staticmethod
    def _human_report(events: list[dict[str, Any]]) -> str:
        lines = [
            "ELGIN SUPERVISOR — RELATÓRIO DE AUDITORIA",
            f"Gerado em: {datetime.now(timezone.utc).isoformat()}",
            f"Eventos: {len(events)}",
            "",
            "Nota: 'solicitado pelo Home Assistant' não confirma emissão física nem recepção pelo aparelho.",
            "Uma relação temporal isolada é apresentada como hipótese, não como causa.",
            "",
        ]
        for event in reversed(events):
            when = event.get("occurred_at_local") or event.get("occurred_at") or "—"
            lines.append(
                f"[{when}] {event.get('severity', 'info').upper()} · "
                f"{event.get('event_type', 'evento')} · {event.get('summary', '')}"
            )
            detail = [
                f"ator={event.get('actor_name')}" if event.get("actor_name") else None,
                f"modo={event.get('climate_mode')}" if event.get("climate_mode") else None,
                f"tratamento={event.get('treatment')}" if event.get("treatment") else None,
                f"preset={event.get('preset')}" if event.get("preset") else None,
                f"potência={event.get('power_profile')}" if event.get("power_profile") else None,
                f"audibilidade={event.get('expected_audibility')}" if event.get("expected_audibility") else None,
                f"correlação={event.get('correlation_id')}" if event.get("correlation_id") else None,
            ]
            if any(detail):
                lines.append("  " + " · ".join(item for item in detail if item))
        return "\n".join(lines) + "\n"
