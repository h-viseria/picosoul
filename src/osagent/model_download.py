"""Ensure the configured local GGUF is present; prompt and download if missing."""

from __future__ import annotations

import sys
import urllib.error
import urllib.request
from pathlib import Path

from osagent.config import AppConfig, LocalLLMConfig


def model_available(path: str | Path) -> bool:
    p = Path(path)
    return p.is_file() and p.stat().st_size > 1_000_000


def _format_bytes(n: int | float) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"


def download_file(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    partial = dest.with_suffix(dest.suffix + ".partial")
    if partial.exists():
        partial.unlink()

    req = urllib.request.Request(
        url,
        headers={"User-Agent": "osagent-model-download"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:  # noqa: S310 — URL from config
            total = int(resp.headers.get("Content-Length") or 0)
            label = dest.name
            print(f"Downloading {label}" + (f" ({_format_bytes(total)})" if total else "") + " …")
            done = 0
            chunk = 1024 * 1024
            last_pct = -1
            with partial.open("wb") as out:
                while True:
                    buf = resp.read(chunk)
                    if not buf:
                        break
                    out.write(buf)
                    done += len(buf)
                    if total > 0:
                        pct = int(done * 100 / total)
                        if pct != last_pct and (pct % 2 == 0 or pct == 100):
                            print(
                                f"\r  {pct:3d}%  {_format_bytes(done)} / {_format_bytes(total)}",
                                end="",
                                flush=True,
                            )
                            last_pct = pct
                    else:
                        print(f"\r  {_format_bytes(done)}", end="", flush=True)
            print()
    except urllib.error.URLError as exc:
        if partial.exists():
            partial.unlink(missing_ok=True)
        raise RuntimeError(f"Download failed: {exc}") from exc

    if dest.exists():
        dest.unlink()
    partial.rename(dest)
    print(f"Saved model to {dest}")


def prompt_download(local: LocalLLMConfig, *, auto_yes: bool = False) -> bool:
    name = local.model_name or Path(local.model_path).name
    print(f"Local model not found: {local.model_path}")
    print(f"Recommended model: {name}")
    if local.download_url:
        print(f"Source: {local.download_url}")
    else:
        print("No download_url configured in config.toml — cannot auto-download.")
        return False

    if auto_yes:
        return True

    if not sys.stdin.isatty():
        print("Non-interactive session; pass --download-model to fetch automatically.")
        return False

    try:
        answer = input("Download now? [Y/n] ").strip().lower()
    except (EOFError, KeyboardInterrupt):
        print()
        return False
    return answer in {"", "y", "yes"}


def ensure_local_model(
    cfg: AppConfig,
    *,
    force_download: bool = False,
    auto_yes: bool = False,
) -> bool:
    """Return True if a usable local model file exists after this call."""
    if cfg.llm.provider != "local":
        return True

    local = cfg.llm.local
    path = Path(local.model_path)

    if model_available(path) and not force_download:
        return True

    if not local.download_on_missing and not force_download:
        print(
            f"Local model missing at {path} and llm.local.download_on_missing is false.",
            file=sys.stderr,
        )
        return False

    if not local.download_url:
        print(
            f"Local model missing at {path} and no llm.local.download_url is set.",
            file=sys.stderr,
        )
        return False

    if force_download or prompt_download(local, auto_yes=auto_yes):
        try:
            download_file(local.download_url, path)
        except Exception as exc:  # noqa: BLE001
            print(f"Model download failed: {exc}", file=sys.stderr)
            return False
        return model_available(path)

    print("Model download skipped.", file=sys.stderr)
    return False
