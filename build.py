#!/usr/bin/env python3
"""
Windows agent executable build (not the Linux live ISO).

- Ensures src / config / external / release layout
- Creates external/venv and installs Python deps
- Downloads llama.cpp Windows binaries into external/llama.cpp
- Compiles a one-file executable into release/  (gitignored)
- Copies config + llama.cpp runtime next to the exe

Linux live ISO (PicoSoul USB):
  ./scripts/distro/build_iso.sh   → out/iso/*.iso

Usage:
  python build.py              # full build
  python build.py --deps-only  # venv + externals, no compile
  python build.py --compile-only
  python build.py --skip-llama
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
SRC = ROOT / "src"
CONFIG = ROOT / "config"
EXTERNAL = ROOT / "external"
RELEASE = ROOT / "release"
VENV = EXTERNAL / "venv"
LLAMA_DIR = EXTERNAL / "llama.cpp"
REQUIREMENTS = ROOT / "requirements.txt"
REQUIREMENTS_VOICE = ROOT / "requirements-voice.txt"

LLAMA_REPO = "ggml-org/llama.cpp"
# Prefer a portable CPU build for the Windows pilot (asset names evolve).
LLAMA_ASSET_HINTS = (
    "bin-win-cpu-x64",
    "bin-win-avx2-x64",
    "bin-win-avx-x64",
    "bin-win-x64",
    "win-cpu-x64",
)


def log(msg: str) -> None:
    print(f"[build] {msg}", flush=True)


def ensure_dirs() -> None:
    for path in (SRC, CONFIG, EXTERNAL, RELEASE, LLAMA_DIR):
        path.mkdir(parents=True, exist_ok=True)
    log(f"dirs ok: src, config, external, release")


def venv_python() -> Path:
    if sys.platform == "win32":
        return VENV / "Scripts" / "python.exe"
    return VENV / "bin" / "python"


def venv_pip() -> list[str]:
    return [str(venv_python()), "-m", "pip"]


def ensure_venv() -> None:
    py = venv_python()
    if py.is_file():
        log(f"venv exists: {VENV}")
        return
    log(f"creating venv at {VENV}")
    subprocess.run([sys.executable, "-m", "venv", str(VENV)], check=True)


def pip_install() -> None:
    ensure_venv()
    log("upgrading pip")
    subprocess.run([*venv_pip(), "install", "--upgrade", "pip"], check=True)
    log(f"installing {REQUIREMENTS.name}")
    subprocess.run([*venv_pip(), "install", "-r", str(REQUIREMENTS)], check=True)
    if REQUIREMENTS_VOICE.is_file():
        log(f"installing {REQUIREMENTS_VOICE.name} (Vosk STT)")
        subprocess.run(
            [*venv_pip(), "install", "-r", str(REQUIREMENTS_VOICE)],
            check=True,
        )


def http_json(url: str) -> dict | list:
    req = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": "osagent-build",
        },
    )
    with urllib.request.urlopen(req, timeout=60) as resp:  # noqa: S310 — fixed GitHub API
        return json.loads(resp.read().decode("utf-8"))


def http_download(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    log(f"downloading {url}")
    req = urllib.request.Request(url, headers={"User-Agent": "osagent-build"})
    with urllib.request.urlopen(req, timeout=300) as resp, dest.open("wb") as out:  # noqa: S310
        shutil.copyfileobj(resp, out)


def pick_llama_asset(assets: list[dict]) -> dict | None:
    names = [(a.get("name") or "", a) for a in assets]
    # Only zip assets on Windows pilot
    zips = [(n, a) for n, a in names if n.lower().endswith(".zip")]
    for hint in LLAMA_ASSET_HINTS:
        for name, asset in zips:
            lower = name.lower()
            if hint in lower and "cuda" not in lower and "rocm" not in lower:
                return asset
    # Fallback: any win x64 zip without cuda / cudart
    for name, asset in zips:
        lower = name.lower()
        if (
            "win" in lower
            and "x64" in lower
            and "cuda" not in lower
            and "cudart" not in lower
            and "rocm" not in lower
            and "arm64" not in lower
        ):
            return asset
    return None


def fetch_llama_release() -> tuple[dict, dict]:
    """Return (release, asset) for the newest llama.cpp build with Windows CPU zips.

    ``/releases/latest`` may point at a tag without binaries; walk recent releases.
    """
    try:
        releases = http_json(
            f"https://api.github.com/repos/{LLAMA_REPO}/releases?per_page=20"
        )
    except urllib.error.URLError as exc:
        raise SystemExit(f"Failed to query GitHub for llama.cpp: {exc}") from exc

    if not isinstance(releases, list):
        raise SystemExit("Unexpected GitHub releases payload for llama.cpp")

    for release in releases:
        asset = pick_llama_asset(release.get("assets") or [])
        if asset is not None:
            return release, asset

    raise SystemExit(
        "No suitable Windows llama.cpp asset found in recent releases. "
        "Download a CPU zip manually into external/llama.cpp"
    )


def llama_server_present() -> bool:
    if not LLAMA_DIR.is_dir():
        return False
    for path in LLAMA_DIR.rglob("*"):
        if path.is_file() and path.name.lower() in {
            "llama-server.exe",
            "llama-server",
            "server.exe",
        }:
            return True
    return False


def download_llama_cpp() -> None:
    if sys.platform != "win32":
        log("skip llama.cpp download (Windows-only pilot build)")
        return
    if llama_server_present():
        log("llama.cpp already present under external/llama.cpp")
        return

    log(f"fetching release metadata for {LLAMA_REPO}")
    release, asset = fetch_llama_release()
    log(f"using llama.cpp {release.get('tag_name')} / {asset.get('name')}")

    name = asset["name"]
    url = asset["browser_download_url"]
    zip_path = EXTERNAL / "cache" / name
    http_download(url, zip_path)

    # Clean previous extract but keep folder
    for child in LLAMA_DIR.iterdir():
        if child.name == ".gitkeep":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()

    log(f"extracting {name} -> {LLAMA_DIR}")
    with zipfile.ZipFile(zip_path, "r") as zf:
        zf.extractall(LLAMA_DIR)

    if not llama_server_present():
        raise SystemExit(
            "Extracted llama.cpp zip but llama-server.exe was not found. "
            "Inspect external/llama.cpp and adjust asset hints in build.py."
        )
    log("llama.cpp ready")


def compile_exe() -> Path:
    ensure_venv()
    py = venv_python()
    work = EXTERNAL / "pyinstaller" / "work"
    spec = EXTERNAL / "pyinstaller"
    work.mkdir(parents=True, exist_ok=True)
    spec.mkdir(parents=True, exist_ok=True)

    # Clean previous exe (skip if locked by a running instance)
    exe_name = "osagent"
    for old in RELEASE.glob("osagent*"):
        if old.is_file():
            try:
                old.unlink()
            except OSError as exc:
                log(f"warning: could not remove {old.name} ({exc}); building side-by-side")
                exe_name = "osagent_new"
        elif old.is_dir() and old.name == "osagent":
            shutil.rmtree(old, ignore_errors=True)

    entry = SRC / "osagent" / "__main__.py"
    cmd = [
        str(py),
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--clean",
        "--onefile",
        "--name",
        exe_name,
        "--paths",
        str(SRC),
        "--distpath",
        str(RELEASE),
        "--workpath",
        str(work),
        "--specpath",
        str(spec),
        "--console",
        # Vosk + PortAudio (lazy-imported at runtime — must collect explicitly)
        "--hidden-import",
        "vosk",
        "--hidden-import",
        "sounddevice",
        "--hidden-import",
        "_sounddevice",
        "--hidden-import",
        "_sounddevice_data",
        "--hidden-import",
        "cffi",
        "--collect-all",
        "vosk",
        "--collect-all",
        "_sounddevice_data",
        "--collect-binaries",
        "sounddevice",
        str(entry),
    ]
    log("running PyInstaller")
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
    subprocess.run(cmd, check=True, env=env, cwd=str(ROOT))

    suffix = ".exe" if sys.platform == "win32" else ""
    exe = RELEASE / f"{exe_name}{suffix}"
    if not exe.is_file():
        raise SystemExit(f"Expected executable missing: {exe}")
    if exe_name != "osagent":
        log(f"note: running instance locked osagent.exe — use {exe.name}, then replace when closed")
    log(f"executable: {exe}")
    return exe


def _is_gguf(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() == ".gguf"


def _copy_tree_preserve_gguf(src: Path, dest: Path) -> None:
    """Merge src into dest. Never delete or overwrite existing *.gguf files."""
    dest.mkdir(parents=True, exist_ok=True)
    for root, _dirs, files in os.walk(src):
        rel = Path(root).relative_to(src)
        target_dir = dest / rel
        target_dir.mkdir(parents=True, exist_ok=True)
        for name in files:
            s = Path(root) / name
            d = target_dir / name
            if _is_gguf(d):
                log(f"keeping existing model: {d}")
                continue
            if _is_gguf(s) and d.exists():
                log(f"keeping existing model (skip copy): {d}")
                continue
            shutil.copy2(s, d)


# Learned runtime state under release/config — never wipe on rebuild
_PRESERVE_CONFIG_FILES = frozenset(
    {
        "inventory.json",
        "inventory.json.tmp",
        "config.local.toml",
    }
)


def _stage_config_preserve_learned() -> None:
    """Sync config/ → release/config without deleting inventory / local overlays."""
    dest_config = RELEASE / "config"
    dest_config.mkdir(parents=True, exist_ok=True)

    # Snapshot learned files already beside the exe
    preserved: dict[str, bytes] = {}
    for name in _PRESERVE_CONFIG_FILES:
        path = dest_config / name
        if path.is_file():
            try:
                preserved[name] = path.read_bytes()
            except OSError:
                pass

    if not CONFIG.is_dir():
        log(f"warning: no {CONFIG}; keeping existing release/config")
    else:
        for item in CONFIG.iterdir():
            target = dest_config / item.name
            # Never replace an existing learned inventory with a stale/empty copy
            if item.name in _PRESERVE_CONFIG_FILES and target.is_file():
                log(f"keeping learned {target.relative_to(RELEASE)}")
                continue
            if item.name in _PRESERVE_CONFIG_FILES and item.name in preserved:
                continue
            try:
                if target.exists():
                    if target.is_dir():
                        shutil.rmtree(target)
                    else:
                        target.unlink()
                if item.is_dir():
                    shutil.copytree(item, target)
                else:
                    shutil.copy2(item, target)
            except OSError as exc:
                log(f"warning: could not stage {item.name}: {exc}")

    # Restore learned files if a previous step removed them
    for name, data in preserved.items():
        path = dest_config / name
        if not path.is_file():
            try:
                path.write_bytes(data)
                log(f"restored learned {path.relative_to(RELEASE)}")
            except OSError as exc:
                log(f"warning: could not restore {name}: {exc}")

    inv = dest_config / "inventory.json"
    if inv.is_file():
        log(f"inventory preserved: {inv} ({inv.stat().st_size} bytes)")
    log(f"staged {dest_config}")


def stage_release_runtime() -> None:
    """Copy config + llama.cpp beside the exe for frozen runs.

    Model GGUF files under release/models (or project models/) are never deleted.
    Learned inventory.json / config.local.toml under release/config are preserved.
    """
    _stage_config_preserve_learned()

    if LLAMA_DIR.is_dir() and any(LLAMA_DIR.iterdir()):
        dest_llama_root = RELEASE / "external" / "llama.cpp"
        refreshed = True
        if dest_llama_root.exists():
            try:
                shutil.rmtree(dest_llama_root)
            except OSError as exc:
                refreshed = False
                log(
                    f"warning: could not refresh {dest_llama_root} ({exc}); "
                    "leaving existing llama.cpp in place"
                )
        if refreshed:
            shutil.copytree(LLAMA_DIR, dest_llama_root)
            log(f"staged {dest_llama_root}")

    # Merge models into release/models — never wipe GGUFs downloaded by the exe
    src_models = ROOT / "models"
    dest_models = RELEASE / "models"
    dest_models.mkdir(parents=True, exist_ok=True)
    if src_models.is_dir():
        _copy_tree_preserve_gguf(src_models, dest_models)
        log(f"staged {dest_models} (GGUF files preserved)")
    else:
        dest_models.mkdir(parents=True, exist_ok=True)

    release_ggufs = list(RELEASE.rglob("*.gguf"))
    if release_ggufs:
        log(
            "model files present: "
            + ", ".join(str(p.relative_to(RELEASE)) for p in release_ggufs)
        )
    else:
        log(
            "no GGUF models in release/ yet "
            "(exe will prompt to download on first run)"
        )


def write_placeholders() -> None:
    (EXTERNAL / ".gitkeep").write_text("", encoding="utf-8")
    (RELEASE / ".gitkeep").write_text("", encoding="utf-8")
    models = ROOT / "models"
    models.mkdir(exist_ok=True)
    readme = models / "README.txt"
    if not readme.is_file():
        readme.write_text(
            "Default: Qwen3.5-4B-Q4_K_M.gguf (downloaded on first run of osagent.exe).\n"
            "Build never deletes *.gguf files under models/ or release/models/.\n",
            encoding="utf-8",
        )


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Build OS Agent (Windows pilot)")
    p.add_argument("--deps-only", action="store_true", help="Only venv + externals")
    p.add_argument("--compile-only", action="store_true", help="Skip downloads; compile")
    p.add_argument("--skip-llama", action="store_true", help="Do not download llama.cpp")
    p.add_argument(
        "--dev",
        action="store_true",
        help="After ensuring deps, run the agent from src via the venv. "
        "Pass agent flags after --dev (example: python build.py --dev --list-tools)",
    )
    return p.parse_known_args()


def run_dev(extra: list[str]) -> int:
    ensure_venv()
    args = list(extra)
    if args and args[0] == "--":
        args = args[1:]
    env = os.environ.copy()
    env["PYTHONPATH"] = str(SRC) + os.pathsep + env.get("PYTHONPATH", "")
    cmd = [str(venv_python()), "-m", "osagent", *args]
    log(f"dev run: {' '.join(cmd)}")
    return subprocess.run(cmd, check=False, env=env, cwd=str(ROOT)).returncode


def main() -> int:
    if sys.platform != "win32":
        log("WARNING: build.py is the Windows pilot. Linux packaging comes later.")

    args, unknown = parse_args()
    ensure_dirs()
    write_placeholders()

    if args.dev:
        pip_install()
        return run_dev(unknown)

    if not args.compile_only:
        pip_install()
        if not args.skip_llama:
            download_llama_cpp()

    if args.deps_only:
        log("deps-only done")
        return 0

    compile_exe()
    stage_release_runtime()
    log("done - run release/osagent.exe")
    log("tip: set llm.provider=api in release/config/config.toml to test without a GGUF")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
