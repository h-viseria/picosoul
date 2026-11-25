"""Linux sysadmin / desktop tools (Debian, Ubuntu, antiX, WSL)."""

from __future__ import annotations

import os
import re
import shutil
from pathlib import Path

from osagent.tools.base import ConfirmLevel, Tool, ToolResult
from osagent.tools.linux_exec import (
    has_systemd,
    package_manager,
    result_from_cmd,
    run_cmd,
    which,
)


def build_tools() -> list[Tool]:
    return [
        # --- Shell escape hatch ---
        Tool(
            id="linux.shell.run",
            description=(
                "Run a bash command when no specialized tool fits. Prefer catalog "
                "tools first. Pass full command + short rationale. Write/delete/"
                "service changes require confirmation; dangerous patterns are blocked."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "command": {"type": "string", "description": "Bash one-liner"},
                    "rationale": {"type": "string"},
                    "timeout_sec": {"type": "integer", "default": 90},
                },
                "required": ["command"],
            },
            confirm=ConfirmLevel.NONE,
            handler=_shell_run,
            platforms=("linux",),
        ),
        # --- System status ---
        Tool(
            id="linux.system.info",
            description="OS name, kernel, arch, hostname, uptime summary.",
            parameters={"type": "object", "properties": {}},
            confirm=ConfirmLevel.NONE,
            handler=_system_info,
            platforms=("linux",),
        ),
        Tool(
            id="linux.system.home",
            description=(
                "Show the current user's home folder. On WSL also reports the "
                "Windows profile path under /mnt/c/Users when available."
            ),
            parameters={"type": "object", "properties": {}},
            confirm=ConfirmLevel.NONE,
            handler=_home_folder,
            platforms=("linux",),
        ),
        Tool(
            id="linux.system.uptime",
            description="System uptime and load averages.",
            parameters={"type": "object", "properties": {}},
            confirm=ConfirmLevel.NONE,
            handler=_uptime,
            platforms=("linux",),
        ),
        Tool(
            id="linux.disk.free",
            description="Disk free space (df -h) for mounted filesystems.",
            parameters={"type": "object", "properties": {}},
            confirm=ConfirmLevel.NONE,
            handler=_disk_free,
            platforms=("linux",),
        ),
        Tool(
            id="linux.memory.status",
            description="RAM and swap usage (free -h).",
            parameters={"type": "object", "properties": {}},
            confirm=ConfirmLevel.NONE,
            handler=_memory,
            platforms=("linux",),
        ),
        Tool(
            id="linux.cpu.info",
            description="CPU model and core count from /proc/cpuinfo / nproc.",
            parameters={"type": "object", "properties": {}},
            confirm=ConfirmLevel.NONE,
            handler=_cpu_info,
            platforms=("linux",),
        ),
        # --- Packages (apt-first; Debian/antiX/Ubuntu/WSL) ---
        Tool(
            id="linux.packages.search",
            description="Search apt packages by name/keyword (apt-cache search).",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 30},
                },
                "required": ["query"],
            },
            confirm=ConfirmLevel.NONE,
            handler=_pkg_search,
            platforms=("linux",),
        ),
        Tool(
            id="linux.packages.list_installed",
            description="List installed packages; optional name filter.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Substring filter"},
                    "limit": {"type": "integer", "default": 40},
                },
            },
            confirm=ConfirmLevel.NONE,
            handler=_pkg_list,
            platforms=("linux",),
        ),
        Tool(
            id="linux.packages.show",
            description="Show details for one package (apt-cache show / dpkg -s).",
            parameters={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
            confirm=ConfirmLevel.NONE,
            handler=_pkg_show,
            platforms=("linux",),
        ),
        Tool(
            id="linux.packages.install",
            description="Install package(s) via apt-get install (needs network + privileges).",
            parameters={
                "type": "object",
                "properties": {
                    "packages": {
                        "type": "string",
                        "description": "Space-separated package names",
                    },
                },
                "required": ["packages"],
            },
            confirm=ConfirmLevel.ASK,
            handler=_pkg_install,
            platforms=("linux",),
        ),
        Tool(
            id="linux.packages.remove",
            description="Remove package(s) via apt-get remove (not purge).",
            parameters={
                "type": "object",
                "properties": {"packages": {"type": "string"}},
                "required": ["packages"],
            },
            confirm=ConfirmLevel.DESTRUCTIVE,
            handler=_pkg_remove,
            platforms=("linux",),
        ),
        Tool(
            id="linux.packages.update",
            description="Refresh package indexes (apt-get update).",
            parameters={"type": "object", "properties": {}},
            confirm=ConfirmLevel.ASK,
            handler=_pkg_update,
            platforms=("linux",),
        ),
        # --- Services ---
        Tool(
            id="linux.service.status",
            description="Status of a service (systemctl or service).",
            parameters={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
            confirm=ConfirmLevel.NONE,
            handler=_svc_status,
            platforms=("linux",),
        ),
        Tool(
            id="linux.service.list",
            description="List services (systemd units or /etc/init.d).",
            parameters={
                "type": "object",
                "properties": {
                    "running_only": {"type": "boolean", "default": False},
                    "limit": {"type": "integer", "default": 50},
                },
            },
            confirm=ConfirmLevel.NONE,
            handler=_svc_list,
            platforms=("linux",),
        ),
        Tool(
            id="linux.service.start",
            description="Start a service.",
            parameters={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
            confirm=ConfirmLevel.ASK,
            handler=lambda a: _svc_action(a, "start"),
            platforms=("linux",),
        ),
        Tool(
            id="linux.service.stop",
            description="Stop a service.",
            parameters={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
            confirm=ConfirmLevel.ASK,
            handler=lambda a: _svc_action(a, "stop"),
            platforms=("linux",),
        ),
        Tool(
            id="linux.service.restart",
            description="Restart a service.",
            parameters={
                "type": "object",
                "properties": {"name": {"type": "string"}},
                "required": ["name"],
            },
            confirm=ConfirmLevel.ASK,
            handler=lambda a: _svc_action(a, "restart"),
            platforms=("linux",),
        ),
        # --- Processes ---
        Tool(
            id="linux.process.list",
            description="List processes (ps); optional name filter.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 40},
                },
            },
            confirm=ConfirmLevel.NONE,
            handler=_proc_list,
            platforms=("linux",),
        ),
        Tool(
            id="linux.process.kill",
            description="Send signal to a PID (default SIGTERM).",
            parameters={
                "type": "object",
                "properties": {
                    "pid": {"type": "integer"},
                    "signal": {"type": "string", "default": "TERM"},
                },
                "required": ["pid"],
            },
            confirm=ConfirmLevel.DESTRUCTIVE,
            handler=_proc_kill,
            platforms=("linux",),
        ),
        # --- Network ---
        Tool(
            id="linux.network.interfaces",
            description="List network interfaces and addresses (ip -br a).",
            parameters={"type": "object", "properties": {}},
            confirm=ConfirmLevel.NONE,
            handler=_net_ifaces,
            platforms=("linux",),
        ),
        Tool(
            id="linux.network.routes",
            description="Show routing table (ip route).",
            parameters={"type": "object", "properties": {}},
            confirm=ConfirmLevel.NONE,
            handler=_net_routes,
            platforms=("linux",),
        ),
        Tool(
            id="linux.network.listening",
            description="Listening TCP/UDP ports (ss -tulpn).",
            parameters={"type": "object", "properties": {}},
            confirm=ConfirmLevel.NONE,
            handler=_net_listening,
            platforms=("linux",),
        ),
        Tool(
            id="linux.network.ping",
            description="Ping a host (count-limited).",
            parameters={
                "type": "object",
                "properties": {
                    "host": {"type": "string"},
                    "count": {"type": "integer", "default": 3},
                },
                "required": ["host"],
            },
            confirm=ConfirmLevel.NONE,
            handler=_net_ping,
            platforms=("linux",),
        ),
        Tool(
            id="linux.network.dns_lookup",
            description="Resolve a hostname (getent hosts / dig).",
            parameters={
                "type": "object",
                "properties": {"host": {"type": "string"}},
                "required": ["host"],
            },
            confirm=ConfirmLevel.NONE,
            handler=_net_dns,
            platforms=("linux",),
        ),
        Tool(
            id="linux.bluetooth.list",
            description=(
                "List Bluetooth adapters and paired/connected devices via bluetoothctl. "
                "Often unavailable in WSL (no BT passthrough)."
            ),
            parameters={"type": "object", "properties": {}},
            confirm=ConfirmLevel.NONE,
            handler=_bluetooth_list,
            platforms=("linux",),
        ),
        # --- Printers (CUPS) ---
        Tool(
            id="linux.printers.list",
            description="List CUPS printers (lpstat). Use for 'list printers'.",
            parameters={"type": "object", "properties": {}},
            confirm=ConfirmLevel.NONE,
            handler=_printers_list,
            platforms=("linux",),
        ),
        Tool(
            id="linux.printers.default",
            description="Show the default CUPS printer (lpstat -d).",
            parameters={"type": "object", "properties": {}},
            confirm=ConfirmLevel.NONE,
            handler=_printers_default,
            platforms=("linux",),
        ),
        # --- Battery / power ---
        Tool(
            id="linux.battery.status",
            description="Laptop battery percent/status from sysfs (/sys/class/power_supply).",
            parameters={"type": "object", "properties": {}},
            confirm=ConfirmLevel.NONE,
            handler=_battery_status,
            platforms=("linux",),
        ),
        # --- Display / brightness ---
        Tool(
            id="linux.display.info",
            description="Current display resolution(s) via xrandr (X11).",
            parameters={"type": "object", "properties": {}},
            confirm=ConfirmLevel.NONE,
            handler=_display_info,
            platforms=("linux",),
        ),
        Tool(
            id="linux.display.get_brightness",
            description="Get backlight brightness percent (brightnessctl or sysfs).",
            parameters={"type": "object", "properties": {}},
            confirm=ConfirmLevel.NONE,
            handler=_get_brightness,
            platforms=("linux",),
        ),
        Tool(
            id="linux.display.set_brightness",
            description="Set backlight brightness 0-100 (brightnessctl or sysfs).",
            parameters={
                "type": "object",
                "properties": {"percent": {"type": "integer"}},
                "required": ["percent"],
            },
            confirm=ConfirmLevel.NONE,
            handler=_set_brightness,
            platforms=("linux",),
        ),
        Tool(
            id="linux.display.get_contrast",
            description=(
                "Report OS accessibility contrast (GNOME high-contrast) when available. "
                "Physical monitor contrast is usually not readable."
            ),
            parameters={"type": "object", "properties": {}},
            confirm=ConfirmLevel.NONE,
            handler=_get_contrast,
            platforms=("linux",),
        ),
        # --- Volume (PulseAudio / PipeWire pactl) ---
        Tool(
            id="linux.volume.get",
            description="Get default sink volume percent via pactl.",
            parameters={"type": "object", "properties": {}},
            confirm=ConfirmLevel.NONE,
            handler=_volume_get,
            platforms=("linux",),
        ),
        Tool(
            id="linux.volume.set_percent",
            description="Set default sink volume to an absolute percent 0-100.",
            parameters={
                "type": "object",
                "properties": {"percent": {"type": "integer"}},
                "required": ["percent"],
            },
            confirm=ConfirmLevel.NONE,
            handler=_volume_set,
            platforms=("linux",),
        ),
        Tool(
            id="linux.volume.adjust",
            description="Adjust default sink volume by a relative delta (e.g. +10 / -15).",
            parameters={
                "type": "object",
                "properties": {"delta": {"type": "integer"}},
                "required": ["delta"],
            },
            confirm=ConfirmLevel.NONE,
            handler=_volume_adjust,
            platforms=("linux",),
        ),
        Tool(
            id="linux.volume.mute",
            description="Mute or unmute the default sink (muted=true/false).",
            parameters={
                "type": "object",
                "properties": {"muted": {"type": "boolean"}},
                "required": ["muted"],
            },
            confirm=ConfirmLevel.NONE,
            handler=_volume_mute,
            platforms=("linux",),
        ),
        Tool(
            id="linux.volume.reset",
            description="Unmute and set default sink volume to a percent (default 50).",
            parameters={
                "type": "object",
                "properties": {"percent": {"type": "integer", "default": 50}},
            },
            confirm=ConfirmLevel.NONE,
            handler=_volume_reset,
            platforms=("linux",),
        ),
        # --- Logs / users ---
        Tool(
            id="linux.logs.tail",
            description=(
                "Tail a log file or journalctl -u <unit>. "
                "path= for file, unit= for systemd journal."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "unit": {"type": "string"},
                    "lines": {"type": "integer", "default": 80},
                },
            },
            confirm=ConfirmLevel.NONE,
            handler=_logs_tail,
            platforms=("linux",),
        ),
        Tool(
            id="linux.users.list",
            description="List local login users (getent passwd, UID>=1000 + root).",
            parameters={"type": "object", "properties": {}},
            confirm=ConfirmLevel.NONE,
            handler=_users_list,
            platforms=("linux",),
        ),
        Tool(
            id="linux.users.who",
            description="Who is logged in (who / w).",
            parameters={"type": "object", "properties": {}},
            confirm=ConfirmLevel.NONE,
            handler=_users_who,
            platforms=("linux",),
        ),
        # --- Desktop helpers (best-effort in WSL) ---
        Tool(
            id="linux.settings.open",
            description=(
                "Open desktop settings (gnome/kde/xfce). Often unavailable in WSL."
            ),
            parameters={
                "type": "object",
                "properties": {"panel": {"type": "string"}},
            },
            confirm=ConfirmLevel.NONE,
            handler=_open_settings,
            platforms=("linux",),
        ),
        Tool(
            id="linux.display.set_resolution",
            description="Set resolution via xrandr (X11). Skip on headless WSL.",
            parameters={
                "type": "object",
                "properties": {
                    "output": {"type": "string"},
                    "width": {"type": "integer"},
                    "height": {"type": "integer"},
                },
                "required": ["width", "height"],
            },
            confirm=ConfirmLevel.ASK,
            handler=_set_resolution,
            platforms=("linux",),
        ),
        Tool(
            id="linux.app.list_desktop",
            description="List .desktop applications under /usr/share/applications.",
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 40},
                },
            },
            confirm=ConfirmLevel.NONE,
            handler=_list_desktop_apps,
            platforms=("linux",),
        ),
    ]


# ----- helpers -----

_SAFE_PKG = re.compile(r"^[a-zA-Z0-9][a-zA-Z0-9.+_-]*$")


def _split_packages(raw: str) -> list[str] | ToolResult:
    parts = [p for p in re.split(r"[\s,]+", (raw or "").strip()) if p]
    if not parts:
        return ToolResult(ok=False, message="No package names given")
    for p in parts:
        if not _SAFE_PKG.match(p) or p.startswith("-"):
            return ToolResult(ok=False, message=f"Invalid package name: {p}")
    return parts


def _apt_prefix() -> list[str]:
    # Prefer sudo when available and not already root
    if os.geteuid() != 0 and which("sudo"):
        return ["sudo", "-n"]
    return []


def _shell_run(args: dict) -> ToolResult:
    from osagent.tools.shell_safe import validate_bash

    command = str(args.get("command") or "").strip()
    rationale = str(args.get("rationale") or "").strip()
    allowed, message, needs_confirm = validate_bash(command)
    if not allowed:
        return ToolResult(ok=False, message=message, data={"command": command})
    if needs_confirm:
        print(f"\nProposed bash (writes/changes state):\n  {command}")
        if rationale:
            print(f"  reason: {rationale}")
        try:
            answer = input("Run this command? [y/N] ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return ToolResult(ok=False, message="Cancelled by user.")
        if answer not in {"y", "yes"}:
            return ToolResult(ok=False, message="Cancelled by user.")
    timeout = max(5, min(int(args.get("timeout_sec") or 90), 600))
    code, out, err = run_cmd(
        ["bash", "-lc", command],
        timeout=timeout,
        env={"DEBIAN_FRONTEND": "noninteractive"},
    )
    prefix = f"({rationale}) " if rationale else ""
    if code == 0:
        return ToolResult(
            ok=True,
            message=prefix + (out[:4000] if out else "OK"),
            data={"exit_code": code, "stdout": out, "stderr": err, "command": command},
        )
    return ToolResult(
        ok=False,
        message=prefix + (err or out or f"exit {code}")[:4000],
        data={"exit_code": code, "stdout": out, "stderr": err, "command": command},
    )


def _system_info(_args: dict) -> ToolResult:
    host = Path("/etc/hostname").read_text(encoding="utf-8").strip() if Path("/etc/hostname").is_file() else ""
    pretty = ""
    os_release = Path("/etc/os-release")
    if os_release.is_file():
        for line in os_release.read_text(encoding="utf-8").splitlines():
            if line.startswith("PRETTY_NAME="):
                pretty = line.split("=", 1)[1].strip().strip('"')
    code, uname, _ = run_cmd(["uname", "-a"], timeout=5)
    code2, up, _ = run_cmd(["uptime", "-p"], timeout=5)
    home = str(Path.home())
    msg = (
        f"{pretty or 'Linux'} | host={host or '?'} | home={home} | "
        f"{uname} | {up or ''}"
    ).strip()
    return ToolResult(
        ok=True,
        message=msg,
        data={
            "pretty": pretty,
            "hostname": host,
            "home": home,
            "uname": uname,
            "uptime": up,
        },
    )


def _home_folder(_args: dict) -> ToolResult:
    linux_home = Path.home()
    data: dict = {"linux_home": str(linux_home), "cwd": os.getcwd()}
    lines = [f"Linux home: {linux_home}"]
    try:
        from osagent.tools.recent_open import _wsl_windows_home

        win = _wsl_windows_home()
        if win is not None:
            data["windows_home"] = str(win)
            data["windows_home_win"] = "C:\\Users\\" + win.name
            lines.append(f"Windows home (WSL): {win}")
            lines.append(f"Windows home (Win): C:\\Users\\{win.name}")
    except Exception:
        pass
    lines.append(f"cwd: {os.getcwd()}")
    return ToolResult(ok=True, message="\n".join(lines), data=data)


def _uptime(_args: dict) -> ToolResult:
    code, out, err = run_cmd(["uptime"], timeout=5)
    return result_from_cmd(code, out, err)


def _disk_free(_args: dict) -> ToolResult:
    code, out, err = run_cmd(["df", "-h", "-x", "tmpfs", "-x", "devtmpfs", "-x", "squashfs"], timeout=15)
    return result_from_cmd(code, out, err)


def _memory(_args: dict) -> ToolResult:
    code, out, err = run_cmd(["free", "-h"], timeout=5)
    return result_from_cmd(code, out, err)


def _cpu_info(_args: dict) -> ToolResult:
    model = ""
    cores = ""
    cpuinfo = Path("/proc/cpuinfo")
    if cpuinfo.is_file():
        for line in cpuinfo.read_text(encoding="utf-8", errors="replace").splitlines():
            if line.startswith("model name") and not model:
                model = line.split(":", 1)[1].strip()
    code, nproc, _ = run_cmd(["nproc"], timeout=5)
    if code == 0:
        cores = nproc
    return ToolResult(
        ok=True,
        message=f"CPU: {model or 'unknown'} | cores: {cores or '?'}",
        data={"model": model, "cores": cores},
    )


def _pkg_search(args: dict) -> ToolResult:
    if package_manager() != "apt":
        return ToolResult(ok=False, message="Only apt is supported in this build")
    q = str(args.get("query") or "").strip()
    if not q:
        return ToolResult(ok=False, message="query required")
    limit = max(1, min(100, int(args.get("limit") or 30)))
    code, out, err = run_cmd(["apt-cache", "search", "--", q], timeout=60)
    if code != 0:
        return result_from_cmd(code, out, err)
    lines = [ln for ln in out.splitlines() if ln.strip()][:limit]
    return ToolResult(
        ok=True,
        message="\n".join(lines) if lines else "No matches",
        data={"matches": lines, "count": len(lines)},
    )


def _pkg_list(args: dict) -> ToolResult:
    if package_manager() != "apt":
        return ToolResult(ok=False, message="Only apt is supported in this build")
    q = str(args.get("query") or "").strip().lower()
    limit = max(1, min(200, int(args.get("limit") or 40)))
    code, out, err = run_cmd(["dpkg-query", "-W", "-f=${Package}\t${Version}\n"], timeout=60)
    if code != 0:
        return result_from_cmd(code, out, err)
    lines = []
    for ln in out.splitlines():
        if q and q not in ln.lower():
            continue
        lines.append(ln)
        if len(lines) >= limit:
            break
    return ToolResult(
        ok=True,
        message="\n".join(lines) if lines else "No packages matched",
        data={"packages": lines, "count": len(lines)},
    )


def _pkg_show(args: dict) -> ToolResult:
    name = str(args.get("name") or "").strip()
    if not _SAFE_PKG.match(name):
        return ToolResult(ok=False, message="Invalid package name")
    code, out, err = run_cmd(["dpkg", "-s", name], timeout=30)
    if code != 0:
        code, out, err = run_cmd(["apt-cache", "show", name], timeout=30)
    return result_from_cmd(code, out[:4000], err)


def _pkg_install(args: dict) -> ToolResult:
    pkgs = _split_packages(str(args.get("packages") or ""))
    if isinstance(pkgs, ToolResult):
        return pkgs
    if package_manager() != "apt":
        return ToolResult(ok=False, message="Only apt is supported in this build")
    cmd = [*_apt_prefix(), "apt-get", "install", "-y", "--", *pkgs]
    code, out, err = run_cmd(cmd, timeout=600, env={"DEBIAN_FRONTEND": "noninteractive"})
    return result_from_cmd(
        code,
        out[-3000:],
        err[-2000:],
        ok_message=f"Installed: {', '.join(pkgs)}",
        data={"packages": pkgs},
    )


def _pkg_remove(args: dict) -> ToolResult:
    pkgs = _split_packages(str(args.get("packages") or ""))
    if isinstance(pkgs, ToolResult):
        return pkgs
    cmd = [*_apt_prefix(), "apt-get", "remove", "-y", "--", *pkgs]
    code, out, err = run_cmd(cmd, timeout=600, env={"DEBIAN_FRONTEND": "noninteractive"})
    return result_from_cmd(
        code,
        out[-3000:],
        err[-2000:],
        ok_message=f"Removed: {', '.join(pkgs)}",
        data={"packages": pkgs},
    )


def _pkg_update(_args: dict) -> ToolResult:
    cmd = [*_apt_prefix(), "apt-get", "update"]
    code, out, err = run_cmd(cmd, timeout=300, env={"DEBIAN_FRONTEND": "noninteractive"})
    return result_from_cmd(code, out[-2000:], err[-2000:], ok_message="apt-get update done")


def _svc_name(raw: str) -> str | ToolResult:
    name = str(raw or "").strip()
    if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_.@-]*$", name):
        return ToolResult(ok=False, message=f"Invalid service name: {name}")
    return name


def _svc_status(args: dict) -> ToolResult:
    name = _svc_name(args.get("name") or "")
    if isinstance(name, ToolResult):
        return name
    if has_systemd():
        code, out, err = run_cmd(
            ["systemctl", "status", name, "--no-pager", "-l"],
            timeout=20,
        )
        # status returns non-zero when inactive — still useful
        text = out or err
        return ToolResult(
            ok=True,
            message=text[:4000] if text else f"No status for {name}",
            data={"exit_code": code, "name": name},
        )
    if which("service"):
        code, out, err = run_cmd(["service", name, "status"], timeout=20)
        return ToolResult(ok=code == 0, message=(out or err)[:4000], data={"name": name})
    return ToolResult(ok=False, message="No systemctl/service available")


def _svc_list(args: dict) -> ToolResult:
    limit = max(1, min(200, int(args.get("limit") or 50)))
    running_only = bool(args.get("running_only"))
    if has_systemd():
        cmd = ["systemctl", "list-units", "--type=service", "--no-pager", "--plain"]
        if running_only:
            cmd.append("--state=running")
        else:
            cmd.append("--all")
        code, out, err = run_cmd(cmd, timeout=30)
        lines = [ln for ln in out.splitlines() if ln.strip()][: limit + 1]
        return result_from_cmd(code, "\n".join(lines), err)
    init_d = Path("/etc/init.d")
    if init_d.is_dir():
        names = sorted(p.name for p in init_d.iterdir() if p.is_file())[:limit]
        return ToolResult(ok=True, message="\n".join(names), data={"services": names})
    return ToolResult(ok=False, message="Cannot list services on this host")


def _svc_action(args: dict, action: str) -> ToolResult:
    name = _svc_name(args.get("name") or "")
    if isinstance(name, ToolResult):
        return name
    if has_systemd():
        cmd = [*_apt_prefix(), "systemctl", action, name]
        code, out, err = run_cmd(cmd, timeout=60)
        return result_from_cmd(code, out, err, ok_message=f"{action} {name}")
    if which("service"):
        code, out, err = run_cmd([*_apt_prefix(), "service", name, action], timeout=60)
        return result_from_cmd(code, out, err, ok_message=f"{action} {name}")
    return ToolResult(ok=False, message="No systemctl/service available")


def _proc_list(args: dict) -> ToolResult:
    q = str(args.get("query") or "").strip().lower()
    limit = max(1, min(200, int(args.get("limit") or 40)))
    code, out, err = run_cmd(["ps", "aux", "--sort=-%cpu"], timeout=15)
    if code != 0:
        return result_from_cmd(code, out, err)
    lines = out.splitlines()
    header = lines[:1]
    body = []
    for ln in lines[1:]:
        if q and q not in ln.lower():
            continue
        body.append(ln)
        if len(body) >= limit:
            break
    text = "\n".join(header + body)
    return ToolResult(ok=True, message=text[:4000], data={"count": len(body)})


def _proc_kill(args: dict) -> ToolResult:
    pid = int(args["pid"])
    if pid <= 1:
        return ToolResult(ok=False, message="Refusing to signal PID <= 1")
    sig = str(args.get("signal") or "TERM").upper().lstrip("SIG")
    if not re.match(r"^[A-Z0-9]+$", sig):
        return ToolResult(ok=False, message="Invalid signal")
    code, out, err = run_cmd(["kill", f"-{sig}", str(pid)], timeout=10)
    return result_from_cmd(code, out, err, ok_message=f"Sent SIG{sig} to {pid}")


def _net_ifaces(_args: dict) -> ToolResult:
    if which("ip"):
        code, out, err = run_cmd(["ip", "-br", "a"], timeout=10)
        return result_from_cmd(code, out, err)
    code, out, err = run_cmd(["ifconfig", "-a"], timeout=10)
    return result_from_cmd(code, out, err)


def _net_routes(_args: dict) -> ToolResult:
    code, out, err = run_cmd(["ip", "route"], timeout=10)
    return result_from_cmd(code, out, err)


def _net_listening(_args: dict) -> ToolResult:
    if which("ss"):
        code, out, err = run_cmd(["ss", "-tulpn"], timeout=15)
        return result_from_cmd(code, out, err)
    code, out, err = run_cmd(["netstat", "-tulpn"], timeout=15)
    return result_from_cmd(code, out, err)


def _net_ping(args: dict) -> ToolResult:
    host = str(args.get("host") or "").strip()
    if not host or not re.match(r"^[a-zA-Z0-9._:-]+$", host):
        return ToolResult(ok=False, message="Invalid host")
    count = max(1, min(10, int(args.get("count") or 3)))
    code, out, err = run_cmd(["ping", "-c", str(count), "--", host], timeout=30)
    return result_from_cmd(code, out, err)


def _net_dns(args: dict) -> ToolResult:
    host = str(args.get("host") or "").strip()
    if not host:
        return ToolResult(ok=False, message="host required")
    if which("getent"):
        code, out, err = run_cmd(["getent", "hosts", host], timeout=15)
        if code == 0 and out:
            return result_from_cmd(code, out, err)
    if which("dig"):
        code, out, err = run_cmd(["dig", "+short", host], timeout=15)
        return result_from_cmd(code, out, err)
    code, out, err = run_cmd(["getent", "hosts", host], timeout=15)
    return result_from_cmd(code, out, err)


def _bluetooth_list(_args: dict) -> ToolResult:
    """List adapters + paired/connected devices via bluetoothctl."""
    bt = which("bluetoothctl")
    if not bt:
        return ToolResult(
            ok=False,
            message=(
                "bluetoothctl not found. Install bluez (e.g. sudo apt install bluez). "
                "On WSL, Bluetooth hardware usually is not passed through — "
                "use Windows: ./scripts/run.ps1 --once \"list bluetooth devices\"."
            ),
            data={"supported": False},
        )

    code_show, show_out, show_err = run_cmd([bt, "show"], timeout=10)
    adapters: list[dict] = []
    controller_ok = False
    if code_show == 0 and show_out:
        controller_ok = True
        name = ""
        powered = ""
        discoverable = ""
        address = ""
        for ln in show_out.splitlines():
            s = ln.strip()
            if s.startswith("Controller "):
                parts = s.split(None, 2)
                address = parts[1] if len(parts) > 1 else ""
            elif s.startswith("Name:"):
                name = s.split(":", 1)[1].strip()
            elif s.startswith("Powered:"):
                powered = s.split(":", 1)[1].strip()
            elif s.startswith("Discoverable:"):
                discoverable = s.split(":", 1)[1].strip()
        adapters.append(
            {
                "name": name or "adapter",
                "address": address,
                "powered": powered.lower() == "yes",
                "discoverable": discoverable.lower() == "yes",
            }
        )
    else:
        err = (show_err or show_out or "").strip()
        # Common on WSL / VMs with no BT radio
        if "No default controller" in err or "No such device" in err or code_show != 0:
            hint = (
                "No Bluetooth controller visible to Linux. "
                "WSL typically cannot access the Windows Bluetooth radio — "
                "run the same ask on Windows (osagent.exe / run.ps1)."
            )
            return ToolResult(
                ok=False,
                message=hint if not err else f"{hint}\n({err[:200]})",
                data={"supported": False, "adapters": [], "devices": []},
            )

    def _devices_for(kind: str) -> list[dict]:
        # bluetoothctl devices [Paired|Connected|…] — older builds may ignore filter
        argv = [bt, "devices", kind] if kind else [bt, "devices"]
        code, out, _err = run_cmd(argv, timeout=15)
        rows: list[dict] = []
        if code != 0 or not out:
            return rows
        for ln in out.splitlines():
            s = ln.strip()
            if not s.startswith("Device "):
                continue
            parts = s.split(None, 2)
            if len(parts) < 2:
                continue
            addr = parts[1]
            name = parts[2] if len(parts) > 2 else addr
            rows.append({"address": addr, "name": name, "kind": kind or "known"})
        return rows

    paired = _devices_for("Paired")
    connected = _devices_for("Connected")
    known = _devices_for("")
    by_addr: dict[str, dict] = {}
    paired_addrs = {d["address"] for d in paired}
    conn_addrs = {d["address"] for d in connected}
    # Seed from known devices, then overlay paired/connected filters
    for d in known + paired + connected:
        addr = d["address"]
        row = by_addr.get(addr) or {
            "name": d["name"],
            "address": addr,
            "paired": False,
            "connected": False,
        }
        row["name"] = d["name"] or row["name"]
        if addr in paired_addrs:
            row["paired"] = True
        elif not paired and not connected:
            # Old bluetoothctl: plain "devices" — treat listed as known/paired
            row["paired"] = True
        if addr in conn_addrs:
            row["connected"] = True
            row["paired"] = True
        by_addr[addr] = row

    devices = sorted(
        by_addr.values(), key=lambda r: (not r["connected"], r["name"].lower())
    )
    lines: list[str] = []
    if adapters:
        a = adapters[0]
        lines.append(
            f"Adapter: {a.get('name') or 'Bluetooth'} "
            f"({a.get('address') or '?'}) "
            f"powered={'yes' if a.get('powered') else 'no'}"
        )
    if not devices:
        lines.append("No paired/known Bluetooth devices.")
    else:
        lines.append(f"Devices ({len(devices)}):")
        for i, d in enumerate(devices, 1):
            flags = []
            if d.get("connected"):
                flags.append("connected")
            if d.get("paired"):
                flags.append("paired")
            flag_s = f" [{', '.join(flags)}]" if flags else ""
            lines.append(f"  {i}. {d['name']} ({d['address']}){flag_s}")

    return ToolResult(
        ok=True,
        message="\n".join(lines),
        data={
            "supported": controller_ok,
            "adapters": adapters,
            "devices": devices,
            "result": devices,
        },
    )


def _wsl_hw_hint(topic: str) -> str:
    return (
        f"{topic} is often unavailable inside WSL (no host hardware passthrough). "
        "Use Windows osagent / run.ps1 for the PC's real devices."
    )


def _printers_list(_args: dict) -> ToolResult:
    if not which("lpstat"):
        return ToolResult(
            ok=False,
            message=(
                "lpstat not found (install CUPS: sudo apt install cups). "
                + _wsl_hw_hint("Printers")
            ),
            data={"supported": False},
        )
    code, out, err = run_cmd(["lpstat", "-a"], timeout=15)
    if code != 0 and not out:
        code, out, err = run_cmd(["lpstat", "-p"], timeout=15)
    if code != 0 and not out:
        return ToolResult(
            ok=False,
            message=(err or out or "No printers found")[:4000],
            data={"supported": True, "result": []},
        )
    rows: list[dict] = []
    for ln in out.splitlines():
        s = ln.strip()
        if not s:
            continue
        name = s.split()[0]
        rows.append({"name": name, "raw": s})
    default = _printers_default_name()
    lines = [f"Printers ({len(rows)}):"]
    for i, r in enumerate(rows, 1):
        mark = " [default]" if default and r["name"] == default else ""
        lines.append(f"  {i}. {r['name']}{mark}")
        r["default"] = bool(default and r["name"] == default)
    if not rows:
        lines = ["No CUPS printers configured."]
    return ToolResult(
        ok=True,
        message="\n".join(lines),
        data={"supported": True, "result": rows, "default": default},
    )


def _printers_default_name() -> str | None:
    if not which("lpstat"):
        return None
    code, out, _err = run_cmd(["lpstat", "-d"], timeout=10)
    if code != 0 or not out:
        return None
    # "system default destination: Foo" or "no system default destination"
    m = re.search(r"destination:\s*(\S+)", out, re.I)
    if m and "no system default" not in out.lower():
        return m.group(1)
    return None


def _printers_default(_args: dict) -> ToolResult:
    if not which("lpstat"):
        return ToolResult(
            ok=False,
            message=(
                "lpstat not found (install CUPS: sudo apt install cups). "
                + _wsl_hw_hint("Printers")
            ),
            data={"supported": False},
        )
    name = _printers_default_name()
    if not name:
        code, out, err = run_cmd(["lpstat", "-d"], timeout=10)
        msg = (out or err or "No default printer set.").strip()
        return ToolResult(ok=False, message=msg[:4000], data={"default": None})
    return ToolResult(
        ok=True,
        message=f"Default printer: {name}",
        data={"default": name, "result": [{"name": name, "default": True}]},
    )


def _battery_status(_args: dict) -> ToolResult:
    root = Path("/sys/class/power_supply")
    if not root.is_dir():
        return ToolResult(
            ok=False,
            message="No power_supply sysfs (desktop / VM). " + _wsl_hw_hint("Battery"),
            data={"supported": False},
        )
    bats: list[dict] = []
    for p in sorted(root.iterdir()):
        typ = (p / "type").read_text(encoding="utf-8").strip() if (p / "type").is_file() else ""
        if typ and typ.lower() != "battery":
            continue
        if not (p / "capacity").is_file() and not (p / "energy_now").is_file():
            continue
        cap = None
        if (p / "capacity").is_file():
            try:
                cap = int((p / "capacity").read_text(encoding="utf-8").strip())
            except ValueError:
                cap = None
        status = (
            (p / "status").read_text(encoding="utf-8").strip()
            if (p / "status").is_file()
            else "Unknown"
        )
        bats.append({"name": p.name, "percent": cap, "status": status})
    if not bats:
        return ToolResult(
            ok=False,
            message="No battery present. " + _wsl_hw_hint("Battery"),
            data={"supported": False, "result": []},
        )
    lines = []
    for b in bats:
        pct = f"{b['percent']}%" if b["percent"] is not None else "?"
        lines.append(f"{b['name']}: {pct} ({b['status']})")
    return ToolResult(
        ok=True,
        message="\n".join(lines),
        data={"supported": True, "result": bats},
    )


def _display_info(_args: dict) -> ToolResult:
    if not which("xrandr"):
        return ToolResult(
            ok=False,
            message="xrandr not found (need X11). " + _wsl_hw_hint("Display"),
            data={"supported": False},
        )
    if not os.environ.get("DISPLAY") and not os.environ.get("WAYLAND_DISPLAY"):
        return ToolResult(
            ok=False,
            message="No DISPLAY/WAYLAND_DISPLAY set. " + _wsl_hw_hint("Display"),
            data={"supported": False},
        )
    code, out, err = run_cmd(["xrandr", "--current"], timeout=10)
    if code != 0 and not out:
        return result_from_cmd(code, out, err)
    rows: list[dict] = []
    lines_out: list[str] = []
    for ln in out.splitlines():
        if " connected" in ln:
            parts = ln.split()
            name = parts[0]
            # e.g. eDP-1 connected primary 1920x1080+0+0
            res = ""
            for tok in parts:
                if re.match(r"^\d+x\d+\+\d+\+\d+$", tok) or re.match(r"^\d+x\d+$", tok):
                    res = tok.split("+", 1)[0]
                    break
            rows.append({"output": name, "resolution": res, "raw": ln.strip()})
            lines_out.append(f"{name}: {res or ln.strip()}")
    if not rows:
        return ToolResult(
            ok=True,
            message=out[:4000] or "No connected displays reported.",
            data={"supported": True, "result": []},
        )
    return ToolResult(
        ok=True,
        message="\n".join(lines_out),
        data={"supported": True, "result": rows},
    )


def _backlight_dirs() -> list[Path]:
    root = Path("/sys/class/backlight")
    if not root.is_dir():
        return []
    return [p for p in sorted(root.iterdir()) if (p / "brightness").is_file()]


def _get_brightness(_args: dict) -> ToolResult:
    if which("brightnessctl"):
        code, out, err = run_cmd(["brightnessctl", "-m"], timeout=10)
        # machine: device,class,current,percent,max
        if code == 0 and out:
            parts = out.strip().split(",")
            if len(parts) >= 4:
                pct_s = parts[3].rstrip("%")
                try:
                    pct = int(pct_s)
                except ValueError:
                    pct = None
                if pct is not None:
                    return ToolResult(
                        ok=True,
                        message=f"Brightness: {pct}%",
                        data={"percent": pct, "device": parts[0], "supported": True},
                    )
    dirs = _backlight_dirs()
    if not dirs:
        return ToolResult(
            ok=False,
            message=(
                "No backlight device (brightnessctl/sysfs). "
                + _wsl_hw_hint("Brightness")
            ),
            data={"supported": False},
        )
    d = dirs[0]
    try:
        cur = int((d / "brightness").read_text(encoding="utf-8").strip())
        mx = int((d / "max_brightness").read_text(encoding="utf-8").strip())
    except (OSError, ValueError) as exc:
        return ToolResult(ok=False, message=f"Could not read backlight: {exc}")
    pct = int(round(100.0 * cur / mx)) if mx else 0
    return ToolResult(
        ok=True,
        message=f"Brightness: {pct}%",
        data={"percent": pct, "device": d.name, "supported": True},
    )


def _set_brightness(args: dict) -> ToolResult:
    pct = max(0, min(100, int(args["percent"])))
    if which("brightnessctl"):
        code, out, err = run_cmd(["brightnessctl", "set", f"{pct}%"], timeout=10)
        if code == 0:
            return ToolResult(
                ok=True,
                message=f"Brightness set to {pct}%",
                data={"percent": pct, "supported": True},
            )
        if err or out:
            return ToolResult(ok=False, message=(err or out)[:4000])
    dirs = _backlight_dirs()
    if not dirs:
        return ToolResult(
            ok=False,
            message=(
                "No backlight device to set. "
                + _wsl_hw_hint("Brightness")
            ),
            data={"supported": False},
        )
    d = dirs[0]
    try:
        mx = int((d / "max_brightness").read_text(encoding="utf-8").strip())
        val = max(0, min(mx, int(round(mx * pct / 100.0))))
        (d / "brightness").write_text(str(val), encoding="utf-8")
    except OSError as exc:
        return ToolResult(
            ok=False,
            message=f"Could not set backlight (need permissions?): {exc}",
        )
    return ToolResult(
        ok=True,
        message=f"Brightness set to {pct}%",
        data={"percent": pct, "device": d.name, "supported": True},
    )


def _get_contrast(_args: dict) -> ToolResult:
    if which("gsettings"):
        code, out, err = run_cmd(
            [
                "gsettings",
                "get",
                "org.gnome.desktop.a11y.interface",
                "high-contrast",
            ],
            timeout=10,
        )
        if code == 0 and out:
            on = "true" in out.lower()
            return ToolResult(
                ok=True,
                message=f"GNOME high-contrast: {'on' if on else 'off'}",
                data={"high_contrast_on": on, "supported": True},
            )
    return ToolResult(
        ok=False,
        message=(
            "Contrast isn't readable on this Linux session "
            "(no GNOME high-contrast setting). Physical monitor contrast "
            "is usually OSD-only. " + _wsl_hw_hint("Display contrast")
        ),
        data={"supported": False},
    )


def _pactl() -> str | None:
    return which("pactl")


def _parse_pactl_volume(out: str) -> int | None:
    # Volume: front-left: 32768 / 50% / -18.06 dB, ...
    m = re.search(r"(\d+)%", out)
    if not m:
        return None
    return max(0, min(100, int(m.group(1))))


def _volume_get(_args: dict) -> ToolResult:
    p = _pactl()
    if not p:
        return ToolResult(
            ok=False,
            message="pactl not found (PulseAudio/PipeWire). " + _wsl_hw_hint("Volume"),
            data={"supported": False},
        )
    code, out, err = run_cmd([p, "get-sink-volume", "@DEFAULT_SINK@"], timeout=10)
    if code != 0:
        return ToolResult(
            ok=False,
            message=(err or out or "Could not read volume")[:4000],
            data={"supported": False},
        )
    pct = _parse_pactl_volume(out)
    if pct is None:
        return ToolResult(ok=False, message=out[:4000] or "Could not parse volume")
    mute_code, mute_out, _ = run_cmd([p, "get-sink-mute", "@DEFAULT_SINK@"], timeout=10)
    muted = mute_code == 0 and "yes" in (mute_out or "").lower()
    msg = f"Volume: {pct}%" + (" (muted)" if muted else "")
    return ToolResult(
        ok=True,
        message=msg,
        data={"percent": pct, "muted": muted, "supported": True},
    )


def _volume_set(args: dict) -> ToolResult:
    p = _pactl()
    if not p:
        return ToolResult(
            ok=False,
            message="pactl not found. " + _wsl_hw_hint("Volume"),
            data={"supported": False},
        )
    pct = max(0, min(100, int(args["percent"])))
    code, out, err = run_cmd(
        [p, "set-sink-volume", "@DEFAULT_SINK@", f"{pct}%"], timeout=10
    )
    if code != 0:
        return ToolResult(ok=False, message=(err or out or f"exit {code}")[:4000])
    return ToolResult(
        ok=True,
        message=f"Volume set to {pct}%",
        data={"percent": pct, "supported": True},
    )


def _volume_adjust(args: dict) -> ToolResult:
    p = _pactl()
    if not p:
        return ToolResult(
            ok=False,
            message="pactl not found. " + _wsl_hw_hint("Volume"),
            data={"supported": False},
        )
    delta = int(args["delta"])
    sign = "+" if delta >= 0 else ""
    code, out, err = run_cmd(
        [p, "set-sink-volume", "@DEFAULT_SINK@", f"{sign}{delta}%"], timeout=10
    )
    if code != 0:
        return ToolResult(ok=False, message=(err or out or f"exit {code}")[:4000])
    got = _volume_get({})
    after = (got.data or {}).get("percent") if got.ok else None
    msg = f"Volume adjusted by {delta:+d}%"
    if after is not None:
        msg = f"Volume now {after}% ({delta:+d}%)"
    return ToolResult(
        ok=True,
        message=msg,
        data={"delta": delta, "percent": after, "supported": True},
    )


def _volume_mute(args: dict) -> ToolResult:
    p = _pactl()
    if not p:
        return ToolResult(
            ok=False,
            message="pactl not found. " + _wsl_hw_hint("Volume"),
            data={"supported": False},
        )
    muted = bool(args.get("muted"))
    code, out, err = run_cmd(
        [p, "set-sink-mute", "@DEFAULT_SINK@", "1" if muted else "0"], timeout=10
    )
    if code != 0:
        return ToolResult(ok=False, message=(err or out or f"exit {code}")[:4000])
    return ToolResult(
        ok=True,
        message="Muted" if muted else "Unmuted",
        data={"muted": muted, "supported": True},
    )


def _volume_reset(args: dict) -> ToolResult:
    pct = max(0, min(100, int(args.get("percent") or 50)))
    mute_res = _volume_mute({"muted": False})
    set_res = _volume_set({"percent": pct})
    if not set_res.ok:
        return set_res
    extra = "" if mute_res.ok else f" (unmute: {mute_res.message})"
    return ToolResult(
        ok=True,
        message=f"Volume reset to {pct}%{extra}",
        data={"percent": pct, "muted": False, "supported": True},
    )


def _logs_tail(args: dict) -> ToolResult:
    lines = max(1, min(500, int(args.get("lines") or 80)))
    unit = str(args.get("unit") or "").strip()
    path = str(args.get("path") or "").strip()
    if unit:
        if not re.match(r"^[a-zA-Z0-9][a-zA-Z0-9_.@-]*$", unit):
            return ToolResult(ok=False, message="Invalid unit name")
        if not which("journalctl"):
            return ToolResult(ok=False, message="journalctl not available")
        code, out, err = run_cmd(
            ["journalctl", "-u", unit, "-n", str(lines), "--no-pager"],
            timeout=30,
        )
        return result_from_cmd(code, out, err)
    if not path:
        # default syslog
        for candidate in ("/var/log/syslog", "/var/log/messages", "/var/log/kern.log"):
            if Path(candidate).is_file():
                path = candidate
                break
    if not path:
        return ToolResult(ok=False, message="Provide path= or unit=")
    p = Path(path).expanduser()
    if not p.is_file():
        return ToolResult(ok=False, message=f"Not a file: {p}")
    # Prevent reading arbitrary sensitive paths outside /var/log and /tmp without ask —
    # still allow; destructive isn't the issue, privacy is — keep simple for sysadmin agent
    code, out, err = run_cmd(["tail", "-n", str(lines), str(p)], timeout=15)
    return result_from_cmd(code, out, err)


def _users_list(_args: dict) -> ToolResult:
    code, out, err = run_cmd(["getent", "passwd"], timeout=15)
    if code != 0:
        return result_from_cmd(code, out, err)
    rows = []
    for ln in out.splitlines():
        parts = ln.split(":")
        if len(parts) < 7:
            continue
        name, _pw, uid_s, *_rest = parts
        try:
            uid = int(uid_s)
        except ValueError:
            continue
        if uid == 0 or uid >= 1000:
            if name in {"nobody", "nogroup"}:
                continue
            rows.append(f"{name}\tuid={uid}\tshell={parts[6]}\thome={parts[5]}")
    return ToolResult(ok=True, message="\n".join(rows) if rows else "No users", data={"users": rows})


def _users_who(_args: dict) -> ToolResult:
    if which("w"):
        code, out, err = run_cmd(["w"], timeout=10)
        return result_from_cmd(code, out, err)
    code, out, err = run_cmd(["who"], timeout=10)
    return result_from_cmd(code, out, err)


def _open_settings(args: dict) -> ToolResult:
    panel = (args.get("panel") or "").strip().lower()
    candidates: list[list[str]] = []
    if which("gnome-control-center"):
        cmd = ["gnome-control-center"]
        if panel:
            cmd.append(panel)
        candidates.append(cmd)
    if which("systemsettings"):
        candidates.append(["systemsettings"])
    if which("systemsettings5"):
        candidates.append(["systemsettings5"])
    if which("xfce4-settings-manager"):
        candidates.append(["xfce4-settings-manager"])
    if not candidates:
        return ToolResult(
            ok=False,
            message="No desktop settings app found (normal on headless WSL).",
        )
    import subprocess

    subprocess.Popen(candidates[0])
    return ToolResult(ok=True, message=f"Launched {' '.join(candidates[0])}")


def _set_resolution(args: dict) -> ToolResult:
    if not which("xrandr"):
        return ToolResult(ok=False, message="xrandr not found (need X11 display).")
    width = int(args["width"])
    height = int(args["height"])
    mode = f"{width}x{height}"
    cmd = ["xrandr"]
    output = args.get("output")
    if output:
        cmd.extend(["--output", str(output), "--mode", mode])
    else:
        cmd.extend(["-s", mode])
    code, out, err = run_cmd(cmd, timeout=15)
    return result_from_cmd(code, out, err, ok_message=f"Resolution set to {mode}")


def _list_desktop_apps(args: dict) -> ToolResult:
    q = str(args.get("query") or "").strip().lower()
    limit = max(1, min(200, int(args.get("limit") or 40)))
    roots = [
        Path("/usr/share/applications"),
        Path("/usr/local/share/applications"),
        Path.home() / ".local/share/applications",
    ]
    hits: list[str] = []
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.glob("*.desktop")):
            name = path.stem
            try:
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            label = name
            for ln in text.splitlines():
                if ln.startswith("Name=") and not ln.startswith("Name["):
                    label = ln.split("=", 1)[1].strip()
                    break
            blob = f"{label} {name}".lower()
            if q and q not in blob:
                continue
            hits.append(f"{label}\t{path}")
            if len(hits) >= limit:
                break
        if len(hits) >= limit:
            break
    return ToolResult(
        ok=True,
        message="\n".join(hits) if hits else "No desktop apps matched",
        data={"apps": hits, "count": len(hits)},
    )
