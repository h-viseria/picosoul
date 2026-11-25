# PicoSoul distro sources (checked in)

Debian **Bookworm** live-build configuration for a **live-only** USB image with persistence hooks.

| Path | Role |
|------|------|
| `branding/` | Name, wallpaper placeholders, GRUB/syslinux splash notes |
| `live-build/` | `auto/`, package lists, hooks (autologin, OS Agent install) |
| `packages/` | Human-readable package groups mirrored into live-build lists |

Build entrypoint: `../scripts/distro/build_iso.sh` → writes `../out/iso/`.

Do **not** commit anything under `../out/`.
