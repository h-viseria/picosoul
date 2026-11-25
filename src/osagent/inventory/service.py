"""High-level inventory API used by launch, tools, and startup."""

from __future__ import annotations

import re
import threading
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from osagent.inventory.builder import run_full_build
from osagent.inventory.store import InventoryStore, _utc_now, default_inventory

_INSTANCE: InventoryService | None = None
_INSTANCE_LOCK = threading.Lock()


def _alnum(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def _score(query: str, candidate: str) -> float:
    q = _alnum(query)
    c = _alnum(candidate)
    if not q or not c:
        return 0.0
    if q == c:
        return 1.0
    if q in c or c in q:
        return 0.92
    q2 = q.replace("cache", "cash").replace("cashe", "cash")
    c2 = c.replace("cache", "cash").replace("cashe", "cash")
    if q2 == c2 or q2 in c2 or c2 in q2:
        return 0.9
    return SequenceMatcher(None, q, c).ratio()


class InventoryService:
    def __init__(self, store: InventoryStore | None = None) -> None:
        self.store = store or InventoryStore()
        self._build_lock = threading.Lock()
        self._building = False

    @property
    def path(self) -> Path:
        return self.store.path

    def needs_capabilities(self) -> bool:
        data = self.store.snapshot()
        caps = data.get("capabilities") or {}
        if not isinstance(caps, dict):
            return True
        hw = caps.get("hardware")
        apps = caps.get("apps")
        if not isinstance(hw, dict) or not hw.get("domains"):
            return True
        if not isinstance(apps, dict) or not apps:
            return True
        return False

    def needs_build(self) -> bool:
        data = self.store.snapshot()
        if data.get("scan", {}).get("status") == "running":
            return False
        if not data.get("apps"):
            return True
        if data.get("scan", {}).get("status") in {None, "never", "error"}:
            return True
        if not data.get("built_at"):
            return True
        return False

    def status(self) -> dict[str, Any]:
        data = self.store.snapshot()
        apps = data.get("apps") or {}
        caps = data.get("capabilities") or {}
        hw = caps.get("hardware") or {}
        domains = hw.get("domains") if isinstance(hw, dict) else {}
        app_caps = caps.get("apps") or {}
        supported_settings = 0
        for meta in (domains or {}).values():
            for s in meta.get("settings") or []:
                if s.get("supported"):
                    supported_settings += 1
        installed_cap_apps = sum(
            1 for a in (app_caps or {}).values() if isinstance(a, dict) and a.get("installed")
        )
        return {
            "path": str(self.path),
            "built_at": data.get("built_at"),
            "updated_at": data.get("updated_at"),
            "scan": data.get("scan"),
            "apps_count": len(apps),
            "default_apps": data.get("default_apps") or {},
            "devices_summary": {
                "printers": len((data.get("devices") or {}).get("printers") or []),
                "displays": len((data.get("devices") or {}).get("displays") or []),
                "updated_at": (data.get("devices") or {}).get("updated_at"),
            },
            "commands_count": len(data.get("commands") or {}),
            "capabilities": {
                "updated_at": caps.get("updated_at"),
                "hardware_domains": len(domains or {}),
                "supported_settings": supported_settings,
                "app_profiles": len(app_caps or {}),
                "installed_known_apps": installed_cap_apps,
            },
            "building": self._building,
        }

    def ensure_built_async(
        self,
        *,
        force: bool = False,
        tool_specs: list[dict[str, str]] | None = None,
        on_progress: Any = None,
    ) -> None:
        if force or self.needs_build():
            if self._building:
                return

            def worker() -> None:
                self.build(force=True, tool_specs=tool_specs, on_progress=on_progress)

            t = threading.Thread(target=worker, name="osagent-inventory", daemon=True)
            t.start()
            return

        # Apps already indexed — only fill missing capabilities cache
        if self.needs_capabilities():
            if self._building:
                return

            def caps_worker() -> None:
                self.ensure_capabilities(on_progress=on_progress)

            t = threading.Thread(
                target=caps_worker, name="osagent-inventory-caps", daemon=True
            )
            t.start()

    def ensure_capabilities(self, *, on_progress: Any = None) -> dict[str, Any]:
        """Probe/fill capabilities without a full app filesystem rescan."""
        with self._build_lock:
            self._building = True

            def progress(msg: str) -> None:
                if on_progress:
                    try:
                        on_progress(msg)
                    except Exception:
                        pass

            try:
                from osagent.inventory.capabilities import build_capabilities_section

                def mutator(data: dict[str, Any]) -> None:
                    progress("Probing hardware & app capabilities…")
                    data["capabilities"] = build_capabilities_section(
                        apps=data.get("apps") or {},
                        devices=data.get("devices") or {},
                        previous=data.get("capabilities")
                        if isinstance(data.get("capabilities"), dict)
                        else {},
                    )
                    progress("Capabilities cache ready")

                self.store.update(mutator)
            finally:
                self._building = False
            return self.status()

    def build(
        self,
        *,
        force: bool = True,
        tool_specs: list[dict[str, str]] | None = None,
        on_progress: Any = None,
    ) -> dict[str, Any]:
        if not force and not self.needs_build():
            return self.status()
        with self._build_lock:
            self._building = True

            def progress(msg: str) -> None:
                if on_progress:
                    try:
                        on_progress(msg)
                    except Exception:
                        pass

            try:
                def mutator(data: dict[str, Any]) -> None:
                    run_full_build(data, progress=progress, tool_specs=tool_specs)

                self.store.update(mutator)
            finally:
                self._building = False
            return self.status()

    def lookup_app(self, query: str, *, limit: int = 5) -> list[dict[str, Any]]:
        """Find apps from inventory (no filesystem crawl)."""
        q = (query or "").strip()
        if not q:
            return []
        data = self.store.snapshot()
        hits: list[dict[str, Any]] = []
        for aid, rec in (data.get("apps") or {}).items():
            names = list(rec.get("names") or [])
            names.extend([rec.get("name") or "", rec.get("stem") or "", aid])
            score = max((_score(q, n) for n in names if n), default=0.0)
            # boost frequently used
            launches = int(rec.get("launch_count") or 0)
            if launches:
                score = min(1.0, score + min(0.08, launches * 0.01))
            if score < 0.72:
                continue
            path = rec.get("path")
            if rec.get("kind") == "exe" and path and not Path(str(path)).is_file():
                continue
            hits.append(
                {
                    "id": aid,
                    "path": path,
                    "name": rec.get("name"),
                    "score": round(score, 3),
                    "kind": rec.get("kind"),
                    "launch_count": launches,
                    "names": rec.get("names"),
                    "source": "inventory",
                }
            )
        hits.sort(key=lambda h: (-float(h["score"]), -int(h["launch_count"])))
        return hits[: max(1, min(limit, 20))]

    def record_launch(
        self,
        *,
        query: str,
        path: str,
        name: str | None = None,
        ok: bool = True,
    ) -> None:
        if not path and not query:
            return

        def mutator(data: dict[str, Any]) -> None:
            apps = data.setdefault("apps", {})
            path_l = (path or "").lower()
            found_id = None
            for aid, rec in apps.items():
                if path_l and str(rec.get("path") or "").lower() == path_l:
                    found_id = aid
                    break
            if found_id is None:
                from osagent.inventory.builder import _app_key

                found_id = _app_key(name or Path(path).stem, path)
                base = found_id
                n = 2
                while found_id in apps:
                    found_id = f"{base}_{n}"
                    n += 1
                apps[found_id] = {
                    "path": path,
                    "name": name or Path(path).name,
                    "stem": Path(path).stem if path else name,
                    "names": [],
                    "kind": "lnk" if (path or "").lower().endswith(".lnk") else "exe",
                    "source": "launch",
                    "launch_count": 0,
                    "last_used": None,
                }
            rec = apps[found_id]
            names = set(rec.get("names") or [])
            if query:
                names.add(query.strip())
            if name:
                names.add(name)
            if path:
                names.add(Path(path).stem)
                names.add(Path(path).name)
                rec["path"] = path
            rec["names"] = sorted({n for n in names if n})
            if ok:
                rec["launch_count"] = int(rec.get("launch_count") or 0) + 1
                rec["last_used"] = _utc_now()

        try:
            self.store.update(mutator)
        except Exception:
            pass

    def record_tool_use(self, tool_id: str, *, ok: bool, description: str = "") -> None:
        if not tool_id:
            return

        def mutator(data: dict[str, Any]) -> None:
            cmds = data.setdefault("commands", {})
            meta = cmds.setdefault(
                tool_id,
                {
                    "description": description or tool_id,
                    "ok_count": 0,
                    "fail_count": 0,
                    "last_used": None,
                    "last_ok": None,
                },
            )
            if description and not meta.get("description"):
                meta["description"] = description[:120]
            meta["last_used"] = _utc_now()
            meta["last_ok"] = bool(ok)
            if ok:
                meta["ok_count"] = int(meta.get("ok_count") or 0) + 1
            else:
                meta["fail_count"] = int(meta.get("fail_count") or 0) + 1

            # Learn hardware support from real outcomes (no rediscovery next time)
            from osagent.inventory.capabilities import (
                TOOL_CAPABILITY_HINTS,
                enrich_capabilities_from_tool,
            )

            if tool_id in TOOL_CAPABILITY_HINTS:
                data["capabilities"] = enrich_capabilities_from_tool(
                    data.get("capabilities") or {},
                    tool_id,
                    ok=ok,
                )

        try:
            self.store.update(mutator)
        except Exception:
            pass

    def enrich_devices(self, section: str, items: list[dict[str, Any]]) -> None:
        if section not in {"printers", "audio", "bluetooth", "displays"}:
            return

        def mutator(data: dict[str, Any]) -> None:
            devices = data.setdefault("devices", default_inventory()["devices"])
            devices[section] = items
            devices["updated_at"] = _utc_now()

        try:
            self.store.update(mutator)
        except Exception:
            pass

    def get_hardware_capabilities(self) -> dict[str, Any]:
        data = self.store.snapshot()
        caps = data.get("capabilities") or {}
        hw = caps.get("hardware")
        return hw if isinstance(hw, dict) else {}

    def get_app_capabilities(self, app_id: str | None = None) -> dict[str, Any]:
        data = self.store.snapshot()
        caps = data.get("capabilities") or {}
        apps = caps.get("apps") if isinstance(caps.get("apps"), dict) else {}
        if not app_id:
            return apps
        q = app_id.strip().lower()
        if q in apps:
            return {q: apps[q]}
        # fuzzy: match alias
        for aid, meta in apps.items():
            aliases = [a.lower() for a in (meta.get("aliases") or [])]
            if q == aid or q in aliases or any(q in a or a in q for a in aliases):
                return {aid: meta}
        return {}

    def supported_hardware_settings(self) -> list[dict[str, Any]]:
        """Flat list of settings this machine can use (from cache)."""
        hw = self.get_hardware_capabilities()
        out: list[dict[str, Any]] = []
        for domain, meta in (hw.get("domains") or {}).items():
            for s in meta.get("settings") or []:
                if not s.get("supported"):
                    continue
                out.append(
                    {
                        "domain": domain,
                        "domain_label": meta.get("label"),
                        "id": s.get("id"),
                        "label": s.get("label"),
                        "readable": s.get("readable"),
                        "writable": s.get("writable"),
                        "tools": s.get("tools") or {},
                        "notes": s.get("notes"),
                    }
                )
        return out

    def summary_for_prompt(self, *, max_apps: int = 25) -> str:
        """Short text block the agent can use for routing hints."""
        data = self.store.snapshot()
        apps = list((data.get("apps") or {}).values())
        apps.sort(key=lambda a: (-int(a.get("launch_count") or 0), str(a.get("name") or "")))
        lines = ["Known apps (from inventory):"]
        for rec in apps[:max_apps]:
            names = ", ".join((rec.get("names") or [])[:3]) or rec.get("name")
            path = rec.get("path") or ""
            short = path if len(str(path)) < 60 else ("…" + str(path)[-55:])
            lines.append(f"- {names} → {short}")
        defaults = data.get("default_apps") or {}
        if defaults:
            lines.append("Default associations: " + ", ".join(f"{k}={v.get('progid')}" for k, v in list(defaults.items())[:6]))
        printers = (data.get("devices") or {}).get("printers") or []
        dflt = next((p for p in printers if p.get("default")), None)
        if dflt:
            lines.append(f"Default printer: {dflt.get('name')}")

        # Cached capabilities — prefer these over rediscovery
        settings = self.supported_hardware_settings()
        if settings:
            lines.append("Hardware settings available (cached):")
            for s in settings[:12]:
                rw = []
                if s.get("readable"):
                    rw.append("get")
                if s.get("writable"):
                    rw.append("set")
                tools = s.get("tools") or {}
                tool_hint = tools.get("get") or tools.get("set") or tools.get("list") or ""
                lines.append(
                    f"- {s.get('domain')}.{s.get('id')}: {s.get('label')} "
                    f"[{'/'.join(rw)}] → {tool_hint}"
                )
        app_caps = self.get_app_capabilities()
        installed = [
            (aid, meta)
            for aid, meta in app_caps.items()
            if isinstance(meta, dict) and meta.get("installed")
        ]
        if installed:
            lines.append("App command options (cached):")
            for aid, meta in installed[:10]:
                actions = ", ".join(
                    a.get("id") for a in (meta.get("actions") or []) if a.get("id")
                )
                lines.append(f"- {aid}: {actions}")
        return "\n".join(lines)


def get_inventory() -> InventoryService:
    global _INSTANCE
    with _INSTANCE_LOCK:
        if _INSTANCE is None:
            _INSTANCE = InventoryService()
        return _INSTANCE
