"""Agent package — keep imports lazy; still allow submodule imports."""

from __future__ import annotations

import importlib
from typing import Any

__all__ = ["Agent"]


def __getattr__(name: str) -> Any:
    if name == "Agent":
        from osagent.agent.loop import Agent

        return Agent
    try:
        return importlib.import_module(f".{name}", __name__)
    except ModuleNotFoundError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
