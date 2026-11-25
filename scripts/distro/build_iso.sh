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

# Strip CRLF (Windows sync). Package lists MUST be LF — apt treats
# "live-boot\r" as a different name and reports Unable to locate package.
find "$WORK" -type f \( \
    -name 'config' -o -name '*.hook.*' -o -name '*.sh' \
    -o -name '*.list*' -o -name '*.chroot' -o -name 'README' \
    -o -name '*.conf' -o -name '*.toml' -o -name '*.txt' \
  \) -exec sed -i 's/\r$//' {} + 2>/dev/null || true
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

# debootstrap needs Debian archive keys (Ubuntu hosts often lack them)
KEYRING="/usr/share/keyrings/debian-archive-keyring.gpg"
if [[ ! -f "$KEYRING" ]]; then
  if [[ -f /usr/share/keyrings/debian-archive-keyring.pgp ]]; then
    KEYRING=/usr/share/keyrings/debian-archive-keyring.pgp
  else
    log "ERROR: missing $KEYRING"
    log "Install: sudo apt-get install -y debian-archive-keyring"
    exit 1
  fi
fi

log "running live-build (this takes a while)…"
cd "$WORK"

# Point lb cache at out/cache
export LB_CACHE="$CACHE"
mkdir -p "$CACHE"

# Prefer sudo -E so LB_CACHE survives
if [[ "$(id -u)" -ne 0 ]] && command -v sudo >/dev/null 2>&1; then
  LB=(sudo -E lb)
else
  LB=(lb)
fi

"${LB[@]}" clean --purge || true
"${LB[@]}" config
set +e
"${LB[@]}" build
LB_RC=$?
set -e

if [[ "$LB_RC" -ne 0 ]]; then
  log "ERROR: lb build failed (exit $LB_RC). Recent log tails:"
  find "$WORK" -type f \( -name '*.log' -o -name 'build.log' \) 2>/dev/null \
    | head -20 \
    | while read -r lf; do
        echo "----- $lf -----"
        tail -n 80 "$lf" || true
      done
  # Also dump apt history if present
  for lf in \
    "$WORK/chroot/var/log/apt/term.log" \
    "$WORK/chroot/var/log/bootstrap.log" \
    "$WORK/build.log"
  do
    if [[ -f "$lf" ]]; then
      echo "----- $lf -----"
      tail -n 100 "$lf" || true
    fi
  done
  exit "$LB_RC"
fi

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
