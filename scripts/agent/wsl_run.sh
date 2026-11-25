#!/usr/bin/env bash
# Run OS Agent inside WSL. Usage: ./scripts/agent/wsl_run.sh [--list-tools] [--once 'prompt'] …
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

if [[ ! -x external/venv-linux/bin/python ]]; then
  echo "Run ./scripts/agent/wsl_setup.sh first" >&2
  exit 1
fi

export PYTHONPATH="$ROOT/src${PYTHONPATH:+:$PYTHONPATH}"
exec external/venv-linux/bin/python -m osagent "$@"
