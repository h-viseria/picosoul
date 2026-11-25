"""Resolve project / frozen-app directories."""

from __future__ import annotations

import sys
from pathlib import Path


def is_frozen() -> bool:
    return bool(getattr(sys, "frozen", False))


def project_root() -> Path:
    """Repo root in dev; folder containing the exe when frozen."""
    if is_frozen():
        return Path(sys.executable).resolve().parent
    # src/osagent/paths.py -> parents[2] == project root
    return Path(__file__).resolve().parents[2]


def src_root() -> Path:
    return project_root() / "src"


def external_dir() -> Path:
    return project_root() / "external"


def release_dir() -> Path:
    return project_root() / "release"


def config_dir() -> Path:
    """Prefer config next to the exe when frozen; else repo config/."""
    root = project_root()
    beside = root / "config"
    if beside.is_dir():
        return beside
    return root / "config"
