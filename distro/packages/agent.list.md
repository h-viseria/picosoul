# OS Agent runtime (in ISO)

- python3
- python3-venv
- python3-pip
- ca-certificates
- curl
- tar
- xz-utils

GGUF models are **not** packaged; downloaded on first launch to persistence.
llama-server (Linux) may be bundled under `/opt/picosoul/external/llama.cpp` by the ISO hook.
