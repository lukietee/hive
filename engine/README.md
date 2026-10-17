# Hive engine

The Python side of Hive. It runs the agents, drives real Chrome windows over DevTools, edits the deck, and broadcasts every action on an event bus. The Mac app uses those events to draw the ghost cursors. The engine ⇄ app contract is in [`../docs/CONTRACT.md`](../docs/CONTRACT.md).

## Setup
```bash
cd hive/engine
uv sync                                 # Python 3.12 venv + deps
brew install --cask libreoffice         # needed for deck rendering (already installed on this Mac)
```
Chrome: the engine launches your installed **Google Chrome** with a fresh temporary profile; it never uses your real profile. If Chrome isn't found it falls back to Playwright's Chromium, which needs `uv run playwright install chromium`.

## Run
```bash
uv run python -m hive_engine --scenario demo_sim      # 3 agents, 3 real Chrome windows, synced cursor events
uv run python -m hive_engine --scenario deck_sim      # Deck agent fills a sample deck; viewer opens in Chrome
uv run python -m hive_engine --scenario demo_sim --wait   # wait for {"cmd":"start"} from a client (the Mac app does NOT send one yet — omit --wait; use --delay N to give the app time to connect)
uv run python tools/ws_tail.py                         # in another terminal: print every bus event
```
- Bus: `ws://127.0.0.1:8765`
- Static server: `http://127.0.0.1:8766` (`/viewer/index.html`, `/test/form.html`, `/render/slide-N.png`)

## Layout
| File | What |
|---|---|
| `bus.py` | WebSocket server; broadcasts events; routes commands (start/pause/resume/say/answer) to agent inboxes; replays spawns to late joiners |
| `agent.py` | `Agent` base: spawn/status/chat/move_to/click_at/typing/highlight/link/ask_human/done, plus pause gating. **Sync rule:** `moving_to` → wait → `click`/`typing` → then the real action |
| `browser_agent.py` | `BrowserAgent`: one Chrome window per agent, positioned via CDP `Browser.setWindowBounds`. `screen_point_for(locator)` = window position + browser-UI offset + element box. `click`, `type`, `point_at`, and `click_xy` (screen point → CDP `Input.dispatchMouseEvent`, for clicks a model picks from a screenshot) |
| `deck_agent.py` / `render.py` | python-pptx step edits (`set_text`, `insert_image`) → LibreOffice headless → PDF → PyMuPDF PNGs; emits `deck_*` events and, given a screen mapper, contract cursor/highlight events on the edited shape |
| `viewer/index.html` | Stopgap Deck Viewer (thumbnail strip, crossfade, zoom, selection handles), driven by the bus |
| `conductor.py` | Request → per-agent tasks via Claude (`claude-opus-5-5`, `ANTHROPIC_API_KEY`); falls back to a canned plan with no key |
| `telegram_bot.py` | Telegram ⇄ bus relay skeleton (`@Web …` → `say`, `@everyone pause`, inline buttons → `answer`). Needs `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`. **Not run yet.** |
| `scenarios/` | `demo_sim`, `deck_sim` (working); `pitch_in_5` (outlined stub) |
| `testpages/form.html` | Local page the demo_sim agents work on; records real click coordinates for verification |
| `tools/ws_tail.py` | Debug client that prints or records events |

## Verified (Oct 17, on this Mac: macOS 26.4, Retina, Chrome)
- **Cursor ↔ real click alignment:** in demo_sim, each agent's final cursor target matched where Chrome actually received the click to within **0.06 pt**. Chrome's reported window position matched the OS window list (CGWindowList) exactly. The page area starts 87 pt below the window's top edge (tabs + toolbar).
- **3 agents in parallel:** each agent drove its own window, 6 real clicks per agent. 69 events reached a client: spawn 3, moving_to 21, click 12, typing 6, highlight 3, status 12, chat 3, done 3, summary 1.
- **Deck rendering:** first LibreOffice render ~3.5s (cold start), then **~0.55–0.6s per re-render** for a 4-slide deck (PDF ~0.53s + PNG ~0.03s). The viewer crossfades and draws selection handles on the edited shape.

## Not done / TODO
- **Contract additions needed** (in `docs/CONTRACT.md`): `deck_loaded`, `deck_focus`, `deck_slide_updated`. The Mac app should ignore unknown event types.
- **browser-use is not added.** It pins `websockets==15`, which conflicts with 17. Add it later in a separate process, or pin websockets ≤15.
- **`unoserver` is not set up.** Plain `soffice` is already ~0.55s warm, which is probably fast enough.
- Telegram relay untested against the real API. One bot only; one bot per agent / Photon later.
- Conductor not wired into the scenarios. The `pitch_in_5` scenario is an outline only.
- Agent screen positions assume the main display. Multi-display setups are untested.
