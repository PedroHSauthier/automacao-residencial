"""Sensor platform for Elgin Supervisor Agenda."""

from __future__ import annotations

from homeassistant.components.sensor import SensorDeviceClass, SensorEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import AgendaEntity
from .manager import AgendaManager


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    manager: AgendaManager = entry.runtime_data
    async_add_entities(
        [
            AgendaPolicySensor(manager),
            AgendaRulesSensor(manager),
            AgendaNextTransitionSensor(manager),
            AgendaConflictSensor(manager),
            AgendaCatalogSensor(manager),
            PresetCatalogSensor(manager),
            PowerCatalogSensor(manager),
        ]
    )


class AgendaPolicySensor(AgendaEntity, SensorEntity):
    _attr_icon = "mdi:calendar-filter"

    def __init__(self, manager: AgendaManager) -> None:
        super().__init__(manager, "policy", "Política")

    @property
    def native_value(self):
        return self.manager.policy["state"]

    @property
    def extra_state_attributes(self):
        return dict(self.manager.policy)


class AgendaRulesSensor(AgendaEntity, SensorEntity):
    _attr_icon = "mdi:format-list-bulleted-square"

    def __init__(self, manager: AgendaManager) -> None:
        super().__init__(manager, "active_rules", "Regras ativas")

    @property
    def native_value(self):
        return self.manager.policy.get("active_count", 0)

    @property
    def extra_state_attributes(self):
        return {
            "regras": self.manager.policy.get("active_rule_names", []),
            "ocorrencias": [
                {
                    **item,
                    "start": item["start"].isoformat(),
                    "end": item["end"].isoformat(),
                }
                for item in self.manager.current_occurrences
            ],
            "total_cadastradas": len(self.manager.rules),
        }


class AgendaNextTransitionSensor(AgendaEntity, SensorEntity):
    _attr_icon = "mdi:clock-fast"
    _attr_device_class = SensorDeviceClass.TIMESTAMP

    def __init__(self, manager: AgendaManager) -> None:
        super().__init__(manager, "next_transition", "Próxima transição")

    @property
    def native_value(self):
        return self.manager.next_transition


class AgendaConflictSensor(AgendaEntity, SensorEntity):
    _attr_icon = "mdi:calendar-alert"

    def __init__(self, manager: AgendaManager) -> None:
        super().__init__(manager, "conflicts", "Conflitos")

    @property
    def native_value(self):
        return len(self.manager.policy.get("conflicts", []))

    @property
    def extra_state_attributes(self):
        return {"conflitos": self.manager.policy.get("conflicts", [])}


class AgendaCatalogSensor(AgendaEntity, SensorEntity):
    _attr_icon = "mdi:book-open-variant"

    def __init__(self, manager: AgendaManager) -> None:
        super().__init__(manager, "catalog", "Catálogo")

    @property
    def native_value(self):
        return "Atualizado"

    @property
    def extra_state_attributes(self):
        return dict(self.manager.catalog)


class PresetCatalogSensor(AgendaEntity, SensorEntity):
    _attr_icon = "mdi:tune-variant"

    def __init__(self, manager: AgendaManager) -> None:
        super().__init__(manager, "presets", "Presets de condição")

    @property
    def native_value(self):
        return self.manager.preset_state.get("preset_in_use", "Nenhum")

    @property
    def extra_state_attributes(self):
        return {
            **dict(self.manager.preset_state),
            "catalog": self.manager.catalog.get("presets", {}),
            "base_presets": dict(self.manager.base_presets),
            "default_presets": self.manager.catalog.get("default_presets", {}),
            "preset_count": len(self.manager.presets),
        }


class PowerCatalogSensor(AgendaEntity, SensorEntity):
    """Expose dynamic power profiles, rules, limits and calculation diagnostics."""

    _attr_icon = "mdi:gauge-full"

    def __init__(self, manager: AgendaManager) -> None:
        super().__init__(manager, "powers", "Potências")

    @property
    def native_value(self):
        return self.manager.power_state.get("profile_in_use", "Nenhum")

    @property
    def extra_state_attributes(self):
        return {
            **dict(self.manager.power_state),
            "profiles": self.manager.catalog.get("power_profiles", {}),
            "base_profiles": dict(self.manager.base_power_profiles),
            "profile_count": len(self.manager.power_profiles),
            "rule_count": len(self.manager.power_rules),
            "settings": dict(self.manager.power_settings),
        }
