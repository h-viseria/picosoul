#!/usr/bin/env bash
# Bootstrap OS Agent for WSL (Ubuntu/Debian). Run from repo root or via path.
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

echo "[wsl] repo: $ROOT"
echo "[wsl] $(uname -a)"
python3 --version

# Prefer python3-venv; fall back to --without-pip + get-pip if apt package missing
if [[ ! -x external/venv-linux/bin/python ]]; then
  echo "[wsl] creating external/venv-linux"
  if python3 -m venv external/venv-linux 2>/dev/null; then
    :
  else
    python3 -m venv --without-pip external/venv-linux
    curl -fsSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
    external/venv-linux/bin/python /tmp/get-pip.py
  fi
fi

# shellcheck disable=SC1091
source external/venv-linux/bin/activate
pip install -U pip
pip install -r requirements.txt

mkdir -p config models external/llama.cpp

if [[ -f /mnt/c/projects/os/models/Qwen3.5-4B-Q4_K_M.gguf ]] && [[ ! -f models/Qwen3.5-4B-Q4_K_M.gguf ]]; then
  echo "[wsl] linking Windows GGUF into models/"
  ln -sf /mnt/c/projects/os/models/Qwen3.5-4B-Q4_K_M.gguf models/Qwen3.5-4B-Q4_K_M.gguf || true
fi

if [[ ! -f config/config.local.toml ]]; then
  cat > config/config.local.toml <<'EOF'
# WSL local overrides (gitignored — safe to edit)
[agent]
platform = "linux"
inventory_on_startup = false
EOF
  echo "[wsl] wrote config/config.local.toml — edit llm host if using Windows llama-server"
fi

echo "[wsl] setup done"
echo "  source external/venv-linux/bin/activate"
echo "  export PYTHONPATH=$ROOT/src"
echo "  python -m osagent --list-tools"
echo "  ./scripts/agent/wsl_run.sh --once 'show disk space'"
