"""Providers package — keep imports lazy; still allow submodule imports."""

from __future__ import annotations

import importlib
from typing import Any

__all__ = ["create_provider"]


def __getattr__(name: str) -> Any:
    if name == "create_provider":
        from osagent.providers.factory import create_provider

        return create_provider
    try:
        return importlib.import_module(f".{name}", __name__)
    except ModuleNotFoundError as exc:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}") from exc
