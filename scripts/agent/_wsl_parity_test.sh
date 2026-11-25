#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT/src"
PY=./external/venv-linux/bin/python

echo "=== tool count (linux/files catalog) ==="
$PY -m osagent --list-tools | grep -E '^(  )?(linux\.|files\.find|files\.disk)' | wc -l

echo "=== intents ==="
$PY -m osagent --once "firewall status"
echo "---"
$PY -m osagent --once "system health"
echo "---"
$PY -m osagent --once "list mounts"
echo "---"
$PY -m osagent --once "pending updates"
echo "---"
$PY -m osagent --once "test connectivity"
