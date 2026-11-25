"""Build the LLM provider from config."""

from __future__ import annotations

from osagent.config import AppConfig
from osagent.providers.anthropic import AnthropicProvider
from osagent.providers.base import LLMProvider
from osagent.providers.local_llama import LocalLlamaProvider
from osagent.providers.openai_compat import OpenAICompatProvider


def create_provider(cfg: AppConfig) -> LLMProvider:
    provider = cfg.llm.provider
    if provider == "local":
        return LocalLlamaProvider(cfg)
    if provider == "api":
        api = cfg.llm.api
        key = api.resolve_api_key()
        if not key:
            raise RuntimeError(
                f"API provider selected but no key found. "
                f"Set {api.api_key_env} or llm.api.api_key in config."
            )
        return OpenAICompatProvider(
            base_url=api.base_url,
            model=api.model,
            api_key=key,
            max_tokens=cfg.llm.max_tokens,
            temperature=cfg.llm.temperature,
            label="api",
        )
    if provider in {"anthropic", "claude"}:
        ant = cfg.llm.anthropic
        key = ant.resolve_api_key()
        if not key:
            raise RuntimeError(
                f"Anthropic provider selected but no key found. "
                f"Set {ant.api_key_env} or llm.anthropic.api_key in config."
            )
        # Claude benefits from a bit more room for tool replies
        max_tokens = max(cfg.llm.max_tokens, 2048)
        return AnthropicProvider(
            api_key=key,
            model=ant.model,
            base_url=ant.base_url,
            max_tokens=max_tokens,
            temperature=cfg.llm.temperature,
            api_version=ant.api_version,
        )
    raise RuntimeError(
        f"Unknown llm.provider: {provider!r} "
        "(use 'local', 'api', or 'anthropic')"
    )
