"""Windows-specific desktop tools — PowerShell/CIM first, Settings as fallback."""

from __future__ import annotations

import subprocess
import sys

from osagent.tools.base import ConfirmLevel, Tool, ToolResult
from osagent.tools import win_ps

# ms-settings URIs — last resort when no direct PowerShell path exists
SETTINGS_URIS = {
    "display": "ms-settings:display",
    "wifi": "ms-settings:network-wifi",
    "bluetooth": "ms-settings:bluetooth",
    "printers": "ms-settings:printers",
    "sound": "ms-settings:sound",
    "personalization": "ms-settings:personalization",
    "apps": "ms-settings:appsfeatures",
    "power": "ms-settings:powersleep",
    "datetime": "ms-settings:dateandtime",
    "update": "ms-settings:windowsupdate",
}


def build_tools() -> list[Tool]:
    if sys.platform != "win32":
        pass

    return [
        Tool(
            id="windows.settings.open",
            description=(
                "Open a Windows Settings page ONLY as a fallback when a direct "
                "PowerShell tool cannot do the job. "
                f"Areas: {', '.join(sorted(SETTINGS_URIS))}."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "area": {
                        "type": "string",
                        "description": "Settings area key or raw ms-settings: URI",
                    },
                },
                "required": ["area"],
            },
            confirm=ConfirmLevel.NONE,
            handler=_open_settings,
            platforms=("windows",),
        ),
        Tool(
            id="windows.powershell.run",
            description=(
                "Propose and run a PowerShell command when no specialized catalog "
                "tool fits. Prefer catalog tools first. Use for discovery queries "
                "(Get-ChildItem, Get-Process, Get-Printer, netsh, etc.). "
                "Pass the full command in 'command' and a short 'rationale'. "
                "Write/delete commands require interactive confirmation."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "command": {
                        "type": "string",
                        "description": "PowerShell one-liner or short script",
                    },
                    "rationale": {
                        "type": "string",
                        "description": "Why this command answers the user",
                    },
                    "timeout_sec": {
                        "type": "integer",
                        "description": "Timeout seconds (default 90, max 300)",
                        "default": 90,
                    },
                },
                "required": ["command"],
            },
            confirm=ConfirmLevel.NONE,
            handler=_run_powershell,
            platforms=("windows",),
        ),
        Tool(
            id="windows.apps.list",
            description=(
                "List Start-menu apps via Get-StartApps. Optional query filter. "
                "Prefer this over opening Settings for 'what apps are installed'."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 40},
                    "open_settings": {"type": "boolean", "default": False},
                },
            },
            confirm=ConfirmLevel.NONE,
            handler=_list_apps,
            platforms=("windows",),
        ),
        # --- Volume / audio ---
        Tool(
            id="windows.volume.get",
            description="Get current master volume percent (0-100) via Windows Core Audio.",
            parameters={"type": "object", "properties": {}},
            confirm=ConfirmLevel.NONE,
            handler=_get_volume,
            platforms=("windows",),
        ),
        Tool(
            id="windows.volume.set_percent",
            description="Set master volume to an absolute percentage 0-100.",
            parameters={
                "type": "object",
                "properties": {
                    "percent": {"type": "integer", "minimum": 0, "maximum": 100},
                },
                "required": ["percent"],
            },
            confirm=ConfirmLevel.NONE,
            handler=_set_volume,
            platforms=("windows",),
        ),
        Tool(
            id="windows.volume.adjust",
            description=(
                "Change master volume by a relative delta (e.g. +10 or -15). "
                "Use this for 'increase/decrease volume' / 'louder' / 'quieter'."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "delta": {
                        "type": "integer",
                        "description": "Percent points to add (negative to lower)",
                    },
                },
                "required": ["delta"],
            },
            confirm=ConfirmLevel.NONE,
            handler=_adjust_volume,
            platforms=("windows",),
        ),
        Tool(
            id="windows.volume.mute",
            description="Mute or unmute master audio. Set muted=true to mute.",
            parameters={
                "type": "object",
                "properties": {"muted": {"type": "boolean"}},
                "required": ["muted"],
            },
            confirm=ConfirmLevel.NONE,
            handler=_mute_volume,
            platforms=("windows",),
        ),
        Tool(
            id="windows.volume.reset",
            description=(
                "Reset master volume: unmute and set to a default percent "
                "(default 50). Use for 'reset volume' / 'restore volume'."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "percent": {
                        "type": "integer",
                        "minimum": 0,
                        "maximum": 100,
                        "default": 50,
                        "description": "Level after reset (default 50)",
                    },
                },
            },
            confirm=ConfirmLevel.NONE,
            handler=_reset_volume,
            platforms=("windows",),
        ),
        Tool(
            id="windows.audio.list_devices",
            description="List audio endpoints (speakers/mics) via Get-PnpDevice -Class Media/AudioEndpoint.",
            parameters={"type": "object", "properties": {}},
            confirm=ConfirmLevel.NONE,
            handler=_list_audio_devices,
            platforms=("windows",),
        ),
        # --- Printers ---
        Tool(
            id="windows.printers.default",
            description=(
                "Show the current default printer name (and driver/port). "
                "Use for 'what is my default printer', 'current default printer', "
                "'name of default printer'. Prefer this over list/get."
            ),
            parameters={"type": "object", "properties": {}},
            confirm=ConfirmLevel.NONE,
            handler=_default_printer,
            platforms=("windows",),
        ),
        Tool(
            id="windows.printers.list",
            description=(
                "List all installed printers (marks which is default). "
                "Use for 'list printers' / 'show all printers' — NOT for "
                "'what is the default printer' (use windows.printers.default)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Optional printer name filter (substring)",
                    },
                },
            },
            confirm=ConfirmLevel.NONE,
            handler=_list_printers,
            platforms=("windows",),
        ),
        Tool(
            id="windows.printers.get",
            description=(
                "Get full details for one printer by exact name. "
                "Requires name=. For the default printer use windows.printers.default."
            ),
            parameters={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
            confirm=ConfirmLevel.NONE,
            handler=_get_printer,
            platforms=("windows",),
        ),
        Tool(
            id="windows.printers.set_default",
            description="Set the default printer by name (requires name=).",
            parameters={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
            confirm=ConfirmLevel.ASK,
            handler=_set_default_printer,
            platforms=("windows",),
        ),
        # --- Bluetooth ---
        Tool(
            id="windows.bluetooth.list",
            description="List Bluetooth adapters and devices via Get-PnpDevice -Class Bluetooth.",
            parameters={"type": "object", "properties": {}},
            confirm=ConfirmLevel.NONE,
            handler=_list_bluetooth,
            platforms=("windows",),
        ),
        Tool(
            id="windows.bluetooth.set_adapter",
            description=(
                "Enable or disable a Bluetooth PnP device by InstanceId "
                "(from windows.bluetooth.list). Prefer adapter radios."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "instance_id": {"type": "string"},
                    "enabled": {"type": "boolean"},
                },
                "required": ["instance_id", "enabled"],
            },
            confirm=ConfirmLevel.ASK,
            handler=_set_bluetooth_device,
            platforms=("windows",),
        ),
        # --- Display ---
        Tool(
            id="windows.display.get_brightness",
            description="Get laptop/monitor brightness percent via WmiMonitorBrightness (when supported).",
            parameters={"type": "object", "properties": {}},
            confirm=ConfirmLevel.NONE,
            handler=_get_brightness,
            platforms=("windows",),
        ),
        Tool(
            id="windows.display.set_brightness",
            description="Set brightness 0-100 via WmiMonitorBrightnessMethods when hardware supports it.",
            parameters={
                "type": "object",
                "properties": {
                    "percent": {"type": "integer", "minimum": 0, "maximum": 100},
                },
                "required": ["percent"],
            },
            confirm=ConfirmLevel.NONE,
            handler=_set_brightness,
            platforms=("windows",),
        ),
        Tool(
            id="windows.display.info",
            description=(
                "Screen RESOLUTION only (width x height, adapters). "
                "Do NOT use for contrast, brightness, or color — use "
                "windows.display.get_contrast / get_brightness instead."
            ),
            parameters={"type": "object", "properties": {}},
            confirm=ConfirmLevel.NONE,
            handler=_display_info,
            platforms=("windows",),
        ),
        Tool(
            id="windows.display.get_contrast",
            description=(
                "Report Windows High Contrast / color-filter accessibility state. "
                "Use for 'contrast setting', 'high contrast', 'screen contrast'. "
                "Note: physical monitor contrast knobs are usually not readable "
                "via Windows — this reports OS accessibility contrast."
            ),
            parameters={"type": "object", "properties": {}},
            confirm=ConfirmLevel.NONE,
            handler=_get_contrast,
            platforms=("windows",),
        ),
        Tool(
            id="windows.app.notepad",
            description="Open Notepad, optionally with a file path.",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
            },
            confirm=ConfirmLevel.NONE,
            handler=_open_notepad,
            platforms=("windows",),
        ),
        Tool(
            id="windows.shell.explorer",
            description="Open File Explorer at a path (default: user profile).",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
            },
            confirm=ConfirmLevel.NONE,
            handler=_open_explorer,
            platforms=("windows",),
        ),
        Tool(
            id="windows.clipboard.set_text",
            description="Copy generated text to the clipboard.",
            parameters={
                "type": "object",
                "properties": {"text": {"type": "string"}},
                "required": ["text"],
            },
            confirm=ConfirmLevel.NONE,
            handler=_clipboard_set,
            platforms=("windows",),
        ),
        Tool(
            id="windows.clipboard.clear",
            description="Clear clipboard contents.",
            parameters={"type": "object", "properties": {}},
            confirm=ConfirmLevel.NONE,
            handler=_clipboard_clear,
            platforms=("windows",),
        ),
    ]


def _clipboard_set(args: dict) -> ToolResult:
    text = str(args.get("text") or "")
    try:
        from osagent.tools.computer import _set_clipboard

        _set_clipboard(text)
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, message=f"Clipboard set failed: {exc}")
    return ToolResult(ok=True, message=f"Clipboard set ({len(text)} chars)")


def _clipboard_clear(_args: dict) -> ToolResult:
    try:
        import ctypes

        user32 = ctypes.windll.user32
        if not user32.OpenClipboard(None):
            raise RuntimeError("OpenClipboard failed")
        try:
            user32.EmptyClipboard()
        finally:
            user32.CloseClipboard()
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, message=f"Clipboard clear failed: {exc}")
    return ToolResult(ok=True, message="Clipboard cleared")


def _open_settings_uri(uri: str) -> None:
    subprocess.Popen(["cmd", "/c", "start", "", uri], shell=False)


def _run_powershell(args: dict) -> ToolResult:
    from osagent.tools.shell_safe import validate_powershell

    command = str(args.get("command") or "").strip()
    rationale = str(args.get("rationale") or "").strip()
    timeout = max(5, min(int(args.get("timeout_sec") or 90), 300))

    allowed, message, needs_confirm = validate_powershell(command)
    if not allowed:
        return ToolResult(
            ok=False,
            message=message,
            data={"command": command, "rationale": rationale},
        )

    if needs_confirm:
        print(f"\nProposed PowerShell (writes/changes state):\n  {command}")
        if rationale:
            print(f"  reason: {rationale}")
        try:
            answer = input("Run this command? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return ToolResult(ok=False, message="Cancelled by user.")
        if answer not in {"y", "yes"}:
            return ToolResult(ok=False, message="Cancelled by user.")

    try:
        code, out, err = win_ps.run_ps(command, timeout=float(timeout))
    except Exception as exc:  # noqa: BLE001
        return ToolResult(
            ok=False,
            message=f"PowerShell failed to start: {exc}",
            data={"command": command},
        )

    stdout = (out or "").strip()
    stderr = (err or "").strip()
    # Cap huge outputs for the model context
    max_len = 8000
    if len(stdout) > max_len:
        stdout = stdout[:max_len] + "\n...[truncated]..."
    if len(stderr) > max_len:
        stderr = stderr[:max_len] + "\n...[truncated]..."

    ok = code == 0
    summary = stdout if stdout else (stderr if stderr else f"exit code {code}")
    return ToolResult(
        ok=ok,
        message=summary[:1500] if ok else (stderr or summary)[:1500],
        data={
            "command": command,
            "rationale": rationale or None,
            "exit_code": code,
            "stdout": stdout,
            "stderr": stderr,
        },
    )


def _open_settings(args: dict) -> ToolResult:
    area = str(args["area"]).strip().lower()
    uri = SETTINGS_URIS.get(area, args["area"])
    if not str(uri).startswith("ms-settings:"):
        uri = SETTINGS_URIS.get(area)
        if not uri:
            return ToolResult(
                ok=False,
                message=f"Unknown settings area: {area}. Known: {list(SETTINGS_URIS)}",
            )
    _open_settings_uri(str(uri))
    return ToolResult(ok=True, message=f"Opened {uri}")


def _list_apps(args: dict) -> ToolResult:
    query = str(args.get("query") or "").strip().lower()
    limit = max(1, min(int(args.get("limit") or 40), 120))
    open_settings = bool(args.get("open_settings"))

    # Prefer filesystem fuzzy search when user gave a query (portable apps, Desktop)
    fs_hits: list[dict] = []
    if query:
        try:
            from osagent.tools.win_launch import find_apps

            fs_hits = find_apps(query, limit=min(limit, 12), min_score=0.55)
        except Exception:  # noqa: BLE001
            fs_hits = []

    script = (
        "Get-StartApps | Select-Object Name, AppID | ConvertTo-Json -Compress"
    )
    names: list[str] = []
    try:
        data = win_ps.run_ps_json(script, timeout=60)
        apps = win_ps.as_list(data)
        seen: set[str] = set()
        for item in apps:
            name = str(item.get("Name") or "").strip()
            if not name:
                continue
            key = name.lower()
            if key in seen:
                continue
            if query and query not in key:
                # also allow fuzzy alnum containment
                from osagent.tools.win_launch import _alnum, _score_name

                if _score_name(query, name) < 0.72 and _alnum(query) not in _alnum(name):
                    continue
            seen.add(key)
            names.append(name)
        names.sort(key=str.casefold)
    except Exception as exc:  # noqa: BLE001
        if not fs_hits:
            if open_settings:
                _open_settings_uri("ms-settings:appsfeatures")
            return ToolResult(
                ok=False,
                message=f"Get-StartApps failed ({exc})",
            )

    shown = names[:limit]
    launchable: list[str] = []
    try:
        from osagent.tools.win_launch import ALIASES, resolve_executable_strict

        for alias in sorted(ALIASES):
            if query and query not in alias and _score_safe(query, alias) < 0.72:
                continue
            if resolve_executable_strict(alias) is not None:
                launchable.append(alias)
    except Exception:  # noqa: BLE001
        pass

    if open_settings:
        _open_settings_uri("ms-settings:appsfeatures")

    if not shown and not launchable and not fs_hits:
        return ToolResult(
            ok=False,
            message=(
                f"No matching apps for '{query or 'all'}'. "
                "Try app.launch with the name (fuzzy Desktop/Downloads search)."
            ),
            data={"query": query, "total": 0},
        )

    parts = []
    if fs_hits:
        parts.append(f"{len(fs_hits)} file match(es) e.g. {fs_hits[0]['name']}")
    if shown:
        parts.append(f"{len(shown)} Start app(s)")
    return ToolResult(
        ok=True,
        message="; ".join(parts) if parts else "Apps listed",
        data={
            "apps": shown,
            "total": len(names),
            "files": fs_hits,
            "launch_aliases": launchable[:30],
            "hint": "Use app.launch with a name or path from files/apps.",
        },
    )


def _score_safe(query: str, name: str) -> float:
    try:
        from osagent.tools.win_launch import _score_name

        return _score_name(query, name)
    except Exception:  # noqa: BLE001
        return 0.0


def _get_volume(_args: dict) -> ToolResult:
    try:
        pct = win_ps.get_volume_percent()
        return ToolResult(ok=True, message=f"Volume is {pct}%", data={"percent": pct})
    except Exception as exc:  # noqa: BLE001
        _open_settings_uri("ms-settings:sound")
        return ToolResult(
            ok=False,
            message=f"Could not read volume ({exc}); opened Sound settings.",
        )


def _set_volume(args: dict) -> ToolResult:
    try:
        pct = win_ps.set_volume_percent(int(args["percent"]))
        return ToolResult(ok=True, message=f"Volume set to {pct}%", data={"percent": pct})
    except Exception as exc:  # noqa: BLE001
        _open_settings_uri("ms-settings:sound")
        return ToolResult(
            ok=False,
            message=f"Could not set volume ({exc}); opened Sound settings.",
        )


def _adjust_volume(args: dict) -> ToolResult:
    delta = int(args["delta"])
    before, after, method = win_ps.adjust_volume_percent(delta)
    if after is not None or method == "hotkeys":
        if before is not None and after is not None:
            msg = f"Volume {before}% -> {after}% (delta {delta:+d}, via {method})"
        elif after is not None:
            msg = f"Volume adjusted to ~{after}% (delta {delta:+d}, via {method})"
        else:
            msg = f"Volume key presses sent (delta {delta:+d}, via {method})"
        return ToolResult(
            ok=True,
            message=msg,
            data={"before": before, "percent": after, "delta": delta, "method": method},
        )
    _open_settings_uri("ms-settings:sound")
    return ToolResult(
        ok=False,
        message="Could not adjust volume; opened Sound settings.",
    )


def _mute_volume(args: dict) -> ToolResult:
    muted = bool(args["muted"])
    try:
        state = win_ps.set_mute(muted)
        return ToolResult(
            ok=True,
            message="Muted" if state else "Unmuted",
            data={"muted": state},
        )
    except Exception as exc:  # noqa: BLE001
        _open_settings_uri("ms-settings:sound")
        return ToolResult(
            ok=False,
            message=f"Could not change mute ({exc}); opened Sound settings.",
        )


def _reset_volume(args: dict) -> ToolResult:
    """Unmute + set a known level — keeps 'reset volume' off the slow LLM path."""
    pct = 50
    if args.get("percent") is not None:
        pct = max(0, min(100, int(args["percent"])))
    try:
        muted_after = win_ps.set_mute(False)
        level = win_ps.set_volume_percent(pct)
        return ToolResult(
            ok=True,
            message=f"Volume reset to {level}% (unmuted)",
            data={"percent": level, "muted": bool(muted_after)},
        )
    except Exception as exc:  # noqa: BLE001
        _open_settings_uri("ms-settings:sound")
        return ToolResult(
            ok=False,
            message=f"Could not reset volume ({exc}); opened Sound settings.",
        )


def _list_audio_devices(_args: dict) -> ToolResult:
    script = r"""
$devs = @()
$devs += Get-PnpDevice -Class 'AudioEndpoint' -ErrorAction SilentlyContinue
$devs += Get-PnpDevice -Class 'MEDIA' -ErrorAction SilentlyContinue
$devs | Select-Object Status, Class, FriendlyName, InstanceId |
  ConvertTo-Json -Compress
"""
    try:
        data = win_ps.run_ps_json(script)
        items = win_ps.as_list(data)
        slim = [
            {
                "name": i.get("FriendlyName"),
                "status": i.get("Status"),
                "class": i.get("Class"),
                "instance_id": i.get("InstanceId"),
            }
            for i in items
        ]
        return ToolResult(
            ok=True,
            message=f"{len(slim)} audio-related device(s)",
            data={"devices": slim[:80]},
        )
    except Exception as exc:  # noqa: BLE001
        _open_settings_uri("ms-settings:sound")
        return ToolResult(
            ok=False,
            message=f"Audio device query failed ({exc}); opened Sound settings.",
        )


def _default_printer(_args: dict) -> ToolResult:
    script = r"""
$ErrorActionPreference = 'Stop'
$p = Get-CimInstance -ClassName Win32_Printer -Filter 'Default=True' -ErrorAction Stop |
  Select-Object -First 1 Name, DriverName, PortName, Shared, Network, Local, WorkOffline
if (-not $p) { throw 'No default printer set' }
[PSCustomObject]@{
  name = $p.Name
  driver = $p.DriverName
  port = $p.PortName
  shared = [bool]$p.Shared
  network = [bool]$p.Network
} | ConvertTo-Json -Compress
"""
    try:
        data = win_ps.run_ps_json(script, timeout=30) or {}
        if isinstance(data, list):
            data = data[0] if data else {}
        name = (data or {}).get("name") or (data or {}).get("Name")
        if not name:
            return ToolResult(ok=False, message="No default printer is set")
        try:
            from osagent.inventory import get_inventory

            get_inventory().enrich_devices(
                "printers",
                [
                    {
                        "name": name,
                        "default": True,
                        **{k: v for k, v in (data or {}).items() if k != "name"},
                        "control": {
                            "default": "windows.printers.default",
                            "list": "windows.printers.list",
                        },
                    }
                ],
            )
        except Exception:
            pass
        return ToolResult(
            ok=True,
            message=f"Default printer: {name}",
            data={"default": data},
        )
    except Exception as exc:  # noqa: BLE001
        _open_settings_uri("ms-settings:printers")
        return ToolResult(
            ok=False,
            message=f"Could not read default printer ({exc}); opened Printers settings.",
        )


def _list_printers(args: dict) -> ToolResult:
    name_filter = str(args.get("name") or "").strip()
    script = r"""
$ErrorActionPreference = 'Stop'
Get-CimInstance -ClassName Win32_Printer |
  Select-Object Name, DriverName, PortName, Default, Shared, Network, Local, WorkOffline |
  ConvertTo-Json -Compress
"""
    try:
        data = win_ps.run_ps_json(script, timeout=45)
        printers = []
        for p in win_ps.as_list(data):
            printers.append(
                {
                    "name": p.get("Name"),
                    "driver": p.get("DriverName"),
                    "port": p.get("PortName"),
                    "default": bool(p.get("Default")),
                    "shared": bool(p.get("Shared")),
                    "network": bool(p.get("Network")),
                }
            )
        if name_filter:
            q = name_filter.lower()
            printers = [p for p in printers if q in str(p.get("name") or "").lower()]
        default = next((p for p in printers if p.get("default")), None)
        if default:
            msg = f"{len(printers)} printer(s); default: {default.get('name')}"
        else:
            msg = f"{len(printers)} printer(s)"
        try:
            from osagent.inventory import get_inventory

            get_inventory().enrich_devices(
                "printers",
                [
                    {
                        **p,
                        "control": {
                            "list": "windows.printers.list",
                            "default": "windows.printers.default",
                            "set_default": "windows.printers.set_default",
                        },
                    }
                    for p in printers
                ],
            )
        except Exception:
            pass
        return ToolResult(ok=True, message=msg, data={"printers": printers})
    except Exception as exc:  # noqa: BLE001
        _open_settings_uri("ms-settings:printers")
        return ToolResult(
            ok=False,
            message=(
                f"Printer list failed ({exc}); opened Printers settings."
            ),
        )


def _get_printer(args: dict) -> ToolResult:
    name_raw = args.get("name")
    if not name_raw or not str(name_raw).strip():
        # Common mistake: asking for default via get without a name
        return _default_printer({})
    name = str(name_raw).replace("'", "''")
    script = f"""
$ErrorActionPreference = 'Stop'
$p = Get-CimInstance -ClassName Win32_Printer -Filter "Name='{name}'" -ErrorAction Stop |
  Select-Object Name, DriverName, PortName, Default, Shared, Network, Local, WorkOffline, PrinterStatus
if (-not $p) {{ throw "Printer not found: {name}" }}
[PSCustomObject]@{{
  name = $p.Name
  driver = $p.DriverName
  port = $p.PortName
  default = [bool]$p.Default
  shared = [bool]$p.Shared
  network = [bool]$p.Network
  status = $p.PrinterStatus
}} | ConvertTo-Json -Compress
"""
    try:
        data = win_ps.run_ps_json(script, timeout=45)
        pname = (data or {}).get("name") if isinstance(data, dict) else name_raw
        return ToolResult(
            ok=True,
            message=f"Printer: {pname}",
            data={"printer": data},
        )
    except Exception as exc:  # noqa: BLE001
        listed = _list_printers({"name": str(name_raw)})
        if listed.ok and listed.data.get("printers"):
            return ToolResult(
                ok=True,
                message=f"Matched from list ({exc})",
                data=listed.data,
            )
        _open_settings_uri("ms-settings:printers")
        return ToolResult(
            ok=False,
            message=f"Could not get printer ({exc}); opened Printers settings.",
        )


def _set_default_printer(args: dict) -> ToolResult:
    name_raw = args.get("name")
    if not name_raw or not str(name_raw).strip():
        return ToolResult(
            ok=False,
            message="Set default printer needs a name, e.g. name=\"HP LaserJet\".",
        )
    name = str(name_raw).replace("'", "''")
    script = f"""
$ErrorActionPreference = 'Stop'
$printer = Get-CimInstance -ClassName Win32_Printer -Filter "Name='{name}'"
if (-not $printer) {{ throw "Printer not found: {name}" }}
Invoke-CimMethod -InputObject $printer -MethodName SetDefaultPrinter | Out-Null
'ok'
"""
    try:
        code, out, err = win_ps.run_ps(script, timeout=30)
        if code != 0:
            raise RuntimeError((err or out).strip())
        return ToolResult(ok=True, message=f"Default printer set to {name_raw}")
    except Exception as exc:  # noqa: BLE001
        _open_settings_uri("ms-settings:printers")
        return ToolResult(
            ok=False,
            message=f"Could not set default printer ({exc}); opened Printers settings.",
        )


def _list_bluetooth(_args: dict) -> ToolResult:
    """
    List Bluetooth radio + paired peripherals, and related headset audio devices.

    Classic paired BT shows as BTHENUM/BTHLEDEVICE. Many 'Bluetooth headsets' are
    actually USB dongles (e.g. Jabra Link) or LE Audio endpoints — surface those
    separately so we don't report 'nothing paired' when a headset is clearly active.
    """
    script = r"""
$ErrorActionPreference = 'SilentlyContinue'
$infraName = 'Enumerator|Protocol TDI|Personal Area Network|Wireless Bluetooth|PCI Enumerator|RFCOMM|LE Enumerator|Bluetooth$'

# Scoped queries (faster than full Get-PnpDevice walk)
$btClass = @(Get-PnpDevice -Class Bluetooth -ErrorAction SilentlyContinue)
$pairedPnP = @(Get-PnpDevice -ErrorAction SilentlyContinue | Where-Object {
  $_.InstanceId -like 'BTHENUM\*' -or $_.InstanceId -like 'BTHLEDEVICE\*'
})
$adapters = @($btClass | Where-Object {
  $_.FriendlyName -match 'Wireless Bluetooth|PCI Enumerator' -or
  $_.InstanceId -match 'IBTPDODEVICE|IBTPCIBUS|PCI\\VEN_|HCIH4'
} | Select-Object -Unique InstanceId, FriendlyName, Status)

# Named peripherals in Bluetooth class that are not infra
$named = @($btClass | Where-Object {
  $_.FriendlyName -and ($_.FriendlyName -notmatch $infraName) -and
  $_.InstanceId -notmatch 'IBTPDODEVICE|IBTPCIBUS|PCI\\VEN_|MS_BTH|MS_RFCOMM|MS_BTHLE'
} | Select-Object -Unique InstanceId, FriendlyName, Status, Class)

$paired = @()
foreach ($d in ($pairedPnP + $named)) {
  if (-not $d.FriendlyName) { continue }
  if ($d.FriendlyName -match $infraName) { continue }
  $paired += [PSCustomObject]@{
    name = $d.FriendlyName
    status = $d.Status
    connected = ($d.Status -eq 'OK')
    class = $d.Class
    instance_id = $d.InstanceId
    kind = 'bluetooth'
  }
}
# de-dupe by instance id
$seen = @{}
$paired = @($paired | Where-Object {
  if ($seen.ContainsKey($_.instance_id)) { $false } else { $seen[$_.instance_id] = $true; $true }
})

# Active headset-like audio (USB dongles / LE audio) — common false "Bluetooth headset"
$headsetRe = 'Headset|Headphone|Jabra|AirPods|Buds|WH-|BOSE|SoundLink|Bluetooth.*Audio|LE Audio'
$audio = @(Get-PnpDevice -Class AudioEndpoint -ErrorAction SilentlyContinue | Where-Object {
  $_.Status -eq 'OK' -and $_.FriendlyName -and ($_.FriendlyName -match $headsetRe)
} | Select-Object -Unique FriendlyName, Status, InstanceId)
$media = @(Get-PnpDevice -Class MEDIA -ErrorAction SilentlyContinue | Where-Object {
  $_.Status -eq 'OK' -and $_.FriendlyName -and ($_.FriendlyName -match 'Jabra|AirPods|Buds|Headset|Bluetooth')
} | Select-Object -Unique FriendlyName, Status, InstanceId, Class)
$related = @()
foreach ($d in ($audio + $media)) {
  $related += [PSCustomObject]@{
    name = $d.FriendlyName
    status = $d.Status
    connected = ($d.Status -eq 'OK')
    class = $(if ($d.Class) { $d.Class } else { 'AudioEndpoint' })
    instance_id = $d.InstanceId
    kind = 'headset_audio'
  }
}
$rseen = @{}
$related = @($related | Where-Object {
  if ($rseen.ContainsKey($_.name)) { $false } else { $rseen[$_.name] = $true; $true }
})

[PSCustomObject]@{
  paired = @($paired)
  related_headsets = @($related)
  adapters = @($adapters | ForEach-Object {
    [PSCustomObject]@{ name = $_.FriendlyName; status = $_.Status; instance_id = $_.InstanceId }
  })
} | ConvertTo-Json -Compress -Depth 5
"""
    try:
        data = win_ps.run_ps_json(script, timeout=45) or {}
        if not isinstance(data, dict):
            data = {}
        paired = win_ps.as_list(data.get("paired"))
        related = win_ps.as_list(data.get("related_headsets"))
        adapters = win_ps.as_list(data.get("adapters"))
        connected = [p for p in paired if p.get("connected")]
        related_ok = [p for p in related if p.get("connected")]

        parts: list[str] = []
        if connected:
            names = ", ".join(str(p.get("name") or "?") for p in connected[:8])
            parts.append(f"{len(connected)} connected Bluetooth device(s): {names}")
        elif paired:
            parts.append(
                f"{len(paired)} paired Bluetooth device(s) (none currently Status=OK)"
            )
        elif adapters:
            parts.append(
                f"Bluetooth adapter present ({adapters[0].get('name')}); "
                "no classic paired Bluetooth peripherals (BTHENUM)"
            )
        else:
            parts.append("No Bluetooth adapters found")

        if related_ok:
            names = ", ".join(str(p.get("name") or "?") for p in related_ok[:8])
            parts.append(
                f"Active headset/audio device(s) (may be USB/dongle, not BT-paired): {names}"
            )

        return ToolResult(
            ok=True,
            message=" | ".join(parts),
            data={
                "connected": connected,
                "paired": paired,
                "related_headsets": related,
                "adapters": adapters,
            },
        )
    except Exception as exc:  # noqa: BLE001
        _open_settings_uri("ms-settings:bluetooth")
        return ToolResult(
            ok=False,
            message=f"Bluetooth query failed ({exc}); opened Bluetooth settings.",
        )


def _set_bluetooth_device(args: dict) -> ToolResult:
    instance_id = str(args["instance_id"]).replace("'", "''")
    enabled = bool(args["enabled"])
    cmd = "Enable-PnpDevice" if enabled else "Disable-PnpDevice"
    script = f"""
$ErrorActionPreference = 'Stop'
{cmd} -InstanceId '{instance_id}' -Confirm:$false
'ok'
"""
    try:
        code, out, err = win_ps.run_ps(script, timeout=30)
        if code != 0:
            raise RuntimeError((err or out).strip())
        return ToolResult(
            ok=True,
            message=f"{'Enabled' if enabled else 'Disabled'} {args['instance_id']}",
        )
    except Exception as exc:  # noqa: BLE001
        _open_settings_uri("ms-settings:bluetooth")
        return ToolResult(
            ok=False,
            message=f"PnP change failed ({exc}); opened Bluetooth settings.",
        )


def _get_brightness(_args: dict) -> ToolResult:
    script = r"""
$ErrorActionPreference = 'Stop'
$b = Get-CimInstance -Namespace root\wmi -ClassName WmiMonitorBrightness -ErrorAction Stop
$b | Select-Object Active, CurrentBrightness, InstanceName | ConvertTo-Json -Compress
"""
    try:
        data = win_ps.run_ps_json(script)
        items = win_ps.as_list(data) or ([data] if isinstance(data, dict) else [])
        if not items and isinstance(data, dict):
            items = [data]
        levels = [int(i.get("CurrentBrightness", 0)) for i in items if i]
        return ToolResult(
            ok=True,
            message=f"Brightness: {levels[0]}%" if levels else "Brightness info returned",
            data={"monitors": items, "percent": levels[0] if levels else None},
        )
    except Exception as exc:  # noqa: BLE001
        _open_settings_uri("ms-settings:display")
        return ToolResult(
            ok=False,
            message=(
                f"Brightness not available via WMI ({exc}); "
                "opened Display settings (common on external-only monitors)."
            ),
        )


def _set_brightness(args: dict) -> ToolResult:
    pct = max(0, min(100, int(args["percent"])))
    # Try CIM then legacy WMI (laptops); desktops with only external monitors often lack this.
    script = f"""
$ErrorActionPreference = 'Stop'
$ok = $false
try {{
  $m = Get-CimInstance -Namespace root\\wmi -ClassName WmiMonitorBrightnessMethods -ErrorAction Stop
  foreach ($x in @($m)) {{
    Invoke-CimMethod -InputObject $x -MethodName WmiSetBrightness -Arguments @{{Brightness={pct}; Timeout=0}} | Out-Null
    $ok = $true
  }}
}} catch {{}}
if (-not $ok) {{
  $m = Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods -ErrorAction Stop
  foreach ($x in @($m)) {{
    $x.WmiSetBrightness(1, {pct}) | Out-Null
    $ok = $true
  }}
}}
if (-not $ok) {{ throw 'No brightness-capable monitor interface found' }}
'ok'
"""
    try:
        code, out, err = win_ps.run_ps(script, timeout=30)
        if code != 0:
            raise RuntimeError((err or out).strip())
        return ToolResult(ok=True, message=f"Brightness set to {pct}%", data={"percent": pct})
    except Exception as exc:  # noqa: BLE001
        _open_settings_uri("ms-settings:display")
        return ToolResult(
            ok=False,
            message=(
                f"Could not set brightness in software ({exc}). "
                "Opened Display settings — many desktop PCs only support "
                "brightness on the monitor OSD, not via Windows."
            ),
            data={"percent": pct, "settings_opened": True},
        )


def _get_contrast(_args: dict) -> ToolResult:
    """OS-level contrast (High Contrast + color filters). Not monitor OSD."""
    script = r"""
$ErrorActionPreference = 'SilentlyContinue'
$hc = Get-ItemProperty 'HKCU:\Control Panel\Accessibility\HighContrast' -ErrorAction SilentlyContinue
$flags = 0
if ($hc -and $null -ne $hc.Flags) { $flags = [int]$hc.Flags }
$scheme = ''
if ($hc) { $scheme = [string]$hc.'High Contrast Scheme' }
$cf = Get-ItemProperty 'HKCU:\Software\Microsoft\ColorFiltering' -ErrorAction SilentlyContinue
$cfActive = $false
$cfType = $null
if ($cf) {
  if ($null -ne $cf.Active) { $cfActive = [bool]$cf.Active }
  if ($null -ne $cf.FilterType) { $cfType = [int]$cf.FilterType }
}
[PSCustomObject]@{
  high_contrast_on = [bool]($flags -band 1)
  high_contrast_flags = $flags
  high_contrast_scheme = $scheme
  color_filter_active = $cfActive
  color_filter_type = $cfType
} | ConvertTo-Json -Compress
"""
    try:
        data = win_ps.run_ps_json(script, timeout=20) or {}
        if isinstance(data, list):
            data = data[0] if data else {}
        hc_on = bool(data.get("high_contrast_on"))
        scheme = (data.get("high_contrast_scheme") or "").strip()
        cf_on = bool(data.get("color_filter_active"))
        parts = []
        if hc_on:
            parts.append(
                f"Windows High Contrast is ON"
                + (f" (scheme: {scheme})" if scheme else "")
            )
        else:
            parts.append("Windows High Contrast is OFF")
        if cf_on:
            parts.append(f"Color filters ON (type={data.get('color_filter_type')})")
        else:
            parts.append("Color filters OFF")
        parts.append(
            "Physical monitor contrast is not exposed by Windows — "
            "adjust it on the display OSD if needed."
        )
        return ToolResult(
            ok=True,
            message="; ".join(parts),
            data={"contrast": data},
        )
    except Exception as exc:  # noqa: BLE001
        _open_settings_uri("ms-settings:easeofaccess-highcontrast")
        return ToolResult(
            ok=False,
            message=(
                f"Could not read contrast settings ({exc}); "
                "opened Ease of Access > High contrast."
            ),
        )


def _display_info(_args: dict) -> ToolResult:
    script = r"""
$ErrorActionPreference = 'SilentlyContinue'
$adapters = @(Get-CimInstance Win32_VideoController | ForEach-Object {
  [PSCustomObject]@{
    name = $_.Name
    width = $_.CurrentHorizontalResolution
    height = $_.CurrentVerticalResolution
    refresh_hz = $_.CurrentRefreshRate
    driver = $_.DriverVersion
  }
})
# Also try Win32_DesktopMonitor / screen via .NET for primary
Add-Type -AssemblyName System.Windows.Forms -ErrorAction SilentlyContinue
$screens = @()
try {
  $screens = @([System.Windows.Forms.Screen]::AllScreens | ForEach-Object {
    [PSCustomObject]@{
      primary = $_.Primary
      width = $_.Bounds.Width
      height = $_.Bounds.Height
      bits = $_.BitsPerPixel
    }
  })
} catch {}
[PSCustomObject]@{ adapters = $adapters; screens = $screens } | ConvertTo-Json -Compress -Depth 4
"""
    try:
        data = win_ps.run_ps_json(script) or {}
        if not isinstance(data, dict):
            data = {"adapters": win_ps.as_list(data)}
        screens = win_ps.as_list(data.get("screens"))
        adapters = win_ps.as_list(data.get("adapters"))
        primary = next((s for s in screens if s.get("primary")), screens[0] if screens else None)
        if primary and primary.get("width") and primary.get("height"):
            msg = f"Screen resolution: {primary['width']}x{primary['height']}"
            if len(screens) > 1:
                msg += f" (primary; {len(screens)} monitors)"
        else:
            active = [
                a
                for a in adapters
                if a.get("width") and a.get("height") and int(a.get("width") or 0) > 0
            ]
            if active:
                a = active[0]
                msg = f"Screen resolution: {a['width']}x{a['height']}"
            else:
                msg = "Display adapter info (resolution unavailable)"
        return ToolResult(
            ok=True,
            message=msg,
            data={"screens": screens, "adapters": adapters},
        )
    except Exception as exc:  # noqa: BLE001
        _open_settings_uri("ms-settings:display")
        return ToolResult(
            ok=False,
            message=f"Display query failed ({exc}); opened Display settings.",
        )


def _open_notepad(args: dict) -> ToolResult:
    path = args.get("path")
    cmd = ["notepad.exe"]
    if path:
        cmd.append(str(path))
    subprocess.Popen(cmd)
    return ToolResult(ok=True, message="Opened Notepad")


def _open_explorer(args: dict) -> ToolResult:
    path = args.get("path") or str(__import__("pathlib").Path.home())
    subprocess.Popen(["explorer.exe", str(path)])
    return ToolResult(ok=True, message=f"Opened Explorer at {path}")
