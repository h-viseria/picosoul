"""Load TOML config with optional config.local.toml overlay."""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

from osagent.paths import config_dir, project_root


@dataclass
class LocalLLMConfig:
    model_path: str = "models/Qwen3.5-4B-Q4_K_M.gguf"
    model_name: str = "Qwen3.5-4B (Q4_K_M)"
    # Hugging Face resolve URL for first-run download
    download_url: str = (
        "https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/resolve/main/"
        "Qwen3.5-4B-Q4_K_M.gguf"
    )
    download_on_missing: bool = True
    host: str = "127.0.0.1"
    port: int = 8080
    # Larger context needed once many tools are listed in the prompt
    extra_args: str = "-c 8192 -ngl 0"
    api_path: str = "/v1/chat/completions"
    # Native OpenAI tools often 400 on llama.cpp with many/dotted tool ids.
    # False = use TEXT "TOOL name {json}" protocol (more reliable locally).
    native_tools: bool = False


@dataclass
class APILLMConfig:
    base_url: str = "https://api.openai.com/v1"
    model: str = "gpt-4o-mini"
    api_key_env: str = "OPENAI_API_KEY"
    api_key: str = ""

    def resolve_api_key(self) -> str:
        if self.api_key.strip():
            return self.api_key.strip()
        return os.environ.get(self.api_key_env, "").strip()


@dataclass
class AnthropicLLMConfig:
    base_url: str = "https://api.anthropic.com"
    # Examples: claude-sonnet-4-5, claude-opus-4-1 — see Anthropic model docs
    model: str = "claude-sonnet-4-5"
    api_key_env: str = "ANTHROPIC_API_KEY"
    api_key: str = ""
    api_version: str = "2023-06-01"

    def resolve_api_key(self) -> str:
        if self.api_key.strip():
            return self.api_key.strip()
        return os.environ.get(self.api_key_env, "").strip()


@dataclass
class LLMConfig:
    provider: str = "local"  # local | api | anthropic
    max_tokens: int = 1024
    temperature: float = 0.2
    local: LocalLLMConfig = field(default_factory=LocalLLMConfig)
    api: APILLMConfig = field(default_factory=APILLMConfig)
    anthropic: AnthropicLLMConfig = field(default_factory=AnthropicLLMConfig)


@dataclass
class AgentConfig:
    confirm_destructive: bool = True
    platform: str = "auto"
    interactive: bool = True
    # After a tool runs, call the LLM again to rephrase the result.
    # False (default) = reply instantly with the tool message (much snappier).
    narrate_tools: bool = False
    # Build/refresh persistent app+device inventory on startup (background thread).
    inventory_on_startup: bool = True
    # When LLM successfully runs a safe tool for an unmatched phrase, remember it
    # for next time (config/learned_intents.json).
    learn_intents: bool = True


@dataclass
class VoiceConfig:
    # Feature available; still requires typed "start audio"
    enabled: bool = True
    model_path: str = "models/vosk-model-small-en-us-0.15"
    model_url: str = (
        "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip"
    )
    sample_rate: int = 16000
    # None = system default mic
    device: int | None = None


@dataclass
class AppConfig:
    llm: LLMConfig = field(default_factory=LLMConfig)
    agent: AgentConfig = field(default_factory=AgentConfig)
    voice: VoiceConfig = field(default_factory=VoiceConfig)
    raw: dict[str, Any] = field(default_factory=dict)


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    out = dict(base)
    for key, value in overlay.items():
        if key in out and isinstance(out[key], dict) and isinstance(value, dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = value
    return out


def _load_toml(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    with path.open("rb") as fh:
        return tomllib.load(fh)


def load_config(explicit: Path | None = None) -> AppConfig:
    cfg_dir = config_dir()
    primary = explicit or (cfg_dir / "config.toml")
    data = _load_toml(primary)
    local_overlay = cfg_dir / "config.local.toml"
    if local_overlay.is_file() and explicit is None:
        data = _deep_merge(data, _load_toml(local_overlay))

    llm_raw = data.get("llm", {})
    local_raw = llm_raw.get("local", {})
    api_raw = llm_raw.get("api", {})
    anthropic_raw = llm_raw.get("anthropic", {})
    agent_raw = data.get("agent", {})

    default_local = LocalLLMConfig()
    local = LocalLLMConfig(
        model_path=str(local_raw.get("model_path", default_local.model_path)),
        model_name=str(local_raw.get("model_name", default_local.model_name)),
        download_url=str(local_raw.get("download_url", default_local.download_url)),
        download_on_missing=bool(
            local_raw.get("download_on_missing", default_local.download_on_missing)
        ),
        host=str(local_raw.get("host", "127.0.0.1")),
        port=int(local_raw.get("port", 8080)),
        extra_args=str(local_raw.get("extra_args", default_local.extra_args)),
        api_path=str(local_raw.get("api_path", "/v1/chat/completions")),
        native_tools=bool(local_raw.get("native_tools", default_local.native_tools)),
    )
    # Resolve relative model paths against project root
    model_path = Path(local.model_path)
    if not model_path.is_absolute():
        local.model_path = str((project_root() / model_path).resolve())

    api = APILLMConfig(
        base_url=str(api_raw.get("base_url", "https://api.openai.com/v1")).rstrip("/"),
        model=str(api_raw.get("model", "gpt-4o-mini")),
        api_key_env=str(api_raw.get("api_key_env", "OPENAI_API_KEY")),
        api_key=str(api_raw.get("api_key", "")),
    )

    default_anthropic = AnthropicLLMConfig()
    anthropic = AnthropicLLMConfig(
        base_url=str(
            anthropic_raw.get("base_url", default_anthropic.base_url)
        ).rstrip("/"),
        model=str(anthropic_raw.get("model", default_anthropic.model)),
        api_key_env=str(
            anthropic_raw.get("api_key_env", default_anthropic.api_key_env)
        ),
        api_key=str(anthropic_raw.get("api_key", "")),
        api_version=str(
            anthropic_raw.get("api_version", default_anthropic.api_version)
        ),
    )

    llm = LLMConfig(
        provider=str(llm_raw.get("provider", "local")).lower().strip(),
        max_tokens=int(llm_raw.get("max_tokens", 1024)),
        temperature=float(llm_raw.get("temperature", 0.2)),
        local=local,
        api=api,
        anthropic=anthropic,
    )
    agent = AgentConfig(
        confirm_destructive=bool(agent_raw.get("confirm_destructive", True)),
        platform=str(agent_raw.get("platform", "auto")).lower().strip(),
        interactive=bool(agent_raw.get("interactive", True)),
        narrate_tools=bool(agent_raw.get("narrate_tools", False)),
        inventory_on_startup=bool(agent_raw.get("inventory_on_startup", True)),
        learn_intents=bool(agent_raw.get("learn_intents", True)),
    )
    voice_raw = data.get("voice") or {}
    default_voice = VoiceConfig()
    device_raw = voice_raw.get("device", None)
    device: int | None
    if device_raw is None or device_raw == "":
        device = None
    else:
        device = int(device_raw)
    voice = VoiceConfig(
        enabled=bool(voice_raw.get("enabled", default_voice.enabled)),
        model_path=str(voice_raw.get("model_path", default_voice.model_path)),
        model_url=str(voice_raw.get("model_url", default_voice.model_url)),
        sample_rate=int(voice_raw.get("sample_rate", default_voice.sample_rate)),
        device=device,
    )
    return AppConfig(llm=llm, agent=agent, voice=voice, raw=data)
