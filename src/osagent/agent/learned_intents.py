"""
Auto-recover intents: when a phrase has no built-in match but the LLM
successfully calls a safe tool, remember phrase → tool+args for next time.
"""

from __future__ import annotations

import json
import re
import threading
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from osagent.agent.intent_types import IntentMatch
from osagent.paths import config_dir
from osagent.tools.base import ConfirmLevel, Tool

_LOCK = threading.RLock()
_CACHE: dict[str, Any] | None = None

# Free-form escape hatches — never auto-learn (would memorize one-off shell)
_NEVER_LEARN_TOOLS = frozenset(
    {
        "linux.shell.run",
        "windows.powershell.run",
        "windows.shell.run",
    }
)

_STORE_NAME = "learned_intents.json"


def _normalize(text: str) -> str:
    t = (text or "").strip().lower()
    t = re.sub(r"[?!.,;:]+$", "", t)
    t = re.sub(r"\s+", " ", t)
    return t


def _store_path() -> Path:
    return config_dir() / _STORE_NAME


def _load() -> dict[str, Any]:
    global _CACHE
    with _LOCK:
        if _CACHE is not None:
            return _CACHE
        path = _store_path()
        if path.is_file():
            try:
                data = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(data, dict) and isinstance(data.get("intents"), list):
                    _CACHE = data
                    return _CACHE
            except (OSError, json.JSONDecodeError):
                pass
        _CACHE = {"version": 1, "intents": []}
        return _CACHE


def _save(data: dict[str, Any]) -> None:
    global _CACHE
    path = _store_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2, ensure_ascii=True) + "\n"
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    try:
        tmp.replace(path)
    except PermissionError:
        # Windows: destination can be briefly locked by AV / indexer
        path.write_text(payload, encoding="utf-8")
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            pass
    _CACHE = data


def match_learned(text: str, *, min_ratio: float = 0.92) -> IntentMatch | None:
    """Exact normalized match, then high-similarity fuzzy match."""
    key = _normalize(text)
    if not key or len(key) < 3:
        return None
    data = _load()
    best: tuple[float, dict[str, Any]] | None = None
    for entry in data.get("intents") or []:
        if not isinstance(entry, dict):
            continue
        phrase = _normalize(str(entry.get("phrase") or ""))
        if not phrase:
            continue
        if phrase == key:
            return IntentMatch(
                str(entry["tool_id"]),
                dict(entry.get("args") or {}),
                f"learned: {entry.get('phrase')}",
            )
        ratio = SequenceMatcher(None, key, phrase).ratio()
        if ratio >= min_ratio and (best is None or ratio > best[0]):
            best = (ratio, entry)
    if best:
        entry = best[1]
        return IntentMatch(
            str(entry["tool_id"]),
            dict(entry.get("args") or {}),
            f"learned~{best[0]:.2f}: {entry.get('phrase')}",
        )
    return None


def should_learn_tool(tool: Tool | None, args: dict[str, Any]) -> bool:
    if tool is None:
        return False
    if tool.id in _NEVER_LEARN_TOOLS:
        return False
    # Only auto-learn non-destructive catalog tools by default
    if tool.confirm != ConfirmLevel.NONE:
        return False
    # Skip one-off huge free-form args
    for k, v in (args or {}).items():
        if k in {"command", "script", "rationale"} and isinstance(v, str) and len(v) > 80:
            return False
    return True


def record_learned(
    phrase: str,
    tool_id: str,
    args: dict[str, Any] | None = None,
    *,
    source: str = "llm",
) -> bool:
    """
    Persist phrase → tool mapping. Returns True if newly stored or updated.
    """
    key = _normalize(phrase)
    if not key or len(key) < 3:
        return False
    tool_id = (tool_id or "").strip()
    if not tool_id or tool_id in _NEVER_LEARN_TOOLS:
        return False
    args = dict(args or {})

    with _LOCK:
        data = _load()
        intents: list[dict[str, Any]] = list(data.get("intents") or [])
        for entry in intents:
            if _normalize(str(entry.get("phrase") or "")) == key:
                # Refresh mapping / bump hit count
                entry["tool_id"] = tool_id
                entry["args"] = args
                entry["hits"] = int(entry.get("hits") or 0) + 1
                entry["source"] = source
                data["intents"] = intents
                _save(data)
                return True
        intents.append(
            {
                "phrase": phrase.strip(),
                "norm": key,
                "tool_id": tool_id,
                "args": args,
                "hits": 1,
                "source": source,
            }
        )
        # Cap growth
        if len(intents) > 500:
            intents = intents[-500:]
        data["intents"] = intents
        _save(data)
        return True


def bump_hit(phrase: str) -> None:
    key = _normalize(phrase)
    if not key:
        return
    with _LOCK:
        data = _load()
        changed = False
        for entry in data.get("intents") or []:
            if _normalize(str(entry.get("phrase") or "")) == key:
                entry["hits"] = int(entry.get("hits") or 0) + 1
                changed = True
                break
        if changed:
            _save(data)
