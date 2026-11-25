"""JSON-backed inventory persistence."""

from __future__ import annotations

import json
import threading
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from osagent.paths import config_dir, project_root

SCHEMA_VERSION = 2


def _utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def default_inventory() -> dict[str, Any]:
    return {
        "version": SCHEMA_VERSION,
        "built_at": None,
        "updated_at": None,
        "scan": {
            "status": "never",  # never | running | ok | error
            "last_error": None,
            "apps_indexed": 0,
            "duration_sec": None,
        },
        "apps": {},  # key -> app record
        "default_apps": {},  # role/ext -> {name, progid, hint}
        "devices": {
            "printers": [],
            "audio": [],
            "bluetooth": [],
            "displays": [],
            "updated_at": None,
        },
        # Cached settings/commands for hardware + known apps (avoid rediscovery)
        "capabilities": {
            "hardware": {},  # domains → settings/commands/supported
            "apps": {},  # app_id → actions/file_kinds/installed
            "updated_at": None,
        },
        "commands": {},  # tool_id -> {description, ok_count, fail_count, last_used, last_ok}
        "notes": [],
    }


def inventory_path() -> Path:
    """Prefer writable config dir next to the exe (survives rebuilds)."""
    # Frozen: always release/config/inventory.json (build preserves this file).
    # Dev: project config/inventory.json.
    candidates = [config_dir(), project_root() / "data", project_root()]
    for base in candidates:
        try:
            base.mkdir(parents=True, exist_ok=True)
            probe = base / ".osagent_write_probe"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink(missing_ok=True)
            return base / "inventory.json"
        except OSError:
            continue
    return project_root() / "inventory.json"


class InventoryStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or inventory_path()
        self._lock = threading.RLock()
        self._data = default_inventory()
        self.load()

    def load(self) -> None:
        with self._lock:
            if not self.path.is_file():
                self._data = default_inventory()
                return
            try:
                raw = json.loads(self.path.read_text(encoding="utf-8"))
                if not isinstance(raw, dict):
                    raise ValueError("not a dict")
                base = default_inventory()
                base.update({k: raw.get(k, base[k]) for k in base})
                # nested merges
                for section in ("scan", "devices", "capabilities"):
                    if isinstance(raw.get(section), dict):
                        merged = dict(base[section])
                        merged.update(raw[section])
                        base[section] = merged
                for section in ("apps", "default_apps", "commands"):
                    if isinstance(raw.get(section), dict):
                        base[section] = raw[section]
                # Migrate older inventories missing capabilities
                if not isinstance(base.get("capabilities"), dict):
                    base["capabilities"] = default_inventory()["capabilities"]
                try:
                    base["version"] = max(
                        int(raw.get("version") or 1), SCHEMA_VERSION
                    )
                except (TypeError, ValueError):
                    base["version"] = SCHEMA_VERSION
                self._data = base
            except Exception:
                self._data = default_inventory()

    def save(self) -> None:
        with self._lock:
            self._data["updated_at"] = _utc_now()
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=True),
                encoding="utf-8",
            )
            tmp.replace(self.path)

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return deepcopy(self._data)

    def update(self, mutator) -> dict[str, Any]:
        """Run mutator(data) under lock, then save. Returns snapshot."""
        with self._lock:
            mutator(self._data)
            self._data["updated_at"] = _utc_now()
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=True),
                encoding="utf-8",
            )
            tmp.replace(self.path)
            return deepcopy(self._data)
