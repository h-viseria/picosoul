"""Tools to inspect / refresh the persistent system inventory."""

from __future__ import annotations

from osagent.tools.base import ConfirmLevel, Tool, ToolResult


def build_tools() -> list[Tool]:
    return [
        Tool(
            id="system.inventory.status",
            description=(
                "Show the local system inventory: apps indexed, default apps, "
                "device summary, cached hardware settings / app command options, "
                "inventory file path. Use for 'what do you know about my apps/devices'."
            ),
            parameters={"type": "object", "properties": {}},
            confirm=ConfirmLevel.NONE,
            handler=_status,
            platforms=("windows", "linux"),
        ),
        Tool(
            id="system.inventory.refresh",
            description=(
                "Rebuild the app/device inventory by scanning Desktop, "
                "Downloads, Start Menu, Program Files, and re-probing "
                "hardware/app capabilities (runs in background unless wait=true)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "wait": {
                        "type": "boolean",
                        "description": "If true, block until scan finishes",
                        "default": False,
                    },
                },
            },
            confirm=ConfirmLevel.NONE,
            handler=_refresh,
            platforms=("windows", "linux"),
        ),
        Tool(
            id="system.inventory.lookup",
            description=(
                "Look up an app in the inventory map (no full disk search). "
                "Returns known paths / aliases / usage counts."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "limit": {"type": "integer", "default": 8},
                },
                "required": ["query"],
            },
            confirm=ConfirmLevel.NONE,
            handler=_lookup,
            platforms=("windows", "linux"),
        ),
        Tool(
            id="system.inventory.capabilities",
            description=(
                "Return cached hardware settings and per-app command options "
                "from inventory (no live rediscovery). Optional domain "
                "(display|audio|printers|bluetooth|network|power) or app "
                "(excel|word|chrome|…). Prefer this over probing hardware again."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "domain": {
                        "type": "string",
                        "description": "Hardware domain filter",
                    },
                    "app": {
                        "type": "string",
                        "description": "App id or alias filter",
                    },
                },
            },
            confirm=ConfirmLevel.NONE,
            handler=_capabilities,
            platforms=("windows", "linux"),
        ),
    ]


def _status(_args: dict) -> ToolResult:
    from osagent.inventory import get_inventory

    st = get_inventory().status()
    scan = st.get("scan") or {}
    caps = st.get("capabilities") or {}
    msg = (
        f"Inventory: {st.get('apps_count', 0)} apps "
        f"(scan={scan.get('status')}, built={st.get('built_at') or 'never'}); "
        f"{caps.get('supported_settings', 0)} hardware settings, "
        f"{caps.get('installed_known_apps', 0)} known apps with command options"
    )
    if st.get("building"):
        msg += " — scan running…"
    return ToolResult(ok=True, message=msg, data=st)


def _refresh(args: dict) -> ToolResult:
    from osagent.inventory import get_inventory

    inv = get_inventory()
    wait = bool(args.get("wait"))
    if wait:
        st = inv.build(force=True)
        return ToolResult(
            ok=st.get("scan", {}).get("status") == "ok",
            message=(
                f"Inventory rebuilt: {st.get('apps_count', 0)} apps "
                f"in {st.get('scan', {}).get('duration_sec')}s"
            ),
            data=st,
        )
    inv.ensure_built_async(force=True)
    return ToolResult(
        ok=True,
        message="Inventory refresh started in the background",
        data={"path": str(inv.path)},
    )


def _lookup(args: dict) -> ToolResult:
    from osagent.inventory import get_inventory

    query = str(args.get("query") or "").strip()
    if not query:
        return ToolResult(ok=False, message="query required")
    limit = max(1, min(int(args.get("limit") or 8), 20))
    hits = get_inventory().lookup_app(query, limit=limit)
    if not hits:
        return ToolResult(
            ok=False,
            message=f"Nothing in inventory for '{query}' — try app.find or refresh",
            data={"query": query, "candidates": []},
        )
    top = hits[0]
    return ToolResult(
        ok=True,
        message=f"Inventory: {top.get('name')} → {top.get('path')}",
        data={"query": query, "candidates": hits},
    )


def _capabilities(args: dict) -> ToolResult:
    from osagent.inventory import get_inventory

    inv = get_inventory()
    domain = str(args.get("domain") or "").strip().lower() or None
    app = str(args.get("app") or "").strip().lower() or None

    hw = inv.get_hardware_capabilities()
    domains = dict(hw.get("domains") or {})
    if domain:
        if domain not in domains:
            return ToolResult(
                ok=False,
                message=f"Unknown hardware domain '{domain}'",
                data={"domains": sorted(domains.keys())},
            )
        domains = {domain: domains[domain]}

    app_caps = inv.get_app_capabilities(app)
    if app and not app_caps:
        return ToolResult(
            ok=False,
            message=f"No cached app capabilities for '{app}'",
            data={"hardware": {"domains": domains}, "apps": {}},
        )

    settings = []
    for dname, meta in domains.items():
        for s in meta.get("settings") or []:
            settings.append(
                {
                    "domain": dname,
                    "id": s.get("id"),
                    "label": s.get("label"),
                    "supported": s.get("supported"),
                    "readable": s.get("readable"),
                    "writable": s.get("writable"),
                    "tools": s.get("tools"),
                    "notes": s.get("notes"),
                }
            )

    supported_n = sum(1 for s in settings if s.get("supported"))
    installed_n = sum(
        1 for m in app_caps.values() if isinstance(m, dict) and m.get("installed")
    )
    msg = (
        f"Cached capabilities: {supported_n}/{len(settings)} hardware settings supported; "
        f"{installed_n} installed app profiles"
        + (f" (filter app={app})" if app else "")
        + (f" (filter domain={domain})" if domain else "")
    )
    return ToolResult(
        ok=True,
        message=msg,
        data={
            "updated_at": (inv.store.snapshot().get("capabilities") or {}).get(
                "updated_at"
            ),
            "hardware": {"domains": domains, "probed": hw.get("probed")},
            "apps": app_caps,
            "settings_flat": settings,
        },
    )
