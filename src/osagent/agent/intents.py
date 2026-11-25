"""Deterministic intent → tool mapping for reliable local-model execution."""

from __future__ import annotations

import re
from typing import Any

from osagent.agent.intent_types import IntentMatch
from osagent.platform_info import HostOS, detect_os

# Re-export for callers
__all__ = ["IntentMatch", "match_intent", "looks_like_action_without_tool"]

# Shared "ask / report" verbs — tell/show/share/what/get all mean the same for status tools
_ASK = (
    r"(?:tell(?:\s+me)?|show(?:\s+me)?|share(?:\s+with\s+me)?|give(?:\s+me)?|"
    r"what(?:'s|\s+is|\s+are)?|whats|how\s+much|how\s+many|check|get|display|"
    r"report|read|print|list)"
)


def match_intent(text: str, host: HostOS | None = None) -> IntentMatch | None:
    """Return a tool call if the user utterance is a clear desktop action."""
    raw = (text or "").strip()
    if not raw:
        return None
    lower = raw.lower()
    host = host or detect_os()
    linux = host == HostOS.LINUX

    # General structured planner first (web-on-site, recent docs, …)
    from osagent.agent.planner import plan_utterance

    planned = plan_utterance(raw)
    if planned:
        return planned

    # --- Linux sysadmin shortcuts (WSL / Debian / antiX) ---
    if linux:
        linux_hit = _match_linux_sysadmin(lower)
        if linux_hit:
            return linux_hit

    # Built-in Windows / shared intents continue below; learned phrases are
    # checked at the end so curated routes always win.

    os_prefix = "linux" if linux else "windows"

    # Brightness get — "tell me / show / what is brightness"
    if re.search(r"\bbrightness\b", lower) and re.search(rf"\b{_ASK}\b", lower) and not re.search(
        r"\b(set|change|to\s+\d|increase|decrease|reduce|raise|lower|make)\b",
        lower,
    ):
        return IntentMatch(
            f"{os_prefix}.display.get_brightness",
            {},
            "get brightness",
        )

    # Brightness: "set/reduce/increase brightness to 10%" / "brightness 10"
    m = re.search(
        r"\b(?:set|change|reduce|lower|increase|raise|make)?\s*"
        r"brightness\s*(?:to\s*)?(\d{1,3})\s*%?",
        lower,
    )
    if not m:
        m = re.search(r"\bbrightness\s*(?:at|=)?\s*(\d{1,3})\s*%", lower)
    if m and any(w in lower for w in ("brightness", "bright")):
        pct = max(0, min(100, int(m.group(1))))
        return IntentMatch(
            f"{os_prefix}.display.set_brightness",
            {"percent": pct},
            f"set brightness to {pct}%",
        )

    # Battery status — "tell me / show / share / what is battery…"
    if re.search(r"\bbatter(?:y|ies)\b", lower) and (
        re.search(rf"\b{_ASK}\b", lower)
        or re.search(r"\b(status|percent|percentage|level|charge|remaining)\b", lower)
        or lower.strip() in {"battery", "battery status", "battery percent"}
    ):
        return IntentMatch(f"{os_prefix}.battery.status", {}, "battery status")

    # Uptime / last boot
    if re.search(r"\b(uptime|last\s+boot|boot\s+time)\b", lower):
        if linux:
            return IntentMatch("linux.system.uptime", {}, "system uptime")
        return IntentMatch("windows.system.uptime", {}, "system uptime")

    # Disk free / storage
    if re.search(
        r"\b(disk|drive|storage)\b.*\b(free|space|usage|status)\b|"
        r"\b(free|space)\b.*\b(disk|drive|storage)\b|"
        rf"\b{_ASK}\b.*\b(disk|drive|storage)\b",
        lower,
    ):
        if linux:
            return IntentMatch("linux.disk.free", {}, "disk free space")
        return IntentMatch("files.disk_free", {}, "disk free space")

    # Volume get (current level) — before set/adjust
    if re.search(r"\bvolume\b", lower) and (
        re.search(rf"\b{_ASK}\b", lower)
        or re.search(r"\b(status|level|percent|now|current)\b", lower)
        or lower.strip() in {"volume", "volume status", "volume level", "volume percent"}
    ) and not re.search(
        r"\b(set|change|to\s+\d|up|down|mute|reset|restore|increase|decrease|"
        r"louder|quieter)\b",
        lower,
    ):
        return IntentMatch(f"{os_prefix}.volume.get", {}, "get volume")

    # Volume reset / restore → unmute + default level (avoid LLM hang)
    if re.search(
        r"\b(reset|restore|default)\b.*\bvolume\b|\bvolume\b.*\b(reset|restore|default)\b",
        lower,
    ):
        pct = 50
        m = re.search(r"(\d{1,3})\s*%?", lower)
        if m:
            pct = max(0, min(100, int(m.group(1))))
        return IntentMatch(
            f"{os_prefix}.volume.reset",
            {"percent": pct},
            f"reset volume to {pct}%",
        )

    # Volume absolute
    m = re.search(
        r"\b(?:set|change)?\s*volume\s*(?:to\s*)?(\d{1,3})\s*%?",
        lower,
    )
    if m and "volume" in lower and not any(
        w in lower
        for w in (
            "up",
            "down",
            "increase",
            "decrease",
            "louder",
            "quieter",
            "mute",
            "reset",
            "restore",
            "default",
        )
    ):
        pct = max(0, min(100, int(m.group(1))))
        return IntentMatch(
            f"{os_prefix}.volume.set_percent",
            {"percent": pct},
            f"set volume to {pct}%",
        )

    # Volume relative
    if re.search(r"\b(volume\s+up|increase\s+volume|louder|turn\s+up\s+(the\s+)?volume)\b", lower):
        delta = 10
        m = re.search(r"(\d{1,3})\s*%?", lower)
        if m:
            delta = max(1, min(50, int(m.group(1))))
        return IntentMatch(
            f"{os_prefix}.volume.adjust", {"delta": delta}, f"volume +{delta}"
        )
    if re.search(
        r"\b(volume\s+down|decrease\s+volume|quieter|lower\s+volume|turn\s+down\s+(the\s+)?volume|"
        r"reduce\s+volume)\b",
        lower,
    ):
        delta = 10
        m = re.search(r"(\d{1,3})\s*%?", lower)
        if m:
            delta = max(1, min(50, int(m.group(1))))
        return IntentMatch(
            f"{os_prefix}.volume.adjust", {"delta": -delta}, f"volume -{delta}"
        )

    if re.search(r"\bunmute\b", lower):
        return IntentMatch(f"{os_prefix}.volume.mute", {"muted": False}, "unmute")
    if re.search(r"\bmute\b", lower) and "unmute" not in lower:
        return IntentMatch(f"{os_prefix}.volume.mute", {"muted": True}, "mute")

    # --- New/blank document in Office / Notepad (Windows) ---
    if not linux:
        doc = _match_new_document(lower)
        if doc:
            return doc

    # --- Find executable (possibly and open) ---
    find_open = _match_find_and_open(lower)
    if find_open:
        return find_open

    # --- Residual web / URL (planner already handled on-site searches) ---
    web = _match_web_intent(lower, raw)
    if web:
        return web

    # Launch apps — known aliases OR fuzzy name (never websites / on-site phrases)
    from osagent.agent.planner import looks_like_web_request

    if looks_like_web_request(raw):
        pass  # do not app.launch
    else:
        app = _match_app_launch(lower)
        if app:
            return app

    # Latest files — fast scoped search (not entire user profile)
    # Covers: "find last 10 files updated by me", "find recent updated files"
    if (
        re.search(
            r"\b(latest|recent|newest|last)\b.*\b"
            r"(file|files|document|documents|updated|edited|modified|changed|saved)\b",
            lower,
        )
        or re.search(
            r"\b(file|files|document|documents)\b.*\b"
            r"(latest|recent|newest|updated|edited|modified)\b",
            lower,
        )
        or re.search(
            r"\b(updated|edited|modified)\s+by\s+me\b",
            lower,
        )
    ):
        # Typed recency ("last updated ppts") is handled by the planner already
        from osagent.agent.planner import _wants_containing_folder
        from osagent.tools.recent_open import FILE_KIND_WORDS

        if any(
            re.search(rf"\b{re.escape(k)}\b", lower)
            for k in FILE_KIND_WORDS
            if k not in {"file", "files", "document", "documents"}
        ):
            pass  # fall through — should have been planned; avoid wrong generic search
        elif _wants_containing_folder(lower):
            # "open folder of last updated file" → Explorer, not a list dump
            return IntentMatch(
                "files.open_recent",
                {"kind": "file", "open": True, "open_folder": True, "count": 1},
                "open folder of latest file",
            )
        else:
            count = (
                1
                if re.search(r"\bfile\b", lower) and not re.search(r"\bfiles\b", lower)
                else 5
            )
            m = re.search(r"\b(\d{1,2})\b", lower)
            if m:
                count = max(1, min(30, int(m.group(1))))
            return IntentMatch(
                "files.find_recent",
                {"count": count, "scope": "quick", "depth": 6},
                f"find {count} recent file(s)",
            )

    # Printers — default first (more specific than "list printers")
    if re.search(
        r"\bdefault\s+printers?\b|\bprinters?\b.*\bdefault\b|\bcurrent\s+(default\s+)?printer\b",
        lower,
    ) or re.search(
        r"\b(name|which|what)\b.*\b(default\s+)?printer\b|\bprinter\s+name\b",
        lower,
    ):
        # "set/change default printer to X" is different
        if not re.search(r"\b(set|change|make|switch)\b.*\bdefault\b", lower):
            return IntentMatch(
                f"{os_prefix}.printers.default",
                {},
                "show default printer",
            )
    if re.search(
        r"\b(list|show|what)\b.*\bprinters\b",
        lower,
    ) or re.search(
        r"\bprinters\b.*\b(list|installed|available|all)\b",
        lower,
    ):
        return IntentMatch(f"{os_prefix}.printers.list", {}, "list printers")
    # Singular "show printer" without default → still list (overview)
    if re.search(r"\b(list|show)\b.*\bprinter\b", lower) and "default" not in lower:
        return IntentMatch(f"{os_prefix}.printers.list", {}, "list printers")

    # Bluetooth devices / connections
    if re.search(r"\bbluetooth\b", lower) and (
        re.search(rf"\b{_ASK}\b", lower)
        or re.search(
            r"\b(active|connected|connection|connections|paired|pairing|"
            r"devices?|headset|headphone|earbuds?)\b",
            lower,
        )
    ):
        return IntentMatch(
            f"{os_prefix}.bluetooth.list", {}, "list bluetooth devices"
        )

    # Contrast (must be before resolution — "screen" alone must not steal this)
    if re.search(r"\bcontrast\b", lower) and not re.search(
        r"\b(resolution|pixels?)\b", lower
    ):
        return IntentMatch(
            f"{os_prefix}.display.get_contrast",
            {},
            "get contrast settings",
        )

    # Screen resolution only (explicit resolution/pixels — not contrast/brightness)
    if re.search(
        r"\b(screen|display|monitor)\b.*\b(resolution|pixels?)\b",
        lower,
    ) or re.search(
        r"\b(resolution|what\s+resolution)\b",
        lower,
    ):
        return IntentMatch(f"{os_prefix}.display.info", {}, "get display resolution")

    # Brightness get (without a percent target — set is handled above)
    if re.search(r"\b(brightness|how\s+bright)\b", lower) and not re.search(
        r"\b\d{1,3}\b", lower
    ):
        return IntentMatch(
            f"{os_prefix}.display.get_brightness",
            {},
            "get brightness",
        )

    # System inventory
    if re.search(
        r"\b(refresh|rebuild|rescan|update)\b.*\b(inventory|app\s+map|app\s+index)\b",
        lower,
    ) or re.search(r"\b(inventory|app\s+index)\b.*\b(refresh|rebuild|rescan)\b", lower):
        return IntentMatch(
            "system.inventory.refresh",
            {"wait": False},
            "refresh inventory",
        )
    if re.search(
        r"\b(hardware|display|audio|printer|bluetooth|network|power)\b.*\b"
        r"(settings|capabilities|commands|options)\b",
        lower,
    ) or re.search(
        r"\b(what|which)\b.*\b(settings|commands|options)\b.*\b"
        r"(available|supported|can\s+(?:you|i)|work)\b",
        lower,
    ) or re.search(
        r"\b(app|application)\b.*\b(capabilities|commands|options)\b",
        lower,
    ) or re.search(r"\binventory\b.*\b(capabilities|settings)\b", lower):
        return IntentMatch(
            "system.inventory.capabilities",
            {},
            "inventory capabilities",
        )
    if re.search(
        r"\b(inventory|app\s+map|known\s+apps|indexed\s+apps)\b",
        lower,
    ) or re.search(r"\bwhat\b.*\b(apps|programs)\b.*\b(know|indexed|mapped)\b", lower):
        return IntentMatch("system.inventory.status", {}, "inventory status")

    # Auto-learned phrases (after built-ins so curated routes always win)
    try:
        from osagent.agent.learned_intents import match_learned

        learned = match_learned(raw)
        if learned:
            return learned
    except Exception:
        pass

    return None


def _match_new_document(lower: str) -> IntentMatch | None:
    """open/create a new/blank excel|word|txt|… file → launch the app."""
    from osagent.tools.win_launch import FILE_TYPE_APPS

    # Do not steal "open last/latest … file" (handled by open_recent)
    if re.search(r"\b(last|latest|newest|recent)\b", lower):
        return None

    # open [a] [new|blank] <type> [file|document|spreadsheet|workbook|presentation]
    m = re.match(
        r"^(?:open|create|start|make|launch)\s+"
        r"(?:a\s+|an\s+)?"
        r"(?:new\s+|blank\s+|empty\s+)?"
        r"(?P<kind>excel|xls|xlsx|spreadsheet|workbook|word|doc|docx|"
        r"powerpoint|ppt|pptx|presentation|notepad|text\s+file|text|txt)"
        r"(?:\s+file|\s+document|\s+spreadsheet|\s+workbook|\s+presentation)?\s*$",
        lower,
    )
    if not m:
        # "new excel file" / "blank spreadsheet" without open/
        m = re.match(
            r"^(?:a\s+|an\s+)?"
            r"(?:new\s+|blank\s+|empty\s+)"
            r"(?P<kind>excel|xls|xlsx|spreadsheet|workbook|word|doc|docx|"
            r"powerpoint|ppt|pptx|presentation|text\s+file|text|txt)"
            r"(?:\s+file|\s+document)?\s*$",
            lower,
        )
    if not m:
        return None
    kind = re.sub(r"\s+", " ", m.group("kind").strip())
    app = FILE_TYPE_APPS.get(kind)
    if not app:
        return None
    return IntentMatch("app.launch", {"target": app}, f"open new {app}")


def _match_web_intent(lower: str, raw: str) -> IntentMatch | None:
    from osagent.tools.web_open import (
        SITE_ALIASES,
        looks_like_url,
        normalize_url,
        resolve_open_target,
    )

    # Explicit search phrases
    m = re.match(
        r"^(?:google|bing)?\s*search\s+(?:the\s+web\s+)?(?:for\s+)?(.+)$",
        lower,
    )
    if m and m.group(1).strip() not in {"google", "bing", "the web", "web"}:
        query = m.group(1).strip()
        # "search google" alone → homepage handled below; "search for X"
        if query not in SITE_ALIASES and query != "google":
            engine = "bing" if lower.startswith("bing") else "google"
            return IntentMatch(
                "web.search",
                {"query": query, "engine": engine},
                f"search {engine} for {query}",
            )

    m = re.match(r"^(?:look\s+up|search\s+for|google)\s+(.+)$", lower)
    if m:
        query = m.group(1).strip()
        # "google chrome" is an app, not a search
        if query in {"chrome", "google chrome"} or query.startswith("chrome "):
            pass
        elif query in SITE_ALIASES or looks_like_url(query):
            pass
        else:
            return IntentMatch(
                "web.search",
                {"query": query, "engine": "google"},
                f"search google for {query}",
            )

    # "open / go to / visit / browse …"
    m = re.match(
        r"^(?:open|go\s+to|goto|visit|browse|navigate\s+to)\s+"
        r"(?:the\s+)?(.+?)\s*$",
        lower,
    )
    if m:
        target = m.group(1).strip(" .")
        # Preserve original casing for URLs from raw when possible
        raw_m = re.match(
            r"^(?:open|go\s+to|goto|visit|browse|navigate\s+to)\s+"
            r"(?:the\s+)?(.+?)\s*$",
            raw,
            re.I,
        )
        raw_target = raw_m.group(1).strip(" .") if raw_m else target

        classified = resolve_open_target(raw_target)
        if classified and classified["kind"] in {"url", "search"}:
            args: dict[str, Any] = {"url": classified["url"]}
            if classified.get("browser"):
                args["browser"] = classified["browser"]
            return IntentMatch("web.open", args, f"open {classified['url']}")

        # "open google search" / site aliases already in resolve; double-check sites
        body = re.sub(
            r"\s+in\s+(?:the\s+)?(?:browser|chrome|edge|firefox|google chrome|"
            r"microsoft edge|msedge|mozilla firefox)\s*$",
            "",
            target,
            flags=re.I,
        ).strip()
        if body in SITE_ALIASES or looks_like_url(body):
            args = {"url": normalize_url(body)}
            br = classified.get("browser") if classified else None
            if br:
                args["browser"] = br
            return IntentMatch("web.open", args, f"open {args['url']}")

        # Fall through — may be app launch

    # Bare "google search" / "google.com"
    if lower in SITE_ALIASES or looks_like_url(lower):
        return IntentMatch(
            "web.open",
            {"url": normalize_url(lower)},
            f"open {normalize_url(lower)}",
        )

    return None


def _match_app_launch(lower: str) -> IntentMatch | None:
    from osagent.tools.web_open import SITE_ALIASES, looks_like_url, resolve_open_target
    from osagent.tools.win_launch import ALIASES

    m = re.match(
        r"^(?:launch|open|start|run)\s+(?:the\s+)?(.+?)(?:\s+app|\s+application)?\s*$",
        lower,
    )
    if not m:
        return None

    target = m.group(1).strip(" .")
    if not target or target in {"settings", "file", "folder", "this", "browser"}:
        return None

    # Never treat websites / YouTube / web searches as apps
    if re.search(r"\byoutube\.?com?\b|\bon\s+youtube\b|\bhttps?://", target):
        return None
    classified = resolve_open_target(target)
    if classified and classified["kind"] in {"url", "search"}:
        return None
    if looks_like_url(target) or target in SITE_ALIASES:
        return None

    # Strip "in browser" leftovers that aren't real apps
    if re.search(r"\bin\s+(?:the\s+)?browser\b", target):
        return None

    known = {k.lower() for k in ALIASES}

    # "new excel file" / "blank word document" left over → map to app
    # Never map "last/latest ppt" or "aayushi image" here
    from osagent.tools.recent_open import FILE_KIND_WORDS

    if re.search(r"\b(last|latest|newest|recent|updated|modified)\b", target):
        return None
    if any(re.search(rf"\b{re.escape(k)}\b", target) for k in FILE_KIND_WORDS):
        return None

    from osagent.tools.win_launch import FILE_TYPE_APPS

    for kind, app in sorted(FILE_TYPE_APPS.items(), key=lambda kv: -len(kv[0])):
        if kind in target and app in known:
            return IntentMatch("app.launch", {"target": app}, f"launch {app}")

    # Exact known app, or path-like / .exe
    if (
        target in known
        or target.endswith(".exe")
        or "\\" in target
        or "/" in target
        or target.startswith("%")
    ):
        return IntentMatch("app.launch", {"target": target}, f"launch {target}")

    # Single/multi-word app-like token → launch with fuzzy filesystem search
    # (e.g. "open gnucache", "open GnuCashPortable")
    if re.fullmatch(r"[a-z0-9][a-z0-9 _.\-]{1,60}", target) and not looks_like_url(
        target
    ):
        return IntentMatch("app.launch", {"target": target}, f"launch {target}")

    return None


def _match_find_and_open(lower: str) -> IntentMatch | None:
    """look for / find <name> executable [on desktop] and open/launch it"""
    # File-by-name+type is handled by planner (files.open_named) — never treat as exe
    from osagent.tools.recent_open import FILE_KIND_WORDS

    if any(re.search(rf"\b{re.escape(k)}\b", lower) for k in FILE_KIND_WORDS):
        return None

    m = re.match(
        r"^(?:look\s+for|find|search\s+for|locate)\s+"
        r"(?:the\s+)?"
        r"(?P<name>.+?)"
        r"(?:\s+executable|\s+exe|\s+app|\s+application|\s+program)?"
        r"(?:\s+on\s+(?:the\s+)?desktop)?"
        r"(?:\s+and\s+(?:open|launch|run|start)(?:\s+it)?)?"
        r"\s*$",
        lower,
    )
    if not m:
        return None
    name = m.group("name").strip(" .")
    # strip trailing "on desktop" left inside name
    name = re.sub(r"\s+on\s+(?:the\s+)?desktop$", "", name).strip()
    name = re.sub(
        r"\s+(?:executable|exe|app|application|program)$",
        "",
        name,
    ).strip()
    if not name or len(name) < 2:
        return None
    # Prefer launch (fuzzy find + open) over find-only when user said open
    if re.search(r"\b(open|launch|run|start)\b", lower):
        return IntentMatch("app.launch", {"target": name}, f"find and launch {name}")
    return IntentMatch("app.find", {"query": name}, f"find app {name}")


_ACTION_TALK = re.compile(
    r"\b(i('ll| will)|let me|going to|i am going to|setting|changing|reducing|"
    r"increasing|launching|opening|running|i can set|i'll set)\b",
    re.I,
)


def looks_like_action_without_tool(text: str) -> bool:
    """True if the model claimed it would act but issued no TOOL line."""
    if not text:
        return False
    if re.search(r"^\s*TOOL\s+\S+", text, re.M):
        return False
    return bool(_ACTION_TALK.search(text))


def _match_linux_sysadmin(lower: str) -> IntentMatch | None:
    """Deterministic Linux admin phrases (packages, services, memory, network)."""
    # Catalog phrase map (firewall, mounts, docker, health, …)
    try:
        from osagent.tools.catalog.loader import linux_catalog_phrase_intents

        for pattern, tool_id, args in linux_catalog_phrase_intents():
            if pattern.search(lower):
                return IntentMatch(tool_id, dict(args), f"catalog {tool_id}")
    except Exception:
        pass

    # Memory / RAM
    if re.search(
        r"\b(memory|ram|swap)\b.*\b(status|usage|free|used|how\s+much)\b|"
        rf"\b{_ASK}\b.*\b(memory|ram|swap)\b|"
        r"\b(free\s+memory|memory\s+usage|ram\s+usage)\b",
        lower,
    ):
        return IntentMatch("linux.memory.status", {}, "memory status")

    # Home folder (before generic system info)
    if re.search(
        r"\b(home\s+folder|home\s+directory|homedir|my\s+home)\b|"
        r"\bwhich\s+is\s+my\s+home\b|"
        rf"\b{_ASK}\b.*\bhome\s+(folder|directory|dir|path)\b|"
        r"\bwhere\s+is\s+my\s+home\b",
        lower,
    ):
        return IntentMatch("linux.system.home", {}, "home folder")

    # System info
    if re.search(
        r"\b(system\s+info|os\s+info|kernel\s+version|what\s+os|which\s+distro)\b|"
        rf"\b{_ASK}\b.*\b(os|distro|hostname|kernel)\b",
        lower,
    ):
        return IntentMatch("linux.system.info", {}, "system info")

    # Network interfaces
    if re.search(
        r"\b(network\s+interfaces?|ip\s+addresses?|show\s+ips?|list\s+interfaces?)\b|"
        rf"\b{_ASK}\b.*\b(ip\s+address|interfaces?)\b",
        lower,
    ):
        return IntentMatch("linux.network.interfaces", {}, "network interfaces")

    # Listening ports
    if re.search(r"\b(listening\s+ports?|open\s+ports?|ports?\s+in\s+use)\b", lower):
        return IntentMatch("linux.network.listening", {}, "listening ports")

    # Who / users
    if re.search(r"\b(who\s+is\s+logged\s+in|logged[\s-]?in\s+users?)\b", lower):
        return IntentMatch("linux.users.who", {}, "who")
    if re.search(r"\b(list\s+users|local\s+users|user\s+accounts)\b", lower):
        return IntentMatch("linux.users.list", {}, "list users")

    # apt search
    m = re.search(
        r"\b(?:search|find)\s+(?:apt\s+)?(?:packages?\s+)?(?:for\s+)?(?P<q>.+)$",
        lower,
    )
    if m and re.search(r"\b(apt|package|packages)\b", lower):
        q = m.group("q").strip(" .")
        q = re.sub(r"^(packages?\s+named\s+|package\s+)", "", q).strip()
        if q and len(q) < 80:
            return IntentMatch(
                "linux.packages.search",
                {"query": q, "limit": 30},
                f"search packages {q}",
            )

    # apt list installed
    if re.search(r"\b(list\s+installed\s+packages|installed\s+packages)\b", lower):
        return IntentMatch("linux.packages.list_installed", {"limit": 40}, "list packages")

    # apt install
    m = re.search(
        r"\b(?:apt(?:-get)?\s+)?install\s+(?:the\s+)?(?:package\s+)?(?P<p>[a-z0-9][a-z0-9.+_-]*(?:\s+[a-z0-9][a-z0-9.+_-]*)*)\b",
        lower,
    )
    if m and re.search(r"\b(install|apt)\b", lower):
        return IntentMatch(
            "linux.packages.install",
            {"packages": m.group("p").strip()},
            f"install {m.group('p').strip()}",
        )

    # service status / start / stop / restart
    m = re.search(
        r"\b(?P<act>start|stop|restart|status)\s+(?:the\s+)?(?P<name>[a-z0-9][a-z0-9_.@-]*)\s+service\b",
        lower,
    )
    if not m:
        m = re.search(
            r"\b(?:service\s+)(?P<name>[a-z0-9][a-z0-9_.@-]*)\s+(?P<act>start|stop|restart|status)\b",
            lower,
        )
    if m:
        act = m.group("act")
        name = m.group("name")
        tool = {
            "status": "linux.service.status",
            "start": "linux.service.start",
            "stop": "linux.service.stop",
            "restart": "linux.service.restart",
        }[act]
        return IntentMatch(tool, {"name": name}, f"{act} service {name}")

    if re.search(r"\b(list\s+services|running\s+services)\b", lower):
        running = bool(re.search(r"\brunning\b", lower))
        return IntentMatch(
            "linux.service.list",
            {"running_only": running, "limit": 50},
            "list services",
        )

    # processes
    if re.search(r"\b(list\s+processes|show\s+processes|process\s+list|top\s+processes)\b", lower):
        return IntentMatch("linux.process.list", {"limit": 40}, "list processes")

    return None
