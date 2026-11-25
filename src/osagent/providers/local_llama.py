"""Local LLM via llama.cpp server (OpenAI-compatible HTTP)."""

from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

import httpx

from osagent.config import AppConfig
from osagent.paths import external_dir
from osagent.providers.base import ChatMessage, ChatResult, LLMProvider, ToolSpec
from osagent.providers.openai_compat import OpenAICompatProvider


def find_llama_server() -> Path | None:
    """Locate a llama-server binary that can run on this OS (do not pick .exe under Linux)."""
    import sys

    root = external_dir() / "llama.cpp"
    if sys.platform.startswith("linux"):
        names = {"llama-server", "server"}
    elif sys.platform == "darwin":
        names = {"llama-server", "server"}
    else:
        names = {"llama-server.exe", "llama-server", "server.exe", "server"}

    if root.is_dir():
        for path in root.rglob("*"):
            if not path.is_file():
                continue
            if path.name.lower() not in {n.lower() for n in names}:
                continue
            # Skip Windows PE binaries when running under Linux/WSL
            if sys.platform.startswith("linux") and path.suffix.lower() == ".exe":
                continue
            return path
    which = shutil.which("llama-server")
    if which:
        return Path(which)
    if not sys.platform.startswith("linux"):
        which = shutil.which("llama-server.exe")
        if which:
            return Path(which)
    return None


def _wsl_windows_host_ip() -> str | None:
    """Return Windows host IP from /etc/resolv.conf nameserver (WSL2)."""
    try:
        text = Path("/etc/resolv.conf").read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("nameserver"):
            parts = line.split()
            if len(parts) >= 2 and parts[1] not in {"127.0.0.1", "::1"}:
                return parts[1]
    return None


class LocalLlamaProvider(LLMProvider):
    """Starts llama-server if needed, then talks OpenAI-compat HTTP."""

    def __init__(self, cfg: AppConfig) -> None:
        self.cfg = cfg
        self._proc: subprocess.Popen[str] | None = None
        local = cfg.llm.local
        self._base = f"http://{local.host}:{local.port}/v1"
        # llama-server ignores model name; use file stem for clarity
        model_name = Path(local.model_path).name or "local"
        # Keep generation headroom inside the loaded context window
        max_tokens = min(int(cfg.llm.max_tokens), 1024)
        self._inner = OpenAICompatProvider(
            base_url=self._base,
            model=model_name,
            api_key="local",
            max_tokens=max_tokens,
            temperature=cfg.llm.temperature,
            label="local-llama",
            send_native_tools=bool(local.native_tools),
            sanitize_tool_names=True,
            max_tool_desc_chars=120,
        )

    def describe(self) -> str:
        mode = "native-tools" if self.cfg.llm.local.native_tools else "text-TOOL"
        return (
            f"local-llama: model_path={self.cfg.llm.local.model_path} "
            f"endpoint={self._base} mode={mode}"
        )

    def ensure_server(self) -> None:
        if self._healthy():
            return

        model = Path(self.cfg.llm.local.model_path)
        if not model.is_file():
            raise RuntimeError(
                f"Local model not found: {model}\n"
                "Place a GGUF at that path (or change llm.local.model_path), "
                "or set llm.provider = \"api\" in config/config.toml."
            )

        import sys

        server = find_llama_server()
        if server is None:
            hint = ""
            if sys.platform.startswith("linux"):
                host_ip = _wsl_windows_host_ip()
                hint = (
                    "\nWSL/Linux note: only Windows llama-server.exe is bundled; "
                    "it cannot run inside Linux.\n"
                    "Options:\n"
                    "  1) Start release/osagent.exe on Windows (starts llama-server), "
                    "then set in config/config.local.toml:\n"
                    "       [llm.local]\n"
                    f"       host = \"{host_ip or 'WINDOWS_HOST_IP'}\"  "
                    "# from: grep nameserver /etc/resolv.conf\n"
                    "       port = 8080\n"
                    "  2) Put a Linux llama-server binary in external/llama.cpp or PATH\n"
                    "  3) Set llm.provider = \"api\" for a cloud model\n"
                )
            raise RuntimeError(
                "llama-server not found for this OS under external/llama.cpp. "
                "Run: python build.py (on the same OS)" + hint
            )

        local = self.cfg.llm.local
        cmd = [
            str(server),
            "-m",
            str(model),
            "--host",
            local.host,
            "--port",
            str(local.port),
        ]
        extra = local.extra_args.strip().split()
        if extra:
            cmd.extend(extra)

        # Capture stderr so failures are diagnosable (exe on Linux, bad model, …)
        self._proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        deadline = time.time() + 60
        while time.time() < deadline:
            if self._healthy():
                return
            if self._proc.poll() is not None:
                err = ""
                try:
                    err = (self._proc.stderr.read() or "")[:800]
                except Exception:
                    pass
                msg = (
                    f"llama-server exited early (code {self._proc.returncode}). "
                    f"binary={server}"
                )
                if err:
                    msg += f"\n{err.strip()}"
                if sys.platform.startswith("linux") and server.suffix.lower() == ".exe":
                    msg += (
                        "\nCannot run Windows .exe under Linux/WSL — "
                        "point [llm.local] host at the Windows IP or install a Linux build."
                    )
                raise RuntimeError(msg)
            time.sleep(0.4)
        raise RuntimeError("Timed out waiting for llama-server to become ready.")

    def _healthy(self) -> bool:
        try:
            with httpx.Client(timeout=2.0) as client:
                # llama-server serves /health; some builds use /v1/models
                for path in ("/health", "/v1/models"):
                    r = client.get(f"http://{self.cfg.llm.local.host}:{self.cfg.llm.local.port}{path}")
                    if r.status_code < 500:
                        return True
        except (httpx.HTTPError, OSError):
            return False
        return False

    def chat(
        self,
        messages: list[ChatMessage],
        *,
        tools: list[ToolSpec] | None = None,
    ) -> ChatResult:
        self.ensure_server()
        # When native tools are off, still pass None so payload stays small
        use_tools = tools if self.cfg.llm.local.native_tools else None
        return self._inner.chat(messages, tools=use_tools)

    def shutdown(self) -> None:
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()
            try:
                self._proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._proc.kill()
        self._proc = None


def llama_server_available() -> bool:
    return find_llama_server() is not None or shutil.which("llama-server") is not None
