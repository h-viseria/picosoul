#!/usr/bin/env bash
# Compatibility wrapper → scripts/agent/wsl_setup.sh
set -euo pipefail
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/agent/wsl_setup.sh" "$@"
