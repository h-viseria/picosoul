"""One-shot / incremental scans that populate the inventory."""

from __future__ import annotations

import os
import re
import time
from pathlib import Path
from typing import Any, Callable

from osagent.inventory.store import _utc_now


def _expand(path: str) -> str:
    return os.path.expandvars(path)


def _alnum(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def _app_key(name: str, path: str | None = None) -> str:
    base = _alnum(Path(name).stem if name else "") or _alnum(path or "") or "app"
    return base[:64]


def _skip_exe(name: str) -> bool:
    low = name.lower()
    skip = (
        "uninstall",
        "unins000",
        "setup.exe",
        "installer",
        "crashreporter",
        "update.exe",
        "updater.exe",
        "vcredist",
        "helper.exe",
    )
    return any(s in low for s in skip)


def scan_filesystem_apps(*, max_files: int = 2500) -> list[dict[str, Any]]:
    """Scan common roots for .exe / .lnk (bounded)."""
    home = Path.home()
    roots: list[tuple[Path, int]] = [
        (Path(_expand(r"%USERPROFILE%\Desktop")), 4),
        (Path(_expand(r"%PUBLIC%\Desktop")), 3),
        (home / "Downloads", 4),
        (Path(_expand(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs")), 5),
        (Path(_expand(r"%ProgramData%\Microsoft\Windows\Start Menu\Programs")), 5),
        (Path(_expand(r"%LOCALAPPDATA%\Programs")), 3),
        (Path(_expand(r"%ProgramFiles%")), 2),
        (Path(_expand(r"%ProgramFiles(x86)%")), 2),
    ]
    found: dict[str, dict[str, Any]] = {}
    count = 0

    for root, depth in roots:
        if not root.is_dir():
            continue
        try:
            for dirpath, dirnames, filenames in os.walk(root):
                if count >= max_files:
                    return list(found.values())
                rel = Path(dirpath).relative_to(root)
                if len(rel.parts) > depth:
                    dirnames[:] = []
                    continue
                dirnames[:] = [
                    d
                    for d in dirnames
                    if d.lower()
                    not in {
                        "node_modules",
                        ".git",
                        "windows",
                        "winsxs",
                        "system32",
                        "syswow64",
                        "__pycache__",
                    }
                ]
                for fn in filenames:
                    low = fn.lower()
                    if not (low.endswith(".exe") or low.endswith(".lnk")):
                        continue
                    if low.endswith(".exe") and _skip_exe(low):
                        continue
                    path = Path(dirpath) / fn
                    try:
                        key = str(path.resolve()).lower()
                    except OSError:
                        key = str(path).lower()
                    if key in found:
                        continue
                    kind = "lnk" if low.endswith(".lnk") else "exe"
                    names = {path.stem, path.name}
                    if "portable" in path.stem.lower():
                        names.add(path.stem.replace("Portable", "").replace("portable", ""))
                    found[key] = {
                        "key": _app_key(path.stem, str(path)),
                        "path": str(path),
                        "name": path.name,
                        "stem": path.stem,
                        "names": sorted({n for n in names if n}),
                        "kind": kind,
                        "source": f"scan:{root.name}",
                        "launch_count": 0,
                        "last_used": None,
                    }
                    count += 1
        except OSError:
            continue
    return list(found.values())


def scan_start_apps() -> list[dict[str, Any]]:
    """Start-menu apps via Get-StartApps (names; AppID as path hint)."""
    try:
        from osagent.tools import win_ps
    except Exception:
        return []
    script = (
        "Get-StartApps | Select-Object -First 400 Name, AppID | ConvertTo-Json -Compress"
    )
    try:
        data = win_ps.run_ps_json(script, timeout=90)
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    for item in win_ps.as_list(data):
        name = str(item.get("Name") or "").strip()
        app_id = str(item.get("AppID") or "").strip()
        if not name:
            continue
        out.append(
            {
                "key": _app_key(name, app_id),
                "path": app_id or None,
                "name": name,
                "stem": name,
                "names": [name],
                "kind": "startapp",
                "source": "startmenu",
                "launch_count": 0,
                "last_used": None,
            }
        )
    return out


def scan_alias_apps() -> list[dict[str, Any]]:
    """Resolve known launch aliases into inventory entries."""
    try:
        from osagent.tools.win_launch import ALIASES, resolve_executable_strict
    except Exception:
        return []
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for alias, exe in ALIASES.items():
        path = resolve_executable_strict(alias)
        if path is None:
            continue
        key = str(path.resolve()).lower()
        if key in seen:
            # merge alias name into existing via key collision handled by merge later
            out.append(
                {
                    "key": _app_key(path.stem, str(path)),
                    "path": str(path),
                    "name": path.name,
                    "stem": path.stem,
                    "names": [alias, path.stem, path.name],
                    "kind": "exe",
                    "source": "alias",
                    "launch_count": 0,
                    "last_used": None,
                }
            )
            continue
        seen.add(key)
        out.append(
            {
                "key": _app_key(path.stem, str(path)),
                "path": str(path),
                "name": path.name,
                "stem": path.stem,
                "names": [alias, path.stem, path.name, exe],
                "kind": "exe",
                "source": "alias",
                "launch_count": 0,
                "last_used": None,
            }
        )
    return out


def scan_default_apps() -> dict[str, Any]:
    """Best-effort default browser / mail / associations."""
    defaults: dict[str, Any] = {}
    try:
        from osagent.tools import win_ps

        script = r"""
$ErrorActionPreference = 'SilentlyContinue'
$http = (Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice' -ErrorAction SilentlyContinue).ProgId
$https = (Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\Shell\Associations\UrlAssociations\https\UserChoice' -ErrorAction SilentlyContinue).ProgId
$mailto = (Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\Shell\Associations\UrlAssociations\mailto\UserChoice' -ErrorAction SilentlyContinue).ProgId
$txt = (Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.txt\UserChoice' -ErrorAction SilentlyContinue).ProgId
$pdf = (Get-ItemProperty 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Explorer\FileExts\.pdf\UserChoice' -ErrorAction SilentlyContinue).ProgId
[PSCustomObject]@{
  http = $http; https = $https; mailto = $mailto; txt = $txt; pdf = $pdf
} | ConvertTo-Json -Compress
"""
        data = win_ps.run_ps_json(script, timeout=20) or {}
        if isinstance(data, dict):
            for role, progid in data.items():
                if progid:
                    defaults[str(role)] = {
                        "progid": str(progid),
                        "hint": str(progid),
                    }
    except Exception:
        pass
    return defaults


def scan_devices_snapshot() -> dict[str, Any]:
    """Lightweight device snapshot (printers + displays)."""
    devices: dict[str, Any] = {
        "printers": [],
        "audio": [],
        "bluetooth": [],
        "displays": [],
        "updated_at": _utc_now(),
    }
    try:
        from osagent.tools import win_ps

        printers = win_ps.run_ps_json(
            r"""
Get-CimInstance Win32_Printer | Select-Object Name, DriverName, PortName, Default |
  ConvertTo-Json -Compress
""",
            timeout=30,
        )
        for p in win_ps.as_list(printers):
            devices["printers"].append(
                {
                    "name": p.get("Name"),
                    "driver": p.get("DriverName"),
                    "port": p.get("PortName"),
                    "default": bool(p.get("Default")),
                    "control": {
                        "list": "windows.printers.list",
                        "default": "windows.printers.default",
                        "set_default": "windows.printers.set_default",
                    },
                }
            )
    except Exception:
        pass

    try:
        from osagent.tools import win_ps

        screens = win_ps.run_ps_json(
            r"""
Add-Type -AssemblyName System.Windows.Forms -ErrorAction SilentlyContinue
[System.Windows.Forms.Screen]::AllScreens | ForEach-Object {
  [PSCustomObject]@{
    primary = $_.Primary
    width = $_.Bounds.Width
    height = $_.Bounds.Height
  }
} | ConvertTo-Json -Compress
""",
            timeout=15,
        )
        for s in win_ps.as_list(screens):
            devices["displays"].append(
                {
                    **s,
                    "control": {
                        "info": "windows.display.info",
                        "brightness": "windows.display.set_brightness",
                    },
                }
            )
    except Exception:
        pass

    devices["audio"] = [
        {
            "name": "System default playback",
            "control": {
                "get": "windows.volume.get",
                "set": "windows.volume.set_percent",
                "adjust": "windows.volume.adjust",
                "mute": "windows.volume.mute",
            },
        }
    ]
    devices["bluetooth"] = [
        {
            "note": "Query live via windows.bluetooth.list",
            "control": {"list": "windows.bluetooth.list"},
        }
    ]
    return devices


def seed_command_catalog(tool_specs: list[dict[str, str]] | None = None) -> dict[str, Any]:
    """Map known control tools into inventory.commands."""
    builtins = [
        ("windows.volume.get", "Get master volume"),
        ("windows.volume.set_percent", "Set master volume 0-100"),
        ("windows.volume.adjust", "Adjust volume by delta"),
        ("windows.volume.mute", "Mute/unmute"),
        ("windows.display.info", "Screen resolution / adapters"),
        ("windows.display.set_brightness", "Set brightness percent"),
        ("windows.printers.default", "Show default printer"),
        ("windows.printers.list", "List printers"),
        ("windows.printers.set_default", "Set default printer by name"),
        ("windows.bluetooth.list", "List Bluetooth devices"),
        ("app.launch", "Launch app (uses inventory + fuzzy search)"),
        ("app.find", "Find executables by name"),
        ("web.open", "Open URL in browser"),
        ("web.search", "Web search"),
    ]
    out: dict[str, Any] = {}
    for tid, desc in builtins:
        out[tid] = {
            "description": desc,
            "ok_count": 0,
            "fail_count": 0,
            "last_used": None,
            "last_ok": None,
        }
    if tool_specs:
        for spec in tool_specs:
            tid = spec.get("id") or ""
            if tid and tid not in out:
                out[tid] = {
                    "description": (spec.get("description") or "")[:120],
                    "ok_count": 0,
                    "fail_count": 0,
                    "last_used": None,
                    "last_ok": None,
                }
    return out


def merge_app_records(
    existing: dict[str, Any],
    incoming: list[dict[str, Any]],
) -> dict[str, Any]:
    """Merge scanned apps into apps dict keyed by stable path/key."""
    apps = dict(existing or {})

    def path_key(rec: dict[str, Any]) -> str:
        p = (rec.get("path") or "").strip().lower()
        if p:
            return "path:" + p
        return "key:" + str(rec.get("key") or rec.get("name") or "unknown")

    index_by_path = {path_key(v): k for k, v in apps.items()}

    for rec in incoming:
        pk = path_key(rec)
        if pk in index_by_path:
            aid = index_by_path[pk]
            cur = apps[aid]
            names = set(cur.get("names") or [])
            names.update(rec.get("names") or [])
            names.add(rec.get("name") or "")
            names.add(rec.get("stem") or "")
            cur["names"] = sorted({n for n in names if n})
            if rec.get("path") and (
                not cur.get("path") or cur.get("kind") == "startapp"
            ):
                if rec.get("kind") == "exe":
                    cur["path"] = rec["path"]
                    cur["kind"] = "exe"
            cur["source"] = cur.get("source") or rec.get("source")
            continue

        # new
        aid = str(rec.get("key") or _app_key(str(rec.get("name")), str(rec.get("path"))))
        base = aid
        n = 2
        while aid in apps:
            aid = f"{base}_{n}"
            n += 1
        apps[aid] = {
            "path": rec.get("path"),
            "name": rec.get("name"),
            "stem": rec.get("stem"),
            "names": sorted(
                {
                    *(rec.get("names") or []),
                    rec.get("name") or "",
                    rec.get("stem") or "",
                }
                - {""}
            ),
            "kind": rec.get("kind") or "exe",
            "source": rec.get("source") or "scan",
            "launch_count": int(rec.get("launch_count") or 0),
            "last_used": rec.get("last_used"),
        }
        index_by_path[pk] = aid
    return apps


ProgressCb = Callable[[str], None]


def run_full_build(
    data: dict[str, Any],
    *,
    progress: ProgressCb | None = None,
    tool_specs: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """Mutate inventory dict in place with a full scan. Returns same dict."""
    t0 = time.time()
    data.setdefault("scan", {})
    data["scan"]["status"] = "running"
    data["scan"]["last_error"] = None

    def note(msg: str) -> None:
        if progress:
            progress(msg)

    try:
        import sys

        if sys.platform.startswith("linux"):
            from osagent.inventory.linux_scan import (
                scan_desktop_apps,
                scan_installed_packages_sample,
                scan_linux_defaults,
                scan_linux_devices,
                scan_path_binaries,
            )

            note("Indexing .desktop applications…")
            desktop_apps = scan_desktop_apps()
            note("Indexing PATH binaries…")
            path_apps = scan_path_binaries()
            note("Sampling installed apt packages…")
            pkg_apps = scan_installed_packages_sample(limit=400)
            note("Reading defaults (xdg/editor)…")
            defaults = scan_linux_defaults()
            note("Snapshotting devices (net/audio/displays)…")
            devices = scan_linux_devices()
            alias_apps: list[dict[str, Any]] = []
            fs_apps = desktop_apps + path_apps + pkg_apps
            start_apps: list[dict[str, Any]] = []
        else:
            note("Indexing launch aliases…")
            alias_apps = scan_alias_apps()
            note("Scanning folders for executables…")
            fs_apps = scan_filesystem_apps()
            note("Reading Start menu apps…")
            start_apps = scan_start_apps()
            note("Reading default app associations…")
            defaults = scan_default_apps()
            note("Snapshotting devices…")
            devices = scan_devices_snapshot()

        note("Seeding command map…")
        commands = seed_command_catalog(tool_specs)
        # preserve usage counters from previous commands
        old_cmds = data.get("commands") or {}
        for tid, meta in commands.items():
            if tid in old_cmds and isinstance(old_cmds[tid], dict):
                meta["ok_count"] = int(old_cmds[tid].get("ok_count") or 0)
                meta["fail_count"] = int(old_cmds[tid].get("fail_count") or 0)
                meta["last_used"] = old_cmds[tid].get("last_used")
                meta["last_ok"] = old_cmds[tid].get("last_ok")

        # preserve launch counts when merging
        old_apps = data.get("apps") or {}
        merged = merge_app_records({}, alias_apps + fs_apps + start_apps)
        # copy usage from old by path
        old_by_path = {
            str(v.get("path") or "").lower(): v
            for v in old_apps.values()
            if v.get("path")
        }
        for rec in merged.values():
            p = str(rec.get("path") or "").lower()
            if p and p in old_by_path:
                prev = old_by_path[p]
                rec["launch_count"] = int(prev.get("launch_count") or 0)
                rec["last_used"] = prev.get("last_used")
                names = set(rec.get("names") or [])
                names.update(prev.get("names") or [])
                rec["names"] = sorted({n for n in names if n})

        note("Probing hardware & app capabilities…")
        from .capabilities import build_capabilities_section

        old_caps = data.get("capabilities") if isinstance(data.get("capabilities"), dict) else {}
        capabilities = build_capabilities_section(
            apps=merged,
            devices=devices,
            previous=old_caps,
        )

        data["apps"] = merged
        data["default_apps"] = defaults
        data["devices"] = devices
        data["commands"] = commands
        data["capabilities"] = capabilities
        data["built_at"] = data.get("built_at") or _utc_now()
        data["scan"]["status"] = "ok"
        data["scan"]["apps_indexed"] = len(merged)
        data["scan"]["duration_sec"] = round(time.time() - t0, 2)
        hw_n = len((capabilities.get("hardware") or {}))
        app_n = len((capabilities.get("apps") or {}))
        note(
            f"Inventory ready: {len(merged)} apps, {hw_n} hardware domains, "
            f"{app_n} app capability profiles in {data['scan']['duration_sec']}s"
        )
    except Exception as exc:  # noqa: BLE001
        data["scan"]["status"] = "error"
        data["scan"]["last_error"] = str(exc)[:400]
        data["scan"]["duration_sec"] = round(time.time() - t0, 2)
        note(f"Inventory scan failed: {exc}")
    return data
