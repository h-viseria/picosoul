"""Shared helpers for Linux tool handlers (WSL / Debian / antiX)."""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Any

from osagent.tools.base import ToolResult


def which(*names: str) -> str | None:
    for name in names:
        path = shutil.which(name)
        if path:
            return path
    return None


def run_cmd(
    argv: list[str],
    *,
    timeout: int = 60,
    input_text: str | None = None,
    env: dict[str, str] | None = None,
    cwd: str | None = None,
) -> tuple[int, str, str]:
    merged = os.environ.copy()
    if env:
        merged.update(env)
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            timeout=max(1, min(int(timeout), 600)),
            input=input_text,
            env=merged,
            cwd=cwd,
            check=False,
        )
    except FileNotFoundError:
        return 127, "", f"Command not found: {argv[0]}"
    except subprocess.TimeoutExpired:
        return 124, "", f"Timed out after {timeout}s"
    return (
        int(completed.returncode),
        (completed.stdout or "").strip(),
        (completed.stderr or "").strip(),
    )


def result_from_cmd(
    code: int,
    out: str,
    err: str,
    *,
    ok_message: str | None = None,
    data: dict[str, Any] | None = None,
) -> ToolResult:
    text = out if out else err
    if code == 0:
        return ToolResult(
            ok=True,
            message=ok_message or (text[:4000] if text else "OK"),
            data={**(data or {}), "exit_code": code, "stdout": out, "stderr": err},
        )
    return ToolResult(
        ok=False,
        message=(err or out or f"exit {code}")[:4000],
        data={**(data or {}), "exit_code": code, "stdout": out, "stderr": err},
    )


def has_systemd() -> bool:
    if not which("systemctl"):
        return False
    # WSL / containers may have the binary but no real init
    code, out, _ = run_cmd(["systemctl", "is-system-running"], timeout=5)
    if code == 0 and out.strip() in {"running", "degraded"}:
        return True
    # Still usable for user services / status queries in many WSL setups
    code2, _, _ = run_cmd(["systemctl", "list-units", "--type=service", "--no-pager"], timeout=8)
    return code2 == 0


def package_manager() -> str | None:
    if which("apt-get"):
        return "apt"
    if which("apk"):
        return "apk"
    if which("dnf"):
        return "dnf"
    if which("yum"):
        return "yum"
    return None
