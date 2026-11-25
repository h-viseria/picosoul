"""Probe and catalog hardware settings + per-app command options."""

from __future__ import annotations

from typing import Any

from osagent.inventory.store import _utc_now


# Static knowledge: what OS Agent can try for each hardware domain
HARDWARE_CATALOG: dict[str, dict[str, Any]] = {
    "display": {
        "label": "Display / screen",
        "settings": [
            {
                "id": "resolution",
                "label": "Screen resolution",
                "readable": True,
                "writable": False,
                "tools": {"get": "windows.display.info"},
            },
            {
                "id": "brightness",
                "label": "Brightness percent",
                "readable": True,
                "writable": True,
                "tools": {
                    "get": "windows.display.get_brightness",
                    "set": "windows.display.set_brightness",
                },
                "notes": "Often laptop panels only; external monitors may lack WMI support",
            },
            {
                "id": "contrast",
                "label": "OS High Contrast / color filters",
                "readable": True,
                "writable": False,
                "tools": {"get": "windows.display.get_contrast"},
                "notes": "Physical monitor contrast is OSD-only on most hardware",
            },
        ],
        "commands": [
            "windows.display.info",
            "windows.display.get_brightness",
            "windows.display.set_brightness",
            "windows.display.get_contrast",
        ],
    },
    "audio": {
        "label": "Audio / speakers",
        "settings": [
            {
                "id": "volume",
                "label": "Master volume percent",
                "readable": True,
                "writable": True,
                "tools": {
                    "get": "windows.volume.get",
                    "set": "windows.volume.set_percent",
                    "adjust": "windows.volume.adjust",
                },
            },
            {
                "id": "mute",
                "label": "Mute",
                "readable": True,
                "writable": True,
                "tools": {"set": "windows.volume.mute"},
            },
        ],
        "commands": [
            "windows.volume.get",
            "windows.volume.set_percent",
            "windows.volume.adjust",
            "windows.volume.mute",
        ],
    },
    "printers": {
        "label": "Printers",
        "settings": [
            {
                "id": "default_printer",
                "label": "Default printer",
                "readable": True,
                "writable": True,
                "tools": {
                    "get": "windows.printers.default",
                    "list": "windows.printers.list",
                    "set": "windows.printers.set_default",
                },
            },
        ],
        "commands": [
            "windows.printers.list",
            "windows.printers.default",
            "windows.printers.get",
            "windows.printers.set_default",
        ],
    },
    "bluetooth": {
        "label": "Bluetooth",
        "settings": [
            {
                "id": "devices",
                "label": "Paired / connected devices",
                "readable": True,
                "writable": True,
                "tools": {
                    "list": "windows.bluetooth.list",
                    "set_adapter": "windows.bluetooth.set_adapter",
                },
            },
        ],
        "commands": [
            "windows.bluetooth.list",
            "windows.bluetooth.set_adapter",
        ],
    },
    "network": {
        "label": "Network / Wi-Fi",
        "settings": [
            {
                "id": "wifi",
                "label": "Wi-Fi profiles / status",
                "readable": True,
                "writable": False,
                "tools": {
                    "list": "windows.wifi.list",
                    "status": "windows.wifi.status",
                },
            },
            {
                "id": "ip",
                "label": "IP configuration",
                "readable": True,
                "writable": False,
                "tools": {"get": "windows.network.ipconfig"},
            },
        ],
        "commands": [
            "windows.wifi.list",
            "windows.wifi.status",
            "windows.network.ipconfig",
        ],
    },
    "power": {
        "label": "Power / battery",
        "settings": [
            {
                "id": "battery",
                "label": "Battery charge",
                "readable": True,
                "writable": False,
                "tools": {"get": "windows.battery.status"},
            },
        ],
        "commands": ["windows.battery.status"],
    },
}


# Known app families → what the agent can do with them
APP_ACTION_CATALOG: dict[str, dict[str, Any]] = {
    "excel": {
        "aliases": ["excel", "microsoft excel"],
        "actions": [
            {"id": "launch", "tool": "app.launch", "args": {"target": "excel"}},
            {
                "id": "open_named",
                "tool": "files.open_named",
                "kinds": ["excel", "xlsx", "xls", "spreadsheet"],
            },
            {"id": "open_recent", "tool": "files.open_recent", "kinds": ["excel", "xlsx"]},
        ],
        "file_kinds": ["xlsx", "xls", "xlsm", "csv"],
    },
    "word": {
        "aliases": ["word", "microsoft word", "winword"],
        "actions": [
            {"id": "launch", "tool": "app.launch", "args": {"target": "word"}},
            {
                "id": "open_named",
                "tool": "files.open_named",
                "kinds": ["word", "docx", "doc"],
            },
            {"id": "open_recent", "tool": "files.open_recent", "kinds": ["word", "docx"]},
        ],
        "file_kinds": ["docx", "doc", "docm"],
    },
    "powerpoint": {
        "aliases": ["powerpoint", "ppt", "microsoft powerpoint"],
        "actions": [
            {"id": "launch", "tool": "app.launch", "args": {"target": "powerpoint"}},
            {
                "id": "open_named",
                "tool": "files.open_named",
                "kinds": ["ppt", "pptx", "powerpoint", "presentation"],
            },
            {"id": "open_recent", "tool": "files.open_recent", "kinds": ["ppt", "pptx"]},
        ],
        "file_kinds": ["pptx", "ppt", "pptm"],
    },
    "notepad": {
        "aliases": ["notepad"],
        "actions": [
            {"id": "launch", "tool": "app.launch", "args": {"target": "notepad"}},
            {
                "id": "open_named",
                "tool": "files.open_named",
                "kinds": ["txt", "text"],
            },
        ],
        "file_kinds": ["txt", "log", "md"],
    },
    "paint": {
        "aliases": ["paint", "mspaint"],
        "actions": [
            {"id": "launch", "tool": "app.launch", "args": {"target": "paint"}},
            {
                "id": "open_named",
                "tool": "files.open_named",
                "kinds": ["image", "photo", "png", "jpg"],
                "args": {"app": "paint"},
            },
        ],
        "file_kinds": ["png", "jpg", "jpeg", "bmp", "gif"],
    },
    "chrome": {
        "aliases": ["chrome", "google chrome"],
        "actions": [
            {"id": "launch", "tool": "app.launch", "args": {"target": "chrome"}},
            {"id": "open_url", "tool": "web.open", "args": {"browser": "chrome"}},
        ],
        "file_kinds": ["html", "htm"],
    },
    "edge": {
        "aliases": ["edge", "microsoft edge", "msedge"],
        "actions": [
            {"id": "launch", "tool": "app.launch", "args": {"target": "edge"}},
            {"id": "open_url", "tool": "web.open", "args": {"browser": "edge"}},
        ],
        "file_kinds": ["html", "htm"],
    },
    "firefox": {
        "aliases": ["firefox", "mozilla firefox"],
        "actions": [
            {"id": "launch", "tool": "app.launch", "args": {"target": "firefox"}},
            {"id": "open_url", "tool": "web.open", "args": {"browser": "firefox"}},
        ],
        "file_kinds": ["html", "htm"],
    },
    "vscode": {
        "aliases": ["vscode", "code", "visual studio code", "vs code"],
        "actions": [
            {"id": "launch", "tool": "app.launch", "args": {"target": "vscode"}},
        ],
        "file_kinds": ["py", "js", "ts", "json", "md"],
    },
    "calculator": {
        "aliases": ["calculator", "calc"],
        "actions": [
            {"id": "launch", "tool": "app.launch", "args": {"target": "calculator"}},
        ],
        "file_kinds": [],
    },
    "explorer": {
        "aliases": ["explorer", "file explorer"],
        "actions": [
            {"id": "launch", "tool": "app.launch", "args": {"target": "explorer"}},
            {"id": "open_path", "tool": "files.open_path"},
        ],
        "file_kinds": [],
    },
}


# ----- Linux capability maps (Debian / Ubuntu / antiX / WSL) -----

LINUX_HARDWARE_CATALOG: dict[str, dict[str, Any]] = {
    "system": {
        "label": "System",
        "settings": [
            {
                "id": "info",
                "label": "OS / hostname / kernel",
                "readable": True,
                "writable": False,
                "tools": {"get": "linux.system.info"},
            },
            {
                "id": "uptime",
                "label": "Uptime",
                "readable": True,
                "writable": False,
                "tools": {"get": "linux.system.uptime"},
            },
            {
                "id": "health",
                "label": "Health report",
                "readable": True,
                "writable": False,
                "tools": {"get": "linux.system.health_report"},
            },
        ],
        "commands": [
            "linux.system.info",
            "linux.system.uptime",
            "linux.system.health_report",
            "linux.system.cpu_report",
            "linux.datetime.get",
        ],
    },
    "storage": {
        "label": "Disk / storage",
        "settings": [
            {
                "id": "disk_free",
                "label": "Disk free space",
                "readable": True,
                "writable": False,
                "tools": {"get": "linux.disk.free", "report": "linux.system.storage_report"},
            },
            {
                "id": "mounts",
                "label": "Mounted filesystems",
                "readable": True,
                "writable": False,
                "tools": {"list": "linux.mounts.list"},
            },
        ],
        "commands": [
            "linux.disk.free",
            "files.disk_free",
            "linux.system.storage_report",
            "linux.mounts.list",
        ],
    },
    "memory": {
        "label": "Memory / RAM",
        "settings": [
            {
                "id": "status",
                "label": "Memory usage",
                "readable": True,
                "writable": False,
                "tools": {"get": "linux.memory.status", "report": "linux.system.memory_report"},
            },
        ],
        "commands": ["linux.memory.status", "linux.system.memory_report"],
    },
    "packages": {
        "label": "Packages (apt)",
        "settings": [
            {
                "id": "search",
                "label": "Search packages",
                "readable": True,
                "writable": False,
                "tools": {"search": "linux.packages.search"},
            },
            {
                "id": "install",
                "label": "Install / remove packages",
                "readable": True,
                "writable": True,
                "tools": {
                    "install": "linux.packages.install",
                    "remove": "linux.packages.remove",
                    "update": "linux.packages.update",
                    "upgradable": "linux.packages.upgradable",
                },
            },
        ],
        "commands": [
            "linux.packages.search",
            "linux.packages.list_installed",
            "linux.packages.show",
            "linux.packages.install",
            "linux.packages.remove",
            "linux.packages.update",
            "linux.packages.upgradable",
        ],
    },
    "services": {
        "label": "Services",
        "settings": [
            {
                "id": "control",
                "label": "Start / stop / restart / status",
                "readable": True,
                "writable": True,
                "tools": {
                    "status": "linux.service.status",
                    "list": "linux.service.list",
                    "start": "linux.service.start",
                    "stop": "linux.service.stop",
                    "restart": "linux.service.restart",
                    "failed": "linux.service.failed",
                },
            },
        ],
        "commands": [
            "linux.service.status",
            "linux.service.list",
            "linux.service.start",
            "linux.service.stop",
            "linux.service.restart",
            "linux.service.failed",
        ],
    },
    "network": {
        "label": "Network",
        "settings": [
            {
                "id": "interfaces",
                "label": "Interfaces / addresses",
                "readable": True,
                "writable": False,
                "tools": {"get": "linux.network.interfaces"},
            },
            {
                "id": "wifi",
                "label": "Wi-Fi (NetworkManager)",
                "readable": True,
                "writable": False,
                "tools": {
                    "list": "linux.network.wifi_list",
                    "status": "linux.network.wifi_status",
                },
            },
            {
                "id": "firewall",
                "label": "Firewall",
                "readable": True,
                "writable": False,
                "tools": {"status": "linux.firewall.status"},
            },
        ],
        "commands": [
            "linux.network.interfaces",
            "linux.network.routes",
            "linux.network.listening",
            "linux.network.ping",
            "linux.network.dns_lookup",
            "linux.network.wifi_list",
            "linux.network.wifi_status",
            "linux.network.test_connectivity",
            "linux.network.dns_flush",
            "linux.firewall.status",
        ],
    },
    "bluetooth": {
        "label": "Bluetooth",
        "settings": [
            {
                "id": "devices",
                "label": "Paired / connected devices",
                "readable": True,
                "writable": False,
                "tools": {"list": "linux.bluetooth.list"},
            },
        ],
        "commands": ["linux.bluetooth.list"],
    },
    "processes": {
        "label": "Processes",
        "settings": [
            {
                "id": "list",
                "label": "List / top processes",
                "readable": True,
                "writable": True,
                "tools": {
                    "list": "linux.process.list",
                    "top": "linux.processes.top",
                    "kill": "linux.process.kill",
                },
            },
        ],
        "commands": [
            "linux.process.list",
            "linux.process.kill",
            "linux.processes.top",
        ],
    },
    "logs": {
        "label": "Logs",
        "settings": [
            {
                "id": "tail",
                "label": "Tail logs / journal",
                "readable": True,
                "writable": False,
                "tools": {
                    "tail": "linux.logs.tail",
                    "search": "linux.logs.journal_search",
                },
            },
        ],
        "commands": ["linux.logs.tail", "linux.logs.journal_search"],
    },
    "display": {
        "label": "Display (X11)",
        "settings": [
            {
                "id": "resolution",
                "label": "Screen resolution",
                "readable": True,
                "writable": True,
                "tools": {
                    "get": "linux.display.info",
                    "set": "linux.display.set_resolution",
                },
                "notes": "Requires X11 / DISPLAY; unavailable on headless WSL",
            },
            {
                "id": "brightness",
                "label": "Backlight brightness",
                "readable": True,
                "writable": True,
                "tools": {
                    "get": "linux.display.get_brightness",
                    "set": "linux.display.set_brightness",
                },
            },
            {
                "id": "contrast",
                "label": "Accessibility contrast",
                "readable": True,
                "writable": False,
                "tools": {"get": "linux.display.get_contrast"},
            },
        ],
        "commands": [
            "linux.display.info",
            "linux.display.set_resolution",
            "linux.display.get_brightness",
            "linux.display.set_brightness",
            "linux.display.get_contrast",
            "linux.settings.open",
        ],
    },
    "audio": {
        "label": "Audio / volume",
        "settings": [
            {
                "id": "volume",
                "label": "Master volume",
                "readable": True,
                "writable": True,
                "tools": {
                    "get": "linux.volume.get",
                    "set": "linux.volume.set_percent",
                    "adjust": "linux.volume.adjust",
                    "mute": "linux.volume.mute",
                    "reset": "linux.volume.reset",
                },
            },
        ],
        "commands": [
            "linux.volume.get",
            "linux.volume.set_percent",
            "linux.volume.adjust",
            "linux.volume.mute",
            "linux.volume.reset",
        ],
    },
    "printers": {
        "label": "Printers (CUPS)",
        "settings": [
            {
                "id": "default_printer",
                "label": "Default printer",
                "readable": True,
                "writable": False,
                "tools": {
                    "get": "linux.printers.default",
                    "list": "linux.printers.list",
                },
            },
        ],
        "commands": ["linux.printers.list", "linux.printers.default"],
    },
    "power": {
        "label": "Power / battery",
        "settings": [
            {
                "id": "battery",
                "label": "Battery status",
                "readable": True,
                "writable": False,
                "tools": {"get": "linux.battery.status"},
            },
        ],
        "commands": ["linux.battery.status"],
    },
}

LINUX_APP_ACTION_CATALOG: dict[str, dict[str, Any]] = {
    "firefox": {
        "aliases": ["firefox", "mozilla firefox"],
        "actions": [{"id": "launch", "tool": "app.launch", "args": {"target": "firefox"}}],
        "file_kinds": [],
    },
    "chrome": {
        "aliases": ["chrome", "google-chrome", "chromium", "chromium-browser"],
        "actions": [{"id": "launch", "tool": "app.launch", "args": {"target": "google-chrome"}}],
        "file_kinds": [],
    },
    "code": {
        "aliases": ["code", "vscode", "visual studio code"],
        "actions": [{"id": "launch", "tool": "app.launch", "args": {"target": "code"}}],
        "file_kinds": [],
    },
    "nautilus": {
        "aliases": ["nautilus", "files", "file manager"],
        "actions": [{"id": "launch", "tool": "app.launch", "args": {"target": "nautilus"}}],
        "file_kinds": [],
    },
    "docker": {
        "aliases": ["docker"],
        "actions": [{"id": "ps", "tool": "linux.docker.ps"}],
        "file_kinds": [],
    },
    "terminal": {
        "aliases": ["terminal", "gnome-terminal", "xterm", "konsole"],
        "actions": [{"id": "launch", "tool": "app.launch", "args": {"target": "x-terminal-emulator"}}],
        "file_kinds": [],
    },
}


def probe_hardware_support() -> dict[str, Any]:
    """Live probes: what this machine actually supports right now."""
    import sys

    if sys.platform.startswith("linux"):
        return _probe_linux_hardware()

    probed: dict[str, Any] = {"updated_at": _utc_now()}

    # Brightness
    try:
        from osagent.tools import win_ps

        data = win_ps.run_ps_json(
            r"""
$ErrorActionPreference = 'Stop'
$b = Get-CimInstance -Namespace root\wmi -ClassName WmiMonitorBrightness -ErrorAction Stop |
  Select-Object -First 1 CurrentBrightness
[PSCustomObject]@{ ok = $true; percent = [int]$b.CurrentBrightness } | ConvertTo-Json -Compress
""",
            timeout=15,
        )
        pct = None
        if isinstance(data, dict):
            pct = data.get("percent")
        probed["brightness"] = {
            "supported": True,
            "last_percent": pct,
            "last_ok": True,
        }
    except Exception as exc:
        probed["brightness"] = {
            "supported": False,
            "last_ok": False,
            "error": str(exc)[:200],
        }

    # Contrast / high contrast (always readable via registry)
    try:
        from osagent.tools import win_ps

        data = win_ps.run_ps_json(
            r"""
$ErrorActionPreference = 'SilentlyContinue'
$hc = Get-ItemProperty 'HKCU:\Control Panel\Accessibility\HighContrast'
$flags = 0
if ($hc -and $null -ne $hc.Flags) { $flags = [int]$hc.Flags }
[PSCustomObject]@{
  ok = $true
  high_contrast_on = [bool]($flags -band 1)
} | ConvertTo-Json -Compress
""",
            timeout=10,
        )
        probed["contrast"] = {
            "supported": True,  # OS-level
            "monitor_osd_only": True,
            "high_contrast_on": bool((data or {}).get("high_contrast_on"))
            if isinstance(data, dict)
            else False,
            "last_ok": True,
        }
    except Exception as exc:
        probed["contrast"] = {"supported": False, "last_ok": False, "error": str(exc)[:200]}

    # Volume
    try:
        from osagent.tools import win_ps

        pct = win_ps.get_volume_percent()
        probed["volume"] = {"supported": True, "last_percent": pct, "last_ok": True}
    except Exception as exc:
        probed["volume"] = {
            "supported": False,
            "last_ok": False,
            "error": str(exc)[:200],
        }

    # Battery present?
    try:
        from osagent.tools import win_ps

        data = win_ps.run_ps_json(
            r"""
$b = Get-CimInstance Win32_Battery -ErrorAction SilentlyContinue
if (-not $b) { [PSCustomObject]@{ present = $false } | ConvertTo-Json -Compress }
else {
  [PSCustomObject]@{
    present = $true
    charge = @($b)[0].EstimatedChargeRemaining
  } | ConvertTo-Json -Compress
}
""",
            timeout=15,
        )
        present = bool((data or {}).get("present")) if isinstance(data, dict) else False
        probed["battery"] = {
            "supported": present,
            "present": present,
            "last_charge": (data or {}).get("charge") if isinstance(data, dict) else None,
            "last_ok": True,
        }
    except Exception as exc:
        probed["battery"] = {"supported": False, "last_ok": False, "error": str(exc)[:200]}

    # Bluetooth adapter present?
    try:
        from osagent.tools import win_ps

        data = win_ps.run_ps_json(
            r"""
$n = @(Get-PnpDevice -Class Bluetooth -PresentOnly -ErrorAction SilentlyContinue).Count
[PSCustomObject]@{ count = $n; present = ($n -gt 0) } | ConvertTo-Json -Compress
""",
            timeout=20,
        )
        present = bool((data or {}).get("present")) if isinstance(data, dict) else False
        probed["bluetooth"] = {
            "supported": present,
            "present": present,
            "device_count": (data or {}).get("count") if isinstance(data, dict) else 0,
            "last_ok": True,
        }
    except Exception as exc:
        probed["bluetooth"] = {
            "supported": False,
            "last_ok": False,
            "error": str(exc)[:200],
        }

    # Resolution always available via .NET / CIM
    probed["resolution"] = {"supported": True, "last_ok": True}

    return probed


def _probe_linux_hardware() -> dict[str, Any]:
    """Best-effort Linux probes (no GUI required)."""
    import shutil
    from pathlib import Path

    probed: dict[str, Any] = {"updated_at": _utc_now()}
    probed["disk"] = {"supported": True, "last_ok": True}
    probed["memory"] = {"supported": Path("/proc/meminfo").is_file(), "last_ok": True}
    probed["packages"] = {"supported": bool(shutil.which("apt-get") or shutil.which("apt")), "last_ok": True}
    probed["services"] = {
        "supported": bool(shutil.which("systemctl") or shutil.which("service")),
        "last_ok": True,
    }
    probed["network"] = {"supported": bool(shutil.which("ip") or shutil.which("ifconfig")), "last_ok": True}
    probed["firewall"] = {
        "supported": bool(shutil.which("ufw") or shutil.which("firewall-cmd")),
        "last_ok": True,
    }
    probed["wifi"] = {"supported": bool(shutil.which("nmcli")), "last_ok": True}
    probed["docker"] = {"supported": bool(shutil.which("docker")), "last_ok": True}
    probed["journal"] = {"supported": bool(shutil.which("journalctl")), "last_ok": True}
    probed["display"] = {
        "supported": bool(shutil.which("xrandr") and __import__("os").environ.get("DISPLAY")),
        "last_ok": True,
    }
    probed["bluetooth"] = {
        "supported": bool(shutil.which("bluetoothctl")),
        "present": bool(shutil.which("bluetoothctl")),
        "last_ok": True,
    }
    probed["volume"] = {"supported": bool(shutil.which("pactl")), "last_ok": True}
    probed["printers"] = {"supported": bool(shutil.which("lpstat")), "last_ok": True}
    probed["brightness"] = {
        "supported": bool(
            shutil.which("brightnessctl") or Path("/sys/class/backlight").is_dir()
        ),
        "last_ok": True,
    }
    probed["contrast"] = {
        "supported": bool(shutil.which("gsettings")),
        "last_ok": True,
    }
    # Battery via sysfs
    bat = Path("/sys/class/power_supply")
    present = False
    if bat.is_dir():
        for p in bat.iterdir():
            if (p / "capacity").is_file() or (p / "energy_now").is_file():
                present = True
                break
    probed["battery"] = {"supported": present, "present": present, "last_ok": True}
    return probed


def build_hardware_capabilities(probed: dict[str, Any] | None = None) -> dict[str, Any]:
    """Merge static catalog with live probe results."""
    import sys

    probed = probed or probe_hardware_support()
    out: dict[str, Any] = {"updated_at": _utc_now(), "domains": {}}
    catalog = LINUX_HARDWARE_CATALOG if sys.platform.startswith("linux") else HARDWARE_CATALOG

    if sys.platform.startswith("linux"):
        support_map = {
            "system": {"info": True, "uptime": True, "health": True},
            "storage": {
                "disk_free": probed.get("disk", {}).get("supported", True),
                "mounts": True,
            },
            "memory": {"status": probed.get("memory", {}).get("supported", True)},
            "packages": {
                "search": probed.get("packages", {}).get("supported", False),
                "install": probed.get("packages", {}).get("supported", False),
            },
            "services": {"control": probed.get("services", {}).get("supported", False)},
            "network": {
                "interfaces": probed.get("network", {}).get("supported", True),
                "wifi": probed.get("wifi", {}).get("supported", False),
                "firewall": probed.get("firewall", {}).get("supported", False),
            },
            "bluetooth": {
                "devices": probed.get("bluetooth", {}).get("supported", False),
            },
            "audio": {
                "volume": probed.get("volume", {}).get("supported", False),
            },
            "printers": {
                "default_printer": probed.get("printers", {}).get("supported", False),
            },
            "power": {
                "battery": probed.get("battery", {}).get("supported", False),
            },
            "processes": {"list": True},
            "logs": {"tail": True},
            "display": {
                "resolution": probed.get("display", {}).get("supported", False),
                "brightness": probed.get("brightness", {}).get("supported", False),
                "contrast": probed.get("contrast", {}).get("supported", False),
            },
        }
    else:
        support_map = {
            "display": {
                "resolution": probed.get("resolution", {}).get("supported", True),
                "brightness": probed.get("brightness", {}).get("supported"),
                "contrast": probed.get("contrast", {}).get("supported", True),
            },
            "audio": {
                "volume": probed.get("volume", {}).get("supported"),
                "mute": probed.get("volume", {}).get("supported"),
            },
            "printers": {"default_printer": True},
            "bluetooth": {"devices": probed.get("bluetooth", {}).get("supported")},
            "network": {"wifi": True, "ip": True},
            "power": {"battery": probed.get("battery", {}).get("supported")},
        }

    for domain, meta in catalog.items():
        settings = []
        for s in meta.get("settings") or []:
            sid = s["id"]
            supported = support_map.get(domain, {}).get(sid)
            entry = dict(s)
            entry["supported"] = True if supported is None else bool(supported)
            # attach probe detail when present
            if domain == "display" and sid == "brightness":
                entry["probe"] = probed.get("brightness")
            if domain == "display" and sid == "contrast":
                entry["probe"] = probed.get("contrast")
            if domain == "audio" and sid in {"volume", "mute"}:
                entry["probe"] = probed.get("volume")
            if domain == "power" and sid == "battery":
                entry["probe"] = probed.get("battery")
            if domain == "bluetooth" and sid == "devices":
                entry["probe"] = probed.get("bluetooth")
            settings.append(entry)
        out["domains"][domain] = {
            "label": meta.get("label"),
            "settings": settings,
            "commands": list(meta.get("commands") or []),
        }
    out["probed"] = probed
    return out


def build_app_capabilities(
    installed_apps: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Catalog of actions per known app family, marked installed when path known.
    """
    import sys

    installed_apps = installed_apps or {}
    # Build lowercase name → path index from inventory apps
    name_index: dict[str, str] = {}
    for rec in installed_apps.values():
        path = rec.get("path") or ""
        for n in rec.get("names") or []:
            name_index[str(n).lower()] = path
        if rec.get("stem"):
            name_index[str(rec["stem"]).lower()] = path
        if rec.get("name"):
            name_index[str(rec["name"]).lower()] = path

    catalog = (
        LINUX_APP_ACTION_CATALOG
        if sys.platform.startswith("linux")
        else APP_ACTION_CATALOG
    )
    out: dict[str, Any] = {"updated_at": _utc_now(), "apps": {}}
    for app_id, meta in catalog.items():
        path = None
        for alias in meta.get("aliases") or []:
            if alias.lower() in name_index:
                path = name_index[alias.lower()]
                break
            # also try exe stem
            for key, p in name_index.items():
                if alias.lower() in key or key in alias.lower():
                    path = p
                    break
            if path:
                break
        out["apps"][app_id] = {
            "aliases": list(meta.get("aliases") or []),
            "actions": list(meta.get("actions") or []),
            "file_kinds": list(meta.get("file_kinds") or []),
            "installed": bool(path),
            "path": path,
        }
    return out


# Map tool_id → capability flag updates on success/failure
TOOL_CAPABILITY_HINTS: dict[str, tuple[str, str]] = {
    # tool_id -> (probe_key, means_supported_on_ok)
    "windows.display.get_brightness": ("brightness", True),
    "windows.display.set_brightness": ("brightness", True),
    "windows.display.get_contrast": ("contrast", True),
    "windows.display.info": ("resolution", True),
    "windows.volume.get": ("volume", True),
    "windows.volume.set_percent": ("volume", True),
    "windows.volume.adjust": ("volume", True),
    "windows.volume.mute": ("volume", True),
    "windows.battery.status": ("battery", True),
    "windows.bluetooth.list": ("bluetooth", True),
    "linux.bluetooth.list": ("bluetooth", True),
    "linux.battery.status": ("battery", True),
    "linux.printers.list": ("printers", True),
    "linux.printers.default": ("printers", True),
    "linux.display.info": ("resolution", True),
    "linux.display.get_brightness": ("brightness", True),
    "linux.display.set_brightness": ("brightness", True),
    "linux.display.get_contrast": ("contrast", True),
    "linux.volume.get": ("volume", True),
    "linux.volume.set_percent": ("volume", True),
    "linux.volume.adjust": ("volume", True),
    "linux.volume.mute": ("volume", True),
    "linux.volume.reset": ("volume", True),
    "linux.disk.free": ("disk", True),
    "files.disk_free": ("disk", True),
    "linux.memory.status": ("memory", True),
    "linux.packages.search": ("packages", True),
    "linux.packages.install": ("packages", True),
    "linux.service.status": ("services", True),
    "linux.network.interfaces": ("network", True),
    "linux.network.wifi_list": ("wifi", True),
    "linux.firewall.status": ("firewall", True),
    "linux.docker.ps": ("docker", True),
    "linux.logs.journal_search": ("journal", True),
    "linux.display.set_resolution": ("display", True),
}


def apply_tool_result_to_probed(
    probed: dict[str, Any],
    tool_id: str,
    *,
    ok: bool,
) -> dict[str, Any]:
    """Learn support flags from real tool outcomes."""
    hint = TOOL_CAPABILITY_HINTS.get(tool_id)
    if not hint:
        return probed
    key, _ = hint
    entry = dict(probed.get(key) or {})
    entry["last_ok"] = ok
    entry["last_used"] = _utc_now()
    if ok:
        entry["supported"] = True
    else:
        # don't flip supported to false on a single failure for volume/resolution
        if key in {"brightness", "battery", "bluetooth"}:
            entry["supported"] = False
        entry["fail_count"] = int(entry.get("fail_count") or 0) + 1
    probed[key] = entry
    return probed


def _refresh_hardware_supported_flags(hardware: dict[str, Any]) -> None:
    """Recompute setting.supported from probed after learning."""
    probed = hardware.get("probed") or {}
    support_map = {
        "display": {
            "resolution": (probed.get("resolution") or {}).get("supported", True),
            "brightness": (probed.get("brightness") or {}).get("supported"),
            "contrast": (probed.get("contrast") or {}).get("supported", True),
        },
        "audio": {
            "volume": (probed.get("volume") or {}).get("supported"),
            "mute": (probed.get("volume") or {}).get("supported"),
        },
        "power": {"battery": (probed.get("battery") or {}).get("supported")},
        "bluetooth": {"devices": (probed.get("bluetooth") or {}).get("supported")},
    }
    domains = hardware.get("domains") or {}
    for domain, meta in domains.items():
        sm = support_map.get(domain) or {}
        for setting in meta.get("settings") or []:
            sid = setting.get("id")
            if sid in sm and sm[sid] is not None:
                setting["supported"] = bool(sm[sid])
            if domain == "display" and sid == "brightness":
                setting["probe"] = probed.get("brightness")
            if domain == "display" and sid == "contrast":
                setting["probe"] = probed.get("contrast")
            if domain == "audio" and sid in {"volume", "mute"}:
                setting["probe"] = probed.get("volume")
            if domain == "power" and sid == "battery":
                setting["probe"] = probed.get("battery")
            if domain == "bluetooth" and sid == "devices":
                setting["probe"] = probed.get("bluetooth")


def enrich_capabilities_from_tool(
    capabilities: dict[str, Any],
    tool_id: str,
    *,
    ok: bool,
) -> dict[str, Any]:
    """Update cached hardware support from a real tool outcome (no re-probe)."""
    if not tool_id or tool_id not in TOOL_CAPABILITY_HINTS:
        return capabilities
    caps = dict(capabilities or {})
    hardware = dict(caps.get("hardware") or {})
    probed = dict(hardware.get("probed") or {})
    apply_tool_result_to_probed(probed, tool_id, ok=ok)
    hardware["probed"] = probed
    if not hardware.get("domains"):
        # Rebuild domains from catalog + probed so first learn still sticks
        rebuilt = build_hardware_capabilities(probed)
        hardware["domains"] = rebuilt.get("domains") or {}
    else:
        _refresh_hardware_supported_flags(hardware)
    hardware["updated_at"] = _utc_now()
    caps["hardware"] = hardware
    caps["updated_at"] = _utc_now()
    return caps


def build_capabilities_section(
    *,
    apps: dict[str, Any] | None = None,
    devices: dict[str, Any] | None = None,  # noqa: ARG001 — reserved for device-aware probes
    previous: dict[str, Any] | None = None,
    probe: bool = True,
) -> dict[str, Any]:
    """
    Full capabilities blob for inventory.json.

    Preserves previously learned probe flags when a fresh probe disagrees
    only because of a transient failure (prefer last successful support).
    """
    previous = previous or {}
    prev_hw = previous.get("hardware") if isinstance(previous.get("hardware"), dict) else {}
    prev_probed = dict(prev_hw.get("probed") or {})

    if probe:
        probed = probe_hardware_support()
        # Prefer previously confirmed support over a single fresh failure
        for key, old in prev_probed.items():
            if not isinstance(old, dict):
                continue
            new = probed.get(key)
            if not isinstance(new, dict):
                probed[key] = old
                continue
            if old.get("supported") and not new.get("supported"):
                # keep learned support; attach fresh error as note
                merged = dict(old)
                if new.get("error"):
                    merged["last_probe_error"] = new.get("error")
                merged["last_used"] = old.get("last_used") or new.get("last_used")
                probed[key] = merged
            elif new.get("supported"):
                # merge last_percent etc from new, keep fail_count from old
                merged = dict(new)
                if old.get("fail_count"):
                    merged["fail_count"] = old.get("fail_count")
                if old.get("last_used"):
                    merged["last_used"] = old.get("last_used")
                probed[key] = merged
    else:
        probed = prev_probed or {"updated_at": _utc_now()}

    hardware = build_hardware_capabilities(probed)
    app_caps = build_app_capabilities(apps)

    return {
        "hardware": hardware,
        "apps": app_caps.get("apps") or {},
        "updated_at": _utc_now(),
    }
