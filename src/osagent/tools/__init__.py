"""Tool package — keep heavy imports lazy; still allow submodule imports."""

from __future__ import annotations

import importlib
from typing import Any

__all__ = ["ToolRegistry", "build_registry"]


def __getattr__(name: str) -> Any:
    if name in {"ToolRegistry", "build_registry"}:
        from osagent.tools.registry import ToolRegistry, build_registry

        return ToolRegistry if name == "ToolRegistry" else build_registry
    try:
        return importlib.import_module(f".{name}", __name__)
    except ModuleNotFoundError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
