"""Download / locate the Vosk speech model."""

from __future__ import annotations

import io
import zipfile
from collections.abc import Callable
from pathlib import Path
from urllib.request import urlopen

from osagent.paths import config_dir, project_root

DEFAULT_MODEL_NAME = "vosk-model-small-en-us-0.15"
DEFAULT_MODEL_URL = (
    "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
)


def resolve_model_dir(configured: str | None = None) -> Path:
    """Return model directory path (may not exist yet)."""
    if configured:
        p = Path(configured).expanduser()
        if p.is_absolute():
            return p
        for base in (config_dir(), project_root()):
            cand = (base / p).resolve()
            if cand.is_dir():
                return cand
        return (config_dir() / p).resolve()
    return (config_dir() / "models" / DEFAULT_MODEL_NAME).resolve()


def model_ready(model_dir: Path) -> bool:
    if not model_dir.is_dir():
        return False
    return (model_dir / "am").is_dir() or (model_dir / "conf").is_dir()


def ensure_vosk_model(
    configured: str | None = None,
    *,
    url: str | None = None,
    progress: Callable[[str], None] | None = None,
) -> Path:
    """
    Ensure the Vosk model is on disk; download+unzip if missing.
    Returns the model directory.
    """
    model_dir = resolve_model_dir(configured)
    if model_ready(model_dir):
        return model_dir

    download_url = url or DEFAULT_MODEL_URL
    model_dir.parent.mkdir(parents=True, exist_ok=True)

    def note(msg: str) -> None:
        if progress:
            progress(msg)
        else:
            print(msg)

    note(f"Downloading Vosk model from {download_url} …")
    with urlopen(download_url, timeout=180) as resp:  # noqa: S310 — fixed URL
        data = resp.read()

    note("Extracting Vosk model…")
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        zf.extractall(model_dir.parent)

    if not model_ready(model_dir):
        raise RuntimeError(
            f"Vosk model missing after extract: {model_dir}. "
            "Check [voice] model_path / model_url in config."
        )
    note(f"Vosk model ready: {model_dir}")
    return model_dir
