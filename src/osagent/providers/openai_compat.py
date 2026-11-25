"""OpenAI-compatible chat completions (remote API or llama-server)."""

from __future__ import annotations

from typing import Any

import httpx

from osagent.providers.base import ChatMessage, ChatResult, LLMProvider, ToolSpec
from osagent.providers.tool_names import build_safe_name_map, safe_tool_name


class OpenAICompatProvider(LLMProvider):
    def __init__(
        self,
        *,
        base_url: str,
        model: str,
        api_key: str = "",
        max_tokens: int = 1024,
        temperature: float = 0.2,
        timeout: float = 120.0,
        label: str = "api",
        send_native_tools: bool = True,
        sanitize_tool_names: bool = True,
        max_tool_desc_chars: int = 160,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.max_tokens = max_tokens
        self.temperature = temperature
        self.timeout = timeout
        self.label = label
        self.send_native_tools = send_native_tools
        self.sanitize_tool_names = sanitize_tool_names
        self.max_tool_desc_chars = max_tool_desc_chars
        self._name_map: dict[str, str] = {}  # safe -> original

    def describe(self) -> str:
        return f"{self.label}: model={self.model} endpoint={self.base_url}"

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[ToolSpec] | None = None,
    ) -> ChatResult:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"

        payload: dict[str, Any] = {
            "model": self.model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
        }

        self._name_map = {}
        if tools and self.send_native_tools:
            api_tools = []
            if self.sanitize_tool_names:
                self._name_map = build_safe_name_map([t.name for t in tools])
                reverse = {orig: safe for safe, orig in self._name_map.items()}
            else:
                reverse = {}
            for t in tools:
                name = reverse.get(t.name, t.name) if self.sanitize_tool_names else t.name
                if self.sanitize_tool_names and name == t.name and "." in t.name:
                    name = safe_tool_name(t.name)
                desc = t.description or ""
                if len(desc) > self.max_tool_desc_chars:
                    desc = desc[: self.max_tool_desc_chars - 3] + "..."
                params = t.parameters or {"type": "object", "properties": {}}
                if not isinstance(params, dict):
                    params = {"type": "object", "properties": {}}
                if params.get("type") != "object":
                    params = {
                        "type": "object",
                        "properties": {"value": params},
                    }
                params.setdefault("properties", {})
                api_tools.append(
                    {
                        "type": "function",
                        "function": {
                            "name": name,
                            "description": desc,
                            "parameters": params,
                        },
                    }
                )
            payload["tools"] = api_tools
            payload["tool_choice"] = "auto"

        url = f"{self.base_url}/chat/completions"
        with httpx.Client(timeout=self.timeout) as client:
            response = client.post(url, headers=headers, json=payload)
            if response.status_code >= 400:
                body = (response.text or "")[:1200]
                raise RuntimeError(
                    f"LLM HTTP {response.status_code} from {url}: {body}"
                )
            data = response.json()

        choice = (data.get("choices") or [{}])[0]
        message = choice.get("message") or {}
        content = message.get("content") or ""
        raw_calls = message.get("tool_calls") or []
        tool_calls: list[dict[str, Any]] = []
        for call in raw_calls:
            call = dict(call)
            fn = dict(call.get("function") or {})
            safe_name = fn.get("name") or ""
            if safe_name in self._name_map:
                fn["name"] = self._name_map[safe_name]
            call["function"] = fn
            tool_calls.append(call)
        return ChatResult(content=content, raw=data, tool_calls=tool_calls)
