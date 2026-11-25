"""Shared intent match type (avoids circular imports)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass
class IntentMatch:
    tool_id: str
    args: dict[str, Any]
    label: str
