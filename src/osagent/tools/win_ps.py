"""Helpers to run PowerShell and parse JSON results on Windows."""

from __future__ import annotations

import json
import subprocess
from typing import Any


def run_ps(script: str, *, timeout: float = 60) -> tuple[int, str, str]:
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


def run_ps_json(script: str, *, timeout: float = 60) -> Any:
    """Run script that prints JSON; return parsed object or raise RuntimeError."""
    code, out, err = run_ps(script, timeout=timeout)
    text = out.strip()
    if code != 0:
        raise RuntimeError((err or out or f"PowerShell exit {code}").strip()[:500])
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Invalid JSON from PowerShell: {text[:200]}") from exc


def as_list(data: Any) -> list[dict[str, Any]]:
    if data is None:
        return []
    if isinstance(data, dict):
        return [data]
    if isinstance(data, list):
        return [x for x in data if isinstance(x, dict)]
    return []


def _send_volume_keys(steps: int) -> None:
    """Emulate keyboard volume keys (each step ~2% on many systems)."""
    import ctypes

    vk = 0xAF if steps > 0 else 0xAE  # VOLUME_UP / VOLUME_DOWN
    keybd = ctypes.windll.user32.keybd_event
    for _ in range(abs(steps)):
        keybd(vk, 0, 0, 0)
        keybd(vk, 0, 2, 0)


def _speakers():
    try:
        from pycaw.pycaw import AudioUtilities  # type: ignore
    except ImportError as exc:
        raise RuntimeError("pycaw not installed") from exc
    return AudioUtilities.GetSpeakers()


def get_volume_percent() -> int:
    try:
        dev = _speakers()
        # Newer pycaw exposes volume_percent (0..100 float)
        if hasattr(dev, "volume_percent") and dev.volume_percent is not None:
            return max(0, min(100, int(round(float(dev.volume_percent)))))
        level = float(dev.EndpointVolume.GetMasterVolumeLevelScalar())
        return max(0, min(100, int(round(level * 100))))
    except Exception as exc:
        raise RuntimeError(str(exc)) from exc


def set_volume_percent(percent: int) -> int:
    pct = max(0, min(100, int(percent)))
    try:
        dev = _speakers()
        if hasattr(dev, "volume_percent"):
            dev.volume_percent = float(pct)
        else:
            dev.EndpointVolume.SetMasterVolumeLevelScalar(pct / 100.0, None)
        return get_volume_percent()
    except Exception as exc:
        raise RuntimeError(str(exc)) from exc


def adjust_volume_percent(delta: int) -> tuple[int | None, int | None, str]:
    """Return (before, after, method). Prefers Core Audio; falls back to hotkeys."""
    try:
        before = get_volume_percent()
        after = set_volume_percent(before + delta)
        return before, after, "coreaudio"
    except Exception:
        steps = max(1, min(50, abs(int(delta)) // 2 or 1))
        if delta < 0:
            steps = -steps
        _send_volume_keys(steps)
        try:
            after = get_volume_percent()
            return None, after, "hotkeys"
        except Exception:
            return None, None, "hotkeys"


def set_mute(mute: bool) -> bool:
    try:
        vol = _speakers().EndpointVolume
        vol.SetMute(1 if mute else 0, None)
        return bool(vol.GetMute())
    except Exception:
        import ctypes

        keybd = ctypes.windll.user32.keybd_event
        keybd(0xAD, 0, 0, 0)
        keybd(0xAD, 0, 2, 0)
        return mute
