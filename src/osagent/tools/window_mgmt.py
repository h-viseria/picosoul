"""windows.windows.* — list / focus / min / max / close / snap."""

from __future__ import annotations

import ctypes
import time
from ctypes import wintypes
from typing import Any

from osagent.tools.base import ConfirmLevel, Tool, ToolResult

user32 = ctypes.windll.user32


def build_tools() -> list[Tool]:
    return [
        Tool(
            id="windows.windows.list",
            description="List open top-level windows and their titles.",
            parameters={"type": "object", "properties": {}},
            confirm=ConfirmLevel.NONE,
            handler=_list,
            platforms=("windows",),
        ),
        Tool(
            id="windows.windows.get_active",
            description="Identify the foreground window title and HWND.",
            parameters={"type": "object", "properties": {}},
            confirm=ConfirmLevel.NONE,
            handler=_get_active,
            platforms=("windows",),
        ),
        Tool(
            id="windows.windows.focus",
            description="Switch focus to a window by title substring.",
            parameters={
                "type": "object",
                "properties": {"title": {"type": "string"}},
                "required": ["title"],
            },
            confirm=ConfirmLevel.NONE,
            handler=_focus,
            platforms=("windows",),
        ),
        Tool(
            id="windows.windows.minimize",
            description="Minimize a window by title substring (or the active window).",
            parameters={
                "type": "object",
                "properties": {"title": {"type": "string"}},
            },
            confirm=ConfirmLevel.NONE,
            handler=lambda a: _show(a, 6, "minimized"),  # SW_MINIMIZE
            platforms=("windows",),
        ),
        Tool(
            id="windows.windows.maximize",
            description="Maximize a window by title substring (or the active window).",
            parameters={
                "type": "object",
                "properties": {"title": {"type": "string"}},
            },
            confirm=ConfirmLevel.NONE,
            handler=lambda a: _show(a, 3, "maximized"),  # SW_MAXIMIZE
            platforms=("windows",),
        ),
        Tool(
            id="windows.windows.close",
            description="Close a window by title substring (WM_CLOSE).",
            parameters={
                "type": "object",
                "properties": {"title": {"type": "string"}},
                "required": ["title"],
            },
            confirm=ConfirmLevel.ASK,
            handler=_close,
            platforms=("windows",),
        ),
        Tool(
            id="windows.windows.snap",
            description=(
                "Snap the active (or titled) window left/right/up/down "
                "(Win+Arrow equivalent)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "side": {
                        "type": "string",
                        "description": "left | right | up | down",
                    },
                    "title": {"type": "string"},
                },
                "required": ["side"],
            },
            confirm=ConfirmLevel.NONE,
            handler=_snap,
            platforms=("windows",),
        ),
    ]


def _enum_windows() -> list[tuple[int, str]]:
    found: list[tuple[int, str]] = []

    @ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    def _cb(hwnd, _lp):  # type: ignore[no-untyped-def]
        if not user32.IsWindowVisible(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.strip()
        if title:
            found.append((int(hwnd), title))
        return True

    user32.EnumWindows(_cb, 0)
    return found


def _find_hwnd(title: str | None) -> tuple[int, str] | None:
    if not title:
        hwnd = int(user32.GetForegroundWindow())
        if not hwnd:
            return None
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        return hwnd, buf.value.strip() or "(untitled)"
    needle = title.lower()
    for hwnd, t in _enum_windows():
        if needle in t.lower():
            return hwnd, t
    return None


def _list(_args: dict) -> ToolResult:
    wins = _enum_windows()
    lines = [f"{i}. {t}" for i, (_h, t) in enumerate(wins[:50], 1)]
    return ToolResult(
        ok=True,
        message=f"{len(wins)} window(s):\n" + "\n".join(lines),
        data={"windows": [{"hwnd": h, "title": t} for h, t in wins]},
    )


def _get_active(_args: dict) -> ToolResult:
    hit = _find_hwnd(None)
    if not hit:
        return ToolResult(ok=False, message="No foreground window")
    hwnd, title = hit
    return ToolResult(
        ok=True,
        message=f"Active: {title}",
        data={"hwnd": hwnd, "title": title},
    )


def _focus(args: dict) -> ToolResult:
    hit = _find_hwnd(str(args.get("title") or ""))
    if not hit:
        return ToolResult(ok=False, message="Window not found")
    hwnd, title = hit
    user32.ShowWindow(hwnd, 9)
    user32.SetForegroundWindow(hwnd)
    return ToolResult(ok=True, message=f"Focused: {title}", data={"title": title})


def _show(args: dict, cmd: int, label: str) -> ToolResult:
    hit = _find_hwnd(str(args.get("title") or "") or None)
    if not hit:
        return ToolResult(ok=False, message="Window not found")
    hwnd, title = hit
    user32.ShowWindow(hwnd, cmd)
    return ToolResult(ok=True, message=f"{label}: {title}", data={"title": title})


def _close(args: dict) -> ToolResult:
    hit = _find_hwnd(str(args.get("title") or ""))
    if not hit:
        return ToolResult(ok=False, message="Window not found")
    hwnd, title = hit
    WM_CLOSE = 0x0010
    user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
    return ToolResult(ok=True, message=f"Close sent: {title}", data={"title": title})


def _snap(args: dict) -> ToolResult:
    side = str(args.get("side") or "").lower().strip()
    key_map = {"left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28}
    if side not in key_map:
        return ToolResult(ok=False, message="side must be left|right|up|down")
    if args.get("title"):
        hit = _find_hwnd(str(args["title"]))
        if not hit:
            return ToolResult(ok=False, message="Window not found")
        user32.ShowWindow(hit[0], 9)
        user32.SetForegroundWindow(hit[0])
        time.sleep(0.15)
    VK_LWIN = 0x5B
    vk = key_map[side]
    user32.keybd_event(VK_LWIN, 0, 0, 0)
    user32.keybd_event(vk, 0, 0, 0)
    user32.keybd_event(vk, 0, 2, 0)
    user32.keybd_event(VK_LWIN, 0, 2, 0)
    return ToolResult(ok=True, message=f"Snapped {side}")
