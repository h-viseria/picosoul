"""Linux inventory scanners (Debian / Ubuntu / antiX / WSL)."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from osagent.inventory.store import _utc_now


def _run(cmd: list[str], timeout: int = 20) -> str:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (p.stdout or "").strip()
    except Exception:
        return ""


def _alnum(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def scan_desktop_apps(*, max_apps: int = 800) -> list[dict[str, Any]]:
    """Parse .desktop files into inventory app records."""
    roots = [
        Path("/usr/share/applications"),
        Path("/usr/local/share/applications"),
        Path.home() / ".local/share/applications",
    ]
    found: dict[str, dict[str, Any]] = {}
    for root in roots:
        if not root.is_dir():
            continue
        for path in root.glob("*.desktop"):
            if len(found) >= max_apps:
                return list(found.values())
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            if "NoDisplay=true" in text or "Hidden=true" in text:
                continue
            name = path.stem
            exec_cmd = ""
            for ln in text.splitlines():
                if ln.startswith("Name=") and not ln.startswith("Name["):
                    name = ln.split("=", 1)[1].strip() or name
                elif ln.startswith("Exec="):
                    exec_cmd = ln.split("=", 1)[1].strip()
            # strip field codes
            bin_name = re.split(r"\s+", exec_cmd.replace("%[a-zA-Z]", "").strip())[0] if exec_cmd else ""
            resolved = shutil.which(Path(bin_name).name) if bin_name else None
            key = _alnum(name) or path.stem.lower()
            found[key] = {
                "id": key[:64],
                "name": name,
                "stem": path.stem,
                "names": sorted({name, path.stem, Path(bin_name).name} - {""}),
                "path": resolved or str(path),
                "desktop": str(path),
                "kind": "desktop",
                "source": "desktop",
                "launch_count": 0,
                "last_used": None,
            }
    return list(found.values())


def scan_path_binaries(*, max_bins: int = 400) -> list[dict[str, Any]]:
    """Index common PATH binaries as launchable apps."""
    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for dir_s in (os.environ.get("PATH") or "").split(os.pathsep):
        d = Path(dir_s)
        if not d.is_dir():
            continue
        try:
            entries = list(d.iterdir())
        except OSError:
            continue
        for p in entries:
            if len(out) >= max_bins:
                return out
            if not p.is_file():
                continue
            name = p.name
            if name in seen or name.startswith("."):
                continue
            seen.add(name)
            key = _alnum(name) or name.lower()
            out.append(
                {
                    "id": key[:64],
                    "name": name,
                    "stem": name,
                    "names": [name],
                    "path": str(p),
                    "kind": "bin",
                    "source": "path",
                    "launch_count": 0,
                    "last_used": None,
                }
            )
    return out


def scan_installed_packages_sample(*, limit: int = 500) -> list[dict[str, Any]]:
    """Sample installed apt packages as inventory 'apps' (name → package)."""
    out: list[dict[str, Any]] = []
    raw = _run(["dpkg-query", "-W", "-f=${Package}\t${Version}\n"], timeout=60)
    for ln in raw.splitlines()[:limit]:
        if "\t" not in ln:
            continue
        pkg, ver = ln.split("\t", 1)
        key = _alnum(pkg) or pkg
        out.append(
            {
                "id": f"pkg-{key}"[:64],
                "name": pkg,
                "stem": pkg,
                "names": [pkg],
                "path": f"package:{pkg}",
                "version": ver,
                "kind": "package",
                "source": "dpkg",
                "launch_count": 0,
                "last_used": None,
                "control": {
                    "show": "linux.packages.show",
                    "remove": "linux.packages.remove",
                },
            }
        )
    return out


def scan_linux_defaults() -> dict[str, Any]:
    defaults: dict[str, Any] = {}
    browser = (
        shutil.which("xdg-settings")
        and _run(["xdg-settings", "get", "default-web-browser"], timeout=5)
    )
    if browser:
        defaults["http"] = {"hint": browser, "progid": browser}
        defaults["https"] = {"hint": browser, "progid": browser}
    editor = os.environ.get("EDITOR") or os.environ.get("VISUAL")
    if editor:
        defaults["txt"] = {"hint": editor}
    shell = os.environ.get("SHELL")
    if shell:
        defaults["shell"] = {"hint": shell}
    return defaults


def scan_linux_devices() -> dict[str, Any]:
    devices: dict[str, Any] = {
        "printers": [],
        "audio": [],
        "bluetooth": [],
        "displays": [],
        "network": [],
        "updated_at": _utc_now(),
    }
    # Network interfaces
    ifaces = _run(["ip", "-br", "a"], timeout=8)
    for ln in ifaces.splitlines()[:30]:
        parts = ln.split()
        if parts:
            devices["network"].append(
                {
                    "name": parts[0],
                    "raw": ln,
                    "control": {
                        "list": "linux.network.interfaces",
                        "routes": "linux.network.routes",
                    },
                }
            )
    # Audio (PulseAudio / PipeWire best-effort)
    if shutil.which("pactl"):
        sinks = _run(["pactl", "list", "short", "sinks"], timeout=8)
        for ln in sinks.splitlines()[:20]:
            devices["audio"].append(
                {
                    "name": ln.split("\t")[1] if "\t" in ln else ln,
                    "raw": ln,
                    "control": {},
                }
            )
    elif shutil.which("aplay"):
        devices["audio"].append({"name": "ALSA default", "control": {}})

    # Bluetooth
    if shutil.which("bluetoothctl"):
        devices["bluetooth"].append(
            {
                "name": "bluetoothctl",
                "control": {"list": "linux.bluetooth.list"},
                "notes": "Query live via linux.bluetooth.list (often no radio in WSL)",
            }
        )

    # Displays via xrandr
    if shutil.which("xrandr") and os.environ.get("DISPLAY"):
        xr = _run(["xrandr"], timeout=8)
        for ln in xr.splitlines():
            if " connected" in ln:
                name = ln.split()[0]
                devices["displays"].append(
                    {
                        "name": name,
                        "raw": ln.strip(),
                        "control": {
                            "set_resolution": "linux.display.set_resolution",
                        },
                    }
                )

    # Printers
    if shutil.which("lpstat"):
        printers = _run(["lpstat", "-a"], timeout=8)
        for ln in printers.splitlines()[:30]:
            name = ln.split()[0] if ln.split() else ln
            devices["printers"].append(
                {
                    "name": name,
                    "raw": ln,
                    "control": {
                        "list": "linux.printers.list",
                        "default": "linux.printers.default",
                    },
                }
            )

    return devices
