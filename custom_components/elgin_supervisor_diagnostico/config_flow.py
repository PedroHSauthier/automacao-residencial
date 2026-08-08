"""Config and options flows for Elgin Supervisor diagnostics."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.config_entries import ConfigFlowResult
from homeassistant.core import callback
from homeassistant.helpers import config_validation as cv

from .const import (
    ANOMALY_TYPES,
    CAPTURE_MODES,
    DATE_FORMATS,
    DEFAULT_COLUMNS,
    DENSITIES,
    DETAIL_MODES,
    DOMAIN,
    NAME,
    SEVERITIES,
    default_options,
    merged_options,
)

ANOMALY_LABELS = {
    "commands_too_close": "Comandos muito próximos",
    "repeated_commands": "Comandos repetidos",
    "decision_oscillation": "Decisão oscilando",
    "desired_state_divergence": "Estado desejado divergente",
    "localtuya_not_confirmed": "LocalTuya sem confirmação",
    "external_change_reaction": "Mudança externa seguida por reação",
    "excessive_volume": "Volume excessivo",
    "repeated_error": "Erro repetitivo",
    "critical_entity_unavailable": "Entidade crítica indisponível",
}

COLUMN_LABELS = {
    "occurred_at": "Horário",
    "severity": "Severidade",
    "category": "Categoria",
    "summary": "Evento",
    "actor": "Ator",
    "origin": "Origem",
    "entity_id": "Entidade",
    "before": "Antes",
    "after": "Depois",
    "outcome": "Resultado",
    "correlation_id": "Correlação",
}

OPTIONS_MENU = (
    "capture",
    "retention",
    "compaction",
    "correlation",
    "anomalies",
    "notifications",
    "interface",
    "privacy",
    "maintenance",
    "reset_defaults",
)


def _required(
    current: Mapping[str, Any], key: str, _validator: Any | None = None
) -> vol.Marker:
    """Build a required marker; the schema dictionary supplies its validator."""

    return vol.Required(key, default=current[key])


def _validate_rate_thresholds(values: dict[str, Any]) -> dict[str, Any]:
    """Keep the warning threshold below the hard protection threshold."""

    if values["rate_warning_events"] > values["rate_hard_limit_events"]:
        raise vol.Invalid(
            "O alerta de volume não pode exceder o limite rígido de proteção"
        )
    return values


def _notification_service(value: Any) -> str:
    """Accept an empty value or one Home Assistant domain.service name."""

    service = cv.string(value).strip()
    if service and "." not in service:
        raise vol.Invalid("Use o formato domínio.serviço")
    return service


class ElginSupervisorDiagnosticoConfigFlow(
    config_entries.ConfigFlow, domain=DOMAIN
):
    """Create the one local diagnostic instance."""

    VERSION = 2
    MINOR_VERSION = 0

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        if self._async_current_entries():
            return self.async_abort(reason="single_instance_allowed")
        await self.async_set_unique_id(DOMAIN)
        self._abort_if_unique_id_configured()
        if user_input is not None:
            return self.async_create_entry(
                title=NAME,
                data={},
                options=default_options(),
            )
        return self.async_show_form(step_id="user", data_schema=vol.Schema({}))

    @staticmethod
    @callback
    def async_get_options_flow(
        config_entry: config_entries.ConfigEntry,
    ) -> config_entries.OptionsFlow:
        return DiagnosticOptionsFlow()


class DiagnosticOptionsFlow(config_entries.OptionsFlow):
    """Native fallback editor; the card remains the primary complete editor."""

    def __init__(self) -> None:
        self._current: dict[str, Any] | None = None

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        self._current = merged_options(dict(self.config_entry.options))
        return self.async_show_menu(step_id="init", menu_options=list(OPTIONS_MENU))

    def _save(self, changes: Mapping[str, Any]) -> ConfigFlowResult:
        if self._current is None:
            self._current = merged_options(dict(self.config_entry.options))
        changes = dict(changes)
        options = {**self._current, **changes}
        return self.async_create_entry(title="", data=options)

    async def async_step_capture(self, user_input=None) -> ConfigFlowResult:
        keys = (
            "capture_decisions",
            "capture_state_changes",
            "capture_service_calls",
            "capture_localtuya",
            "capture_climate",
            "capture_agenda",
            "capture_presets",
            "capture_power_profiles",
            "capture_protections",
            "capture_errors",
            "capture_external_changes",
        )
        if user_input is not None:
            return self._save(user_input)
        schema = {vol.Required("capture_mode", default=self._current["capture_mode"]): vol.In(CAPTURE_MODES)}
        schema.update({_required(self._current, key, bool): bool for key in keys})
        return self.async_show_form(step_id="capture", data_schema=vol.Schema(schema))

    async def async_step_retention(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(user_input)
        return self.async_show_form(
            step_id="retention",
            data_schema=vol.Schema(
                {
                    _required(self._current, "retention_essential_days", vol.All(vol.Coerce(int), vol.Range(min=1, max=3650))): vol.All(vol.Coerce(int), vol.Range(min=1, max=3650)),
                    _required(self._current, "retention_error_days", vol.All(vol.Coerce(int), vol.Range(min=1, max=365))): vol.All(vol.Coerce(int), vol.Range(min=1, max=365)),
                    _required(self._current, "retention_trace_days", vol.All(vol.Coerce(int), vol.Range(min=1, max=90))): vol.All(vol.Coerce(int), vol.Range(min=1, max=90)),
                }
            ),
        )

    async def async_step_compaction(self, user_input=None) -> ConfigFlowResult:
        keys = (
            "compaction_enabled",
            "compact_identical_evaluations",
            "compact_no_change",
            "compact_identical_states",
            "compact_repeated_blocks",
            "compact_repeated_unavailable",
        )
        if user_input is not None:
            return self._save(user_input)
        schema = {_required(self._current, key, bool): bool for key in keys}
        schema.update(
            {
                _required(self._current, "compaction_window_seconds", vol.All(vol.Coerce(int), vol.Range(min=1, max=3600))): vol.All(vol.Coerce(int), vol.Range(min=1, max=3600)),
                _required(self._current, "rate_window_seconds", vol.All(vol.Coerce(int), vol.Range(min=1, max=3600))): vol.All(vol.Coerce(int), vol.Range(min=1, max=3600)),
                _required(self._current, "rate_warning_events", vol.All(vol.Coerce(int), vol.Range(min=10, max=100000))): vol.All(vol.Coerce(int), vol.Range(min=10, max=100000)),
                _required(self._current, "rate_hard_limit_events", vol.All(vol.Coerce(int), vol.Range(min=100, max=1000000))): vol.All(vol.Coerce(int), vol.Range(min=100, max=1000000)),
            }
        )
        return self.async_show_form(
            step_id="compaction",
            data_schema=vol.Schema(vol.All(schema, _validate_rate_thresholds)),
        )

    async def async_step_correlation(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(user_input)
        ranges = {
            "correlation_window_seconds": (1, 600),
            "localtuya_confirmation_window_seconds": (1, 600),
            "external_observation_window_seconds": (1, 1800),
            "beep_window_before_seconds": (10, 1800),
            "beep_window_after_seconds": (10, 1800),
        }
        schema = {
            _required(self._current, key, vol.All(vol.Coerce(int), vol.Range(min=limits[0], max=limits[1]))): vol.All(vol.Coerce(int), vol.Range(min=limits[0], max=limits[1]))
            for key, limits in ranges.items()
        }
        return self.async_show_form(step_id="correlation", data_schema=vol.Schema(schema))

    async def async_step_anomalies(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(user_input)
        ranges = {
            "anomaly_close_commands_seconds": (1, 60),
            "anomaly_repeated_command_window_seconds": (1, 3600),
            "anomaly_oscillation_window_seconds": (10, 7200),
            "anomaly_oscillation_min_changes": (4, 50),
            "anomaly_divergence_seconds": (1, 3600),
            "anomaly_volume_window_seconds": (1, 3600),
            "anomaly_volume_event_limit": (10, 1000000),
            "anomaly_repeated_error_window_seconds": (1, 86400),
            "anomaly_repeated_error_count": (2, 1000),
            "anomaly_unavailable_seconds": (1, 86400),
        }
        schema: dict[Any, Any] = {
            _required(self._current, "anomalies_enabled", bool): bool,
            vol.Required("anomaly_enabled_types", default=self._current["anomaly_enabled_types"]): cv.multi_select(ANOMALY_LABELS)
        }
        schema.update(
            {
                _required(self._current, key, vol.All(vol.Coerce(int), vol.Range(min=limits[0], max=limits[1]))): vol.All(vol.Coerce(int), vol.Range(min=limits[0], max=limits[1]))
                for key, limits in ranges.items()
            }
        )
        return self.async_show_form(step_id="anomalies", data_schema=vol.Schema(schema))

    async def async_step_notifications(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(user_input)
        return self.async_show_form(
            step_id="notifications",
            data_schema=vol.Schema(
                {
                    _required(self._current, "notifications_enabled", bool): bool,
                    vol.Required("notification_min_severity", default=self._current["notification_min_severity"]): vol.In(SEVERITIES),
                    vol.Required("notification_types", default=self._current["notification_types"]): cv.multi_select(ANOMALY_LABELS),
                    _required(self._current, "notification_cooldown_seconds", vol.All(vol.Coerce(int), vol.Range(min=10, max=86400))): vol.All(vol.Coerce(int), vol.Range(min=10, max=86400)),
                    _required(self._current, "notification_persistent", bool): bool,
                    vol.Optional("notification_service", default=self._current["notification_service"]): _notification_service,
                }
            ),
        )

    async def async_step_interface(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(user_input)
        return self.async_show_form(
            step_id="interface",
            data_schema=vol.Schema(
                {
                    _required(self._current, "interface_items_per_page", vol.All(vol.Coerce(int), vol.Range(min=10, max=250))): vol.All(vol.Coerce(int), vol.Range(min=10, max=250)),
                    _required(self._current, "interface_auto_refresh", bool): bool,
                    vol.Required("interface_columns", default=self._current["interface_columns"]): cv.multi_select(COLUMN_LABELS),
                    vol.Required("interface_density", default=self._current["interface_density"]): vol.In(DENSITIES),
                    _required(self._current, "interface_show_technical_codes", bool): bool,
                    _required(self._current, "interface_show_unchanged_attributes", bool): bool,
                    vol.Required("interface_date_format", default=self._current["interface_date_format"]): vol.In(DATE_FORMATS),
                    vol.Required("interface_detail_mode", default=self._current["interface_detail_mode"]): vol.In(DETAIL_MODES),
                }
            ),
        )

    async def async_step_privacy(self, user_input=None) -> ConfigFlowResult:
        keys = (
            "privacy_resolve_user_names",
            "privacy_store_user_ids",
            "privacy_store_user_names",
            "privacy_capture_raw_events",
            "privacy_capture_service_data",
            "privacy_redact_sensitive_values",
        )
        if user_input is not None:
            return self._save(user_input)
        schema = {_required(self._current, key, bool): bool for key in keys}
        return self.async_show_form(step_id="privacy", data_schema=vol.Schema(schema))

    async def async_step_maintenance(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            return self._save(user_input)
        return self.async_show_form(
            step_id="maintenance",
            data_schema=vol.Schema(
                {
                    _required(self._current, "maintenance_database_limit_mb", vol.All(vol.Coerce(int), vol.Range(min=10, max=4096))): vol.All(vol.Coerce(int), vol.Range(min=10, max=4096)),
                    _required(self._current, "maintenance_cleanup_interval_hours", vol.All(vol.Coerce(int), vol.Range(min=1, max=168))): vol.All(vol.Coerce(int), vol.Range(min=1, max=168)),
                    _required(self._current, "maintenance_export_max_rows", vol.All(vol.Coerce(int), vol.Range(min=100, max=1000000))): vol.All(vol.Coerce(int), vol.Range(min=100, max=1000000)),
                    _required(self._current, "queue_limit", vol.All(vol.Coerce(int), vol.Range(min=100, max=100000))): vol.All(vol.Coerce(int), vol.Range(min=100, max=100000)),
                    _required(self._current, "critical_queue_limit", vol.All(vol.Coerce(int), vol.Range(min=100, max=100000))): vol.All(vol.Coerce(int), vol.Range(min=100, max=100000)),
                    _required(self._current, "batch_size", vol.All(vol.Coerce(int), vol.Range(min=1, max=5000))): vol.All(vol.Coerce(int), vol.Range(min=1, max=5000)),
                    _required(self._current, "flush_interval_seconds", vol.All(vol.Coerce(float), vol.Range(min=0.01, max=60))): vol.All(vol.Coerce(float), vol.Range(min=0.01, max=60)),
                    _required(self._current, "anonymize_entity_ids", bool): bool,
                }
            ),
        )

    async def async_step_reset_defaults(self, user_input=None) -> ConfigFlowResult:
        if user_input is not None:
            return self.async_create_entry(title="", data=default_options())
        return self.async_show_form(
            step_id="reset_defaults",
            data_schema=vol.Schema(
                {vol.Required("confirm", default=False): vol.In([True])}
            ),
        )
