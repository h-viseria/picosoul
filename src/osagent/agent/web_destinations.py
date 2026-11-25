"""Catalog of web destinations for 'open/search X on <site>' planning."""

from __future__ import annotations

import re
import urllib.parse
from dataclasses import dataclass
from typing import Callable


def _q(s: str) -> str:
    return urllib.parse.quote_plus((s or "").strip())


@dataclass(frozen=True)
class WebDestination:
    id: str
    home: str
    aliases: tuple[str, ...]
    # Build a search URL; entity may be channel|video|repo|user|product|article|…
    search: Callable[[str, str | None], str]
    # Entity words that specialize the search
    entities: tuple[str, ...] = ()


def _youtube_search(query: str, entity: str | None) -> str:
    q = _q(query)
    if entity in {"channel", "channels"}:
        return f"https://www.youtube.com/results?search_query={q}&sp=EgIQAg%3D%3D"
    if entity in {"video", "videos", "clip", "clips"}:
        return f"https://www.youtube.com/results?search_query={q}&sp=EgIQAQ%3D%3D"
    return f"https://www.youtube.com/results?search_query={q}"


def _google_search(query: str, entity: str | None) -> str:
    return f"https://www.google.com/search?q={_q(query)}"


def _bing_search(query: str, entity: str | None) -> str:
    return f"https://www.bing.com/search?q={_q(query)}"


def _github_search(query: str, entity: str | None) -> str:
    if entity in {"user", "users", "profile", "profiles"}:
        return f"https://github.com/search?q={_q(query)}&type=users"
    if entity in {"repo", "repos", "repository", "repositories"}:
        return f"https://github.com/search?q={_q(query)}&type=repositories"
    return f"https://github.com/search?q={_q(query)}&type=repositories"


def _amazon_search(query: str, entity: str | None) -> str:
    return f"https://www.amazon.com/s?k={_q(query)}"


def _reddit_search(query: str, entity: str | None) -> str:
    if entity in {"subreddit", "community", "communities"}:
        return f"https://www.reddit.com/subreddits/search/?q={_q(query)}"
    return f"https://www.reddit.com/search/?q={_q(query)}"


def _wikipedia_search(query: str, entity: str | None) -> str:
    return f"https://en.wikipedia.org/wiki/Special:Search?search={_q(query)}"


def _twitter_search(query: str, entity: str | None) -> str:
    if entity in {"user", "users", "profile", "profiles", "account", "accounts"}:
        return f"https://x.com/search?q={_q(query)}&f=user"
    return f"https://x.com/search?q={_q(query)}"


def _linkedin_search(query: str, entity: str | None) -> str:
    if entity in {"job", "jobs"}:
        return f"https://www.linkedin.com/jobs/search/?keywords={_q(query)}"
    if entity in {"company", "companies"}:
        return f"https://www.linkedin.com/search/results/companies/?keywords={_q(query)}"
    return f"https://www.linkedin.com/search/results/all/?keywords={_q(query)}"


def _maps_search(query: str, entity: str | None) -> str:
    return f"https://www.google.com/maps/search/{_q(query)}"


def _netflix_search(query: str, entity: str | None) -> str:
    return f"https://www.netflix.com/search?q={_q(query)}"


def _facebook_search(query: str, entity: str | None) -> str:
    return f"https://www.facebook.com/search/top/?q={_q(query)}"


def _stackoverflow_search(query: str, entity: str | None) -> str:
    return f"https://stackoverflow.com/search?q={_q(query)}"


def _duckduckgo_search(query: str, entity: str | None) -> str:
    return f"https://duckduckgo.com/?q={_q(query)}"


DESTINATIONS: tuple[WebDestination, ...] = (
    WebDestination(
        "youtube",
        "https://www.youtube.com",
        ("youtube", "youtube.com", "yt"),
        _youtube_search,
        ("channel", "channels", "video", "videos", "clip", "clips"),
    ),
    WebDestination(
        "google",
        "https://www.google.com",
        ("google", "google.com", "google search"),
        _google_search,
    ),
    WebDestination(
        "bing",
        "https://www.bing.com",
        ("bing", "bing.com"),
        _bing_search,
    ),
    WebDestination(
        "github",
        "https://github.com",
        ("github", "github.com", "gh"),
        _github_search,
        ("repo", "repos", "repository", "repositories", "user", "users", "profile"),
    ),
    WebDestination(
        "amazon",
        "https://www.amazon.com",
        ("amazon", "amazon.com"),
        _amazon_search,
        ("product", "products", "item", "items"),
    ),
    WebDestination(
        "reddit",
        "https://www.reddit.com",
        ("reddit", "reddit.com"),
        _reddit_search,
        ("subreddit", "community", "communities"),
    ),
    WebDestination(
        "wikipedia",
        "https://wikipedia.org",
        ("wikipedia", "wikipedia.org", "wiki"),
        _wikipedia_search,
        ("article", "articles", "page", "pages"),
    ),
    WebDestination(
        "twitter",
        "https://x.com",
        ("twitter", "twitter.com", "x.com"),
        _twitter_search,
        ("user", "users", "profile", "profiles", "account", "accounts"),
    ),
    WebDestination(
        "linkedin",
        "https://www.linkedin.com",
        ("linkedin", "linkedin.com"),
        _linkedin_search,
        ("job", "jobs", "company", "companies", "profile", "profiles"),
    ),
    WebDestination(
        "maps",
        "https://maps.google.com",
        ("maps", "google maps", "googlemaps"),
        _maps_search,
        ("place", "places", "location", "locations"),
    ),
    WebDestination(
        "netflix",
        "https://www.netflix.com",
        ("netflix", "netflix.com"),
        _netflix_search,
        ("show", "shows", "movie", "movies", "series"),
    ),
    WebDestination(
        "facebook",
        "https://www.facebook.com",
        ("facebook", "facebook.com", "fb"),
        _facebook_search,
        ("page", "pages", "profile", "profiles", "group", "groups"),
    ),
    WebDestination(
        "stackoverflow",
        "https://stackoverflow.com",
        ("stackoverflow", "stackoverflow.com", "stack overflow"),
        _stackoverflow_search,
    ),
    WebDestination(
        "duckduckgo",
        "https://duckduckgo.com",
        ("duckduckgo", "ddg"),
        _duckduckgo_search,
    ),
)


def site_home_aliases() -> dict[str, str]:
    """Flat alias → homepage map (for simple 'open youtube')."""
    out: dict[str, str] = {}
    for d in DESTINATIONS:
        out[d.id] = d.home
        for a in d.aliases:
            out[a.lower()] = d.home
    return out


def match_destination(site_text: str) -> WebDestination | None:
    t = re.sub(r"^www\.", "", (site_text or "").strip().lower())
    t = t.rstrip("/").strip()
    best: WebDestination | None = None
    best_len = -1
    for d in DESTINATIONS:
        candidates = {d.id.lower(), *(a.lower() for a in d.aliases)}
        for al in candidates:
            hit = False
            if t == al or t == f"{al}.com":
                hit = True
            elif len(al) > 2 and (t.startswith(al + ".") or t.endswith("." + al)):
                hit = True
            elif len(al) > 3 and al in t.split():  # multi-word site phrase
                hit = True
            if hit and len(al) > best_len:
                best = d
                best_len = len(al)
    return best


def unknown_site_search(query: str, site: str) -> str:
    """Fallback: Google site: search for an unrecognized domain/site name."""
    site_clean = re.sub(r"^https?://", "", site.strip().lower())
    site_clean = re.sub(r"^www\.", "", site_clean).split("/")[0]
    if "." in site_clean:
        return f"https://www.google.com/search?q={_q(query + ' site:' + site_clean)}"
    return f"https://www.google.com/search?q={_q(query + ' ' + site_clean)}"


# Entity words that may appear before "on <site>"
ENTITY_WORDS = frozenset(
    {
        "channel",
        "channels",
        "video",
        "videos",
        "clip",
        "clips",
        "repo",
        "repos",
        "repository",
        "repositories",
        "user",
        "users",
        "profile",
        "profiles",
        "account",
        "accounts",
        "product",
        "products",
        "item",
        "items",
        "subreddit",
        "community",
        "communities",
        "article",
        "articles",
        "page",
        "pages",
        "job",
        "jobs",
        "company",
        "companies",
        "place",
        "places",
        "location",
        "locations",
        "show",
        "shows",
        "movie",
        "movies",
        "series",
        "group",
        "groups",
    }
)
