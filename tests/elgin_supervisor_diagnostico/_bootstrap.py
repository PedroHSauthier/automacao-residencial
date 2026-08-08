"""Import pure integration modules without executing the HA package initializer."""

from __future__ import annotations

import importlib
from pathlib import Path
import sys
from types import ModuleType
from typing import Any


REPOSITORY = Path(__file__).resolve().parents[2]
CUSTOM_COMPONENTS = REPOSITORY / "custom_components"
COMPONENT = CUSTOM_COMPONENTS / "elgin_supervisor_diagnostico"
PACKAGE = "custom_components.elgin_supervisor_diagnostico"


def load(name: str) -> Any:
    """Load one pure module while bypassing the HA-dependent ``__init__``."""

    if "custom_components" not in sys.modules:
        namespace = ModuleType("custom_components")
        namespace.__path__ = [str(CUSTOM_COMPONENTS)]  # type: ignore[attr-defined]
        sys.modules["custom_components"] = namespace
    if PACKAGE not in sys.modules:
        namespace = ModuleType(PACKAGE)
        namespace.__path__ = [str(COMPONENT)]  # type: ignore[attr-defined]
        namespace.__package__ = PACKAGE
        sys.modules[PACKAGE] = namespace
    return importlib.import_module(f"{PACKAGE}.{name}")

