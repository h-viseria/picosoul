"""app.* lifecycle + windows.apps.* install helpers."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from osagent.tools.base import ConfirmLevel, Tool, ToolResult
from osagent.tools.win_ps import run_ps


def build_tools() -> list[Tool]:
    return [
        Tool(
            id="app.close",
            description="Close an application gracefully by process name (e.g. excel, chrome).",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Process name without .exe"},
                    "force": {"type": "boolean", "default": False},
                },
                "required": ["name"],
            },
            confirm=ConfirmLevel.ASK,
            handler=_app_close,
            platforms=("windows",),
        ),
        Tool(
            id="app.get_status",
            description="Check whether an app process is running / responding.",
            parameters={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
            confirm=ConfirmLevel.NONE,
            handler=_app_status,
            platforms=("windows",),
        ),
        Tool(
            id="app.get_installed_details",
            description="Get version, publisher, install location for an installed app.",
            parameters={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
            confirm=ConfirmLevel.NONE,
            handler=_installed_details,
            platforms=("windows",),
        ),
        Tool(
            id="app.create_shortcut",
            description="Create a desktop or Start Menu shortcut to an exe/path.",
            parameters={
                "type": "object",
                "properties": {
                    "target": {"type": "string", "description": "Exe or file path"},
                    "name": {"type": "string", "description": "Shortcut name"},
                    "location": {
                        "type": "string",
                        "description": "desktop | startmenu",
                        "default": "desktop",
                    },
                },
                "required": ["target", "name"],
            },
            confirm=ConfirmLevel.ASK,
            handler=_create_shortcut,
            platforms=("windows",),
        ),
        Tool(
            id="app.uninstall",
            description="Uninstall an application via winget (requires confirmation).",
            parameters={
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "winget package id or name"},
                },
                "required": ["name"],
            },
            confirm=ConfirmLevel.DESTRUCTIVE,
            handler=_uninstall,
            platforms=("windows",),
        ),
        Tool(
            id="windows.apps.search_available",
            description="Search winget for available applications to install.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 10},
                },
                "required": ["query"],
            },
            confirm=ConfirmLevel.NONE,
            handler=_winget_search,
            platforms=("windows",),
        ),
        Tool(
            id="windows.apps.install",
            description="Install an application with winget (id or name).",
            parameters={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "winget package id preferred"},
                    "name": {"type": "string"},
                },
            },
            confirm=ConfirmLevel.DESTRUCTIVE,
            handler=_winget_install,
            platforms=("windows",),
        ),
        Tool(
            id="windows.apps.update",
            description="Upgrade packages with winget (all or one id).",
            parameters={
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "Optional single package id"},
                },
            },
            confirm=ConfirmLevel.ASK,
            handler=_winget_update,
            platforms=("windows",),
        ),
        Tool(
            id="windows.apps.uninstall",
            description="Uninstall via winget (alias of app.uninstall).",
            parameters={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
            confirm=ConfirmLevel.DESTRUCTIVE,
            handler=_uninstall,
            platforms=("windows",),
        ),
        Tool(
            id="windows.apps.get_install_status",
            description="List winget upgrades available (install/update queue proxy).",
            parameters={"type": "object", "properties": {}},
            confirm=ConfirmLevel.NONE,
            handler=_winget_status,
            platforms=("windows",),
        ),
        Tool(
            id="windows.apps.create_shortcut",
            description="Create a desktop/Start Menu shortcut (same as app.create_shortcut).",
            parameters={
                "type": "object",
                "properties": {
                    "target": {"type": "string"},
                    "name": {"type": "string"},
                    "location": {"type": "string", "default": "desktop"},
                },
                "required": ["target", "name"],
            },
            confirm=ConfirmLevel.ASK,
            handler=_create_shortcut,
            platforms=("windows",),
        ),
    ]


def _app_close(args: dict) -> ToolResult:
    name = str(args.get("name") or "").strip().removesuffix(".exe")
    force = bool(args.get("force"))
    if not name:
        return ToolResult(ok=False, message="name required")
    verb = "Stop-Process -Force" if force else "Stop-Process"
    script = rf"""
$n = '{name.replace("'", "''")}'
$p = Get-Process -Name $n -ErrorAction SilentlyContinue
if (-not $p) {{ [PSCustomObject]@{{ ok=$false; message='Not running' }} | ConvertTo-Json -Compress }}
else {{
  $p | {verb} -ErrorAction SilentlyContinue
  [PSCustomObject]@{{ ok=$true; count=@($p).Count; name=$n }} | ConvertTo-Json -Compress
}}
"""
    return _json_ps(script, timeout=30)


def _app_status(args: dict) -> ToolResult:
    name = str(args.get("name") or "").strip().removesuffix(".exe")
    script = rf"""
$n = '{name.replace("'", "''")}'
$p = @(Get-Process -Name $n -ErrorAction SilentlyContinue)
[PSCustomObject]@{{
  name = $n
  running = ($p.Count -gt 0)
  count = $p.Count
  responding = if ($p.Count -gt 0) {{ [bool]($p | Where-Object Responding | Select-Object -First 1) }} else {{ $null }}
  pids = @($p | ForEach-Object Id)
}} | ConvertTo-Json -Compress
"""
    code, out, err = run_ps(script, timeout=20)
    if code != 0:
        return ToolResult(ok=False, message=(err or out)[:400])
    try:
        data = json.loads(out.strip() or "{}")
    except json.JSONDecodeError:
        return ToolResult(ok=False, message=out[:300])
    running = bool(data.get("running"))
    return ToolResult(
        ok=True,
        message=(
            f"{name}: {'running' if running else 'not running'}"
            + (f", responding={data.get('responding')}" if running else "")
        ),
        data=data if isinstance(data, dict) else {},
    )


def _installed_details(args: dict) -> ToolResult:
    name = str(args.get("name") or "").strip()
    script = rf"""
$ErrorActionPreference = 'SilentlyContinue'
$needle = '{name.replace("'", "''")}'
$paths = @(
  'HKLM:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*',
  'HKLM:\Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall\*',
  'HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*'
)
$hits = foreach ($p in $paths) {{
  Get-ItemProperty $p | Where-Object {{
    $_.DisplayName -and ($_.DisplayName -like ("*" + $needle + "*"))
  }} | Select-Object -First 8 DisplayName, DisplayVersion, Publisher, InstallLocation, UninstallString
}}
@($hits) | ConvertTo-Json -Compress
"""
    code, out, err = run_ps(script, timeout=45)
    if code != 0:
        return ToolResult(ok=False, message=(err or out)[:400])
    text = out.strip()
    if not text or text == "null":
        return ToolResult(ok=False, message=f"No installed app matching '{name}'")
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return ToolResult(ok=False, message=text[:300])
    items = data if isinstance(data, list) else [data]
    lines = [
        f"- {i.get('DisplayName')} v{i.get('DisplayVersion')} ({i.get('Publisher')})"
        for i in items
        if isinstance(i, dict)
    ]
    return ToolResult(
        ok=True,
        message=f"{len(items)} match(es):\n" + "\n".join(lines),
        data={"apps": items},
    )


def _create_shortcut(args: dict) -> ToolResult:
    target = str(args.get("target") or "").strip()
    name = str(args.get("name") or "").strip()
    loc = str(args.get("location") or "desktop").lower()
    if not target or not name:
        return ToolResult(ok=False, message="target and name required")
    if loc == "startmenu":
        folder = Path.home() / "AppData/Roaming/Microsoft/Windows/Start Menu/Programs"
    else:
        folder = Path.home() / "Desktop"
    lnk = folder / f"{name}.lnk"
    script = rf"""
$W = New-Object -ComObject WScript.Shell
$s = $W.CreateShortcut('{str(lnk).replace("'", "''")}')
$s.TargetPath = '{target.replace("'", "''")}'
$s.WorkingDirectory = '{str(Path(target).parent).replace("'", "''")}'
$s.Save()
[PSCustomObject]@{{ ok=$true; path='{str(lnk).replace("'", "''")}' }} | ConvertTo-Json -Compress
"""
    return _json_ps(script, timeout=20)


def _uninstall(args: dict) -> ToolResult:
    name = str(args.get("name") or "").strip()
    if not name:
        return ToolResult(ok=False, message="name required")
    cmd = [
        "winget",
        "uninstall",
        "--exact",
        "--id",
        name,
        "--accept-source-agreements",
        "--disable-interactivity",
    ]
    # try id first; fallback to name query
    completed = subprocess.run(cmd, capture_output=True, text=True, timeout=300, check=False)
    if completed.returncode != 0:
        completed = subprocess.run(
            [
                "winget",
                "uninstall",
                "--name",
                name,
                "--accept-source-agreements",
                "--disable-interactivity",
            ],
            capture_output=True,
            text=True,
            timeout=300,
            check=False,
        )
    ok = completed.returncode == 0
    msg = (completed.stdout or completed.stderr or "").strip()[:800]
    return ToolResult(ok=ok, message=msg or ("Uninstalled" if ok else "Uninstall failed"))


def _winget_search(args: dict) -> ToolResult:
    query = str(args.get("query") or "").strip()
    limit = max(1, min(int(args.get("limit") or 10), 30))
    if not query:
        return ToolResult(ok=False, message="query required")
    completed = subprocess.run(
        ["winget", "search", query, "--accept-source-agreements", "--disable-interactivity"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    text = (completed.stdout or completed.stderr or "").strip()
    lines = [ln for ln in text.splitlines() if ln.strip()][: limit + 5]
    return ToolResult(
        ok=completed.returncode == 0,
        message="\n".join(lines) or "No results",
        data={"raw": text[:4000]},
    )


def _winget_install(args: dict) -> ToolResult:
    pkg = str(args.get("id") or args.get("name") or "").strip()
    if not pkg:
        return ToolResult(ok=False, message="id or name required")
    cmd = [
        "winget",
        "install",
        "--id" if args.get("id") else "--name",
        pkg,
        "--accept-package-agreements",
        "--accept-source-agreements",
        "--disable-interactivity",
    ]
    completed = subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=False)
    msg = (completed.stdout or completed.stderr or "").strip()[:1000]
    return ToolResult(
        ok=completed.returncode == 0,
        message=msg or ("Installed" if completed.returncode == 0 else "Install failed"),
    )


def _winget_update(args: dict) -> ToolResult:
    pkg = str(args.get("id") or "").strip()
    cmd = ["winget", "upgrade", "--accept-package-agreements", "--accept-source-agreements", "--disable-interactivity"]
    if pkg:
        cmd.extend(["--id", pkg])
    else:
        cmd.append("--all")
    completed = subprocess.run(cmd, capture_output=True, text=True, timeout=600, check=False)
    msg = (completed.stdout or completed.stderr or "").strip()[:1000]
    return ToolResult(ok=completed.returncode == 0, message=msg or "Upgrade finished")


def _winget_status(_args: dict) -> ToolResult:
    completed = subprocess.run(
        ["winget", "upgrade", "--accept-source-agreements", "--disable-interactivity"],
        capture_output=True,
        text=True,
        timeout=180,
        check=False,
    )
    text = (completed.stdout or completed.stderr or "").strip()
    return ToolResult(
        ok=True,
        message=text[:2000] or "No upgrades listed",
        data={"raw": text[:4000]},
    )


def _json_ps(script: str, *, timeout: float) -> ToolResult:
    code, out, err = run_ps(script, timeout=timeout)
    if code != 0:
        return ToolResult(ok=False, message=(err or out)[:400])
    try:
        data = json.loads(out.strip() or "{}")
    except json.JSONDecodeError:
        return ToolResult(ok=False, message=out[:300] or err[:300])
    if isinstance(data, dict) and data.get("ok") is False:
        return ToolResult(ok=False, message=str(data.get("message") or "failed"), data=data)
    msg = "ok"
    if isinstance(data, dict):
        msg = str(data.get("message") or data.get("path") or data.get("name") or "ok")
    return ToolResult(ok=True, message=msg, data=data if isinstance(data, dict) else {"result": data})
