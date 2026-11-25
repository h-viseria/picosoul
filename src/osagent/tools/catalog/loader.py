"""Load declarative command catalogs into Tool objects."""

from __future__ import annotations

import json
import re
import subprocess
from typing import Any, Callable

from osagent.platform_info import HostOS
from osagent.tools.base import ConfirmLevel, Tool, ToolResult
from osagent.tools.catalog import windows_commands
from osagent.tools.win_ps import run_ps


def _escape_ps_single(value: str) -> str:
    return value.replace("'", "''")


def _escape_bash_double(value: str) -> str:
    """Escape for insertion into double-quoted bash / python string templates."""
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("`", "\\`")
        .replace("$", "\\$")
    )


_BATTERY_STATUS = {
    1: "discharging",
    2: "on AC",
    3: "fully charged",
    4: "low",
    5: "critical",
    6: "charging",
    7: "charging (high)",
    8: "charging (low)",
    9: "charging (critical)",
    10: "undefined",
    11: "partially charged",
}


def _format_catalog_message(tool_id: str, label: str, items: Any) -> str:
    """Turn JSON catalog results into a user-facing sentence (not just a label)."""
    if not isinstance(items, list):
        return label

    # File discovery
    if tool_id.startswith("files.find_"):
        lines: list[str] = []
        for i, it in enumerate(items[:30], 1):
            if not isinstance(it, dict):
                continue
            path = str(it.get("path") or it.get("Path") or it.get("FullName") or "")
            when = it.get("last_write") or it.get("LastWriteTime") or ""
            if path and when:
                lines.append(f"{i}. {path}\n    modified {when}")
            elif path:
                lines.append(f"{i}. {path}")
        if lines:
            return f"{len(lines)} newest file(s):\n" + "\n".join(lines)
        return "No matching files found"

    first = items[0] if items and isinstance(items[0], dict) else None
    if not first:
        return label

    if tool_id == "windows.battery.status":
        if not first.get("present"):
            return "No battery present (desktop / no Win32_Battery)"
        pct = first.get("estimated_charge_remaining")
        st = _BATTERY_STATUS.get(int(first.get("battery_status") or 0), "unknown")
        name = first.get("name") or "Battery"
        if pct is None:
            return f"{name}: status={st}"
        return f"{name}: {pct}% ({st})"

    if tool_id == "windows.system.uptime":
        return (
            f"Uptime {first.get('uptime') or '?'}; "
            f"last boot {first.get('last_boot') or '?'}"
            + (f" — {first.get('caption')}" if first.get("caption") else "")
        )

    if tool_id == "files.disk_free":
        lines = []
        for it in items[:12]:
            if not isinstance(it, dict):
                continue
            lines.append(
                f"{it.get('drive')}: {it.get('free_gb')} GB free / "
                f"{it.get('total_gb')} GB ({it.get('used_pct')}% used)"
            )
        return "Disk space:\n" + "\n".join(lines) if lines else label

    if tool_id == "windows.clipboard.get_text":
        text = first.get("text") or ""
        length = first.get("length")
        if not text:
            return "Clipboard is empty"
        preview = text if len(text) <= 400 else text[:400] + "…"
        return f"Clipboard ({length or len(text)} chars):\n{preview}"

    if tool_id in {"windows.datetime.get", "linux.datetime.get"}:
        return (
            f"{first.get('display') or first.get('local') or label}"
            + (f" ({first.get('timezone')})" if first.get("timezone") else "")
        )

    if tool_id == "linux.system.health_report":
        load = first.get("loadavg") or []
        root = first.get("root_disk") or {}
        return (
            f"Load {load}; root free {root.get('free_gb')} GB / "
            f"{root.get('total_gb')} GB; failed units={first.get('failed_units')}; "
            f"{first.get('uptime') or ''}"
        ).strip()

    # Generic: if label-only and dict has a few scalar fields, show them
    if label and "\n" not in label and len(label.split()) <= 4:
        bits = []
        for k, v in list(first.items())[:8]:
            if v is None or isinstance(v, (list, dict)):
                continue
            bits.append(f"{k}={v}")
        if bits:
            return f"{label}: " + ", ".join(bits)
        # pretty-print short JSON-ish text fields
        textish = []
        for k in ("lsblk", "df", "free", "status", "general", "timedatectl"):
            if isinstance(first.get(k), str) and first[k].strip():
                textish.append(f"{k}:\n{first[k][:1200]}")
        if textish:
            return "\n\n".join(textish)
    return label


def _render(
    template: str,
    args: dict[str, Any],
    defaults: dict[str, Any],
    *,
    engine: str,
) -> str:
    merged = {**defaults, **{k: v for k, v in args.items() if v is not None}}
    safe: dict[str, str] = {}
    for key, val in merged.items():
        if isinstance(val, bool):
            if engine == "powershell":
                safe[key] = "$true" if val else "$false"
            else:
                safe[key] = "1" if val else "0"
        elif isinstance(val, (int, float)):
            safe[key] = str(val)
        elif engine == "powershell":
            safe[key] = _escape_ps_single(str(val))
        else:
            # bash templates embed into python/heredoc strings — strip risky chars
            raw = str(val)
            if re.search(r"[\n\r`$]", raw) or '"' in raw:
                raw = re.sub(r"[\n\r`$\"\\]", "", raw)
            safe[key] = raw
    try:
        return template.format(**safe)
    except KeyError as exc:
        raise RuntimeError(f"Missing template param: {exc}") from exc


def _run_bash(script: str, *, timeout: float) -> tuple[int, str, str]:
    try:
        completed = subprocess.run(
            ["bash", "-lc", script],
            capture_output=True,
            text=True,
            timeout=max(1.0, min(float(timeout), 600.0)),
            check=False,
        )
    except FileNotFoundError:
        return 127, "", "bash not found"
    except subprocess.TimeoutExpired:
        return 124, "", f"Timed out after {timeout}s"
    return (
        int(completed.returncode),
        (completed.stdout or "").strip(),
        (completed.stderr or "").strip(),
    )


def _make_handler(entry: dict[str, Any]) -> Callable[[dict[str, Any]], ToolResult]:
    defaults = dict(entry.get("defaults") or {})
    timeout = float(entry.get("timeout") or 90)
    result_mode = entry.get("result") or "json"
    engine = str(entry.get("engine") or "powershell").lower()

    def handler(args: dict[str, Any]) -> ToolResult:
        script = _render(entry["script"], args, defaults, engine=engine)
        try:
            if engine in {"bash", "sh", "linux"}:
                code, out, err = _run_bash(script, timeout=timeout)
            else:
                code, out, err = run_ps(script, timeout=timeout)

            if result_mode == "json":
                if code != 0 and not out.strip():
                    return ToolResult(
                        ok=False,
                        message=(err or out or f"exit {code}").strip()[:500],
                        data={"command_id": entry["id"]},
                    )
                text = out.strip()
                if not text:
                    return ToolResult(
                        ok=True,
                        message="No matches",
                        data={"result": [], "command_id": entry["id"]},
                    )
                data = json.loads(text)
                if isinstance(data, list):
                    items: Any = data
                elif isinstance(data, dict):
                    items = [data]
                else:
                    items = data
                count = len(items) if isinstance(items, list) else 1
                label = entry.get("success_message") or f"{entry['id']}: {count} result(s)"
                msg = _format_catalog_message(entry["id"], label, items)
                return ToolResult(
                    ok=True,
                    message=msg,
                    data={"result": items, "command_id": entry["id"]},
                )

            if code != 0:
                return ToolResult(
                    ok=False,
                    message=(err or out or f"exit {code}").strip()[:500],
                    data={"command_id": entry["id"]},
                )
            return ToolResult(
                ok=True,
                message=(out.strip()[:1000] or "ok"),
                data={"stdout": out.strip(), "command_id": entry["id"]},
            )
        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                ok=False,
                message=f"{entry['id']} failed: {exc}",
                data={"command_id": entry["id"]},
            )

    return handler


def build_catalog_tools(host: HostOS) -> list[Tool]:
    if host == HostOS.WINDOWS:
        from osagent.tools.catalog import windows_commands_extended

        entries = list(windows_commands.COMMANDS) + list(
            windows_commands_extended.COMMANDS
        )
        platforms = ("windows",)
        default_engine = "powershell"
    elif host == HostOS.LINUX:
        from osagent.tools.catalog import linux_commands

        entries = list(linux_commands.COMMANDS)
        platforms = ("linux",)
        default_engine = "bash"
    else:
        return []

    tools: list[Tool] = []
    for entry in entries:
        confirm = ConfirmLevel(entry.get("confirm") or "none")
        params = entry.get("parameters") or {"type": "object", "properties": {}}
        if isinstance(params, str):
            params = json.loads(params)
        if "engine" not in entry:
            entry = {**entry, "engine": default_engine}
        tools.append(
            Tool(
                id=entry["id"],
                description=entry["description"],
                parameters=params,
                confirm=confirm,
                handler=_make_handler(entry),
                platforms=platforms,
            )
        )
    return tools


def linux_catalog_phrase_intents() -> list[tuple[re.Pattern[str], str, dict[str, Any]]]:
    """Compile phrase → tool_id mappings from the Linux catalog."""
    from osagent.tools.catalog import linux_commands

    out: list[tuple[re.Pattern[str], str, dict[str, Any]]] = []
    for entry in linux_commands.COMMANDS:
        tid = entry["id"]
        for phrase in entry.get("phrases") or []:
            try:
                out.append((re.compile(phrase, re.I), tid, {}))
            except re.error:
                continue
    return out
