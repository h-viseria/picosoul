# OS Agent on WSL (Phase 1 Linux)

Test the **Linux sysadmin agent** from Windows using Ubuntu WSL. Full desktop GUI (antiX) comes later; WSL is for packages, services, disk, network, processes, logs, and shell tools.

## One-time setup

Your default WSL distro may be `docker-desktop` (not useful for apt sysadmin). Use Ubuntu:

```powershell
wsl -l -v
# If Ubuntu-24.04 is missing:
wsl --install -d Ubuntu-24.04
wsl --set-default Ubuntu-24.04
```

Inside Ubuntu:

```bash
cd /mnt/c/projects/os
sudo apt-get update
sudo apt-get install -y python3-venv python3-pip
chmod +x scripts/agent/*.sh scripts/wsl_setup.sh scripts/wsl_run.sh
./scripts/agent/wsl_setup.sh
# (wrappers scripts/wsl_*.sh still work)
```

## Smoke tests (no LLM required)

```bash
cd /mnt/c/projects/os
./scripts/agent/wsl_run.sh --list-tools | head
./scripts/agent/wsl_run.sh --once "show disk space"
./scripts/agent/wsl_run.sh --once "system info"
./scripts/agent/wsl_run.sh --once "firewall status"
./scripts/agent/wsl_run.sh --once "system health"
./scripts/agent/wsl_run.sh --once "list mounts"
./scripts/agent/wsl_run.sh --once "pending updates"
./scripts/agent/wsl_run.sh --once "test connectivity"
```


These hit **deterministic intents + Linux command catalog** (no model).  
Inventory maps packages/services/network → tool ids (`system.inventory.capabilities`).

## Using an LLM from WSL

`external/llama.cpp` currently ships **Windows** `llama-server.exe`. That binary **cannot** run inside WSL. The GGUF can be shared; the server must be Linux-native or run on Windows.

1. **Point at Windows llama-server** (recommended for now):
   - On Windows: start `release/osagent.exe` (or `llama-server.exe` on port 8080).
   - In WSL: `grep nameserver /etc/resolv.conf | awk '{print $2}'`
   - Edit `config/config.local.toml`:

```toml
[llm]
provider = "local"

[llm.local]
host = "172.x.x.x"   # nameserver IP from resolv.conf
port = 8080
```

2. **API provider** — set `provider = "api"` and `OPENAI_API_KEY`.

3. **Native Linux llama-server** — build/install `llama-server` (ELF) into `external/llama.cpp` or PATH.

Everyday questions like disk/home/packages should hit **intents** and never need the LLM.

## Voice

Mic capture in WSL is limited. Prefer typed commands in WSL; use Windows `osagent.exe` for Vosk audio until Phase 2 / antiX desktop.

## What works in WSL vs antiX

| Area | WSL Ubuntu | antiX bare metal / VM |
|------|------------|------------------------|
| apt / dpkg | yes | yes |
| systemctl | often partial | depends (antiX may be sysv — agent falls back to `service`) |
| disk / mem / ps / net | yes | yes |
| GUI settings / xrandr | no | yes |
| Audio / Vosk | usually no | yes |
