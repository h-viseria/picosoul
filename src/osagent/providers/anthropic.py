"""Anthropic Messages API (Claude Sonnet / Opus)."""

from __future__ import annotations

import json
from typing import Any

import httpx

from osagent.providers.base import ChatMessage, ChatResult, LLMProvider, ToolSpec
from osagent.providers.tool_names import build_safe_name_map


class AnthropicProvider(LLMProvider):
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        base_url: str = "https://api.anthropic.com",
        max_tokens: int = 2048,
        temperature: float = 0.2,
        api_version: str = "2023-06-01",
        timeout: float = 180.0,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.api_version = api_version
        self.timeout = timeout
        self._name_map: dict[str, str] = {}  # safe -> original

    def describe(self) -> str:
        return f"anthropic: model={self.model} endpoint={self.base_url}"

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[ToolSpec] | None = None,
    ) -> ChatResult:
        system_parts: list[str] = []
        api_messages: list[dict[str, Any]] = []
        for msg in messages:
            if msg.role == "system":
                system_parts.append(msg.content)
                continue
            role = msg.role if msg.role in {"user", "assistant"} else "user"
            # Merge consecutive same-role messages (Anthropic requirement)
            if api_messages and api_messages[-1]["role"] == role:
                prev = api_messages[-1]["content"]
                if isinstance(prev, str):
                    api_messages[-1]["content"] = prev + "\n\n" + msg.content
                else:
                    api_messages[-1]["content"] = msg.content
            else:
                api_messages.append({"role": role, "content": msg.content})

        if not api_messages:
            api_messages = [{"role": "user", "content": "Hello"}]

        payload: dict[str, Any] = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "messages": api_messages,
        }
        if system_parts:
            payload["system"] = "\n\n".join(system_parts)

        self._name_map = {}
        if tools:
            # Anthropic rejects '.' in tool names — sanitize and map back
            self._name_map = build_safe_name_map([t.name for t in tools])
            reverse = {orig: safe for safe, orig in self._name_map.items()}
            payload["tools"] = []
            for t in tools:
                desc = t.description or ""
                if len(desc) > 400:
                    desc = desc[:397] + "..."
                params = t.parameters or {"type": "object", "properties": {}}
                if not isinstance(params, dict):
                    params = {"type": "object", "properties": {}}
                params.setdefault("type", "object")
                params.setdefault("properties", {})
                payload["tools"].append(
                    {
                        "name": reverse.get(t.name, t.name),
                        "description": desc,
                        "input_schema": params,
                    }
                )

        headers = {
            "Content-Type": "application/json",
            "x-api-key": self.api_key,
            "anthropic-version": self.api_version,
        }
        url = f"{self.base_url}/v1/messages"
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(url, headers=headers, json=payload)
            if response.status_code >= 400:
                detail = response.text[:800]
                raise RuntimeError(
                    f"Anthropic API {response.status_code}: {detail}"
                )
            data = response.json()

        text_parts: list[str] = []
        tool_calls: list[dict[str, Any]] = []
        for block in data.get("content") or []:
            btype = block.get("type")
            if btype == "text":
                text_parts.append(block.get("text") or "")
            elif btype == "tool_use":
                safe = block.get("name") or ""
                real = self._name_map.get(safe, safe)
                tool_calls.append(
                    {
                        "id": block.get("id") or "",
                        "type": "function",
                        "function": {
                            "name": real,
                            "arguments": json.dumps(block.get("input") or {}),
                        },
                    }
                )

        return ChatResult(
            content="\n".join(p for p in text_parts if p).strip(),
            raw=data,
            tool_calls=tool_calls,
        )
