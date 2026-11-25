"""
General utterance planner.

Turns natural language into a tool call when the request has clear structure:
  - open/search/play <query> [entity] on/at <site>
  - open last/latest <doc-type> file
  - find <app> and open it
  - open <site> homepage

This is the shared "intelligence" layer so we don't special-case only YouTube.
"""

from __future__ import annotations

import re
from typing import Any

from osagent.agent.intent_types import IntentMatch
from osagent.agent.web_destinations import (
    ENTITY_WORDS,
    match_destination,
    site_home_aliases,
    unknown_site_search,
)

_OPEN_VERBS = r"open|go\s+to|goto|visit|browse|navigate\s+to|play|show|find|search(?:\s+for)?|look\s+up"


def plan_utterance(text: str) -> IntentMatch | None:
    """Return a planned tool call, or None to fall through to other matchers / LLM."""
    raw = (text or "").strip()
    if not raw:
        return None
    lower = raw.lower().strip()

    # 1) Web: query on/at site (YouTube, GitHub, Amazon, … or any domain)
    web = _plan_web_on_site(raw, lower)
    if web:
        return web

    # 2) Bare site homepage: "open youtube", "go to github.com"
    home = _plan_site_home(lower)
    if home:
        return home

    # 3) Open/list last/latest document of a type
    #    ("open last ppt", "find last updated ppts", "show newest excels")
    recent = _plan_open_recent_doc(lower)
    if recent:
        return recent

    # 4) Find/open file by name + type: "find aayushi image", "open budget pdf"
    named = _plan_named_file(raw, lower)
    if named:
        return named

    return None


def looks_like_web_request(text: str) -> bool:
    """True if the utterance is clearly about the web (block app.launch)."""
    lower = (text or "").lower()
    if re.search(r"\bhttps?://|\bwww\.", lower):
        return True
    if re.search(r"\bon\s+(?:www\.)?[a-z0-9.-]+\.[a-z]{2,}\b", lower):
        return True
    if re.search(rf"\b(?:{_OPEN_VERBS})\b.+\b(?:on|at)\b.+\b", lower):
        # "open X on Y" — Y might be a known site name
        m = re.search(rf"\b(?:on|at)\s+(?:the\s+)?(?P<site>.+)$", lower)
        if m and match_destination(m.group("site").strip()):
            return True
    aliases = site_home_aliases()
    for a in aliases:
        if len(a) >= 3 and re.search(rf"\b{re.escape(a)}\b", lower):
            # only if also has open/search and more than just the site name alone
            if re.search(rf"\b(?:{_OPEN_VERBS})\b", lower) and lower.strip() not in {
                f"open {a}",
                f"go to {a}",
            }:
                if " on " in lower or " at " in lower or "channel" in lower:
                    return True
    return False


def _extract_quoted(raw: str) -> str | None:
    m = re.search(r'["“](.+?)["”]|\'(.+?)\'', raw)
    if not m:
        return None
    return (m.group(1) or m.group(2) or "").strip() or None


def _plan_web_on_site(raw: str, lower: str) -> IntentMatch | None:
    quoted = _extract_quoted(raw)

    # @handle on youtube / twitter
    m = re.search(
        rf"(?:{_OPEN_VERBS})?\s*@(?P<h>[a-zA-Z0-9._]+)\s+(?:on|at)\s+(?P<site>.+)$",
        raw,
        re.I,
    )
    if m:
        site = match_destination(m.group("site"))
        handle = m.group("h")
        if site and site.id == "youtube":
            url = f"https://www.youtube.com/@{handle}"
            return IntentMatch("web.open", {"url": url}, f"YouTube @{handle}")
        if site and site.id == "twitter":
            url = f"https://x.com/{handle}"
            return IntentMatch("web.open", {"url": url}, f"X @{handle}")
        if site and site.id == "github":
            url = f"https://github.com/{handle}"
            return IntentMatch("web.open", {"url": url}, f"GitHub @{handle}")

    # open <query> [entity] on|at <site>
    # Examples:
    #   open "sanscari summit" channel on youtube.com
    #   search rust async on stackoverflow
    #   find wireless mouse product on amazon
    m = re.search(
        rf"^(?:{_OPEN_VERBS})\s+"
        r"(?:the\s+)?"
        r"(?P<body>.+?)\s+"
        r"(?P<on>on|at)\s+"
        r"(?:the\s+)?"
        r"(?P<site>.+?)\s*$",
        lower,
    )
    if not m:
        # site first: "open youtube channel sanscari" / "youtube search cats"
        return _plan_site_first(raw, lower, quoted)

    body = m.group("body").strip(" .\"'")
    site_raw = m.group("site").strip(" .\"'")
    # Drop trailing "in chrome" etc.
    site_raw = re.sub(
        r"\s+in\s+(?:the\s+)?(?:browser|chrome|edge|firefox).*$",
        "",
        site_raw,
    ).strip()

    entity: str | None = None
    # body ends with entity word: "sanscari summit channel"
    parts = body.split()
    if len(parts) >= 2 and parts[-1] in ENTITY_WORDS:
        entity = parts[-1]
        body = " ".join(parts[:-1]).strip()
    # or "channel sanscari summit" (entity first) — rare
    if parts and parts[0] in ENTITY_WORDS and len(parts) >= 2:
        entity = parts[0]
        body = " ".join(parts[1:]).strip()

    query = quoted or body
    query = re.sub(r"\s+", " ", query).strip(" .\"'")
    if not query:
        return None

    dest = match_destination(site_raw)
    if dest:
        # Prefer destination-known entities
        if entity and entity not in dest.entities and dest.entities:
            # still pass entity; search fn can ignore
            pass
        url = dest.search(query, entity)
        label = f"{dest.id} search: {query}" + (f" ({entity})" if entity else "")
        return IntentMatch("web.open", {"url": url}, label)

    # Unknown site / raw domain
    if re.search(r"\.[a-z]{2,}$", site_raw) or " " not in site_raw:
        url = unknown_site_search(query, site_raw)
        return IntentMatch(
            "web.open",
            {"url": url},
            f"search '{query}' on {site_raw}",
        )

    return None


def _plan_site_first(raw: str, lower: str, quoted: str | None) -> IntentMatch | None:
    """open youtube channel X  /  github repo X  /  amazon search X"""
    m = re.search(
        rf"^(?:{_OPEN_VERBS})\s+"
        r"(?P<site>youtube|yt|github|gh|amazon|reddit|wikipedia|wiki|"
        r"twitter|linkedin|netflix|facebook|fb|bing|google|maps|"
        r"stackoverflow|duckduckgo|ddg)"
        r"(?:\.com)?"
        r"\s+"
        r"(?:(?P<entity>channel|channels|video|videos|repo|repos|repository|"
        r"user|users|product|products|subreddit|article|job|jobs|search)\s+)?"
        r"(?:for\s+)?"
        r"(?P<q>.+)$",
        lower,
    )
    if not m:
        return None
    dest = match_destination(m.group("site"))
    if not dest:
        return None
    entity = m.group("entity")
    if entity == "search":
        entity = None
    q = quoted or m.group("q").strip(" .\"'")
    if not q:
        return None
    url = dest.search(q, entity)
    return IntentMatch(
        "web.open",
        {"url": url},
        f"{dest.id} search: {q}" + (f" ({entity})" if entity else ""),
    )


def _plan_site_home(lower: str) -> IntentMatch | None:
    m = re.match(
        rf"^(?:{_OPEN_VERBS})\s+(?:the\s+)?(?P<site>.+?)\s*$",
        lower,
    )
    if not m:
        return None
    site = m.group("site").strip(" .")
    # Don't treat multi-word queries as homepage
    if " on " in site or " at " in site:
        return None
    aliases = site_home_aliases()
    key = site.lower()
    if key in aliases:
        return IntentMatch("web.open", {"url": aliases[key]}, f"open {key}")
    # domain-only
    if re.fullmatch(r"(?:www\.)?[a-z0-9.-]+\.[a-z]{2,}(?:/\S*)?", key):
        url = key if key.startswith("http") else "https://" + key.lstrip("/")
        return IntentMatch("web.open", {"url": url}, f"open {url}")
    return None


# Words that are recency/filters, not a filename
_RECENCY_NAME = re.compile(
    r"^(?:the\s+)?"
    r"(?:last|latest|newest|recent(?:ly)?|most\s+recent(?:ly)?)"
    r"(?:\s+(?:\d{1,2}|updated|modified|edited|changed|saved|created))*"
    r"(?:\s+by\s+me)?$",
    re.I,
)


def _is_recency_filler(name: str) -> bool:
    n = re.sub(r"\s+", " ", (name or "").strip().lower())
    if not n:
        return True
    if _RECENCY_NAME.match(n):
        return True
    # leftover crumbs like "updated", "by me", "last 10"
    if re.fullmatch(
        r"(?:updated|modified|edited|changed|saved|created|by\s+me|"
        r"\d{1,2}|last|latest|newest|recent(?:ly)?)+",
        n,
    ):
        return True
    return False


def _wants_containing_folder(lower: str) -> bool:
    """True for 'open folder of last ppt', 'show directory containing newest excel'."""
    # Any open/show/reveal + folder/directory with a typed recent file → Explorer, not the app
    if re.search(r"\b(folder|directory|dir|explorer)\b", lower) and re.search(
        r"\b(open|show|reveal|go\s+to|locate)\b",
        lower,
    ):
        return True
    if re.search(
        r"\b(?:containing|holding)\s+(?:folder|directory|dir)\b",
        lower,
    ):
        return True
    return False


def _plan_open_recent_doc(lower: str) -> IntentMatch | None:
    """
    Recency + typed file:
      open last ppt → open newest
      open folder of ppt last updated → open parent folder of newest
      find last updated ppts / show newest excels → list newest (do not open)
    """
    from osagent.tools.recent_open import kind_regex_alternation

    if not re.search(rf"\b(?:{_OPEN_VERBS}|list|reveal)\b", lower):
        return None
    if not re.search(
        r"\b(last|latest|newest|recent(?:ly)?|most\s+recent(?:ly)?)\b",
        lower,
    ):
        return None

    kind_alt = kind_regex_alternation()
    m = re.search(rf"\b(?P<kind>{kind_alt})\b", lower)
    kind: str | None = m.group("kind") if m else None
    if kind == "text":
        kind = "txt"
    # Generic: "open folder of last updated file" (no ppt/xlsx/…)
    if kind is None and re.search(r"\b(?:files?|documents?)\b", lower):
        kind = "file"
    if kind is None:
        return None

    count = 5
    cm = re.search(r"\b(\d{1,2})\b", lower)
    if cm:
        count = max(1, min(30, int(cm.group(1))))

    if _wants_containing_folder(lower):
        return IntentMatch(
            "files.open_recent",
            {"kind": kind, "open": True, "open_folder": True, "count": 1},
            f"open folder of latest {kind}",
        )
    # Bare "open last file" without a type → list via find_recent (intents), not open junk
    if kind == "file":
        return None

    # find/list/show → list; open/launch/view → open one
    list_only = bool(
        re.match(r"^(?:find|search(?:\s+for)?|look\s+up|locate|list)\b", lower)
    )
    if re.search(r"\b(show|list)\b", lower) and not re.search(
        r"\b(open|launch|view|play)\b", lower
    ):
        list_only = True
    if re.search(r"\b(open|launch)\b", lower):
        list_only = False

    if list_only:
        return IntentMatch(
            "files.open_recent",
            {"kind": kind, "open": False, "count": count},
            f"list {count} recent {kind}",
        )
    return IntentMatch(
        "files.open_recent",
        {"kind": kind, "open": True, "count": 1},
        f"open latest {kind} file",
    )


def _plan_named_file(raw: str, lower: str) -> IntentMatch | None:
    """
    find/open/show <name> <any file kind>
    (images, pdfs, ppts, excels, text files, videos, …)
    """
    from osagent.tools.recent_open import kind_regex_alternation

    kind_alt = kind_regex_alternation()
    quoted = _extract_quoted(raw)

    def _should_open(kind: str) -> bool:
        """find/search/list → list matches; open/view/play → open best hit."""
        plural = bool(re.search(r"(?:s|es)$", kind)) and kind not in {
            "csv",
            "xls",
            "xlsx",
            "docs",
            "xls",
        }
        if re.search(r"\b(list|search\s+only|just\s+find)\b", lower):
            return False
        if re.match(r"^(?:find|search(?:\s+for)?|look\s+up|locate)\b", lower):
            return False
        if plural and re.match(r"^(?:show)\b", lower):
            return False
        if re.search(r"\b(open|launch|view|display|play)\b", lower):
            return True
        if re.match(r"^(?:show)\b", lower) and not plural:
            return True
        return False

    # Pattern A: find/open <name> <kind> [files]
    m = re.match(
        rf"^(?:{_OPEN_VERBS})\s+"
        r"(?:the\s+|an?\s+)?"
        rf"(?P<name>.+?)\s+"
        rf"(?P<kind>{kind_alt})"
        r"(?:\s+files?)?\s*$",
        lower,
    )
    if m:
        name = quoted or m.group("name").strip(" .\"'")
        kind = m.group("kind")
        name = re.sub(rf"\b{re.escape(kind)}\b", "", name).strip(" .\"'")
        name = re.sub(r"\b(named|called|file|files|the|a|an)\b", " ", name)
        name = re.sub(r"\s+", " ", name).strip()
        # "find last updated ppts" → name is recency filler, not a title
        if name and _is_recency_filler(name):
            return None
        if name and kind:
            open_it = _should_open(kind)
            return IntentMatch(
                "files.open_named",
                {"query": name, "kind": kind, "open": open_it},
                f"{'open' if open_it else 'list'} {kind} matching '{name}'",
            )

    # Pattern B: find/open <kind> [files] [named/called] <name>
    m = re.match(
        rf"^(?:{_OPEN_VERBS})\s+"
        r"(?:the\s+|an?\s+)?"
        rf"(?P<kind>{kind_alt})"
        r"(?:\s+files?)?"
        r"(?:\s+(?:named|called|with\s+name|titled))?\s+"
        r"(?P<name>.+?)\s*$",
        lower,
    )
    if m:
        kind = m.group("kind")
        name = quoted or m.group("name").strip(" .\"'")
        name = re.sub(r"\b(named|called|file|files)\b", " ", name)
        name = re.sub(r"\s+", " ", name).strip()
        if name and kind:
            open_it = _should_open(kind)
            return IntentMatch(
                "files.open_named",
                {"query": name, "kind": kind, "open": open_it},
                f"{'open' if open_it else 'list'} {kind} matching '{name}'",
            )

    # Pattern C: open <name>.jpg / find report.pdf
    m = re.match(
        rf"^(?:{_OPEN_VERBS})\s+"
        r"(?:the\s+)?"
        r"(?P<name>.+?)\.(?P<ext>jpg|jpeg|png|gif|bmp|webp|pdf|docx?|xlsx?|pptx?|"
        r"txt|mp4|mp3|csv|md|log)\s*$",
        lower,
    )
    if m:
        name = quoted or m.group("name").strip(" .\"'")
        ext = m.group("ext")
        if name:
            open_it = not re.match(
                r"^(?:find|search(?:\s+for)?|look\s+up|locate)\b", lower
            )
            return IntentMatch(
                "files.open_named",
                {"query": name, "extension": ext, "open": open_it},
                f"{'open' if open_it else 'list'} '{name}.{ext}'",
            )

    return None
