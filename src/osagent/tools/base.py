"""Tool capability definitions shared across platforms."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable


class ConfirmLevel(str, Enum):
    NONE = "none"
    ASK = "ask"
    DESTRUCTIVE = "destructive"


@dataclass
class ToolResult:
    ok: bool
    message: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class Tool:
    id: str
    description: str
    parameters: dict[str, Any]
    confirm: ConfirmLevel
    handler: Callable[[dict[str, Any]], ToolResult]
    platforms: tuple[str, ...] = ("windows", "linux")

    def to_spec_params(self) -> dict[str, Any]:
        return self.parameters
