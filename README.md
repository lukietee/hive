# Hive

A swarm of AI agents that works your computer, your phone and the real world, and you manage them by text. Built for LA Hacks 2026.

The full plan is in [`../PROJECT_OVERVIEW.md`](../PROJECT_OVERVIEW.md). The engine ⇄ app protocol is in [`docs/CONTRACT.md`](docs/CONTRACT.md).

## Layout
| Folder | What |
|---|---|
| `mac/` | Swift Package: the notch panel + ghost-cursor overlay (`swift build`, run with `--sim` to preview) |
| `engine/` | Python 3.12 (uv): WebSocket event bus, agents, Playwright browser agent with cursor sync, Deck agent + render, Conductor, Telegram bot skeleton |
| `demo-world/` | The half-built "Pitch in 5" startup: product repo, broken site, `pitch.pptx`, social draft, logo brief |
| `party/` | Surprise-party demo prep: bakery call scripts, voice agent prompt, guest messages, Treasurer rules, recording checklist, the live judge call |
| `docs/` | Contract + notes, including [`docs/LUCAS_TODO.md`](docs/LUCAS_TODO.md) |

## Quick start
```bash
# 1. Engine
cd engine && uv sync && uv run python -m hive_engine --scenario demo_sim

# 2. Mac app (separate terminal)
cd mac && swift build && .build/debug/Hive
#    or preview the UI without the engine:
.build/debug/Hive --sim
```
