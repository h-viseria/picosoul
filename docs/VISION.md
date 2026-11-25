# PicoSoul vision

PicoSoul explores a **compact, AI-native personal computer experience**: small foundation, local intelligence, explicit security boundaries, and one launcher for web/native/compatibility apps.

Full product narrative: https://picoai.org/picosoul/  
Canonical GitHub README: https://github.com/h-viseria/picosoul

## How this repo relates

| Layer | In this repo |
|-------|----------------|
| Experience / AI | `src/osagent/` — intents, tools, local LLM, Linux/Windows |
| Distro | `distro/` — Bookworm live USB, PicoSoul branding |
| Orchestration (future) | Agent + first-run install packs / cloud AI config |

Phase focus now: **prove the agent + ship a &lt;1 GB live ISO**, then grow app packs and isolation.
