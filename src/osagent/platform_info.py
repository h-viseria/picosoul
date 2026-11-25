"""Detect current OS; keep Linux hooks ready while piloting on Windows."""

from __future__ import annotations

import platform
import sys
from enum import Enum


class HostOS(str, Enum):
    WINDOWS = "windows"
    LINUX = "linux"
    MACOS = "macos"
    UNKNOWN = "unknown"


def detect_os() -> HostOS:
    name = sys.platform
    if name.startswith("win"):
        return HostOS.WINDOWS
    if name.startswith("linux"):
        return HostOS.LINUX
    if name == "darwin":
        return HostOS.MACOS
    return HostOS.UNKNOWN


def resolve_platform(preference: str = "auto") -> HostOS:
    pref = (preference or "auto").lower().strip()
    if pref == "windows":
        return HostOS.WINDOWS
    if pref == "linux":
        return HostOS.LINUX
    if pref == "macos":
        return HostOS.MACOS
    return detect_os()


def platform_summary() -> str:
    return (
        f"{platform.system()} {platform.release()} "
        f"({platform.machine()}), Python {platform.python_version()}"
    )
