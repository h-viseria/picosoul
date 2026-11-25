"""Sanitize tool ids for providers that disallow '.' in names."""

from __future__ import annotations

import re

# Anthropic / OpenAI: ^[a-zA-Z0-9_-]{1,128}$
_SAFE_NAME = re.compile(r"[^a-zA-Z0-9_-]+")


def safe_tool_name(name: str) -> str:
    return _SAFE_NAME.sub("__", name).strip("_") or "tool"


def build_safe_name_map(names: list[str]) -> dict[str, str]:
    """Return mapping safe_name -> original, avoiding collisions."""
    mapping: dict[str, str] = {}
    for original in names:
        safe = safe_tool_name(original)
        base = safe
        n = 2
        while safe in mapping and mapping[safe] != original:
            safe = f"{base}_{n}"
            n += 1
        mapping[safe] = original
    return mapping
