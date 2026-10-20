"""Load pure Agenda modules without starting a Home Assistant integration."""

from __future__ import annotations

from enum import StrEnum
from datetime import datetime, timezone
import importlib
from pathlib import Path
import sys
from types import ModuleType
from typing import Any
from unittest.mock import AsyncMock, Mock


REPOSITORY = Path(__file__).resolve().parents[2]
COMPONENT = REPOSITORY / "custom_components" / "elgin_supervisor_agenda"
PACKAGE = "custom_components.elgin_supervisor_agenda"


def load(name: str) -> Any:
    """Stub only the two HA type imports used by presets and constants."""
    if "homeassistant" not in sys.modules:
        ha = ModuleType("homeassistant")
        ha.__path__ = []
        sys.modules["homeassistant"] = ha
    if "homeassistant.const" not in sys.modules:
        constants = ModuleType("homeassistant.const")
        constants.Platform = StrEnum(
            "Platform", {key.upper(): key for key in ("calendar", "sensor", "binary_sensor", "switch", "button", "select")}
        )
        sys.modules["homeassistant.const"] = constants
    if "homeassistant.core" not in sys.modules:
        core = ModuleType("homeassistant.core")
        core.HomeAssistant = type("HomeAssistant", (), {})
        sys.modules["homeassistant.core"] = core
    if name in {"manager", "powers"}:
        sys.modules["homeassistant.const"].EVENT_STATE_CHANGED = "state_changed"
        core = sys.modules["homeassistant.core"]
        core.callback = lambda function: function
        core.Event = type("Event", (), {})
        for package_name in ("homeassistant.helpers", "homeassistant.util"):
            if package_name not in sys.modules:
                package = ModuleType(package_name)
                package.__path__ = []
                sys.modules[package_name] = package
        if "homeassistant.helpers.event" not in sys.modules:
            events = ModuleType("homeassistant.helpers.event")
            for function in ("async_call_later", "async_track_point_in_time", "async_track_state_change_event", "async_track_time_interval"):
                setattr(events, function, Mock(side_effect=lambda *args: Mock()))
            sys.modules["homeassistant.helpers.event"] = events
        if "homeassistant.helpers.storage" not in sys.modules:
            storage = ModuleType("homeassistant.helpers.storage")
            storage.Store = Mock(side_effect=lambda *args: Mock(async_load=AsyncMock(return_value=None), async_save=AsyncMock()))
            sys.modules["homeassistant.helpers.storage"] = storage
        if "homeassistant.util.dt" not in sys.modules:
            dates = ModuleType("homeassistant.util.dt")
            dates.now = lambda: datetime.now(timezone.utc)
            dates.as_local = lambda value: value
            dates.DEFAULT_TIME_ZONE = timezone.utc
            sys.modules["homeassistant.util.dt"] = dates
    for module_name, directory in (
        ("custom_components", COMPONENT.parent),
        (PACKAGE, COMPONENT),
    ):
        if module_name not in sys.modules:
            namespace = ModuleType(module_name)
            namespace.__path__ = [str(directory)]
            namespace.__package__ = module_name
            sys.modules[module_name] = namespace
    return importlib.import_module(f"{PACKAGE}.{name}")
