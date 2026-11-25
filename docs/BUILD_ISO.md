# Building the PicoSoul live ISO

**Goal:** plug-and-play USB (live + persistence), single user, autologin, no disk installer.  
**Base:** Debian 12 Bookworm · IceWM · NetworkManager · BlueZ · OS Agent (local LLM default).  
**Not in ISO:** GGUF models, Craft/LibreOffice/Firefox (first-run / later).

## Prerequisites (local)

- Linux x86_64 (native or Ubuntu WSL2 with enough disk)
- `sudo`, `git`, `curl`/`wget`
- Packages: `live-build`, `debootstrap`, `squashfs-tools`, `xorriso`, `isolinux`/`syslinux`, `dpkg-dev`

```bash
sudo apt-get update
sudo apt-get install -y live-build debootstrap squashfs-tools xorriso \
  isolinux syslinux-common rsync
```

On **Windows**, run the script from **WSL Ubuntu**, not PowerShell.

## Local build

From the repo root:

```bash
chmod +x scripts/distro/build_iso.sh
./scripts/distro/build_iso.sh
```

Outputs (gitignored):

| Path | Contents |
|------|----------|
| `out/iso/picosoul-*.iso` | Hybrid live ISO (Rufus / dd) |
| `out/iso/*.sha256` | Checksum |
| `out/work/` | live-build working tree |
| `out/cache/` | Optional package cache |

Environment overrides:

```bash
PICOSOUL_OUT=out/iso \
PICOSOUL_WORK=out/work \
PICOSOUL_CACHE=out/cache \
./scripts/distro/build_iso.sh
```

## GitHub Actions

Workflow: `.github/workflows/build-picosoul-iso.yml`

- Trigger: `workflow_dispatch` or push tag `iso-*`
- Runs `scripts/distro/build_iso.sh` on `ubuntu-latest`
- Uploads the ISO to a **GitHub Release**

Repo: https://github.com/h-viseria/picosoul

## USB (Rufus)

1. Download the Release ISO  
2. Rufus → select USB → **DD Image** mode for hybrid ISO  
3. Add a **persistence** partition/file (or follow PicoSoul first-boot helper when available)  
4. Boot → Wi‑Fi → OS Agent downloads GGUF onto persistence  

## Size target

Aim **~600–800 MB** ISO (agent + IceWM + drivers; **no** model). Model lands on USB persistence after first online launch.
