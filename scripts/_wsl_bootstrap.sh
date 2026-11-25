#!/usr/bin/env bash
# Compatibility wrapper → scripts/agent/_wsl_bootstrap.sh
set -euo pipefail
exec "$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/agent/_wsl_bootstrap.sh" "$@"
