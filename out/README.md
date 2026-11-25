# Generated output (not checked in)

This directory is created by local builds and CI. Everything here is **gitignored** except this README.

| Subdir | Producer | Contents |
|--------|----------|----------|
| `iso/` | `scripts/distro/build_iso.sh` | `picosoul-*.iso`, checksums |
| `work/` | live-build | Temporary build tree / chroot |
| `cache/` | live-build / apt | Reusable download cache |

Windows agent binaries still go to `../release/` via `build.py` (also gitignored).
