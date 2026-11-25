"""
Computer-use style desktop tools (OpenAI Computer Use–compatible surface).

Works from screenshots + coordinates + keys. Element discovery uses UI Automation
when available. A text-only local model can drive these with explicit coords /
UIA names; visual click-targeting needs a vision/VL model.
"""

from __future__ import annotations

import subprocess
import time
from pathlib import Path
from typing import Any

from osagent.tools.base import ConfirmLevel, Tool, ToolResult


def _shot_dir() -> Path:
    try:
        from osagent.paths import config_dir

        return config_dir() / "screenshots"
    except Exception:
        return Path.home() / ".osagent" / "screenshots"


def build_tools() -> list[Tool]:
    return [
        Tool(
            id="computer.screenshot",
            description=(
                "Capture the current screen (or a monitor region) to a PNG file. "
                "Use before deciding where to click when driving the desktop."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "monitor": {
                        "type": "integer",
                        "description": "0 = virtual desktop, 1 = primary, …",
                        "default": 0,
                    },
                },
            },
            confirm=ConfirmLevel.NONE,
            handler=_screenshot,
            platforms=("windows",),
        ),
        Tool(
            id="computer.open",
            description=(
                "Open an application by name/path OR a URL in the default browser. "
                "Examples: target='notepad', target='chrome', target='https://rediff.com'."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": "App alias/path or http(s) URL",
                    },
                },
                "required": ["target"],
            },
            confirm=ConfirmLevel.NONE,
            handler=_open,
            platforms=("windows",),
        ),
        Tool(
            id="computer.search",
            description=(
                "Open Windows Search, type a query, and press Enter to launch the "
                "top result (apps, settings, files)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "submit": {
                        "type": "boolean",
                        "description": "Press Enter after typing (default true)",
                        "default": True,
                    },
                },
                "required": ["query"],
            },
            confirm=ConfirmLevel.ASK,
            handler=_search,
            platforms=("windows",),
        ),
        Tool(
            id="computer.click_at",
            description=(
                "Left/right/middle click at screen coordinates (pixels from top-left "
                "of the virtual desktop). Prefer after computer.screenshot or "
                "computer.find_element."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "button": {
                        "type": "string",
                        "description": "left | right | middle",
                        "default": "left",
                    },
                    "clicks": {
                        "type": "integer",
                        "description": "1=single, 2=double",
                        "default": 1,
                    },
                },
                "required": ["x", "y"],
            },
            confirm=ConfirmLevel.ASK,
            handler=_click_at,
            platforms=("windows",),
        ),
        Tool(
            id="computer.click",
            description=(
                "Click a UI element found by name/type via Windows UI Automation "
                "(no vision). Prefer for buttons/menus with visible accessible names."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Accessible name / Name property substring",
                    },
                    "control_type": {
                        "type": "string",
                        "description": "Optional: Button, Edit, MenuItem, Hyperlink, …",
                    },
                    "window": {
                        "type": "string",
                        "description": "Optional: restrict to window title substring",
                    },
                },
                "required": ["name"],
            },
            confirm=ConfirmLevel.ASK,
            handler=_click_element,
            platforms=("windows",),
        ),
        Tool(
            id="computer.type",
            description="Type text into the focused control (Unicode supported).",
            parameters={
                "type": "object",
                "properties": {
                    "text": {"type": "string"},
                    "clear_first": {
                        "type": "boolean",
                        "description": "Ctrl+A then Delete before typing",
                        "default": False,
                    },
                },
                "required": ["text"],
            },
            confirm=ConfirmLevel.ASK,
            handler=_type_text,
            platforms=("windows",),
        ),
        Tool(
            id="computer.keypress",
            description=(
                "Press a key or chord. Examples: enter, escape, tab, backspace, "
                "ctrl+c, ctrl+v, alt+f4, win, win+s, up, down, left, right."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "keys": {
                        "type": "string",
                        "description": "Key or chord joined by +",
                    },
                },
                "required": ["keys"],
            },
            confirm=ConfirmLevel.ASK,
            handler=_keypress,
            platforms=("windows",),
        ),
        Tool(
            id="computer.scroll",
            description="Scroll the mouse wheel at coordinates (or current cursor).",
            parameters={
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                    "delta": {
                        "type": "integer",
                        "description": "Positive=up, negative=down (clicks of wheel)",
                        "default": -3,
                    },
                },
            },
            confirm=ConfirmLevel.NONE,
            handler=_scroll,
            platforms=("windows",),
        ),
        Tool(
            id="computer.drag",
            description="Drag from (x1,y1) to (x2,y2) with the left mouse button.",
            parameters={
                "type": "object",
                "properties": {
                    "x1": {"type": "integer"},
                    "y1": {"type": "integer"},
                    "x2": {"type": "integer"},
                    "y2": {"type": "integer"},
                },
                "required": ["x1", "y1", "x2", "y2"],
            },
            confirm=ConfirmLevel.ASK,
            handler=_drag,
            platforms=("windows",),
        ),
        Tool(
            id="computer.move",
            description="Move the mouse pointer to screen coordinates without clicking.",
            parameters={
                "type": "object",
                "properties": {
                    "x": {"type": "integer"},
                    "y": {"type": "integer"},
                },
                "required": ["x", "y"],
            },
            confirm=ConfirmLevel.NONE,
            handler=_move,
            platforms=("windows",),
        ),
        Tool(
            id="computer.wait",
            description="Pause for N milliseconds (UI settle / page load).",
            parameters={
                "type": "object",
                "properties": {
                    "ms": {
                        "type": "integer",
                        "description": "Milliseconds to sleep (max 30000)",
                        "default": 1000,
                    },
                },
            },
            confirm=ConfirmLevel.NONE,
            handler=_wait,
            platforms=("windows", "linux"),
        ),
        Tool(
            id="computer.switch_app",
            description=(
                "Focus a top-level window by title substring (e.g. 'Outlook', "
                "'Chrome', 'Rediff')."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                },
                "required": ["title"],
            },
            confirm=ConfirmLevel.NONE,
            handler=_switch_app,
            platforms=("windows",),
        ),
        Tool(
            id="computer.list_windows",
            description="List visible top-level window titles (for switch_app).",
            parameters={"type": "object", "properties": {}},
            confirm=ConfirmLevel.NONE,
            handler=_list_windows,
            platforms=("windows",),
        ),
        Tool(
            id="computer.find_element",
            description=(
                "Find UI Automation elements by name (and optional control type / "
                "window). Returns name, type, and clickable center coordinates."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "control_type": {"type": "string"},
                    "window": {"type": "string"},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": ["name"],
            },
            confirm=ConfirmLevel.NONE,
            handler=_find_element,
            platforms=("windows",),
        ),
        Tool(
            id="computer.read_ui_text",
            description=(
                "Extract accessible Name/Value text from the focused window (or a "
                "window title match) via UI Automation — not OCR, not full web DOM."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "window": {
                        "type": "string",
                        "description": "Optional window title substring",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Max text nodes",
                        "default": 80,
                    },
                },
            },
            confirm=ConfirmLevel.NONE,
            handler=_read_ui_text,
            platforms=("windows",),
        ),
    ]


# ---------- handlers ----------


def _screenshot(args: dict) -> ToolResult:
    try:
        path = _capture_screenshot(int(args.get("monitor") or 0))
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, message=f"Screenshot failed: {exc}")
    return ToolResult(
        ok=True,
        message=f"Screenshot saved: {path}",
        data={"path": str(path)},
    )


def _open(args: dict) -> ToolResult:
    target = str(args.get("target") or "").strip()
    if not target:
        return ToolResult(ok=False, message="target required")
    if target.lower().startswith(("http://", "https://", "www.")):
        from osagent.tools.web_open import open_url

        url = target if "://" in target else "https://" + target
        return open_url(url)
    from osagent.tools.win_launch import launch_windows_app

    return launch_windows_app(target)


def _search(args: dict) -> ToolResult:
    query = str(args.get("query") or "").strip()
    if not query:
        return ToolResult(ok=False, message="query required")
    submit = True if args.get("submit") is None else bool(args.get("submit"))
    try:
        _press_chord("win+s")
        time.sleep(0.45)
        _type_unicode(query)
        time.sleep(0.35)
        if submit:
            _press_chord("enter")
            time.sleep(0.4)
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, message=f"Search failed: {exc}")
    return ToolResult(
        ok=True,
        message=f"Windows Search: '{query}'" + (" (submitted)" if submit else ""),
        data={"query": query, "submitted": submit},
    )


def _click_at(args: dict) -> ToolResult:
    x, y = int(args["x"]), int(args["y"])
    button = str(args.get("button") or "left").lower()
    clicks = max(1, min(int(args.get("clicks") or 1), 3))
    try:
        _mouse_click(x, y, button=button, clicks=clicks)
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, message=f"Click failed: {exc}")
    return ToolResult(
        ok=True,
        message=f"{button} click×{clicks} at ({x},{y})",
        data={"x": x, "y": y, "button": button, "clicks": clicks},
    )


def _click_element(args: dict) -> ToolResult:
    hits = _uia_find(
        name=str(args.get("name") or ""),
        control_type=str(args.get("control_type") or "") or None,
        window=str(args.get("window") or "") or None,
        limit=5,
    )
    if not hits:
        return ToolResult(ok=False, message="No matching UI element")
    best = hits[0]
    x, y = int(best["cx"]), int(best["cy"])
    _mouse_click(x, y, button="left", clicks=1)
    return ToolResult(
        ok=True,
        message=f"Clicked '{best.get('name')}' ({best.get('control_type')}) at ({x},{y})",
        data={"clicked": best, "candidates": hits},
    )


def _type_text(args: dict) -> ToolResult:
    text = str(args.get("text") or "")
    if args.get("clear_first"):
        _press_chord("ctrl+a")
        time.sleep(0.05)
        _press_chord("backspace")
        time.sleep(0.05)
    try:
        _type_unicode(text)
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, message=f"Type failed: {exc}")
    return ToolResult(ok=True, message=f"Typed {len(text)} character(s)")


def _keypress(args: dict) -> ToolResult:
    keys = str(args.get("keys") or "").strip()
    if not keys:
        return ToolResult(ok=False, message="keys required")
    try:
        _press_chord(keys)
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, message=f"Keypress failed: {exc}")
    return ToolResult(ok=True, message=f"Pressed {keys}")


def _scroll(args: dict) -> ToolResult:
    delta = int(args.get("delta") if args.get("delta") is not None else -3)
    x = args.get("x")
    y = args.get("y")
    try:
        if x is not None and y is not None:
            _mouse_move(int(x), int(y))
            time.sleep(0.05)
        _mouse_wheel(delta)
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, message=f"Scroll failed: {exc}")
    return ToolResult(ok=True, message=f"Scrolled delta={delta}")


def _drag(args: dict) -> ToolResult:
    x1, y1, x2, y2 = int(args["x1"]), int(args["y1"]), int(args["x2"]), int(args["y2"])
    try:
        _mouse_drag(x1, y1, x2, y2)
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, message=f"Drag failed: {exc}")
    return ToolResult(ok=True, message=f"Dragged ({x1},{y1}) → ({x2},{y2})")


def _move(args: dict) -> ToolResult:
    x, y = int(args["x"]), int(args["y"])
    _mouse_move(x, y)
    return ToolResult(ok=True, message=f"Moved pointer to ({x},{y})")


def _wait(args: dict) -> ToolResult:
    ms = max(0, min(int(args.get("ms") or 1000), 30_000))
    time.sleep(ms / 1000.0)
    return ToolResult(ok=True, message=f"Waited {ms} ms")


def _switch_app(args: dict) -> ToolResult:
    title = str(args.get("title") or "").strip()
    if not title:
        return ToolResult(ok=False, message="title required")
    hit = _focus_window(title)
    if not hit:
        return ToolResult(ok=False, message=f"No window matching '{title}'")
    return ToolResult(ok=True, message=f"Focused: {hit}", data={"title": hit})


def _list_windows(_args: dict) -> ToolResult:
    wins = _enum_windows()
    if not wins:
        return ToolResult(ok=True, message="No visible windows", data={"windows": []})
    lines = [f"{i}. {t}" for i, t in enumerate(wins[:40], 1)]
    return ToolResult(
        ok=True,
        message=f"{len(wins)} window(s):\n" + "\n".join(lines),
        data={"windows": wins},
    )


def _find_element(args: dict) -> ToolResult:
    hits = _uia_find(
        name=str(args.get("name") or ""),
        control_type=str(args.get("control_type") or "") or None,
        window=str(args.get("window") or "") or None,
        limit=max(1, min(int(args.get("limit") or 10), 30)),
    )
    if not hits:
        return ToolResult(ok=False, message="No matching elements", data={"elements": []})
    lines = [
        f"{i}. {h.get('name')} [{h.get('control_type')}] @ ({h.get('cx')},{h.get('cy')})"
        for i, h in enumerate(hits, 1)
    ]
    return ToolResult(
        ok=True,
        message=f"{len(hits)} element(s):\n" + "\n".join(lines),
        data={"elements": hits},
    )


def _read_ui_text(args: dict) -> ToolResult:
    texts = _uia_texts(
        window=str(args.get("window") or "") or None,
        limit=max(1, min(int(args.get("limit") or 80), 200)),
    )
    if not texts:
        return ToolResult(
            ok=False,
            message="No accessible text (try computer.screenshot + vision, or app-specific tools)",
            data={"texts": []},
        )
    body = "\n".join(texts[:80])
    return ToolResult(
        ok=True,
        message=f"{len(texts)} text node(s):\n{body[:2500]}",
        data={"texts": texts},
    )


# ---------- Win32 input / capture ----------


def _capture_screenshot(monitor: int = 0) -> Path:
    shot_dir = _shot_dir()
    shot_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d-%H%M%S")
    out = shot_dir / f"shot-{stamp}.png"
    try:
        from PIL import ImageGrab  # type: ignore

        # all_screens=True → virtual desktop
        img = ImageGrab.grab(all_screens=True if monitor == 0 else False)
        img.save(out)
        return out
    except Exception:
        pass
    # Fallback: PowerShell + .NET Bitmap
    ps = rf"""
Add-Type -AssemblyName System.Windows.Forms,System.Drawing
$bounds = [System.Windows.Forms.SystemInformation]::VirtualScreen
$bmp = New-Object System.Drawing.Bitmap $bounds.Width, $bounds.Height
$g = [System.Drawing.Graphics]::FromImage($bmp)
$g.CopyFromScreen($bounds.Location, [System.Drawing.Point]::Empty, $bounds.Size)
$bmp.Save('{str(out).replace("'", "''")}')
$g.Dispose(); $bmp.Dispose()
"""
    code, _, err = _run_ps(ps, timeout=30)
    if code != 0 or not out.is_file():
        raise RuntimeError(err or "capture failed")
    return out


def _run_ps(script: str, timeout: float = 30) -> tuple[int, str, str]:
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            script,
        ],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )
    return completed.returncode, completed.stdout or "", completed.stderr or ""


def _mouse_move(x: int, y: int) -> None:
    import ctypes

    ctypes.windll.user32.SetCursorPos(int(x), int(y))


def _mouse_click(x: int, y: int, *, button: str = "left", clicks: int = 1) -> None:
    import ctypes

    _mouse_move(x, y)
    time.sleep(0.03)
    down_up = {
        "left": (0x0002, 0x0004),
        "right": (0x0008, 0x0010),
        "middle": (0x0020, 0x0040),
    }.get(button, (0x0002, 0x0004))
    for _ in range(clicks):
        ctypes.windll.user32.mouse_event(down_up[0], 0, 0, 0, 0)
        ctypes.windll.user32.mouse_event(down_up[1], 0, 0, 0, 0)
        time.sleep(0.05)


def _mouse_wheel(delta_clicks: int) -> None:
    import ctypes

    # WHEEL_DELTA = 120
    ctypes.windll.user32.mouse_event(0x0800, 0, 0, int(delta_clicks) * 120, 0)


def _mouse_drag(x1: int, y1: int, x2: int, y2: int) -> None:
    import ctypes

    _mouse_move(x1, y1)
    time.sleep(0.05)
    ctypes.windll.user32.mouse_event(0x0002, 0, 0, 0, 0)  # left down
    time.sleep(0.05)
    steps = 12
    for i in range(1, steps + 1):
        x = x1 + (x2 - x1) * i // steps
        y = y1 + (y2 - y1) * i // steps
        _mouse_move(x, y)
        time.sleep(0.01)
    ctypes.windll.user32.mouse_event(0x0004, 0, 0, 0, 0)  # left up


_VK: dict[str, int] = {
    "backspace": 0x08,
    "tab": 0x09,
    "enter": 0x0D,
    "return": 0x0D,
    "shift": 0x10,
    "ctrl": 0x11,
    "control": 0x11,
    "alt": 0x12,
    "pause": 0x13,
    "caps": 0x14,
    "escape": 0x1B,
    "esc": 0x1B,
    "space": 0x20,
    "pageup": 0x21,
    "pagedown": 0x22,
    "end": 0x23,
    "home": 0x24,
    "left": 0x25,
    "up": 0x26,
    "right": 0x27,
    "down": 0x28,
    "insert": 0x2D,
    "delete": 0x2E,
    "win": 0x5B,
    "cmd": 0x5B,
    "meta": 0x5B,
    "f1": 0x70,
    "f2": 0x71,
    "f3": 0x72,
    "f4": 0x73,
    "f5": 0x74,
    "f6": 0x75,
    "f7": 0x76,
    "f8": 0x77,
    "f9": 0x78,
    "f10": 0x79,
    "f11": 0x7A,
    "f12": 0x7B,
}


def _press_chord(spec: str) -> None:
    import ctypes

    parts = [p.strip().lower() for p in spec.replace("-", "+").split("+") if p.strip()]
    if not parts:
        return
    vks: list[int] = []
    for p in parts:
        if p in _VK:
            vks.append(_VK[p])
        elif len(p) == 1:
            vk = ctypes.windll.user32.VkKeyScanW(ord(p))
            vks.append(vk & 0xFF)
        else:
            raise ValueError(f"Unknown key: {p}")
    for vk in vks:
        ctypes.windll.user32.keybd_event(vk, 0, 0, 0)
    time.sleep(0.02)
    for vk in reversed(vks):
        ctypes.windll.user32.keybd_event(vk, 0, 2, 0)


def _type_unicode(text: str) -> None:
    """Send Unicode text via clipboard paste (reliable) with SendInput fallback."""
    if not text:
        return
    # Prefer clipboard paste for speed/reliability with unicode
    try:
        _set_clipboard(text)
        time.sleep(0.05)
        _press_chord("ctrl+v")
        return
    except Exception:
        pass
    import ctypes

    for ch in text:
        if ch == "\n":
            _press_chord("enter")
            continue
        if ch == "\t":
            _press_chord("tab")
            continue
        # KEYEVENTF_UNICODE = 4
        class KEYBDINPUT(ctypes.Structure):
            _fields_ = [
                ("wVk", ctypes.c_ushort),
                ("wScan", ctypes.c_ushort),
                ("dwFlags", ctypes.c_uint),
                ("time", ctypes.c_uint),
                ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong)),
            ]

        class INPUT(ctypes.Structure):
            _fields_ = [("type", ctypes.c_uint), ("ki", KEYBDINPUT)]

        extra = ctypes.c_ulong(0)
        for flags in (0x0004, 0x0004 | 0x0002):  # unicode down/up
            inp = INPUT(
                type=1,
                ki=KEYBDINPUT(0, ord(ch), flags, 0, ctypes.pointer(extra)),
            )
            ctypes.windll.user32.SendInput(1, ctypes.byref(inp), ctypes.sizeof(INPUT))


def _set_clipboard(text: str) -> None:
    import ctypes
    from ctypes import wintypes

    CF_UNICODETEXT = 13
    GMEM_MOVEABLE = 0x0002
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    if not user32.OpenClipboard(None):
        raise RuntimeError("OpenClipboard failed")
    try:
        user32.EmptyClipboard()
        data = text.encode("utf-16-le") + b"\x00\x00"
        h = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(data))
        p = kernel32.GlobalLock(h)
        ctypes.memmove(p, data, len(data))
        kernel32.GlobalUnlock(h)
        user32.SetClipboardData(CF_UNICODETEXT, h)
    finally:
        user32.CloseClipboard()


def _enum_windows() -> list[str]:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    titles: list[str] = []

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
            titles.append(title)
        return True

    user32.EnumWindows(_cb, 0)
    # de-dupe preserve order
    seen: set[str] = set()
    out: list[str] = []
    for t in titles:
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def _focus_window(title_substr: str) -> str | None:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    needle = title_substr.lower()
    found: list[tuple[Any, str]] = []

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
        if title and needle in title.lower():
            found.append((hwnd, title))
        return True

    user32.EnumWindows(_cb, 0)
    if not found:
        return None
    hwnd, title = found[0]
    user32.ShowWindow(hwnd, 9)  # SW_RESTORE
    user32.SetForegroundWindow(hwnd)
    time.sleep(0.15)
    return title


def _uia_find(
    *,
    name: str,
    control_type: str | None,
    window: str | None,
    limit: int,
) -> list[dict[str, Any]]:
    """PowerShell UI Automation search — no extra pip deps."""
    if not name.strip():
        return []
    name_esc = name.replace("'", "''")
    win_esc = (window or "").replace("'", "''")
    ctype_esc = (control_type or "").replace("'", "''")
    script = rf"""
$ErrorActionPreference = 'SilentlyContinue'
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$root = [System.Windows.Automation.AutomationElement]::RootElement
$winFilter = '{win_esc}'
$scope = $root
if ($winFilter) {{
  $wc = New-Object System.Windows.Automation.PropertyCondition(
    [System.Windows.Automation.AutomationElement]::NameProperty, $winFilter,
    [System.Windows.Automation.PropertyConditionFlags]::IgnoreCase)
  # fallback: contains via manual scan of top-level
  $tops = $root.FindAll(
    [System.Windows.Automation.TreeScope]::Children,
    [System.Windows.Automation.Condition]::TrueCondition)
  foreach ($t in $tops) {{
    if ($t.Current.Name -and ($t.Current.Name -like ("*" + $winFilter + "*"))) {{
      $scope = $t; break
    }}
  }}
}}
$needle = '{name_esc}'.ToLower()
$ctype = '{ctype_esc}'
$all = $scope.FindAll(
  [System.Windows.Automation.TreeScope]::Descendants,
  [System.Windows.Automation.Condition]::TrueCondition)
$hits = @()
foreach ($el in $all) {{
  try {{
    $n = $el.Current.Name
    if (-not $n) {{ continue }}
    if ($n.ToLower().IndexOf($needle) -lt 0) {{ continue }}
    $ct = $el.Current.ControlType.ProgrammaticName
    if ($ctype -and ($ct -notlike ("*" + $ctype + "*"))) {{ continue }}
    $r = $el.Current.BoundingRectangle
    if ($r.Width -le 0 -or $r.Height -le 0) {{ continue }}
    $hits += [PSCustomObject]@{{
      name = $n
      control_type = ($ct -replace 'ControlType\.', '')
      cx = [int]($r.X + $r.Width/2)
      cy = [int]($r.Y + $r.Height/2)
      x = [int]$r.X; y = [int]$r.Y
      width = [int]$r.Width; height = [int]$r.Height
    }}
    if ($hits.Count -ge {int(limit)}) {{ break }}
  }} catch {{}}
}}
$hits | ConvertTo-Json -Compress
"""
    code, out, _err = _run_ps(script, timeout=45)
    if code != 0 or not out.strip():
        return []
    import json

    try:
        data = json.loads(out.strip())
    except json.JSONDecodeError:
        return []
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    return []


def _uia_texts(*, window: str | None, limit: int) -> list[str]:
    win_esc = (window or "").replace("'", "''")
    script = rf"""
$ErrorActionPreference = 'SilentlyContinue'
Add-Type -AssemblyName UIAutomationClient, UIAutomationTypes
$root = [System.Windows.Automation.AutomationElement]::RootElement
$scope = $root
$winFilter = '{win_esc}'
if ($winFilter) {{
  $tops = $root.FindAll(
    [System.Windows.Automation.TreeScope]::Children,
    [System.Windows.Automation.Condition]::TrueCondition)
  foreach ($t in $tops) {{
    if ($t.Current.Name -and ($t.Current.Name -like ("*" + $winFilter + "*"))) {{
      $scope = $t; break
    }}
  }}
}} else {{
  $scope = [System.Windows.Automation.AutomationElement]::FocusedElement
  if (-not $scope) {{ $scope = $root }}
}}
$all = $scope.FindAll(
  [System.Windows.Automation.TreeScope]::Descendants,
  [System.Windows.Automation.Condition]::TrueCondition)
$texts = New-Object System.Collections.Generic.List[string]
foreach ($el in $all) {{
  try {{
    $n = $el.Current.Name
    if ($n -and $n.Trim().Length -gt 0) {{
      $t = $n.Trim()
      if (-not $texts.Contains($t)) {{ [void]$texts.Add($t) }}
    }}
    $vp = $el.GetCurrentPattern([System.Windows.Automation.ValuePattern]::Pattern)
    if ($vp -and $vp.Current.Value) {{
      $v = ([string]$vp.Current.Value).Trim()
      if ($v -and -not $texts.Contains($v)) {{ [void]$texts.Add($v) }}
    }}
    if ($texts.Count -ge {int(limit)}) {{ break }}
  }} catch {{}}
}}
$texts | ConvertTo-Json -Compress
"""
    code, out, _err = _run_ps(script, timeout=45)
    if code != 0 or not out.strip():
        return []
    import json

    try:
        data = json.loads(out.strip())
    except json.JSONDecodeError:
        return []
    if isinstance(data, str):
        return [data]
    if isinstance(data, list):
        return [str(x) for x in data if x]
    return []
