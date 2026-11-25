"""Register and run platform tool catalogs."""

from __future__ import annotations

from typing import Any

from osagent.platform_info import HostOS
from osagent.providers.base import ToolSpec
from osagent.tools.base import ConfirmLevel, Tool, ToolResult


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        self._tools[tool.id] = tool

    def register_many(self, tools: list[Tool]) -> None:
        for tool in tools:
            self.register(tool)

    def list_tools(self) -> list[Tool]:
        return list(self._tools.values())

    def get(self, tool_id: str) -> Tool | None:
        tool = self._tools.get(tool_id)
        if tool is not None:
            return tool
        # Providers may sanitize dots → underscores (windows.display.info → windows__display__info)
        if "__" in tool_id or "_" in tool_id:
            dotted = tool_id.replace("__", ".")
            tool = self._tools.get(dotted)
            if tool is not None:
                return tool
        return None

    def as_provider_specs(self) -> list[ToolSpec]:
        return [
            ToolSpec(
                name=t.id,
                description=t.description,
                parameters=t.to_spec_params(),
            )
            for t in self._tools.values()
        ]

    def run(
        self,
        tool_id: str,
        args: dict[str, Any],
        *,
        confirm_destructive: bool,
        ask: Any = input,
    ) -> ToolResult:
        tool = self.get(tool_id)
        if tool is None:
            return ToolResult(ok=False, message=f"Unknown tool: {tool_id}")
        tool_id = tool.id

        if tool.confirm != ConfirmLevel.NONE and confirm_destructive:
            if tool.confirm == ConfirmLevel.DESTRUCTIVE:
                answer = ask(f"Confirm destructive action {tool_id}? [y/N] ").strip().lower()
                if answer not in {"y", "yes"}:
                    return ToolResult(ok=False, message="Cancelled by user.")
            elif tool.confirm == ConfirmLevel.ASK:
                answer = ask(f"Allow {tool_id}? [Y/n] ").strip().lower()
                if answer in {"n", "no"}:
                    return ToolResult(ok=False, message="Cancelled by user.")

        try:
            result = tool.handler(args)
        except Exception as exc:  # noqa: BLE001 — surface to agent
            result = ToolResult(ok=False, message=f"{type(exc).__name__}: {exc}")
        try:
            from osagent.inventory import get_inventory

            get_inventory().record_tool_use(
                tool.id,
                ok=bool(result.ok),
                description=(tool.description or "")[:120],
            )
        except Exception:
            pass
        return result


def build_registry(host: HostOS) -> ToolRegistry:
    from osagent.tools import common as common_tools
    from osagent.tools import inventory_tools
    from osagent.tools import linux as linux_tools
    from osagent.tools import windows as windows_tools
    from osagent.tools.catalog import build_catalog_tools

    registry = ToolRegistry()
    registry.register_many(common_tools.build_tools())
    registry.register_many(inventory_tools.build_tools())

    from osagent.tools import files_ops

    registry.register_many(files_ops.build_tools())

    if host == HostOS.WINDOWS:
        registry.register_many(windows_tools.build_tools())
        from osagent.tools import app_extra, computer, ui_tools, window_mgmt

        registry.register_many(computer.build_tools())
        registry.register_many(window_mgmt.build_tools())
        registry.register_many(app_extra.build_tools())
        registry.register_many(ui_tools.build_tools())
    elif host == HostOS.LINUX:
        registry.register_many(linux_tools.build_tools())
    else:
        pass

    # Declarative PowerShell/command catalog (expansive everyday actions)
    registry.register_many(build_catalog_tools(host))
    return registry
