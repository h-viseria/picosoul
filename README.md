# PicoSoul

**AI-Native · Compact · Secure** — local AI desktop agent + thin Debian live USB.

| | |
|--|--|
| Vision / product | https://picoai.org/picosoul/ |
| GitHub | https://github.com/h-viseria/picosoul |
| Layout | [docs/REPO_LAYOUT.md](docs/REPO_LAYOUT.md) |
| Live ISO | [docs/BUILD_ISO.md](docs/BUILD_ISO.md) |
| Agent on WSL | [docs/WSL.md](docs/WSL.md) |

## Repository map

```text
CHECKED IN                              GENERATED (gitignored)
─────────────────────────────           ─────────────────────────────
src/osagent/     agent code             out/iso/      PicoSoul *.iso
config/          default config         out/work/     live-build tree
distro/          Debian live + brand    out/cache/    apt/lb cache
scripts/agent/   WSL / agent helpers    external/     venv, llama.cpp
scripts/distro/  ISO build scripts      models/       GGUF downloads
docs/            docs                   release/      Windows osagent.exe
.github/         CI (ISO → Release)
build.py         Windows exe builder
```

## Quick start

### Agent (dev)

```bash
# WSL / Linux
./scripts/agent/wsl_setup.sh
./scripts/agent/wsl_run.sh --once "system info"

# Windows exe bundle
python build.py
```

### Live ISO (Linux or GitHub Actions)

```bash
# Local (Ubuntu/Debian or WSL with live-build)
./scripts/distro/build_iso.sh --dry-run   # stage only
./scripts/distro/build_iso.sh             # full ISO → out/iso/

# CI: Actions → “Build PicoSoul ISO” or push tag iso-0.1.0
```

Burn `out/iso/picosoul-*.iso` with **Rufus** (DD mode). Use **USB persistence** for models and settings — no install-to-disk in v1.

## Design (ISO v1)

- Debian **12 Bookworm**, IceWM, autologin user `picosoul`, no greeter  
- NetworkManager + BlueZ + trimmed firmware  
- Full OS Agent (intents/tools/local LLM) — **GGUF downloaded on first Wi‑Fi** to persistence  
- Optional later: Craft/LibreOffice/Firefox + cloud AI providers  

## License

Apache-2.0 (see project license on GitHub).
