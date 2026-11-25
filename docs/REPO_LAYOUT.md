# Repository layout

PicoSoul keeps a hard split between **source (checked in)** and **generated output (local / CI only)**.

## Checked in (source)

| Path | Purpose |
|------|---------|
| `src/osagent/` | OS Agent Python package (intents, tools, local LLM, Linux/Windows) |
| `config/` | Default `config.toml` + command catalogs (no secrets) |
| `distro/` | Debian live-build config, PicoSoul branding, package lists |
| `scripts/agent/` | Dev helpers (WSL setup/run, smoke tests) |
| `scripts/distro/` | ISO build entrypoints (local + CI) |
| `docs/` | Vision, WSL, ISO build, this layout doc |
| `build.py` | Windows **agent exe** packager (not the Linux ISO) |
| `requirements*.txt` | Python deps for the agent |
| `.github/workflows/` | GitHub Actions (ISO release) |

GitHub remote: https://github.com/h-viseria/picosoul

## Generated (do not commit)

| Path | Purpose |
|------|---------|
| `out/iso/` | Built PicoSoul live ISO + checksums |
| `out/cache/` | live-build / apt caches (speeds local rebuilds) |
| `out/work/` | Temporary chroot / lb build tree |
| `external/` | Downloaded llama.cpp, venvs, PyInstaller bits |
| `models/` | GGUF weights (downloaded on demand → USB persistence later) |
| `release/` | Windows `osagent.exe` bundle from `build.py` |

`.gitignore` ignores all of the generated trees above.

## Mental model

```text
  CHECKED IN                         GENERATED
 ─────────────                      ─────────────
  src/osagent  ──build.py────────►  release/          (Windows agent)
  distro/      ──build_iso.sh────►  out/iso/          (Linux live USB)
  config/      (defaults only)
               downloads ────────►  models/, external/
```

## Quick commands

```bash
# Agent on WSL (dev)
./scripts/agent/wsl_setup.sh
./scripts/agent/wsl_run.sh --once "system info"

# Live ISO (Linux host or GitHub Actions)
./scripts/distro/build_iso.sh

# Windows agent exe
python build.py
```
