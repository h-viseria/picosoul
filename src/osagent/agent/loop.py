"""Agent loop: deterministic intents + chat + TOOL protocol / native tools."""

from __future__ import annotations

import json
import re
from typing import Any

from osagent.agent.intents import looks_like_action_without_tool, match_intent
from osagent.config import AppConfig
from osagent.platform_info import HostOS
from osagent.providers.base import ChatMessage, LLMProvider
from osagent.tools.registry import ToolRegistry

# Models without reliable tool-calling can emit this line:
# TOOL files.list_dir {"path": "C:/Users"}
# Also accept bare TOOL name (no args) → treated as {}.
_TOOL_LINE = re.compile(
    r"TOOL\s+(?P<name>[a-zA-Z0-9_.-]+)(?:\s+(?P<args>\{.*?\}))?\s*$",
    re.MULTILINE,
)

SYSTEM_TEMPLATE = """You are OS Agent, a desktop / sysadmin assistant.
Host platform: {platform}

CRITICAL:
- To change the system you MUST call a tool. Never claim you acted unless a tool ran.
- With text tool mode, your ENTIRE reply must be exactly one line:
TOOL <tool_id> {{"param": value}}
- Only after tools run may you speak to the user in plain language.

Available tools:
{tool_list}

{routing_hints}
"""

_ROUTING_WINDOWS = """Routing hints (Windows):
- brightness N% → windows.display.set_brightness
- volume up/down → windows.volume.adjust; volume N% → windows.volume.set_percent
- reset/restore volume → windows.volume.reset
- tell/show battery|uptime|disk|brightness|volume → matching status tool
- CLI only: 'start audio' / 'stop audio' for Vosk (not a tool)
- web search / site → web.open / web.search
- desktop app → app.launch; recent docs → files.open_recent
- printers / display / bluetooth / volume / battery → windows.* tools
- If no catalog tool fits → windows.powershell.run
"""

_ROUTING_LINUX = """Routing hints (Linux / WSL / Debian / antiX):
- Prefer catalog/intents over LLM for everyday admin (disk, packages, services, firewall, mounts, docker, health).
- system info / uptime / disk / memory / cpu → linux.system.* / linux.disk.free / files.disk_free / linux.memory.status
- health / storage / memory / cpu reports → linux.system.health_report|storage_report|memory_report|cpu_report
- battery → linux.battery.status; bluetooth → linux.bluetooth.list; printers → linux.printers.*
- brightness / resolution / contrast → linux.display.*; volume/mute → linux.volume.*
- apt search/list/install/remove/update/upgradable → linux.packages.*
- service status/start/stop/restart/list/failed → linux.service.*
- processes / top / kill → linux.process.* / linux.processes.top
- network interfaces / routes / ports / ping / dns / wifi / connectivity → linux.network.*
- firewall status → linux.firewall.status; mounts → linux.mounts.list; cron → linux.cron.list
- logs → linux.logs.tail or linux.logs.journal_search; docker ps → linux.docker.ps
- find recent/named files → files.find_recent / files.find_by_name
- users / who / last logins → linux.users.* / linux.users.last_logins
- inventory → system.inventory.status|capabilities|refresh
- If no catalog tool fits → linux.shell.run {{"command":"...","rationale":"..."}}
- Destructive apt remove / kill / reboot / shutdown require confirmation.
- WSL often lacks host BT/audio/backlight/printers — tools still answer with a clear message.
"""

_FORCE_TOOL_MSG = (
    "You claimed you would act but did not call a tool. "
    "Reply with ONLY one line, no other text:\n"
    'TOOL <tool_id> {"param": value}\n'
    "Pick the correct tool for the user's last request."
)


class Agent:
    def __init__(
        self,
        cfg: AppConfig,
        provider: LLMProvider,
        tools: ToolRegistry,
        platform_name: str,
    ) -> None:
        self.cfg = cfg
        self.provider = provider
        self.tools = tools
        self.platform_name = platform_name
        self.messages: list[ChatMessage] = [
            ChatMessage(role="system", content=self._system_prompt()),
        ]
        # When set, a successful LLM tool call may be saved as a learned intent
        self._learn_utterance: str | None = None

    def _resolve_platform_tool(self, tool_id: str) -> str | None:
        """Map windows.* ↔ linux.* when the peer tool exists on this host."""
        if self.tools.get(tool_id):
            return tool_id
        host = self._host()
        if host == HostOS.LINUX and tool_id.startswith("windows."):
            alt = "linux." + tool_id[len("windows.") :]
            if self.tools.get(alt):
                return alt
        if host == HostOS.WINDOWS and tool_id.startswith("linux."):
            alt = "windows." + tool_id[len("linux.") :]
            if self.tools.get(alt):
                return alt
        return None

    def _host(self) -> HostOS:
        name = (self.platform_name or "").lower()
        if name == "linux":
            return HostOS.LINUX
        if name == "windows":
            return HostOS.WINDOWS
        if name in {"macos", "darwin"}:
            return HostOS.MACOS
        return HostOS.UNKNOWN

    def _system_prompt(self) -> str:
        lines = []
        for tool in self.tools.list_tools():
            desc = (tool.description or "").replace("\n", " ").strip()
            if len(desc) > 90:
                desc = desc[:87] + "..."
            lines.append(f"- {tool.id}: {desc}")
        hints = _ROUTING_LINUX if self._host() == HostOS.LINUX else _ROUTING_WINDOWS
        return (
            SYSTEM_TEMPLATE.replace("{platform}", self.platform_name)
            .replace("{tool_list}", "\n".join(lines) if lines else "(none)")
            .replace("{routing_hints}", hints)
        )

    def handle_user(self, text: str) -> str:
        self.messages.append(ChatMessage(role="user", content=text))
        self._learn_utterance = None

        # 1) Reliable path for clear desktop commands (local models often skip tools)
        intent = match_intent(text, host=self._host())
        if intent:
            tool_id = self._resolve_platform_tool(intent.tool_id)
            if tool_id and self.tools.get(tool_id):
                # Learned hits: bump usage; do not re-learn
                if intent.label.startswith("learned"):
                    try:
                        from osagent.agent.learned_intents import bump_hit

                        bump_hit(text)
                    except Exception:
                        pass
                return self._execute_tool(
                    tool_id,
                    intent.args,
                    assistant_note=f"TOOL {tool_id} {json.dumps(intent.args)}",
                )
            # Known desktop intent but no tool on this OS — never fall through to LLM
            if intent.tool_id.startswith(("windows.", "linux.")):
                self._learn_utterance = None
                msg = (
                    f"No tool available for “{intent.label}” "
                    f"({intent.tool_id}) on this platform."
                )
                self.messages.append(ChatMessage(role="assistant", content=msg))
                return msg

        # 2) Model path — candidate for auto-learn if a safe tool succeeds
        self._learn_utterance = text
        result = self.provider.chat(
            self.messages,
            tools=self.tools.as_provider_specs(),
        )

        if result.tool_calls:
            return self._run_native_tools(result)

        content = result.content or ""
        match = _TOOL_LINE.search(content)
        if match:
            return self._run_text_tool(match.group("name"), match.group("args"), content)

        # 3) Model talked about acting but issued no tool — force one retry
        if looks_like_action_without_tool(content):
            self.messages.append(ChatMessage(role="assistant", content=content))
            self.messages.append(ChatMessage(role="user", content=_FORCE_TOOL_MSG))
            retry = self.provider.chat(self.messages, tools=self.tools.as_provider_specs())
            if retry.tool_calls:
                return self._run_native_tools(retry)
            retry_content = retry.content or ""
            match = _TOOL_LINE.search(retry_content)
            if match:
                return self._run_text_tool(
                    match.group("name"), match.group("args"), retry_content
                )
            # Last resort: try intent again from original user text
            if intent and self.tools.get(intent.tool_id):
                return self._execute_tool(intent.tool_id, intent.args)
            fail = (
                "I described the action but failed to call a tool. "
                "Please retry, or use a clearer command like "
                "'set brightness to 10%'."
            )
            self._learn_utterance = None
            self.messages.append(ChatMessage(role="assistant", content=fail))
            return fail

        self._learn_utterance = None
        self.messages.append(ChatMessage(role="assistant", content=content))
        return content.strip() or "(empty model response)"

    def _user_facing_tool_reply(self, name: str, tr: Any) -> str:
        """Short reply from the tool itself — no second LLM round-trip."""
        msg = (tr.message or "").strip()
        data = tr.data if isinstance(getattr(tr, "data", None), dict) else {}
        items = data.get("result") if data else None
        if items is None and isinstance(data.get("candidates"), list):
            items = data.get("candidates")
        if isinstance(items, dict):
            items = [items]

        # Label-only catalog replies ("Battery status") → expand from JSON
        label_only = bool(msg) and "\n" not in msg and len(msg.split()) <= 5
        if label_only and isinstance(items, list) and items:
            try:
                from osagent.tools.catalog.loader import _format_catalog_message

                expanded = _format_catalog_message(name, msg, items)
                if expanded and expanded != msg:
                    return expanded
            except Exception:
                pass

        # Don't replace a successful open/folder message with a candidate dump
        if data.get("opened") or data.get("opened_folder"):
            if msg:
                return msg
        if msg.lower().startswith("opened"):
            return msg

        if isinstance(items, list) and items:
            if "\n" not in msg or not any(
                line.strip()[:1].isdigit() for line in msg.splitlines()[1:]
            ):
                lines: list[str] = []
                for i, it in enumerate(items[:30], 1):
                    if not isinstance(it, dict):
                        continue
                    path = str(it.get("path") or it.get("Path") or "")
                    when = it.get("last_write") or it.get("LastWriteTime") or ""
                    if path and when:
                        lines.append(f"{i}. {path}\n    modified {when}")
                    elif path:
                        lines.append(f"{i}. {path}")
                if lines:
                    header = msg.split("\n", 1)[0] if msg else f"{len(lines)} file(s)"
                    if header and "\\" not in header and "/" not in header:
                        header = f"{len(lines)} newest file(s)"
                    return header + ":\n" + "\n".join(lines)
        if msg:
            return msg
        return f"{'Done' if tr.ok else 'Failed'}: {name}"

    def _maybe_learn(self, name: str, args: dict[str, Any], *, ok: bool) -> None:
        if not ok or not self._learn_utterance:
            return
        if not getattr(self.cfg.agent, "learn_intents", True):
            self._learn_utterance = None
            return
        try:
            from osagent.agent.learned_intents import record_learned, should_learn_tool

            tool = self.tools.get(name)
            if should_learn_tool(tool, args):
                if record_learned(self._learn_utterance, name, args, source="llm"):
                    print(
                        f"[learn] remembered intent → {name} "
                        f"for “{self._learn_utterance.strip()}”",
                        flush=True,
                    )
        except Exception:
            pass
        self._learn_utterance = None

    def _execute_tool(
        self,
        name: str,
        args: dict[str, Any],
        *,
        assistant_note: str | None = None,
    ) -> str:
        tr = self.tools.run(
            name,
            args,
            confirm_destructive=self.cfg.agent.confirm_destructive,
        )
        self._maybe_learn(name, args, ok=bool(tr.ok))
        note = assistant_note or f"TOOL {name} {json.dumps(args)}"
        self.messages.append(ChatMessage(role="assistant", content=note))

        # Fast path (default): action already finished — don't wait on another LLM call
        if not getattr(self.cfg.agent, "narrate_tools", False):
            reply = self._user_facing_tool_reply(name, tr)
            self.messages.append(ChatMessage(role="assistant", content=reply))
            return reply

        tool_line = f"{name}: {tr.message}"
        if tr.data:
            raw = json.dumps(tr.data, ensure_ascii=True)
            if len(raw) > 800:
                raw = raw[:800] + "…"
            tool_line += f" | {raw}"

        self.messages.append(
            ChatMessage(
                role="user",
                content=(
                    f"Tool result:\n{tool_line}\n"
                    "Reply to the user in one or two short sentences. "
                    "If the tool failed, say so plainly."
                ),
            )
        )
        follow = self.provider.chat(self.messages, tools=None)
        if not tr.ok:
            reply = tr.message
        else:
            reply = (follow.content or tool_line).strip()
            if looks_like_action_without_tool(reply) and "TOOL" not in reply:
                reply = tr.message
        self.messages.append(ChatMessage(role="assistant", content=reply))
        return reply

    def _run_native_tools(self, result: Any) -> str:
        parts: list[str] = []
        if result.content:
            parts.append(result.content)
        summary_bits: list[str] = []
        any_ok = False
        last_fail = ""
        for call in result.tool_calls:
            fn = call.get("function") or {}
            name = fn.get("name") or call.get("name") or ""
            raw_args = fn.get("arguments") or "{}"
            try:
                args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
            except json.JSONDecodeError:
                args = {}
            tr = self.tools.run(
                name,
                args,
                confirm_destructive=self.cfg.agent.confirm_destructive,
            )
            if tr.ok:
                any_ok = True
                # Learn from first successful tool in the batch
                if self._learn_utterance:
                    self._maybe_learn(name, args, ok=True)
            else:
                last_fail = tr.message
            summary_bits.append(self._user_facing_tool_reply(name, tr))
            line = f"{name}: {tr.message}"
            parts.append(line)

        if self._learn_utterance and not any_ok:
            self._learn_utterance = None

        # Fast path: return tool messages immediately
        if not getattr(self.cfg.agent, "narrate_tools", False):
            if not any_ok and last_fail:
                reply = last_fail
            else:
                reply = "\n".join(summary_bits).strip() or "Done."
            self.messages.append(ChatMessage(role="assistant", content=reply))
            return reply

        assistant_text = "\n".join(parts).strip()
        self.messages.append(ChatMessage(role="assistant", content=assistant_text))
        self.messages.append(
            ChatMessage(
                role="user",
                content=(
                    "Tool results:\n"
                    + "\n".join(summary_bits)
                    + "\nReply to the user in one or two short sentences. "
                    "If a tool failed, say so plainly — never claim it succeeded."
                ),
            )
        )
        follow = self.provider.chat(self.messages, tools=None)
        reply = (follow.content or assistant_text).strip()
        if not any_ok and last_fail:
            reply = last_fail
        self.messages.append(ChatMessage(role="assistant", content=reply))
        return reply

    def _run_text_tool(self, name: str, args_json: str | None, raw_content: str) -> str:
        raw = (args_json or "").strip() or "{}"
        try:
            args = json.loads(raw)
        except json.JSONDecodeError:
            args = {}
        if not isinstance(args, dict):
            args = {}
        return self._execute_tool(name, args, assistant_note=raw_content)
