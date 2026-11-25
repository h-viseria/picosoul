"""Open URLs / web searches in a browser."""

from __future__ import annotations

import re
import urllib.parse
import webbrowser
from typing import Any

from osagent.tools.base import ToolResult

def _load_site_aliases() -> dict[str, str]:
    try:
        from osagent.agent.web_destinations import site_home_aliases

        aliases = site_home_aliases()
    except Exception:
        aliases = {}
    # Extra mail/web apps not in search destinations
    aliases.update(
        {
            "gmail": "https://mail.google.com",
            "outlook web": "https://outlook.live.com",
            "outlook.com": "https://outlook.live.com",
            "google search": "https://www.google.com",
        }
    )
    return aliases


SITE_ALIASES: dict[str, str] = _load_site_aliases()

_BROWSER_ALIASES = {
    "chrome": "chrome",
    "google chrome": "chrome",
    "edge": "edge",
    "microsoft edge": "edge",
    "msedge": "edge",
    "firefox": "firefox",
    "mozilla firefox": "firefox",
}

# domain.tld or www.domain.tld with optional path/query
_DOMAIN_RE = re.compile(
    r"^(?:https?://)?(?:www\.)?"
    r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?"
    r"(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)+"
    r"(?:[/:?#]\S*)?$",
    re.I,
)


def looks_like_url(text: str) -> bool:
    t = (text or "").strip().strip('"').rstrip(".,)")
    if not t:
        return False
    if re.match(r"^https?://", t, re.I):
        return True
    return bool(_DOMAIN_RE.match(t))


def normalize_url(text: str) -> str:
    t = (text or "").strip().strip('"').rstrip(".,)")
    key = t.lower()
    if key in SITE_ALIASES:
        return SITE_ALIASES[key]
    if re.match(r"^https?://", t, re.I):
        return t
    if looks_like_url(t):
        return "https://" + t.lstrip("/")
    return t


def google_search_url(query: str) -> str:
    q = urllib.parse.quote_plus((query or "").strip())
    return f"https://www.google.com/search?q={q}"


def bing_search_url(query: str) -> str:
    q = urllib.parse.quote_plus((query or "").strip())
    return f"https://www.bing.com/search?q={q}"


def youtube_search_url(query: str, *, channels_only: bool = False) -> str:
    """YouTube results page (optionally filtered to Channels)."""
    q = urllib.parse.quote_plus((query or "").strip())
    if channels_only:
        # sp=EgIQAg%3D%3D → Type: Channel
        return f"https://www.youtube.com/results?search_query={q}&sp=EgIQAg%3D%3D"
    return f"https://www.youtube.com/results?search_query={q}"


def youtube_handle_url(handle: str) -> str:
    h = (handle or "").strip().lstrip("@")
    return f"https://www.youtube.com/@{urllib.parse.quote(h)}"


def parse_youtube_open(text: str) -> dict[str, Any] | None:
    """
    Detect 'open <name> channel on youtube', 'play X on youtube', etc.
    Returns {url, query, mode: search|channel_search|handle|url} or None.
    """
    raw = (text or "").strip()
    if not raw:
        return None
    lower = raw.lower()
    if "youtube" not in lower:
        return None

    # Prefer quoted query from original casing
    quoted = re.search(r'["“](.+?)["”]|\'(.+?)\'', raw)
    quoted_q = (quoted.group(1) or quoted.group(2) or "").strip() if quoted else ""

    # Direct youtube URL already
    m = re.search(r"(https?://(?:www\.)?youtube\.com/\S+|youtube\.com/\S+)", lower)
    if m and not quoted_q:
        url = m.group(1)
        if not url.startswith("http"):
            url = "https://" + url
        return {"url": url, "query": None, "mode": "url"}

    # @handle on youtube
    m = re.search(
        r"(?:open|go\s+to|visit)?\s*@(?P<h>[a-zA-Z0-9._]+)(?:\s+on\s+youtube)?",
        raw,
        re.I,
    )
    if m and re.search(r"\byoutube\b", lower):
        return {
            "url": youtube_handle_url(m.group("h")),
            "query": m.group("h"),
            "mode": "handle",
        }

    channels = bool(re.search(r"\bchannels?\b", lower))

    # open [the] <query> channel on youtube[.com]
    m = re.search(
        r"(?:open|go\s+to|visit|browse|play|show|find|search(?:\s+for)?)\s+"
        r"(?:the\s+)?"
        r"(?P<q>.+?)\s+"
        r"channels?\s+on\s+(?:www\.)?youtube(?:\.com)?\b",
        lower,
    )
    if m:
        q = quoted_q or m.group("q").strip(" .\"'")
        q = re.sub(r"\s+channels?$", "", q).strip()
        if q:
            return {
                "url": youtube_search_url(q, channels_only=True),
                "query": q,
                "mode": "channel_search",
            }

    # open [the] <query> on youtube[.com]  (video/channel/generic search)
    m = re.search(
        r"(?:open|go\s+to|visit|browse|play|show|find|search(?:\s+for)?)\s+"
        r"(?:the\s+)?"
        r"(?P<q>.+?)\s+"
        r"on\s+(?:www\.)?youtube(?:\.com)?\b",
        lower,
    )
    if m:
        q = quoted_q or m.group("q").strip(" .\"'")
        q = re.sub(r"\s+channels?$", "", q).strip()
        # strip trailing site words accidentally captured
        q = re.sub(r"\s+on\s+(?:www\.)?youtube(?:\.com)?$", "", q).strip()
        if q and q not in {"channel", "channels", "video", "videos"}:
            return {
                "url": youtube_search_url(q, channels_only=channels),
                "query": q,
                "mode": "channel_search" if channels else "search",
            }

    # open youtube channel <query>  /  youtube search <query>
    m = re.search(
        r"(?:open|go\s+to|visit|browse)?\s*"
        r"(?:www\.)?youtube(?:\.com)?\s+"
        r"(?:channels?\s+|search(?:\s+for)?\s+|videos?\s+)?"
        r"(?P<q>.+)$",
        lower,
    )
    if m:
        q = quoted_q or m.group("q").strip(" .\"'")
        q = re.sub(r"^(?:channels?|search|for|videos?)\s+", "", q).strip()
        if q and q not in {"com", ".com"}:
            return {
                "url": youtube_search_url(q, channels_only=channels or "channel" in lower),
                "query": q,
                "mode": "channel_search" if channels else "search",
            }

    return None


def open_url(url: str, *, browser: str | None = None) -> ToolResult:
    """Open URL in default browser, or a named browser if given."""
    final = normalize_url(url)
    if not final.startswith(("http://", "https://", "file:")):
        return ToolResult(
            ok=False,
            message=f"Not a valid URL: {url!r}",
            data={"url": url},
        )

    browser_key = (browser or "").strip().lower()
    if browser_key in _BROWSER_ALIASES:
        browser_key = _BROWSER_ALIASES[browser_key]
        # Launch specific browser with URL as argument
        try:
            import platform

            if platform.system() == "Windows":
                from osagent.tools.win_launch import launch_windows_app

                return launch_windows_app(browser_key, [final])
        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                ok=False,
                message=f"Could not open in {browser_key}: {exc}",
                data={"url": final, "browser": browser_key},
            )

    try:
        ok = webbrowser.open(final, new=2)
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, message=f"Failed to open browser: {exc}")
    if not ok:
        return ToolResult(
            ok=False,
            message=f"Browser open returned false for {final}",
            data={"url": final},
        )
    return ToolResult(
        ok=True,
        message=f"Opened {final}",
        data={"url": final},
    )


def resolve_open_target(raw_target: str) -> dict[str, Any] | None:
    """
    Classify an 'open …' target.
    Returns {"kind": "url"|"search"|"app"|"unknown", ...} or None if empty.
    """
    target = (raw_target or "").strip().strip('"')
    if not target:
        return None

    lower = target.lower()
    browser: str | None = None

    # Strip trailing "in browser" / "in chrome"
    m = re.match(
        r"^(?P<body>.+?)\s+in\s+(?:the\s+)?(?P<br>browser|chrome|edge|firefox|"
        r"google chrome|microsoft edge|msedge|mozilla firefox)\s*$",
        lower,
    )
    if m:
        target = m.group("body").strip()
        lower = target.lower()
        br = m.group("br")
        if br != "browser":
            browser = br

    # General "query on site" (youtube, github, amazon, …)
    try:
        from osagent.agent.planner import plan_utterance

        planned = plan_utterance("open " + target) or plan_utterance(target)
        if planned and planned.tool_id == "web.open" and planned.args.get("url"):
            return {
                "kind": "search",
                "url": planned.args["url"],
                "browser": browser,
                "plan": planned.label,
            }
    except Exception:
        pass

    # Site alias (google, youtube, …)
    if lower in SITE_ALIASES:
        return {"kind": "url", "url": SITE_ALIASES[lower], "browser": browser}

    # Explicit URL / domain — but not "foo on youtube.com" prose
    if looks_like_url(target) and " " not in target.strip():
        return {"kind": "url", "url": normalize_url(target), "browser": browser}

    # "google search" alone already covered; "google search for cats"
    m = re.match(r"^google\s+search(?:\s+for)?\s+(.+)$", lower)
    if m:
        return {"kind": "search", "url": google_search_url(m.group(1)), "browser": browser}

    if lower in {"google search", "search google"}:
        return {"kind": "url", "url": SITE_ALIASES["google"], "browser": browser}

    return {"kind": "unknown", "target": target, "browser": browser}
