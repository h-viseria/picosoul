#!/usr/bin/env bash
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"
sed -i 's/\r$//' scripts/agent/*.sh scripts/distro/*.sh 2>/dev/null || true
rm -rf external/venv-linux
python3 -m venv --without-pip external/venv-linux
curl -fsSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
external/venv-linux/bin/python /tmp/get-pip.py
external/venv-linux/bin/pip install -r requirements.txt
export PYTHONPATH="$ROOT/src"
external/venv-linux/bin/python -m osagent --list-tools | head -40
echo '---'
external/venv-linux/bin/python -m osagent --once "show disk space"
echo '---'
external/venv-linux/bin/python -m osagent --once "system info"
