"""OS Agent entry point."""

from __future__ import annotations

import argparse
import sys
import threading
from typing import Any

from osagent import __version__
from osagent.agent.loop import Agent
from osagent.config import load_config
from osagent.model_download import ensure_local_model
from osagent.platform_info import platform_summary, resolve_platform
from osagent.providers.factory import create_provider
from osagent.providers.local_llama import LocalLlamaProvider
from osagent.tools.registry import build_registry
from osagent.voice import VoiceSession, is_start_audio_command, is_stop_audio_command


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(prog="osagent", description="Desktop OS Agent")
    p.add_argument("--version", action="store_true", help="Print version and exit")
    p.add_argument("--config", type=str, default=None, help="Path to config.toml")
    p.add_argument(
        "--once",
        type=str,
        default=None,
        help="Run a single prompt and exit (non-interactive)",
    )
    p.add_argument(
        "--list-tools",
        action="store_true",
        help="List registered tools for this platform and exit",
    )
    p.add_argument(
        "--download-model",
        action="store_true",
        help="Download the configured local GGUF if missing (no prompt)",
    )
    p.add_argument(
        "--force-download-model",
        action="store_true",
        help="Re-download the configured local GGUF even if present",
    )
    return p.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.version:
        print(f"osagent {__version__}")
        return 0

    from pathlib import Path

    cfg = load_config(Path(args.config) if args.config else None)
    host = resolve_platform(cfg.agent.platform)
    tools = build_registry(host)

    if args.list_tools:
        print(f"Platform: {host.value}")
        for tool in tools.list_tools():
            print(f"  {tool.id}  [{tool.confirm.value}]  {tool.description}")
        return 0

    print(f"osagent {__version__} | {platform_summary()}")
    print(f"platform catalog: {host.value}")
    print(f"llm.provider: {cfg.llm.provider}")

    # --once with a deterministic intent: run the tool without starting an LLM
    # (useful for WSL smoke tests before llama-server is wired)
    if args.once is not None:
        from osagent.agent.intents import match_intent

        intent = match_intent(args.once, host=host)
        if intent and tools.get(intent.tool_id):
            print(f"intent: {intent.label} → {intent.tool_id}")
            tr = tools.run(
                intent.tool_id,
                intent.args,
                confirm_destructive=cfg.agent.confirm_destructive,
            )
            print(tr.message)
            return 0 if tr.ok else 1

    if cfg.llm.provider == "local":
        ok = ensure_local_model(
            cfg,
            force_download=args.force_download_model,
            auto_yes=args.download_model or args.force_download_model,
        )
        if not ok:
            print(
                "Cannot start local provider without a model. "
                "Re-run and accept the download, use --download-model, "
                "or set llm.provider = \"api\".",
                file=sys.stderr,
            )
            return 1

    provider: Any
    try:
        provider = create_provider(cfg)
    except Exception as exc:  # noqa: BLE001
        print(f"Failed to create LLM provider: {exc}", file=sys.stderr)
        return 1

    print(f"llm: {provider.describe()}")

    # Persistent app/device inventory — build on first run, enrich afterward
    if getattr(cfg.agent, "inventory_on_startup", True):
        try:
            from osagent.inventory import get_inventory

            inv = get_inventory()
            st = inv.status()

            def _inv_progress(msg: str) -> None:
                print(f"  [inventory] {msg}")

            if inv.needs_build():
                print(
                    f"Building system inventory in background → {st['path']} "
                    "(apps, defaults, devices, capabilities)…"
                )
                inv.ensure_built_async(
                    force=True,
                    tool_specs=[
                        {"id": t.id, "description": t.description or ""}
                        for t in tools.list_tools()
                    ],
                    on_progress=_inv_progress,
                )
            elif inv.needs_capabilities():
                print(
                    f"inventory: {st.get('apps_count', 0)} apps — "
                    "caching hardware/app capabilities in background…"
                )
                inv.ensure_built_async(on_progress=_inv_progress)
            else:
                caps = st.get("capabilities") or {}
                print(
                    f"inventory: {st.get('apps_count', 0)} apps, "
                    f"{caps.get('supported_settings', 0)} hardware settings, "
                    f"{caps.get('installed_known_apps', 0)} app command profiles "
                    f"(built {st.get('built_at')}) @ {st['path']}"
                )
        except Exception as exc:  # noqa: BLE001
            print(f"inventory: unavailable ({exc})")

    agent = Agent(cfg, provider, tools, host.value)

    try:
        if args.once is not None:
            print(agent.handle_user(args.once))
            return 0

        if not cfg.agent.interactive:
            print("Interactive mode disabled (agent.interactive = false).")
            return 0

        print(
            "Type a command (or 'quit'). "
            "Voice: 'start audio' / 'stop audio' (needs requirements-voice.txt)."
        )
        agent_lock = threading.Lock()
        voice: VoiceSession | None = None
        if cfg.voice.enabled:
            voice = VoiceSession(
                model_path=cfg.voice.model_path,
                model_url=cfg.voice.model_url,
                sample_rate=cfg.voice.sample_rate,
                device=cfg.voice.device,
            )

        def _run_utterance(text: str, *, source: str) -> None:
            prefix = f"[{source}] " if source else ""
            if source == "voice":
                print(f"\n{prefix}{text}")
            try:
                with agent_lock:
                    reply = agent.handle_user(text)
                print(reply)
            except Exception as exc:  # noqa: BLE001
                print(f"Error: {exc}", file=sys.stderr)
            if source == "voice" and voice and voice.running:
                print("> ", end="", flush=True)

        def _on_voice_utterance(text: str) -> None:
            _run_utterance(text, source="voice")

        def _on_voice_stopped() -> None:
            print("[voice] stopped — type 'start audio' to listen again")

        def _on_voice_error(exc: BaseException) -> None:
            print(f"[voice] failed: {exc}", file=sys.stderr)

        try:
            while True:
                try:
                    line = input("> ").strip()
                except (EOFError, KeyboardInterrupt):
                    print()
                    break
                if not line:
                    continue
                if line.lower() in {"quit", "exit", "/bye", ":q"}:
                    break
                if line.lower() in {"/tools", "list tools"}:
                    for tool in tools.list_tools():
                        print(f"  {tool.id}")
                    continue

                if is_start_audio_command(line):
                    if voice is None or not cfg.voice.enabled:
                        print(
                            "Voice disabled. Set [voice] enabled=true and install "
                            "requirements-voice.txt (vosk, sounddevice)."
                        )
                        continue
                    if voice.running:
                        print("Already listening. Type 'stop audio' to stop.")
                        continue
                    try:
                        voice.start(
                            _on_voice_utterance,
                            on_stopped=_on_voice_stopped,
                            on_error=_on_voice_error,
                        )
                        print(
                            "Audio started. Speak commands; type or say "
                            "'stop audio' when done."
                        )
                    except Exception as exc:  # noqa: BLE001
                        print(f"Could not start audio: {exc}", file=sys.stderr)
                    continue

                if is_stop_audio_command(line):
                    if voice is None or not voice.running:
                        print("Audio is not running.")
                        continue
                    voice.stop()
                    continue

                _run_utterance(line, source="text")
        finally:
            if voice is not None and voice.running:
                voice.stop()
        return 0
    finally:
        if isinstance(provider, LocalLlamaProvider):
            provider.shutdown()


if __name__ == "__main__":
    raise SystemExit(main())
