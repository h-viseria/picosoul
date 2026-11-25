#!/usr/bin/env bash
# Build PicoSoul live ISO (Debian Bookworm, hybrid, no disk installer).
#
# Outputs (gitignored):
#   out/iso/picosoul-<date>.iso
#   out/iso/picosoul-<date>.iso.sha256
#   out/work/   — live-build tree
#   out/cache/  — apt/lb cache
#
# Usage (from repo root, on Linux or WSL):
#   ./scripts/distro/build_iso.sh
#   ./scripts/distro/build_iso.sh --dry-run   # stage only, do not lb build
#
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

OUT="${PICOSOUL_OUT:-$ROOT/out/iso}"
WORK="${PICOSOUL_WORK:-$ROOT/out/work/live-build}"
CACHE="${PICOSOUL_CACHE:-$ROOT/out/cache/live-build}"
DISTRO_LB="$ROOT/distro/live-build"
DRY_RUN=0

for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY_RUN=1 ;;
    -h|--help)
      sed -n '2,20p' "$0"
      exit 0
      ;;
  esac
done

log() { printf '[picosoul-iso] %s\n' "$*"; }

if [[ "$(uname -s)" != "Linux" ]]; then
  log "ERROR: ISO build must run on Linux (use WSL Ubuntu or GitHub Actions)."
  exit 1
fi

if [[ "$(id -u)" -ne 0 ]]; then
  if command -v sudo >/dev/null 2>&1; then
    SUDO=(sudo)
  else
    log "ERROR: need root or sudo for live-build/debootstrap."
    exit 1
  fi
else
  SUDO=()
fi

need_cmds=(lb debootstrap xorriso mksquashfs)
MISSING=()
for c in "${need_cmds[@]}"; do
  command -v "$c" >/dev/null 2>&1 || MISSING+=("$c")
done
if ((${#MISSING[@]})); then
  log "Missing tools: ${MISSING[*]}"
  log "Install: sudo apt-get install -y live-build debootstrap squashfs-tools xorriso isolinux syslinux-common"
  if [[ "$DRY_RUN" -eq 0 ]]; then
    exit 1
  fi
  log "(continuing dry-run without lb)"
fi

mkdir -p "$OUT" "$WORK" "$CACHE"

log "repo:   $ROOT"
log "out:    $OUT"
log "work:   $WORK"
log "cache:  $CACHE"

# Fresh work tree from checked-in live-build sources
rm -rf "$WORK"
mkdir -p "$WORK"
rsync -a --delete \
  --exclude 'cache' \
  "$DISTRO_LB/" "$WORK/"

# Stage agent sources for chroot hook (/build/picosoul-agent)
STAGE="$WORK/config/includes.chroot/build/picosoul-agent"
mkdir -p "$STAGE"
rsync -a \
  --exclude '__pycache__' \
  --exclude '*.pyc' \
  "$ROOT/src" "$STAGE/"
rsync -a \
  --exclude 'config.local.toml' \
  --exclude 'inventory.json' \
  --exclude 'learned_intents.json' \
  --exclude 'models' \
  "$ROOT/config" "$STAGE/"
cp "$ROOT/requirements.txt" "$STAGE/"
# Drop voice extras from ISO by default (keeps image smaller)
if [[ -f "$ROOT/requirements-voice.txt" ]]; then
  cp "$ROOT/requirements-voice.txt" "$STAGE/" || true
fi

# Make hooks executable
find "$WORK/config/hooks" -type f -name '*.hook.*' -exec chmod +x {} \; 2>/dev/null || true
chmod +x "$WORK/auto/config" 2>/dev/null || true

STAMP="$(date -u +%Y%m%d)"
ISO_NAME="picosoul-${STAMP}-amd64.iso"

if [[ "$DRY_RUN" -eq 1 ]]; then
  log "dry-run: staged live-build tree at $WORK"
  log "dry-run: agent staged at $STAGE"
  log "dry-run: skip lb build"
  exit 0
fi

log "running live-build (this takes a while)…"
cd "$WORK"

# Point lb cache at out/cache
export LB_CACHE="$CACHE"
mkdir -p "$CACHE"

"${SUDO[@]}" lb clean --purge || true
"${SUDO[@]}" lb config
"${SUDO[@]}" lb build

# live-build names the hybrid image live-image-amd64.hybrid.iso (typical)
BUILT=""
for candidate in \
  live-image-amd64.hybrid.iso \
  live-image-amd64.iso \
  binary.hybrid.iso \
  binary.iso
do
  if [[ -f "$WORK/$candidate" ]]; then
    BUILT="$WORK/$candidate"
    break
  fi
done

if [[ -z "$BUILT" ]]; then
  log "ERROR: ISO not found under $WORK — check lb build logs."
  ls -la "$WORK" | head -50 || true
  exit 1
fi

cp -f "$BUILT" "$OUT/$ISO_NAME"
(
  cd "$OUT"
  if command -v sha256sum >/dev/null 2>&1; then
    sha256sum "$ISO_NAME" >"$ISO_NAME.sha256"
  else
    shasum -a 256 "$ISO_NAME" >"$ISO_NAME.sha256"
  fi
)

log "OK: $OUT/$ISO_NAME"
log "OK: $OUT/$ISO_NAME.sha256"
ls -lh "$OUT/$ISO_NAME"
