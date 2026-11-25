"""ui.* tools — accessibility / input surface (wraps computer helpers)."""

from __future__ import annotations

from osagent.tools.base import ConfirmLevel, Tool, ToolResult


def build_tools() -> list[Tool]:
    return [
        Tool(
            id="ui.get_active_window_tree",
            description=(
                "Dump accessible Name/control-type nodes for the focused window "
                "(UI Automation tree sample)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "default": 80},
                },
            },
            confirm=ConfirmLevel.NONE,
            handler=_tree,
            platforms=("windows",),
        ),
        Tool(
            id="ui.get_controls",
            description="Find UI controls by name (and optional type/window).",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "control_type": {"type": "string"},
                    "window": {"type": "string"},
                    "limit": {"type": "integer", "default": 15},
                },
                "required": ["name"],
            },
            confirm=ConfirmLevel.NONE,
            handler=_get_controls,
            platforms=("windows",),
        ),
        Tool(
            id="ui.click_element",
            description="Click a UI Automation element by accessible name.",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "control_type": {"type": "string"},
                    "window": {"type": "string"},
                },
                "required": ["name"],
            },
            confirm=ConfirmLevel.ASK,
            handler=_click,
            platforms=("windows",),
        ),
        Tool(
            id="ui.set_text",
            description="Focus a named Edit control (if found) and type text into it.",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Edit control name"},
                    "text": {"type": "string"},
                    "window": {"type": "string"},
                    "clear_first": {"type": "boolean", "default": True},
                },
                "required": ["text"],
            },
            confirm=ConfirmLevel.ASK,
            handler=_set_text,
            platforms=("windows",),
        ),
        Tool(
            id="ui.select_element",
            description="Click/select a named UI element (same as click for most controls).",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "window": {"type": "string"},
                },
                "required": ["name"],
            },
            confirm=ConfirmLevel.ASK,
            handler=_click,
            platforms=("windows",),
        ),
        Tool(
            id="ui.press_key",
            description="Press a key or chord (enter, ctrl+c, alt+f4, …).",
            parameters={
                "type": "object",
                "properties": {"keys": {"type": "string"}},
                "required": ["keys"],
            },
            confirm=ConfirmLevel.ASK,
            handler=_press,
            platforms=("windows",),
        ),
        Tool(
            id="ui.wait_for_state",
            description=(
                "Poll until a window title appears, a process is running, or a path exists."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "window": {"type": "string"},
                    "process": {"type": "string"},
                    "path": {"type": "string"},
                    "timeout_ms": {"type": "integer", "default": 15000},
                    "poll_ms": {"type": "integer", "default": 500},
                },
            },
            confirm=ConfirmLevel.NONE,
            handler=_wait_for,
            platforms=("windows",),
        ),
    ]


def _tree(args: dict) -> ToolResult:
    from osagent.tools import computer as c

    return c._read_ui_text({"window": None, "limit": int(args.get("limit") or 80)})


def _get_controls(args: dict) -> ToolResult:
    from osagent.tools import computer as c

    return c._find_element(args)


def _click(args: dict) -> ToolResult:
    from osagent.tools import computer as c

    return c._click_element(args)


def _set_text(args: dict) -> ToolResult:
    from osagent.tools import computer as c

    name = str(args.get("name") or "").strip()
    if name:
        hit = c._click_element(
            {
                "name": name,
                "control_type": "Edit",
                "window": args.get("window"),
            }
        )
        if not hit.ok:
            # try without control_type
            hit = c._click_element({"name": name, "window": args.get("window")})
            if not hit.ok:
                return hit
    return c._type_text(
        {
            "text": str(args.get("text") or ""),
            "clear_first": True if args.get("clear_first") is None else bool(args.get("clear_first")),
        }
    )


def _press(args: dict) -> ToolResult:
    from osagent.tools import computer as c

    return c._keypress(args)


def _wait_for(args: dict) -> ToolResult:
    import time
    from pathlib import Path

    from osagent.tools.window_mgmt import _enum_windows

    timeout = max(100, min(int(args.get("timeout_ms") or 15000), 120_000))
    poll = max(100, min(int(args.get("poll_ms") or 500), 5000))
    window = str(args.get("window") or "").strip().lower()
    process = str(args.get("process") or "").strip().removesuffix(".exe")
    path = str(args.get("path") or "").strip()
    if not any([window, process, path]):
        return ToolResult(ok=False, message="Need window, process, or path")

    deadline = time.time() + timeout / 1000.0
    while time.time() < deadline:
        if window:
            for _h, t in _enum_windows():
                if window in t.lower():
                    return ToolResult(ok=True, message=f"Window ready: {t}", data={"title": t})
        if process:
            import json

            from osagent.tools.win_ps import run_ps

            code, out, _ = run_ps(
                rf"@((Get-Process -Name '{process.replace(chr(39), chr(39)+chr(39))}' -EA SilentlyContinue).Count) | ConvertTo-Json",
                timeout=10,
            )
            try:
                n = int(json.loads(out.strip() or "0"))
            except Exception:
                n = 0
            if n > 0:
                return ToolResult(ok=True, message=f"Process running: {process}", data={"count": n})
        if path and Path(path).expanduser().exists():
            return ToolResult(ok=True, message=f"Path exists: {path}")
        time.sleep(poll / 1000.0)

    return ToolResult(ok=False, message=f"Timed out after {timeout} ms waiting for state")
