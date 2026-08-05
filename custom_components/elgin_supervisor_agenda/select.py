"""Select platform for Elgin Supervisor Agenda."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import MODE_NAMES, MODES
from .entity import AgendaEntity
from .manager import AgendaManager
from .powers import find_power_profile
from .presets import find_preset


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    manager: AgendaManager = entry.runtime_data
    async_add_entities(
        [PresetBaseSelect(manager, mode) for mode in MODES]
        + [PowerBaseSelect(manager, mode) for mode in MODES]
    )


class PresetBaseSelect(AgendaEntity, SelectEntity):
    """Select the persistent base preset for exactly one climate mode."""

    _attr_icon = "mdi:tune-variant"

    def __init__(self, manager: AgendaManager, mode: str) -> None:
        self.mode = mode
        super().__init__(
            manager,
            f"preset_base_{mode}",
            f"Preset base de {MODE_NAMES[mode].lower()}",
        )

    @property
    def options(self) -> list[str]:
        return [
            item["name"]
            for item in sorted(
                [
                    preset
                    for preset in self.manager.presets
                    if preset["mode"] == self.mode and preset.get("enabled", True)
                ],
                key=lambda preset: (preset["level"], preset["name"].casefold()),
            )
        ]

    @property
    def current_option(self) -> str | None:
        preset = find_preset(
            self.manager.presets,
            self.manager.base_presets.get(self.mode),
            self.mode,
        )
        return preset["name"] if preset else None

    @property
    def extra_state_attributes(self):
        preset = find_preset(
            self.manager.presets,
            self.manager.base_presets.get(self.mode),
            self.mode,
        )
        return {
            "modo": self.mode,
            "modo_nome": MODE_NAMES[self.mode],
            "preset_id": preset["id"] if preset else None,
            "nivel": preset["level"] if preset else None,
        }

    async def async_select_option(self, option: str) -> None:
        preset = next(
            (
                item
                for item in self.manager.presets
                if item["mode"] == self.mode
                and item.get("enabled", True)
                and item["name"] == option
            ),
            None,
        )
        if preset is None:
            raise ValueError(f"Preset base inválido para {MODE_NAMES[self.mode]}: {option}")
        await self.manager.async_set_base_preset(self.mode, preset["id"])


class PowerBaseSelect(AgendaEntity, SelectEntity):
    """Select the persistent base power profile and manual fallback per mode."""

    _attr_icon = "mdi:gauge"

    def __init__(self, manager: AgendaManager, mode: str) -> None:
        self.mode = mode
        super().__init__(
            manager,
            f"power_base_{mode}",
            f"Potência base e fallback de {MODE_NAMES[mode].lower()}",
        )

    @property
    def options(self) -> list[str]:
        return [
            item["name"]
            for item in sorted(
                [
                    profile
                    for profile in self.manager.power_profiles
                    if profile["mode"] == self.mode and profile.get("enabled", True)
                ],
                key=lambda profile: (profile["level"], profile["name"].casefold()),
            )
        ]

    @property
    def current_option(self) -> str | None:
        profile = find_power_profile(
            self.manager.power_profiles,
            self.manager.base_power_profiles.get(self.mode),
            self.mode,
        )
        return profile["name"] if profile else None

    @property
    def extra_state_attributes(self):
        profile = find_power_profile(
            self.manager.power_profiles,
            self.manager.base_power_profiles.get(self.mode),
            self.mode,
        )
        return {
            "modo": self.mode,
            "modo_nome": MODE_NAMES[self.mode],
            "profile_id": profile["id"] if profile else None,
            "nivel": profile["level"] if profile else None,
            "temperatura_alvo": profile["target_temperature"] if profile else None,
            "ventilacao": profile["fan"] if profile else None,
            "funcao": "Potência base e fallback manual do modo",
        }

    async def async_select_option(self, option: str) -> None:
        profile = next(
            (
                item
                for item in self.manager.power_profiles
                if item["mode"] == self.mode
                and item.get("enabled", True)
                and item["name"] == option
            ),
            None,
        )
        if profile is None:
            raise ValueError(f"Potência base inválida para {MODE_NAMES[self.mode]}: {option}")
        await self.manager.async_set_base_power_profile(self.mode, profile["id"])
