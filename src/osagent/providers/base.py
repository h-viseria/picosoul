"""LLM provider interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ChatMessage:
    role: str
    content: str


@dataclass
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any] = field(default_factory=dict)


@dataclass
class ChatResult:
    content: str
    raw: dict[str, Any] = field(default_factory=dict)
    tool_calls: list[dict[str, Any]] = field(default_factory=list)


class LLMProvider(ABC):
    @abstractmethod
    def chat(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[ToolSpec] | None = None,
    ) -> ChatResult:
        raise NotImplementedError

    @abstractmethod
    def describe(self) -> str:
        raise NotImplementedError
