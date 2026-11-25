"""Resolve and launch Windows applications by friendly name or path."""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from difflib import SequenceMatcher
from pathlib import Path

from osagent.tools.base import ToolResult

# "open new xls file" / blank document phrases → app alias key in ALIASES
FILE_TYPE_APPS: dict[str, str] = {
    "excel": "excel",
    "xls": "excel",
    "xlsx": "excel",
    "spreadsheet": "excel",
    "workbook": "excel",
    "word": "word",
    "doc": "word",
    "docx": "word",
    "powerpoint": "powerpoint",
    "ppt": "powerpoint",
    "pptx": "powerpoint",
    "presentation": "powerpoint",
    "notepad": "notepad",
    "text": "notepad",
    "txt": "notepad",
    "text file": "notepad",
    "blank text file": "notepad",
    "new text file": "notepad",
}

# Friendly names users / models say -> executable names registered in App Paths
ALIASES: dict[str, str] = {
    "edge": "msedge.exe",
    "microsoft edge": "msedge.exe",
    "msedge": "msedge.exe",
    "chrome": "chrome.exe",
    "google chrome": "chrome.exe",
    "google-chrome": "chrome.exe",
    "firefox": "firefox.exe",
    "mozilla firefox": "firefox.exe",
    "word": "WINWORD.EXE",
    "ms word": "WINWORD.EXE",
    "microsoft word": "WINWORD.EXE",
    "winword": "WINWORD.EXE",
    "excel": "EXCEL.EXE",
    "microsoft excel": "EXCEL.EXE",
    "powerpoint": "POWERPNT.EXE",
    "ppt": "POWERPNT.EXE",
    "microsoft powerpoint": "POWERPNT.EXE",
    "outlook": "OUTLOOK.EXE",
    "microsoft outlook": "OUTLOOK.EXE",
    "onenote": "ONENOTE.EXE",
    "notepad": "notepad.exe",
    "calculator": "calc.exe",
    "calc": "calc.exe",
    "paint": "mspaint.exe",
    "mspaint": "mspaint.exe",
    "cmd": "cmd.exe",
    "command prompt": "cmd.exe",
    "powershell": "powershell.exe",
    "pwsh": "pwsh.exe",
    "explorer": "explorer.exe",
    "file explorer": "explorer.exe",
    "terminal": "wt.exe",
    "windows terminal": "wt.exe",
    "spotify": "spotify.exe",
    "discord": "Discord.exe",
    "slack": "slack.exe",
    "teams": "ms-teams.exe",
    "microsoft teams": "ms-teams.exe",
    "vscode": "Code.exe",
    "vs code": "Code.exe",
    "visual studio code": "Code.exe",
    "code": "Code.exe",
    "gnucash": "GnuCashPortable.exe",
    "gnu cash": "GnuCashPortable.exe",
    "gnucache": "GnuCashPortable.exe",  # common misspelling
}

# Extra filesystem guesses when App Paths is missing
COMMON_PATHS: dict[str, tuple[str, ...]] = {
    "chrome.exe": (
        r"%ProgramFiles%\Google\Chrome\Application\chrome.exe",
        r"%ProgramFiles(x86)%\Google\Chrome\Application\chrome.exe",
        r"%LocalAppData%\Google\Chrome\Application\chrome.exe",
    ),
    "msedge.exe": (
        r"%ProgramFiles(x86)%\Microsoft\Edge\Application\msedge.exe",
        r"%ProgramFiles%\Microsoft\Edge\Application\msedge.exe",
    ),
    "firefox.exe": (
        r"%ProgramFiles%\Mozilla Firefox\firefox.exe",
        r"%ProgramFiles(x86)%\Mozilla Firefox\firefox.exe",
    ),
    "WINWORD.EXE": (
        r"%ProgramFiles%\Microsoft Office\root\Office16\WINWORD.EXE",
        r"%ProgramFiles(x86)%\Microsoft Office\root\Office16\WINWORD.EXE",
        r"%ProgramFiles%\Microsoft Office\Office16\WINWORD.EXE",
        r"%ProgramFiles%\Microsoft Office\Office15\WINWORD.EXE",
    ),
    "EXCEL.EXE": (
        r"%ProgramFiles%\Microsoft Office\root\Office16\EXCEL.EXE",
        r"%ProgramFiles(x86)%\Microsoft Office\root\Office16\EXCEL.EXE",
    ),
    "POWERPNT.EXE": (
        r"%ProgramFiles%\Microsoft Office\root\Office16\POWERPNT.EXE",
        r"%ProgramFiles(x86)%\Microsoft Office\root\Office16\POWERPNT.EXE",
    ),
    "OUTLOOK.EXE": (
        r"%ProgramFiles%\Microsoft Office\root\Office16\OUTLOOK.EXE",
        r"%ProgramFiles(x86)%\Microsoft Office\root\Office16\OUTLOOK.EXE",
    ),
    "Code.exe": (
        r"%LocalAppData%\Programs\Microsoft VS Code\Code.exe",
        r"%ProgramFiles%\Microsoft VS Code\Code.exe",
    ),
    "Discord.exe": (r"%LocalAppData%\Discord\Update.exe",),
    "spotify.exe": (
        r"%AppData%\Spotify\Spotify.exe",
        r"%LocalAppData%\Microsoft\WindowsApps\Spotify.exe",
    ),
    "GnuCashPortable.exe": (
        r"%USERPROFILE%\Downloads\GnuCashPortable\GnuCashPortable.exe",
        r"%USERPROFILE%\Desktop\GnuCashPortable\GnuCashPortable.exe",
        r"%USERPROFILE%\Desktop\GnuCashPortable.exe",
    ),
}

# Noise executables we never auto-pick as the "app"
_SKIP_EXE_NAMES = {
    "uninstall.exe",
    "unins000.exe",
    "setup.exe",
    "installer.exe",
    "update.exe",
    "updater.exe",
    "crashreporter.exe",
    "helper.exe",
    "vcredist",
}


def _expand(path: str) -> str:
    return os.path.expandvars(path)


def _app_paths_lookup(exe_name: str) -> Path | None:
    try:
        import winreg
    except ImportError:
        return None

    candidates = [exe_name]
    if not exe_name.lower().endswith(".exe"):
        candidates.append(f"{exe_name}.exe")

    roots = (
        (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
        (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows\CurrentVersion\App Paths"),
        (
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\App Paths",
        ),
    )
    for hive, base in roots:
        for name in candidates:
            try:
                with winreg.OpenKey(hive, f"{base}\\{name}") as key:
                    value, _ = winreg.QueryValueEx(key, "")
            except OSError:
                continue
            path = Path(_expand(str(value).strip().strip('"')))
            if path.is_file():
                return path
    return None


def _common_path_lookup(exe_name: str) -> Path | None:
    for pattern in COMMON_PATHS.get(exe_name, ()):
        path = Path(_expand(pattern))
        if path.is_file():
            return path
    return None


def _which_lookup(exe_name: str) -> Path | None:
    found = shutil.which(exe_name)
    if found:
        return Path(found)
    if not exe_name.lower().endswith(".exe"):
        found = shutil.which(f"{exe_name}.exe")
        if found:
            return Path(found)
    return None


def normalize_target(raw: str) -> str:
    text = raw.strip().strip('"')
    key = text.lower()
    if key in ALIASES:
        return ALIASES[key]
    stem = Path(text).stem.lower()
    if stem in ALIASES:
        return ALIASES[stem]
    if text.lower() in {v.lower() for v in ALIASES.values()}:
        for v in ALIASES.values():
            if v.lower() == text.lower():
                return v
    return text


def _alnum(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def _score_name(query: str, candidate: str) -> float:
    """Higher is better. Typo-tolerant (gnucache ≈ gnucash)."""
    q = query.lower().strip()
    c = candidate.lower().strip()
    if not q or not c:
        return 0.0
    stem = Path(c).stem.lower() if "." in c else c
    qa, ca = _alnum(q), _alnum(stem)
    if qa == ca:
        return 1.0
    if qa and ca and (qa in ca or ca in qa):
        return 0.92
    # soft phonetic-ish: cash/cache
    q2 = qa.replace("cache", "cash").replace("cashe", "cash")
    c2 = ca.replace("cache", "cash").replace("cashe", "cash")
    if q2 and c2 and (q2 == c2 or q2 in c2 or c2 in q2):
        return 0.9
    ratio = SequenceMatcher(None, qa, ca).ratio() if qa and ca else 0.0
    # prefer names that start similarly
    prefix = 0.08 if qa and ca and ca.startswith(qa[: max(3, len(qa) // 2)]) else 0.0
    return min(1.0, ratio + prefix)


def _search_roots(*, desktop_only: bool = False) -> list[tuple[Path, int]]:
    """(root, max_depth) pairs."""
    home = Path.home()
    desktop = Path(_expand(r"%USERPROFILE%\Desktop"))
    public_desktop = Path(_expand(r"%PUBLIC%\Desktop"))
    downloads = home / "Downloads"
    start_user = Path(
        _expand(r"%APPDATA%\Microsoft\Windows\Start Menu\Programs")
    )
    start_common = Path(
        _expand(r"%ProgramData%\Microsoft\Windows\Start Menu\Programs")
    )
    local_programs = Path(_expand(r"%LOCALAPPDATA%\Programs"))

    roots: list[tuple[Path, int]] = [
        (desktop, 4),
        (public_desktop, 3),
    ]
    if desktop_only:
        return [(p, d) for p, d in roots if p.is_dir()]

    roots.extend(
        [
            (downloads, 4),
            (start_user, 5),
            (start_common, 5),
            (local_programs, 3),
            (Path(_expand(r"%ProgramFiles%")), 2),
            (Path(_expand(r"%ProgramFiles(x86)%")), 2),
        ]
    )
    return [(p, d) for p, d in roots if p.is_dir()]


def _is_skipped_exe(path: Path) -> bool:
    name = path.name.lower()
    if name in _SKIP_EXE_NAMES:
        return True
    return any(name.startswith(s.rstrip(".exe")) for s in _SKIP_EXE_NAMES if len(s) > 4)


def find_apps(
    query: str,
    *,
    limit: int = 8,
    desktop_only: bool = False,
    min_score: float = 0.72,
    use_inventory: bool = True,
) -> list[dict]:
    """
    Fuzzy-find .exe / .lnk matching query under Desktop, Downloads, Start Menu, etc.
    Returns list of {path, name, score, kind}. Prefers inventory when available.
    """
    q = (query or "").strip()
    if not q:
        return []

    if use_inventory and not desktop_only:
        try:
            from osagent.inventory import get_inventory

            inv_hits = get_inventory().lookup_app(q, limit=limit)
            file_hits = [
                {
                    "path": h["path"],
                    "name": h.get("name") or Path(str(h["path"])).name,
                    "score": h.get("score", 0.8),
                    "kind": h.get("kind") or "exe",
                    "source": "inventory",
                }
                for h in inv_hits
                if h.get("path") and Path(str(h["path"])).is_file()
            ]
            if file_hits and float(file_hits[0].get("score") or 0) >= max(min_score, 0.85):
                return file_hits[:limit]
            # keep inventory hits and merge with disk scan below
            seed = {str(h["path"]).lower(): h for h in file_hits}
        except Exception:
            seed = {}
    else:
        seed = {}

    hits: dict[str, dict] = dict(seed)

    def consider(path: Path, kind: str) -> None:
        if not path.is_file():
            return
        if kind == "exe" and _is_skipped_exe(path):
            return
        score = max(
            _score_name(q, path.name),
            _score_name(q, path.stem),
            _score_name(q, path.parent.name),
        )
        stem_l = path.stem.lower()
        parent_l = path.parent.name.lower()
        # Prefer extracted portable launcher over the downloaded installer zip/exe
        if stem_l.endswith("portable") and parent_l != "downloads":
            score = min(1.0, score + 0.08)
        elif "portable" in stem_l and score >= 0.7:
            score = min(1.0, score + 0.03)
        # Demote versioned installers sitting in Downloads (gnucash-portable-5-14.exe)
        if parent_l == "downloads" and re.search(r"-\d", stem_l):
            score -= 0.12
        if stem_l.endswith("-cli") or stem_l.endswith("_cli") or stem_l.endswith("cli"):
            score -= 0.1
        if "\\bin\\" in str(path).lower() or "/bin/" in str(path).lower():
            score -= 0.08
        if score < min_score:
            return
        key = str(path.resolve()).lower()
        prev = hits.get(key)
        if prev is None or score > float(prev["score"]):
            hits[key] = {
                "path": str(path),
                "name": path.name,
                "score": round(score, 3),
                "kind": kind,
            }

    # Also score known aliases quickly
    for alias, exe in ALIASES.items():
        sc = max(_score_name(q, alias), _score_name(q, exe))
        if sc >= min_score:
            resolved = resolve_executable_strict(alias)
            if resolved:
                consider(resolved, "exe")

    for root, depth in _search_roots(desktop_only=desktop_only):
        try:
            for dirpath, dirnames, filenames in os.walk(root):
                rel = Path(dirpath).relative_to(root)
                if len(rel.parts) > depth:
                    dirnames[:] = []
                    continue
                # prune huge / irrelevant trees
                dirnames[:] = [
                    d
                    for d in dirnames
                    if d.lower()
                    not in {
                        "node_modules",
                        ".git",
                        "__pycache__",
                        "windows",
                        "winsxs",
                        "system32",
                        "syswow64",
                    }
                ]
                for fn in filenames:
                    low = fn.lower()
                    if low.endswith(".exe"):
                        consider(Path(dirpath) / fn, "exe")
                    elif low.endswith(".lnk"):
                        consider(Path(dirpath) / fn, "lnk")
        except OSError:
            continue

    ranked = sorted(hits.values(), key=lambda x: (-float(x["score"]), x["name"].lower()))
    return ranked[: max(1, min(limit, 20))]


def resolve_executable_strict(raw: str) -> Path | None:
    """Exact/alias resolution only (no fuzzy filesystem crawl)."""
    target = normalize_target(raw)
    path = Path(_expand(target)).expanduser()
    if path.is_file():
        return path

    name = path.name if path.suffix else target
    if not name.lower().endswith(".exe") and "\\" not in name and "/" not in name:
        name = f"{name}.exe"

    for resolver in (_app_paths_lookup, _common_path_lookup, _which_lookup):
        found = resolver(name)
        if found is not None:
            return found
        found = resolver(target if target.lower().endswith(".exe") else f"{target}.exe")
        if found is not None:
            return found
    return None


def resolve_executable(raw: str) -> Path | None:
    found = resolve_executable_strict(raw)
    if found is not None:
        return found
    # Inventory first (no filesystem crawl)
    try:
        from osagent.inventory import get_inventory

        for hit in get_inventory().lookup_app(raw, limit=3):
            p = hit.get("path")
            if p and hit.get("kind") in {None, "exe", "lnk"} and Path(str(p)).is_file():
                return Path(str(p))
    except Exception:
        pass
    # Fuzzy filesystem fallback
    matches = find_apps(raw, limit=3, min_score=0.78)
    if not matches:
        matches = find_apps(raw, limit=3, min_score=0.65)
    if matches:
        return Path(str(matches[0]["path"]))
    return None


def _remember_launch(query: str, path: Path, *, ok: bool) -> None:
    try:
        from osagent.inventory import get_inventory

        get_inventory().record_launch(
            query=query,
            path=str(path),
            name=path.name,
            ok=ok,
        )
    except Exception:
        pass


def _start_path(path: Path, extra: list[str] | None = None) -> ToolResult:
    extra = list(extra or [])
    try:
        if path.suffix.lower() == ".lnk" and not extra:
            # Shell-execute shortcut
            os.startfile(str(path))  # type: ignore[attr-defined]
        else:
            subprocess.Popen(
                [str(path), *extra] if path.suffix.lower() == ".exe" else [str(path)],
                cwd=str(path.parent) if path.suffix.lower() == ".exe" else None,
                shell=False,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
    except OSError as exc:
        # Fallback: cmd start
        completed = subprocess.run(
            ["cmd.exe", "/c", "start", "", str(path), *extra],
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            return ToolResult(
                ok=False,
                message=f"Failed to start {path}: {exc}",
                data={"resolved": str(path)},
            )
    return ToolResult(
        ok=True,
        message=f"Launched {path.name}",
        data={"resolved": str(path)},
    )


def launch_windows_app(target: str, args: list[str] | None = None) -> ToolResult:
    extra = list(args or [])
    raw = (target or "").strip()
    if not raw:
        return ToolResult(ok=False, message="No app name given")

    # Direct path
    direct = Path(_expand(raw)).expanduser()
    if direct.is_file():
        result = _start_path(direct, extra)
        result.data = {**(result.data or {}), "target": raw, "method": "path"}
        _remember_launch(raw, direct, ok=result.ok)
        return result

    # Inventory hit (learned map) before alias/fuzzy crawl
    try:
        from osagent.inventory import get_inventory

        for hit in get_inventory().lookup_app(raw, limit=1):
            p = hit.get("path")
            if p and Path(str(p)).is_file():
                path = Path(str(p))
                result = _start_path(path, extra)
                result.data = {
                    **(result.data or {}),
                    "target": raw,
                    "method": "inventory",
                    "score": hit.get("score"),
                }
                _remember_launch(raw, path, ok=result.ok)
                return result
    except Exception:
        pass

    strict = resolve_executable_strict(raw)
    if strict is not None:
        result = _start_path(strict, extra)
        result.data = {**(result.data or {}), "target": raw, "method": "alias"}
        _remember_launch(raw, strict, ok=result.ok)
        return result

    # Fuzzy search — prefer Desktop if user said so
    desktop_only = "desktop" in raw.lower()
    query = raw
    for noise in (
        "on desktop",
        "from desktop",
        "on the desktop",
        "executable",
        "exe",
        "app",
        "application",
        "program",
        "and open it",
        "and launch it",
        "and run it",
        "look for",
        "find",
        "search for",
        "open",
        "launch",
        "start",
        "run",
    ):
        query = re.sub(rf"\b{re.escape(noise)}\b", " ", query, flags=re.I)
    query = re.sub(r"\s+", " ", query).strip(" .")

    matches = find_apps(query or raw, limit=5, desktop_only=desktop_only, min_score=0.7)
    if not matches and not desktop_only:
        matches = find_apps(query or raw, limit=5, min_score=0.6)

    if matches:
        best = matches[0]
        result = _start_path(Path(str(best["path"])), extra)
        others = [m["name"] for m in matches[1:3]]
        msg = result.message
        if others:
            msg += f" (also found: {', '.join(others)})"
        method = "inventory" if best.get("source") == "inventory" else "fuzzy"
        if result.ok:
            try:
                from osagent.inventory import get_inventory

                get_inventory().record_launch(
                    query=query or raw,
                    path=str(best["path"]),
                    name=str(best.get("name") or ""),
                    ok=True,
                )
            except Exception:
                pass
        return ToolResult(
            ok=result.ok,
            message=msg if result.ok else result.message,
            data={
                "target": raw,
                "query": query,
                "resolved": best["path"],
                "score": best["score"],
                "candidates": matches,
                "method": method,
            },
        )

    # Last resort: ShellExecute via `start`
    normalized = normalize_target(raw)
    completed = subprocess.run(
        ["cmd.exe", "/c", "start", "", normalized, *extra],
        capture_output=True,
        text=True,
        shell=False,
        check=False,
    )
    err = (completed.stderr or completed.stdout or "").strip()
    if completed.returncode != 0:
        return ToolResult(
            ok=False,
            message=(
                f"Could not find '{raw}'. Searched Desktop, Downloads, Start Menu, "
                f"and Program Files. Try a fuller name or path."
                + (f" ({err})" if err else "")
            ),
            data={"target": raw, "normalized": normalized, "candidates": []},
        )

    return ToolResult(
        ok=True,
        message=f"Started '{normalized}' via Windows shell",
        data={"target": raw, "normalized": normalized, "method": "start"},
    )
