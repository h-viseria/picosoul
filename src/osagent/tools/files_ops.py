"""Remaining files.* tools: copy/move/rename/compress/metadata/text/recycle."""

from __future__ import annotations

import os
import shutil
import subprocess
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from osagent.tools.base import ConfirmLevel, Tool, ToolResult


def build_tools() -> list[Tool]:
    return [
        Tool(
            id="files.copy",
            description="Copy a file or folder to a destination path.",
            parameters={
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "destination": {"type": "string"},
                    "overwrite": {"type": "boolean", "default": False},
                },
                "required": ["source", "destination"],
            },
            confirm=ConfirmLevel.ASK,
            handler=_copy,
        ),
        Tool(
            id="files.move",
            description="Move a file or folder to a destination path.",
            parameters={
                "type": "object",
                "properties": {
                    "source": {"type": "string"},
                    "destination": {"type": "string"},
                    "overwrite": {"type": "boolean", "default": False},
                },
                "required": ["source", "destination"],
            },
            confirm=ConfirmLevel.ASK,
            handler=_move,
        ),
        Tool(
            id="files.rename",
            description="Rename a file or folder (new_name can be a basename or full path).",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "new_name": {"type": "string"},
                },
                "required": ["path", "new_name"],
            },
            confirm=ConfirmLevel.ASK,
            handler=_rename,
        ),
        Tool(
            id="files.get_metadata",
            description="Read type, size, created/modified dates for a path.",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
            confirm=ConfirmLevel.NONE,
            handler=_get_metadata,
        ),
        Tool(
            id="files.get_properties",
            description="Inspect hidden, read-only, system, archive attributes.",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
            confirm=ConfirmLevel.NONE,
            handler=_get_properties,
        ),
        Tool(
            id="files.open_with",
            description="Open a file with a specified application (alias or exe path).",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "app": {"type": "string", "description": "notepad, excel, chrome, or exe path"},
                },
                "required": ["path", "app"],
            },
            confirm=ConfirmLevel.NONE,
            handler=_open_with,
        ),
        Tool(
            id="files.read_text",
            description="Read a text file (utf-8/latin-1 fallback). Cap size for safety.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "max_chars": {"type": "integer", "default": 50000},
                },
                "required": ["path"],
            },
            confirm=ConfirmLevel.NONE,
            handler=_read_text,
        ),
        Tool(
            id="files.write_text",
            description="Create or overwrite a text file with content.",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                    "append": {"type": "boolean", "default": False},
                },
                "required": ["path", "content"],
            },
            confirm=ConfirmLevel.ASK,
            handler=_write_text,
        ),
        Tool(
            id="files.search_content",
            description=(
                "Search inside text-like files under a folder for a string "
                "(not just filenames). Scoped and depth-limited."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "query": {"type": "string"},
                    "path": {
                        "type": "string",
                        "description": "Root folder (default: Documents)",
                    },
                    "extensions": {
                        "type": "string",
                        "description": "Comma list e.g. txt,md,py,csv,log",
                        "default": "txt,md,py,csv,log,json,xml,html,cs,js,ts",
                    },
                    "limit": {"type": "integer", "default": 20},
                    "depth": {"type": "integer", "default": 4},
                },
                "required": ["query"],
            },
            confirm=ConfirmLevel.NONE,
            handler=_search_content,
        ),
        Tool(
            id="files.create_folder",
            description="Create a folder (and parents if needed).",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
            confirm=ConfirmLevel.NONE,
            handler=_create_folder,
        ),
        Tool(
            id="files.compress",
            description="Create a ZIP archive from files/folders.",
            parameters={
                "type": "object",
                "properties": {
                    "sources": {
                        "type": "string",
                        "description": "One path, or several separated by |",
                    },
                    "archive": {
                        "type": "string",
                        "description": "Output .zip path",
                    },
                },
                "required": ["sources", "archive"],
            },
            confirm=ConfirmLevel.ASK,
            handler=_compress,
        ),
        Tool(
            id="files.extract_archive",
            description="Extract a ZIP archive to a destination folder.",
            parameters={
                "type": "object",
                "properties": {
                    "archive": {"type": "string"},
                    "destination": {"type": "string"},
                },
                "required": ["archive", "destination"],
            },
            confirm=ConfirmLevel.ASK,
            handler=_extract,
        ),
        Tool(
            id="files.reveal_in_explorer",
            description="Show a file or folder selected in File Explorer.",
            parameters={
                "type": "object",
                "properties": {"path": {"type": "string"}},
                "required": ["path"],
            },
            confirm=ConfirmLevel.NONE,
            handler=_reveal,
            platforms=("windows",),
        ),
        Tool(
            id="files.open_recycle_bin",
            description="Open the Recycle Bin in Explorer.",
            parameters={"type": "object", "properties": {}},
            confirm=ConfirmLevel.NONE,
            handler=_open_recycle_bin,
            platforms=("windows",),
        ),
        Tool(
            id="files.restore_from_recycle_bin",
            description=(
                "Restore an item from Recycle Bin by original name substring "
                "(best-effort via Shell.Application)."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "description": "Original filename substring to match",
                    },
                },
                "required": ["name"],
            },
            confirm=ConfirmLevel.ASK,
            handler=_restore_recycle,
            platforms=("windows",),
        ),
    ]


def _p(path: str) -> Path:
    return Path(path).expanduser()


def _copy(args: dict) -> ToolResult:
    src, dst = _p(args["source"]), _p(args["destination"])
    if not src.exists():
        return ToolResult(ok=False, message=f"Source not found: {src}")
    overwrite = bool(args.get("overwrite"))
    try:
        if src.is_dir():
            if dst.exists() and not overwrite:
                return ToolResult(ok=False, message=f"Destination exists: {dst}")
            if dst.exists() and overwrite:
                shutil.rmtree(dst)
            shutil.copytree(src, dst)
        else:
            dst.parent.mkdir(parents=True, exist_ok=True)
            if dst.exists() and not overwrite:
                return ToolResult(ok=False, message=f"Destination exists: {dst}")
            shutil.copy2(src, dst)
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, message=f"Copy failed: {exc}")
    return ToolResult(ok=True, message=f"Copied → {dst}", data={"destination": str(dst)})


def _move(args: dict) -> ToolResult:
    src, dst = _p(args["source"]), _p(args["destination"])
    if not src.exists():
        return ToolResult(ok=False, message=f"Source not found: {src}")
    overwrite = bool(args.get("overwrite"))
    try:
        if dst.exists():
            if not overwrite:
                return ToolResult(ok=False, message=f"Destination exists: {dst}")
            if dst.is_dir() and src.is_dir():
                shutil.rmtree(dst)
            elif dst.is_file():
                dst.unlink()
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(src), str(dst))
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, message=f"Move failed: {exc}")
    return ToolResult(ok=True, message=f"Moved → {dst}", data={"destination": str(dst)})


def _rename(args: dict) -> ToolResult:
    src = _p(args["path"])
    if not src.exists():
        return ToolResult(ok=False, message=f"Not found: {src}")
    new = str(args.get("new_name") or "").strip()
    if not new:
        return ToolResult(ok=False, message="new_name required")
    dest = Path(new).expanduser() if ("/" in new or "\\" in new) else src.with_name(new)
    try:
        src.rename(dest)
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, message=f"Rename failed: {exc}")
    return ToolResult(ok=True, message=f"Renamed → {dest}", data={"path": str(dest)})


def _fmt_ts(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone().isoformat(timespec="seconds")


def _get_metadata(args: dict) -> ToolResult:
    path = _p(args["path"])
    if not path.exists():
        return ToolResult(ok=False, message=f"Not found: {path}")
    st = path.stat()
    data = {
        "path": str(path.resolve()),
        "name": path.name,
        "is_dir": path.is_dir(),
        "is_file": path.is_file(),
        "extension": path.suffix.lower(),
        "size_bytes": st.st_size if path.is_file() else None,
        "created": _fmt_ts(st.st_ctime),
        "modified": _fmt_ts(st.st_mtime),
        "accessed": _fmt_ts(st.st_atime),
    }
    return ToolResult(
        ok=True,
        message=(
            f"{path.name}: "
            f"{'folder' if path.is_dir() else path.suffix or 'file'}, "
            f"{data['size_bytes'] or '-'} bytes, modified {data['modified']}"
        ),
        data=data,
    )


def _get_properties(args: dict) -> ToolResult:
    path = _p(args["path"])
    if not path.exists():
        return ToolResult(ok=False, message=f"Not found: {path}")
    if os.name != "nt":
        mode = path.stat().st_mode
        return ToolResult(
            ok=True,
            message=f"mode={oct(mode)}",
            data={"mode": oct(mode)},
        )
    import ctypes

    GetFileAttributesW = ctypes.windll.kernel32.GetFileAttributesW
    GetFileAttributesW.argtypes = [ctypes.c_wchar_p]
    GetFileAttributesW.restype = ctypes.c_uint32
    attrs = GetFileAttributesW(str(path))
    if attrs == 0xFFFFFFFF:
        return ToolResult(ok=False, message="Could not read attributes")
    flags = {
        "readonly": bool(attrs & 0x1),
        "hidden": bool(attrs & 0x2),
        "system": bool(attrs & 0x4),
        "directory": bool(attrs & 0x10),
        "archive": bool(attrs & 0x20),
        "normal": bool(attrs & 0x80),
        "temporary": bool(attrs & 0x100),
        "compressed": bool(attrs & 0x800),
    }
    on = [k for k, v in flags.items() if v]
    return ToolResult(
        ok=True,
        message=f"Attributes: {', '.join(on) or 'none'}",
        data={"path": str(path), "attributes": flags},
    )


def _open_with(args: dict) -> ToolResult:
    path = _p(args["path"])
    if not path.exists():
        return ToolResult(ok=False, message=f"Not found: {path}")
    app = str(args.get("app") or "").strip()
    if not app:
        return ToolResult(ok=False, message="app required")
    if os.name == "nt":
        from osagent.tools.win_launch import launch_windows_app

        return launch_windows_app(app, [str(path)])
    try:
        subprocess.Popen([app, str(path)])
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, message=str(exc))
    return ToolResult(ok=True, message=f"Opened {path.name} with {app}")


def _read_text(args: dict) -> ToolResult:
    path = _p(args["path"])
    if not path.is_file():
        return ToolResult(ok=False, message=f"Not a file: {path}")
    max_chars = max(100, min(int(args.get("max_chars") or 50000), 200_000))
    if path.stat().st_size > 5_000_000:
        return ToolResult(ok=False, message="File too large to read as text (>5MB)")
    raw = path.read_bytes()
    text = None
    for enc in ("utf-8", "utf-8-sig", "utf-16", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    if text is None:
        return ToolResult(ok=False, message="Could not decode as text")
    truncated = len(text) > max_chars
    body = text[:max_chars]
    return ToolResult(
        ok=True,
        message=body if not truncated else body + f"\n… [truncated at {max_chars} chars]",
        data={"path": str(path), "chars": len(text), "truncated": truncated},
    )


def _write_text(args: dict) -> ToolResult:
    path = _p(args["path"])
    content = str(args.get("content") or "")
    append = bool(args.get("append"))
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if append and path.exists():
            with path.open("a", encoding="utf-8") as fh:
                fh.write(content)
        else:
            path.write_text(content, encoding="utf-8")
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, message=f"Write failed: {exc}")
    return ToolResult(ok=True, message=f"Wrote {path} ({len(content)} chars)")


def _search_content(args: dict) -> ToolResult:
    query = str(args.get("query") or "").strip()
    if not query:
        return ToolResult(ok=False, message="query required")
    root = _p(args["path"]) if args.get("path") else Path.home() / "Documents"
    if not root.is_dir():
        return ToolResult(ok=False, message=f"Not a folder: {root}")
    exts = {
        e.strip().lower().lstrip(".")
        for e in str(args.get("extensions") or "txt,md,py,csv,log").split(",")
        if e.strip()
    }
    limit = max(1, min(int(args.get("limit") or 20), 50))
    depth = max(1, min(int(args.get("depth") or 4), 8))
    q_lower = query.lower()
    hits: list[dict[str, Any]] = []
    root_depth = len(root.resolve().parts)

    for dirpath, dirnames, filenames in os.walk(root):
        cur = Path(dirpath)
        if len(cur.resolve().parts) - root_depth > depth:
            dirnames.clear()
            continue
        # skip heavy trees
        dirnames[:] = [
            d
            for d in dirnames
            if d.lower() not in {".git", "node_modules", ".venv", "venv", "__pycache__"}
        ]
        for name in filenames:
            p = cur / name
            if p.suffix.lower().lstrip(".") not in exts:
                continue
            try:
                if p.stat().st_size > 2_000_000:
                    continue
                text = p.read_text(encoding="utf-8", errors="ignore")
            except Exception:
                continue
            idx = text.lower().find(q_lower)
            if idx < 0:
                continue
            start = max(0, idx - 40)
            snippet = text[start : idx + len(query) + 40].replace("\n", " ")
            hits.append({"path": str(p), "snippet": snippet})
            if len(hits) >= limit:
                break
        if len(hits) >= limit:
            break

    if not hits:
        return ToolResult(ok=False, message=f"No content matches for '{query}' under {root}")
    lines = [f"{i}. {h['path']}\n    …{h['snippet']}…" for i, h in enumerate(hits, 1)]
    return ToolResult(
        ok=True,
        message=f"{len(hits)} content hit(s):\n" + "\n".join(lines),
        data={"hits": hits},
    )


def _create_folder(args: dict) -> ToolResult:
    path = _p(args["path"])
    try:
        path.mkdir(parents=True, exist_ok=True)
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, message=str(exc))
    return ToolResult(ok=True, message=f"Folder ready: {path}", data={"path": str(path)})


def _compress(args: dict) -> ToolResult:
    sources_raw = str(args.get("sources") or "")
    archive = _p(args["archive"])
    parts = [p.strip() for p in sources_raw.split("|") if p.strip()]
    if not parts:
        return ToolResult(ok=False, message="sources required")
    paths = [_p(p) for p in parts]
    missing = [str(p) for p in paths if not p.exists()]
    if missing:
        return ToolResult(ok=False, message=f"Missing: {', '.join(missing)}")
    try:
        archive.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            for src in paths:
                if src.is_file():
                    zf.write(src, arcname=src.name)
                else:
                    for f in src.rglob("*"):
                        if f.is_file():
                            zf.write(f, arcname=str(f.relative_to(src.parent)))
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, message=f"Compress failed: {exc}")
    size = archive.stat().st_size
    return ToolResult(
        ok=True,
        message=f"Created {archive} ({size} bytes)",
        data={"archive": str(archive), "size_bytes": size},
    )


def _extract(args: dict) -> ToolResult:
    archive = _p(args["archive"])
    dest = _p(args["destination"])
    if not archive.is_file():
        return ToolResult(ok=False, message=f"Archive not found: {archive}")
    if archive.suffix.lower() != ".zip":
        return ToolResult(ok=False, message="Only .zip is supported currently")
    try:
        dest.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(archive, "r") as zf:
            # basic zip-slip guard
            for info in zf.infolist():
                target = (dest / info.filename).resolve()
                if not str(target).startswith(str(dest.resolve())):
                    return ToolResult(ok=False, message="Blocked unsafe archive entry")
            zf.extractall(dest)
            names = zf.namelist()[:30]
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, message=f"Extract failed: {exc}")
    return ToolResult(
        ok=True,
        message=f"Extracted to {dest} ({len(names)}+ entries)",
        data={"destination": str(dest), "entries_sample": names},
    )


def _reveal(args: dict) -> ToolResult:
    path = _p(args["path"])
    if not path.exists():
        return ToolResult(ok=False, message=f"Not found: {path}")
    try:
        if path.is_dir():
            subprocess.Popen(["explorer", str(path)])
        else:
            subprocess.Popen(["explorer", "/select,", str(path)])
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, message=str(exc))
    return ToolResult(ok=True, message=f"Revealed in Explorer: {path}")


def _open_recycle_bin(_args: dict) -> ToolResult:
    try:
        subprocess.Popen(["explorer", "shell:RecycleBinFolder"])
    except Exception as exc:  # noqa: BLE001
        return ToolResult(ok=False, message=str(exc))
    return ToolResult(ok=True, message="Opened Recycle Bin")


def _restore_recycle(args: dict) -> ToolResult:
    name = str(args.get("name") or "").strip()
    if not name:
        return ToolResult(ok=False, message="name required")
    name_esc = name.replace("'", "''")
    script = rf"""
$ErrorActionPreference = 'Stop'
$shell = New-Object -ComObject Shell.Application
$bin = $shell.NameSpace(0xA)
$needle = '{name_esc}'.ToLower()
$item = $null
foreach ($i in $bin.Items()) {{
  if ($i.Name -and $i.Name.ToLower().Contains($needle)) {{ $item = $i; break }}
}}
if (-not $item) {{
  [PSCustomObject]@{{ ok = $false; message = 'No matching item in Recycle Bin' }} | ConvertTo-Json -Compress
}} else {{
  $item.InvokeVerb('restore')
  [PSCustomObject]@{{ ok = $true; name = $item.Name }} | ConvertTo-Json -Compress
}}
"""
    from osagent.tools.win_ps import run_ps

    code, out, err = run_ps(script, timeout=60)
    if code != 0:
        return ToolResult(ok=False, message=(err or out or "restore failed")[:400])
    import json

    try:
        data = json.loads(out.strip() or "{}")
    except json.JSONDecodeError:
        return ToolResult(ok=False, message=out[:300] or "bad response")
    if not data.get("ok"):
        return ToolResult(ok=False, message=str(data.get("message") or "restore failed"))
    return ToolResult(
        ok=True,
        message=f"Restored: {data.get('name')}",
        data=data if isinstance(data, dict) else {},
    )
