"""Find recently modified documents and open them in the right app (2-step)."""

from __future__ import annotations

import os
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from osagent.tools.base import ToolResult

# Spoken type → (extensions without dot, preferred app alias or None for default handler)
DOC_KINDS: dict[str, tuple[tuple[str, ...], str | None]] = {
    "ppt": (("pptx", "ppt", "pptm"), "powerpoint"),
    "ppts": (("pptx", "ppt", "pptm"), "powerpoint"),
    "pptx": (("pptx", "ppt", "pptm"), "powerpoint"),
    "pptm": (("pptm", "pptx", "ppt"), "powerpoint"),
    "powerpoint": (("pptx", "ppt", "pptm"), "powerpoint"),
    "presentation": (("pptx", "ppt", "pptm"), "powerpoint"),
    "presentations": (("pptx", "ppt", "pptm"), "powerpoint"),
    "deck": (("pptx", "ppt", "pptm"), "powerpoint"),
    "decks": (("pptx", "ppt", "pptm"), "powerpoint"),
    "xls": (("xlsx", "xls", "xlsm", "csv"), "excel"),
    "xlsx": (("xlsx", "xls", "xlsm"), "excel"),
    "xlsm": (("xlsm", "xlsx", "xls"), "excel"),
    "excel": (("xlsx", "xls", "xlsm"), "excel"),
    "excels": (("xlsx", "xls", "xlsm"), "excel"),
    "spreadsheet": (("xlsx", "xls", "xlsm", "csv"), "excel"),
    "spreadsheets": (("xlsx", "xls", "xlsm", "csv"), "excel"),
    "workbook": (("xlsx", "xls", "xlsm"), "excel"),
    "workbooks": (("xlsx", "xls", "xlsm"), "excel"),
    "doc": (("docx", "doc", "docm"), "word"),
    "docs": (("docx", "doc", "docm"), "word"),
    "docx": (("docx", "doc", "docm"), "word"),
    "docm": (("docm", "docx", "doc"), "word"),
    "word": (("docx", "doc", "docm"), "word"),
    "document": (("docx", "doc", "pdf", "txt"), None),
    "documents": (("docx", "doc", "pdf", "txt"), None),
    "pdf": (("pdf",), None),
    "pdfs": (("pdf",), None),
    "txt": (("txt", "log", "md"), "notepad"),
    "text": (("txt", "log", "md"), "notepad"),
    "texts": (("txt", "log", "md"), "notepad"),
    "csv": (("csv",), "excel"),
    "csvs": (("csv",), "excel"),
    # Media — None app → OS default viewer (Photos); pass app="paint" to force Paint
    "image": (("jpg", "jpeg", "png", "gif", "bmp", "webp", "heic", "tif", "tiff", "ico"), None),
    "images": (("jpg", "jpeg", "png", "gif", "bmp", "webp", "heic", "tif", "tiff"), None),
    "photo": (("jpg", "jpeg", "png", "heic", "webp"), None),
    "photos": (("jpg", "jpeg", "png", "heic", "webp"), None),
    "picture": (("jpg", "jpeg", "png", "gif", "bmp", "webp"), None),
    "pictures": (("jpg", "jpeg", "png", "gif", "bmp", "webp"), None),
    "img": (("jpg", "jpeg", "png", "gif", "bmp", "webp"), None),
    "screenshot": (("png", "jpg", "jpeg", "bmp"), None),
    "screenshots": (("png", "jpg", "jpeg", "bmp"), None),
    "jpg": (("jpg", "jpeg"), None),
    "jpeg": (("jpg", "jpeg"), None),
    "png": (("png",), None),
    "gif": (("gif",), None),
    "bmp": (("bmp",), None),
    "video": (("mp4", "mkv", "avi", "mov", "wmv", "webm", "m4v"), None),
    "videos": (("mp4", "mkv", "avi", "mov", "wmv", "webm"), None),
    "movie": (("mp4", "mkv", "avi", "mov", "wmv"), None),
    "movies": (("mp4", "mkv", "avi", "mov", "wmv"), None),
    "mp4": (("mp4",), None),
    "music": (("mp3", "wav", "flac", "m4a", "aac", "ogg"), None),
    "audio": (("mp3", "wav", "flac", "m4a", "aac", "ogg"), None),
    "song": (("mp3", "wav", "m4a", "flac"), None),
    "songs": (("mp3", "wav", "m4a", "flac"), None),
    "mp3": (("mp3",), None),
}

# Kind words used in planner / guards (image, pdf, excel, ppt, …)
FILE_KIND_WORDS = frozenset(DOC_KINDS.keys()) | {"file", "files"}


def kind_regex_alternation() -> str:
    """Longest-first regex alternation of all file-kind words."""
    words = sorted(FILE_KIND_WORDS - {"file", "files"}, key=len, reverse=True)
    return "|".join(re.escape(w) for w in words)


def _expand(p: str) -> str:
    return os.path.expandvars(p)


def _wsl_windows_home() -> Path | None:
    """Under WSL, resolve the Windows user profile (where real Desktop/Downloads live)."""
    users_dir = Path("/mnt/c/Users")
    if not users_dir.is_dir():
        return None

    def _usable(profile: Path) -> bool:
        try:
            return profile.is_dir() and (
                (profile / "Downloads").is_dir() or (profile / "Documents").is_dir()
            )
        except OSError:
            return False

    # Prefer explicit overrides
    win_user = (os.environ.get("WSL_WINDOWS_USER") or "").strip()
    if win_user:
        cand = users_dir / win_user
        if _usable(cand):
            return cand
    userprofile = (os.environ.get("USERPROFILE") or "").strip()
    if userprofile:
        norm = userprofile.replace("\\", "/")
        if re.match(r"^[A-Za-z]:/", norm):
            cand = Path("/mnt") / norm[0].lower() / norm[3:]
            if _usable(cand):
                return cand

    # Match Linux username to Windows profile (hiteshviseria ↔ hitesh.viseria)
    linux_user = Path.home().name
    al_linux = re.sub(r"[^a-z0-9]+", "", linux_user.lower())
    ranked: list[tuple[int, Path]] = []
    try:
        entries = list(users_dir.iterdir())
    except OSError:
        entries = []
    for entry in entries:
        try:
            if not entry.is_dir():
                continue
        except OSError:
            continue
        name = entry.name
        if name in {"Public", "Default", "Default User", "All Users"} or name.startswith("."):
            continue
        if not _usable(entry):
            continue
        al_win = re.sub(r"[^a-z0-9]+", "", name.lower())
        if al_linux and al_linux == al_win:
            ranked.append((0, entry))
        elif al_linux and (al_linux in al_win or al_win in al_linux):
            ranked.append((1, entry))
        else:
            ranked.append((2, entry))
    ranked.sort(key=lambda t: t[0])
    return ranked[0][1] if ranked else None


def _search_roots() -> list[Path]:
    home = Path.home()
    roots: list[Path] = [
        Path(_expand(r"%USERPROFILE%\Desktop")),
        home / "Desktop",
        home / "Documents",
        Path(_expand(r"%USERPROFILE%\OneDrive\Documents")),
        home / "Downloads",
        home / "Pictures",
        Path(_expand(r"%USERPROFILE%\OneDrive\Pictures")),
        home / "Videos",
        home / "Music",
        Path(_expand(r"%USERPROFILE%\OneDrive")),
        # Public Desktop last — often only shortcuts; keep behind user folders
        Path(_expand(r"%PUBLIC%\Desktop")),
    ]
    # WSL: also search the Windows profile (PPTs live on /mnt/c/Users/..., not ~/Downloads)
    win_home = _wsl_windows_home()
    if win_home is not None:
        roots = [
            win_home / "Desktop",
            win_home / "Documents",
            win_home / "Downloads",
            win_home / "Pictures",
            win_home / "Videos",
            win_home / "Music",
            win_home / "OneDrive",
            win_home / "OneDrive" / "Documents",
            win_home / "OneDrive" / "Pictures",
            *roots,
        ]
    out: list[Path] = []
    seen: set[str] = set()
    for r in roots:
        try:
            if r.is_dir():
                key = str(r.resolve()).lower()
                if key not in seen:
                    seen.add(key)
                    out.append(r)
        except OSError:
            continue
    return out


def _score_name_match(query: str, filename: str) -> float:
    """Higher is better for substring / token overlap in the file name."""
    q = (query or "").lower().strip()
    name = Path(filename).stem.lower()
    full = filename.lower()
    if not q:
        return 0.0
    if q == name or q == full:
        return 1.0
    if q in name or q in full:
        return 0.95
    # token overlap: "aayushi pic" vs "aayushi_holiday.jpg"
    q_tokens = [t for t in re_split_tokens(q) if len(t) > 1]
    n_tokens = set(re_split_tokens(name))
    if not q_tokens:
        return 0.0
    hit = sum(1 for t in q_tokens if t in name or any(t in n for n in n_tokens))
    return 0.5 + 0.4 * (hit / len(q_tokens)) if hit else 0.0


def re_split_tokens(s: str) -> list[str]:
    return [t for t in re.split(r"[^a-z0-9]+", s.lower()) if t]


def find_files(
    *,
    extensions: tuple[str, ...],
    name_query: str | None = None,
    limit: int = 8,
    depth: int = 6,
) -> list[dict[str, Any]]:
    """
    Find files under common user folders.
    If name_query is set, rank by name match then recency; else newest first.
    """
    exts = {"." + e.lower().lstrip(".") for e in extensions if e}
    # Empty extensions → any file (used for "last updated file" / open its folder)
    any_ext = not exts

    exclude = {".git", "node_modules", ".venv", "venv", "__pycache__", ".cache", "AppData"}
    hits: list[tuple[float, float, Path]] = []  # (name_score, mtime, path)
    q = (name_query or "").strip()

    for root in _search_roots():
        try:
            for dirpath, dirnames, filenames in os.walk(root):
                rel = Path(dirpath).relative_to(root)
                if len(rel.parts) > depth:
                    dirnames[:] = []
                    continue
                dirnames[:] = [d for d in dirnames if d not in exclude and not d.startswith(".")]
                # Bonus: files inside a folder whose name matches the query
                folder_bonus = 0.0
                if q:
                    folder_bonus = _score_name_match(q, Path(dirpath).name)

                for fn in filenames:
                    path = Path(dirpath) / fn
                    suf = path.suffix.lower()
                    if not any_ext and suf not in exts:
                        continue
                    # Skip shortcuts/tmp when scanning "any file"
                    if any_ext and suf in {".lnk", ".url", ".tmp", ".temp", ".partial"}:
                        continue
                    try:
                        mtime = path.stat().st_mtime
                    except OSError:
                        continue
                    if q:
                        score = max(
                            _score_name_match(q, fn),
                            folder_bonus * 0.9 if folder_bonus >= 0.5 else 0.0,
                        )
                        if score < 0.5:
                            continue
                    else:
                        score = 0.0
                    hits.append((score, mtime, path))
        except OSError:
            continue

    if q:
        hits.sort(key=lambda x: (-x[0], -x[1]))
    else:
        hits.sort(key=lambda x: -x[1])

    out: list[dict[str, Any]] = []
    seen: set[str] = set()
    for score, mtime, path in hits:
        key = str(path).lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(
            {
                "path": str(path),
                "name": path.name,
                "extension": path.suffix.lower(),
                "last_write": datetime.fromtimestamp(mtime).isoformat(timespec="seconds"),
                "name_score": round(score, 3),
            }
        )
        if len(out) >= limit:
            break
    return out


def find_recent_files(
    *,
    extensions: tuple[str, ...],
    limit: int = 5,
    depth: int = 6,
) -> list[dict[str, Any]]:
    """Return newest files matching extensions under common user folders."""
    return find_files(extensions=extensions, name_query=None, limit=limit, depth=depth)


def open_file_in_app(path: Path, app: str | None = None) -> ToolResult:
    """Open path with preferred app (Windows) or OS default handler."""
    if not path.is_file():
        return ToolResult(ok=False, message=f"File not found: {path}")

    if app and os.name == "nt":
        from osagent.tools.win_launch import launch_windows_app

        # Pass the document as an argument to PowerPoint / Excel / Word / etc.
        result = launch_windows_app(app, [str(path)])
        if result.ok:
            return ToolResult(
                ok=True,
                message=f"Opened {path.name} in {app}",
                data={"path": str(path), "app": app, "method": "app+file"},
            )
        # fall through to default handler

    try:
        if os.name == "nt":
            os.startfile(str(path))  # type: ignore[attr-defined]
        elif platform_is_mac():
            import subprocess

            subprocess.Popen(["open", str(path)])
        else:
            import subprocess

            subprocess.Popen(["xdg-open", str(path)])
    except OSError as exc:
        return ToolResult(ok=False, message=f"Could not open {path.name}: {exc}")

    return ToolResult(
        ok=True,
        message=f"Opened {path.name}",
        data={"path": str(path), "app": app, "method": "default"},
    )


def platform_is_mac() -> bool:
    import platform

    return platform.system() == "Darwin"


def open_folder_path(folder: Path, *, select: Path | None = None) -> ToolResult:
    """Open a directory in the OS file manager (optionally highlight a file)."""
    folder = folder.expanduser()
    select_path = select.expanduser() if select is not None else None
    if select_path is not None and not select_path.exists():
        select_path = None
    if select_path is None and not folder.is_dir():
        return ToolResult(ok=False, message=f"Not a folder: {folder}")
    try:
        import platform
        import subprocess

        system = platform.system()
        if system == "Windows":
            if select_path is not None:
                # /select, brings Explorer forward and highlights the file
                subprocess.Popen(["explorer", f"/select,{select_path}"])
            else:
                # os.startfile focuses an existing Explorer window more reliably
                # than bare `explorer <dir>` when the folder is already open
                try:
                    os.startfile(str(folder))  # type: ignore[attr-defined]
                except OSError:
                    subprocess.Popen(["explorer", str(folder)])
        elif system == "Darwin":
            if select_path is not None:
                subprocess.Popen(["open", "-R", str(select_path)])
            else:
                subprocess.Popen(["open", str(folder)])
        else:
            subprocess.Popen(["xdg-open", str(folder)])
    except OSError as exc:
        return ToolResult(ok=False, message=f"Could not open folder {folder}: {exc}")
    shown = str(folder if select_path is None else select_path.parent)
    return ToolResult(
        ok=True,
        message=f"Opened folder: {shown}",
        data={
            "path": shown,
            "file": str(select_path) if select_path is not None else None,
            "opened": True,
            "opened_folder": True,
        },
    )


def open_most_recent(
    *,
    kind: str | None = None,
    extension: str | None = None,
    app: str | None = None,
    open_it: bool = True,
    open_folder: bool = False,
    count: int = 5,
) -> ToolResult:
    """
    Step 1: find newest matching document(s).
    Step 2: open the newest in the associated app (unless open_it=False → list only).
    If open_folder=True, open the parent folder of the newest match instead.
    """
    kind_l = (kind or "").strip().lower()
    ext_l = (extension or "").strip().lower().lstrip(".")
    limit = max(1, min(int(count or 5), 30))

    extensions: tuple[str, ...] = ()
    preferred_app = app

    if kind_l in {"file", "files", "document", "documents"}:
        # Any file under common user folders (matches files.find_recent style)
        extensions = ()
        preferred_app = preferred_app or None
    elif kind_l and kind_l in DOC_KINDS:
        extensions, mapped_app = DOC_KINDS[kind_l]
        if not preferred_app:
            preferred_app = mapped_app
    elif ext_l:
        extensions = (ext_l,)
        if not preferred_app:
            for _k, (exts, mapped) in DOC_KINDS.items():
                if ext_l in exts:
                    preferred_app = mapped
                    break
    else:
        return ToolResult(
            ok=False,
            message="Need a file type (e.g. ppt, xlsx, docx) or extension=",
        )

    # ppt alone should also search pptx
    if extensions == ("ppt",):
        extensions = ("pptx", "ppt", "pptm")

    # Folder-of-file only needs the newest hit
    if open_folder:
        open_it = True
        limit = 1

    found = find_recent_files(extensions=extensions, limit=limit)
    if not found:
        return ToolResult(
            ok=False,
            message=(
                f"No recent {', '.join('.' + e for e in extensions)} files "
                "under Desktop/Documents/Downloads/Pictures"
                + (" (incl. Windows home via /mnt/c/Users)" if _wsl_windows_home() else "")
            ),
            data={"extensions": list(extensions), "candidates": []},
        )

    if not open_it:
        lines = []
        for i, hit in enumerate(found, 1):
            p = Path(str(hit.get("path") or ""))
            when = hit.get("last_write") or ""
            lines.append(f"{i}. {p.name}  ({when})")
        label = kind_l or ("." + ext_l if ext_l else "files")
        return ToolResult(
            ok=True,
            message=f"{len(found)} newest {label}:\n" + "\n".join(lines),
            data={
                "candidates": found,
                "kind": kind_l or ext_l,
                "opened": False,
            },
        )

    best = found[0]
    path = Path(str(best["path"]))

    if open_folder:
        folder = path.parent
        opened = open_folder_path(folder, select=path)
        opened.data = {
            **(opened.data or {}),
            "candidates": found,
            "kind": kind_l or ext_l,
            "file": str(path),
            "last_write": best.get("last_write"),
            "opened": opened.ok,
            "opened_folder": True,
        }
        if opened.ok:
            opened.message = (
                f"Opened folder in Explorer: {folder} "
                f"(selected {path.name}, modified {best.get('last_write')})"
            )
        return opened

    opened = open_file_in_app(path, preferred_app)
    opened.data = {
        **(opened.data or {}),
        "candidates": found,
        "kind": kind_l or ext_l,
        "last_write": best.get("last_write"),
        "opened": opened.ok,
    }
    if opened.ok:
        opened.message = (
            f"Opened latest {path.suffix.lstrip('.')} file: {path.name} "
            f"({best.get('last_write')})"
            + (f" in {preferred_app}" if preferred_app else "")
        )
    return opened


def resolve_kind(kind: str | None, extension: str | None = None) -> tuple[tuple[str, ...], str | None]:
    kind_l = (kind or "").strip().lower()
    ext_l = (extension or "").strip().lower().lstrip(".")
    if kind_l in DOC_KINDS:
        return DOC_KINDS[kind_l]
    if ext_l:
        for _k, (exts, app) in DOC_KINDS.items():
            if ext_l in exts:
                return exts if len(exts) > 1 else (ext_l,), app
        return (ext_l,), None
    return (), None


def open_named_file(
    *,
    query: str,
    kind: str | None = None,
    extension: str | None = None,
    app: str | None = None,
    open_it: bool = True,
) -> ToolResult:
    """
    Find files whose names match query (+ type), optionally open the best hit.
    Example: query='aayushi', kind='image' → search *.jpg/png… then open in Paint.
    """
    q = (query or "").strip()
    if not q:
        return ToolResult(ok=False, message="Need a name to search for")

    extensions, mapped_app = resolve_kind(kind, extension)
    if not extensions:
        # No kind → search common document+media extensions
        extensions = (
            "jpg",
            "jpeg",
            "png",
            "gif",
            "bmp",
            "webp",
            "pdf",
            "docx",
            "xlsx",
            "pptx",
            "txt",
            "mp4",
            "mp3",
        )
        mapped_app = None

    preferred = app or mapped_app
    # List mode: return more candidates; open mode: still keep a short shortlist
    limit = 20 if not open_it else 8
    found = find_files(extensions=extensions, name_query=q, limit=limit)
    if not found:
        kind_label = kind or extension or "file"
        return ToolResult(
            ok=False,
            message=(
                f"No {kind_label} matching '{q}' under "
                "Desktop/Documents/Downloads/Pictures"
            ),
            data={"query": q, "kind": kind, "candidates": []},
        )

    best = found[0]
    path = Path(str(best["path"]))
    if not open_it:
        lines = [
            f"{i}. {c['name']}  ({c.get('last_write', '?')})  {c['path']}"
            for i, c in enumerate(found, 1)
        ]
        msg = f"Found {len(found)} file(s) matching '{q}':\n" + "\n".join(lines)
        return ToolResult(
            ok=True,
            message=msg,
            data={"query": q, "best": best, "candidates": found, "listed": True},
        )

    opened = open_file_in_app(path, preferred)
    # If paint fails, default viewer still tried inside open_file_in_app
    opened.data = {
        **(opened.data or {}),
        "query": q,
        "kind": kind,
        "candidates": found,
        "last_write": best.get("last_write"),
    }
    if opened.ok:
        opened.message = (
            f"Opened {path.name} (matched '{q}')"
            + (f" in {preferred}" if preferred else " with default viewer")
        )
    return opened
