"""Cross-platform tools available on every host."""

from __future__ import annotations

import os
import platform
import shutil
import subprocess
from pathlib import Path

from osagent.tools.base import ConfirmLevel, Tool, ToolResult


def build_tools() -> list[Tool]:
    return [
        Tool(
            id="system.info",
            description="Return OS name, version, machine, and user home path.",
            parameters={"type": "object", "properties": {}},
            confirm=ConfirmLevel.NONE,
            handler=_system_info,
        ),
        Tool(
            id="files.open_path",
            description="Open a file or folder with the OS default handler.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute or relative path"},
                },
                "required": ["path"],
            },
            confirm=ConfirmLevel.NONE,
            handler=_open_path,
        ),
        Tool(
            id="files.open_recent",
            description=(
                "Find the most recently modified document(s) of a type "
                "(ppt/ppts, xls/xlsx, doc/docx, pdf, images, …) under Desktop/"
                "Documents/Downloads. open=true (default) opens the newest in "
                "the right app; open=false only lists them; open_folder=true "
                "opens the parent folder of the newest (not the file). Use for "
                "'open last ppt', 'open folder of ppt last updated', "
                "'find last updated ppts', 'show newest excels'."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "kind": {
                        "type": "string",
                        "description": "ppt, ppts, powerpoint, excel, xlsx, word, docx, pdf, …",
                    },
                    "extension": {
                        "type": "string",
                        "description": "Optional raw extension without dot, e.g. pptx",
                    },
                    "app": {
                        "type": "string",
                        "description": "Optional app override (powerpoint, excel, word, notepad)",
                    },
                    "open": {
                        "type": "boolean",
                        "description": "If false, list newest matches only (default true)",
                        "default": True,
                    },
                    "open_folder": {
                        "type": "boolean",
                        "description": (
                            "If true, open the containing folder of the newest "
                            "match instead of the file (Explorer)"
                        ),
                        "default": False,
                    },
                    "count": {
                        "type": "integer",
                        "description": "How many newest to list when open=false (default 5)",
                        "default": 5,
                    },
                },
            },
            confirm=ConfirmLevel.NONE,
            handler=_open_recent,
        ),
        Tool(
            id="files.open_named",
            description=(
                "Search user folders for files by name AND type, then either "
                "LIST matches (find/search) or OPEN the best one (open/view). "
                "Kinds: image(s), photo(s), pdf(s), ppt/ppts/powerpoint, "
                "excel/excels/spreadsheet(s), word/doc(s), text/txt, video(s), "
                "music/mp3, csv. Examples: 'find aayushi images', "
                "'find budget excels', 'open q3 ppt', 'find notes text files'."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Name fragment, e.g. aayushi or budget",
                    },
                    "kind": {
                        "type": "string",
                        "description": "image, excel, ppt, pdf, text, video, …",
                    },
                    "extension": {"type": "string"},
                    "app": {
                        "type": "string",
                        "description": "Optional: paint, excel, word, powerpoint, notepad",
                    },
                    "open": {
                        "type": "boolean",
                        "description": "true=open best match; false=list all matches",
                        "default": True,
                    },
                },
                "required": ["query"],
            },
            confirm=ConfirmLevel.NONE,
            handler=_open_named,
        ),
        Tool(
            id="files.list_dir",
            description="List entries in a directory (names only, capped).",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Directory path"},
                    "limit": {"type": "integer", "description": "Max entries", "default": 50},
                },
                "required": ["path"],
            },
            confirm=ConfirmLevel.NONE,
            handler=_list_dir,
        ),
        Tool(
            id="files.create_file",
            description="Create a text file with optional content.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string", "default": ""},
                },
                "required": ["path"],
            },
            confirm=ConfirmLevel.ASK,
            handler=_create_file,
        ),
        Tool(
            id="files.delete_path",
            description="Delete a file (not directories). Requires confirmation.",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
            confirm=ConfirmLevel.DESTRUCTIVE,
            handler=_delete_file,
        ),
        Tool(
            id="web.open",
            description=(
                "Open a URL or website in the browser. Use for google.com, "
                "youtube, any http(s) link, or a search results page. "
                "Not for launching desktop apps — use app.launch for those."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "url": {
                        "type": "string",
                        "description": "URL or site, e.g. https://google.com or google.com",
                    },
                    "browser": {
                        "type": "string",
                        "description": "Optional: chrome, edge, or firefox (default: system browser)",
                    },
                },
                "required": ["url"],
            },
            confirm=ConfirmLevel.NONE,
            handler=_web_open,
        ),
        Tool(
            id="web.search",
            description=(
                "Search the web (Google by default). Use for "
                "'google search …', 'search for …', 'look up …'."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Search query"},
                    "engine": {
                        "type": "string",
                        "description": "google (default) or bing",
                    },
                    "browser": {"type": "string"},
                },
                "required": ["query"],
            },
            confirm=ConfirmLevel.NONE,
            handler=_web_search,
        ),
        Tool(
            id="app.find",
            description=(
                "Search Desktop/Downloads/Start Menu/Program Files for an .exe "
                "or shortcut by name (fuzzy; handles typos like gnucache→gnucash). "
                "Use when launch failed or user says 'find/look for … executable'."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "App name fragment"},
                    "desktop_only": {"type": "boolean", "default": False},
                    "limit": {"type": "integer", "default": 8},
                },
                "required": ["query"],
            },
            confirm=ConfirmLevel.NONE,
            handler=_find_app,
        ),
        Tool(
            id="app.launch",
            description=(
                "Launch a desktop application by name or path. Resolves aliases "
                "(chrome, excel, …) then fuzzy-searches Desktop/Downloads/Start "
                "Menu if needed (e.g. 'gnucash', 'GnuCashPortable'). "
                "Do NOT use for websites/URLs — use web.open instead."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "target": {
                        "type": "string",
                        "description": (
                            "App name, typo-tolerant fragment, or full .exe path"
                        ),
                    },
                    "args": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional arguments",
                    },
                },
                "required": ["target"],
            },
            confirm=ConfirmLevel.NONE,
            handler=_launch_app,
        ),
    ]


def _system_info(_args: dict) -> ToolResult:
    home = str(Path.home())
    data = {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python": platform.python_version(),
        "home": home,
        "cwd": os.getcwd(),
    }
    return ToolResult(
        ok=True,
        message=(
            f"{data['system']} {data['release']} ({data['machine']}) | "
            f"home={home} | cwd={data['cwd']}"
        ),
        data=data,
    )


def _open_path(args: dict) -> ToolResult:
    path = Path(args["path"]).expanduser()
    if not path.exists():
        return ToolResult(ok=False, message=f"Path not found: {path}")
    if platform.system() == "Windows":
        os.startfile(str(path))  # type: ignore[attr-defined]
    elif platform.system() == "Darwin":
        subprocess.Popen(["open", str(path)])
    else:
        subprocess.Popen(["xdg-open", str(path)])
    return ToolResult(ok=True, message=f"Opened {path}")


def _open_recent(args: dict) -> ToolResult:
    from osagent.tools.recent_open import open_most_recent

    open_flag = args.get("open")
    open_it = True if open_flag is None else bool(open_flag)
    open_folder = bool(args.get("open_folder"))
    if open_folder:
        open_it = True
    count = int(args.get("count") or (1 if open_it else 5))
    return open_most_recent(
        kind=str(args.get("kind") or "").strip() or None,
        extension=str(args.get("extension") or "").strip() or None,
        app=str(args.get("app") or "").strip() or None,
        open_it=open_it,
        open_folder=open_folder,
        count=count,
    )


def _open_named(args: dict) -> ToolResult:
    from osagent.tools.recent_open import open_named_file

    open_flag = args.get("open")
    if open_flag is None:
        open_it = True
    else:
        open_it = bool(open_flag)
    return open_named_file(
        query=str(args.get("query") or "").strip(),
        kind=str(args.get("kind") or "").strip() or None,
        extension=str(args.get("extension") or "").strip() or None,
        app=str(args.get("app") or "").strip() or None,
        open_it=open_it,
    )


def _list_dir(args: dict) -> ToolResult:
    path = Path(args["path"]).expanduser()
    limit = int(args.get("limit") or 50)
    if not path.is_dir():
        return ToolResult(ok=False, message=f"Not a directory: {path}")
    names = sorted(p.name for p in path.iterdir())
    truncated = names[:limit]
    return ToolResult(
        ok=True,
        message=f"{len(truncated)} of {len(names)} entries",
        data={"entries": truncated, "total": len(names)},
    )


def _create_file(args: dict) -> ToolResult:
    path = Path(args["path"]).expanduser()
    path.parent.mkdir(parents=True, exist_ok=True)
    content = args.get("content") or ""
    path.write_text(str(content), encoding="utf-8")
    return ToolResult(ok=True, message=f"Created {path}")


def _delete_file(args: dict) -> ToolResult:
    path = Path(args["path"]).expanduser()
    if not path.is_file():
        return ToolResult(ok=False, message=f"Not a file: {path}")
    path.unlink()
    return ToolResult(ok=True, message=f"Deleted {path}")


def _find_app(args: dict) -> ToolResult:
    from osagent.tools.win_launch import find_apps

    query = str(args.get("query") or "").strip()
    if not query:
        return ToolResult(ok=False, message="app.find needs query=")
    desktop_only = bool(args.get("desktop_only"))
    limit = max(1, min(int(args.get("limit") or 8), 20))
    hits = find_apps(query, limit=limit, desktop_only=desktop_only, min_score=0.6)
    if not hits:
        where = "Desktop" if desktop_only else "Desktop/Downloads/Start Menu/Program Files"
        return ToolResult(
            ok=False,
            message=f"No executables matching '{query}' under {where}",
            data={"query": query, "candidates": []},
        )
    top = hits[0]
    names = ", ".join(f"{h['name']} ({h['score']})" for h in hits[:5])
    return ToolResult(
        ok=True,
        message=f"Best match: {top['name']} — also: {names}" if len(hits) > 1 else f"Found {top['name']}",
        data={"query": query, "best": top, "candidates": hits},
    )


def _web_open(args: dict) -> ToolResult:
    from osagent.tools.web_open import open_url

    return open_url(str(args["url"]), browser=args.get("browser"))


def _web_search(args: dict) -> ToolResult:
    from osagent.tools.web_open import bing_search_url, google_search_url, open_url

    query = str(args["query"]).strip()
    if not query:
        return ToolResult(ok=False, message="Empty search query")
    engine = str(args.get("engine") or "google").lower()
    url = bing_search_url(query) if engine == "bing" else google_search_url(query)
    return open_url(url, browser=args.get("browser"))


def _launch_app(args: dict) -> ToolResult:
    target = str(args.get("target") or args.get("app") or args.get("name") or "").strip()
    if not target:
        return ToolResult(
            ok=False,
            message=(
                "app.launch needs target= (e.g. excel, word, notepad, chrome). "
                "For a new spreadsheet say 'open new excel file'."
            ),
        )
    extra = [str(a) for a in (args.get("args") or [])]

    # Guard: websites must not go through app launch
    from osagent.tools.web_open import looks_like_url, open_url, resolve_open_target

    classified = resolve_open_target(target)
    if classified and classified.get("kind") in {"url", "search"}:
        return open_url(
            str(classified["url"]),
            browser=classified.get("browser") or args.get("browser"),
        )
    if looks_like_url(target):
        return open_url(target)

    # Map file-type shorthand the model sometimes sends as target
    from osagent.tools.win_launch import FILE_TYPE_APPS

    mapped = FILE_TYPE_APPS.get(target.lower())
    if mapped:
        target = mapped

    if platform.system() == "Windows":
        from osagent.tools.win_launch import launch_windows_app

        return launch_windows_app(target, extra)

    # Linux / macOS: require resolvable binary on PATH or absolute path
    path = Path(target).expanduser()
    cmd: list[str]
    if path.is_file():
        cmd = [str(path), *extra]
    else:
        resolved = shutil.which(target)
        if not resolved:
            return ToolResult(
                ok=False,
                message=f"Application not found on PATH: {target}",
                data={"target": target},
            )
        cmd = [resolved, *extra]
    try:
        subprocess.Popen(cmd, shell=False)
    except OSError as exc:
        return ToolResult(ok=False, message=f"Failed to launch {target}: {exc}")
    return ToolResult(ok=True, message=f"Launched {cmd[0]}")
