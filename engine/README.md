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
uv run python -m hive_engine --scenario pitch_in_5    # THE live demo (~2:10): 5 agents finish the Whisk startup
uv run python -m hive_engine --scenario pitch_in_5 --fast --auto-human   # ~1 min rehearsal, answers itself
uv run python -m hive_engine --wait                   # no auto-run: serve {"cmd":"start"} (notch Start button) until Ctrl-C
uv run python -m hive_engine --scenario pitch_in_5 --stay   # auto-run once, then keep serving start commands
uv run python tools/ws_tail.py                         # in another terminal: print every bus event
uv run python -m hive_engine.messenger --fake         # iMessage thread, faked: http://127.0.0.1:8769/
uv run python -m hive_engine.messenger --photon       # the real thread via Photon (docs/PHOTON_SETUP.md)
uv run python tools/chat_check.py                      # a script plays the phone against --fake
```
- Bus: `ws://127.0.0.1:8765`
- Static server: `http://127.0.0.1:8766` (`/viewer/index.html`, `/test/form.html`, `/render/slide-N.png`)
- `{"cmd":"start"}` always works (the notch's Start button). A second start while a scenario runs is rejected with a chat line. Start args may also carry `fast`, `auto_human`, `answer_timeout`.

### pitch_in_5 (the live demo)
Runs on a **fresh temp copy** of `demo-world/` every time (the repo copy is never modified; the path is printed at the end). A small server for the copy runs at `http://127.0.0.1:8768` (`/site/`, `/hive/editor.html`, `/hive/composer.html`, `POST /api/test` runs the real `node --test`).

| Window | Agent | What happens |
|---|---|---|
| ① top-left | 🔴 Fixer | Editor page: runs the tests (1 failing), patches the null-referrer bug, finishes student plan / welcome email / session token, re-enables the todo tests → **5/5**. Screenshot → slide 5 |
| ② top-right | 🔵 Web | Landing page: hero, knocked-off button, logo, pricing (from the old **$39** note), wired waitlist (types an email, joins). Screenshots → slides 5 and 7 |
| ③ bottom-left | 🟡 Deck | The Mac app's native Deck Viewer if it reports `deck_viewer` within ~2s of `deck_loaded`, else the Chrome stopgap viewer. Fills slides 3/5/6/7/10, logo on 1/3, market chart on 6; asks **"$4B or $2B?"** |
| ④ bottom-right | 🟣 Social | Composer: rewrites the rambling draft with the live URL and price (311 chars, over the limit on purpose); takes `@Social make it shorter` or trims itself; saves the draft (never posts) |
| overlay | ⚪ Checker | Site **$39** vs deck **$29**: circles both, `link`, asks which is right (8s → $29), the loser fixes it, then re-checks site/deck/post |

Human moments time out to a default (`--answer-timeout`, 8s), so the run never hangs. Answer from the notch, or send `{"cmd":"answer","args":{"choice":"$29/mo"}}` (agent optional) and `{"cmd":"say","args":{"text":"@Social make it shorter"}}`. With `ANTHROPIC_API_KEY`, the Conductor's plan, slide 3 copy and the post come from Claude (`claude-opus-5-5`, 12–15s timeout, canned fallback).

## Layout
| File | What |
|---|---|
| `bus.py` | WebSocket server; broadcasts events; routes commands: start (one run at a time), pause/resume, say (`@Agent …` mentions), answer (to whoever is waiting if no agent), deck_viewer/deck_box (native Deck Viewer geometry); replays spawns + latest countdown/budget to late joiners |
| `agent.py` | `Agent` base: spawn/status/chat/move_to/click_at/typing/highlight/link/ask_human/done, plus pause gating. **Sync rule:** `moving_to` → wait → `click`/`typing` → then the real action |
| `browser_agent.py` | `BrowserAgent`: one Chrome window per agent, positioned via CDP `Browser.setWindowBounds`. `screen_point_for(locator)` = window position + browser-UI offset + element box. `click`, `type`, `point_at`, and `click_xy` (screen point → CDP `Input.dispatchMouseEvent`, for clicks a model picks from a screenshot) |
| `deck_agent.py` / `render.py` | python-pptx step edits (`set_text`, `insert_image`) → LibreOffice headless → PDF → PyMuPDF PNGs; emits `deck_*` events and, given a screen mapper, contract cursor/highlight events on the edited shape |
| `viewer/index.html` | Stopgap Deck Viewer (thumbnail strip, crossfade, zoom, selection handles), driven by the bus |
| `conductor.py` | Request → per-agent tasks via Claude (`claude-opus-5-5`, `ANTHROPIC_API_KEY`); falls back to a canned plan with no key |
| `telegram_bot.py` | Telegram ⇄ bus relay skeleton (`@Web …` → `say`, `@everyone pause`, inline buttons → `answer`). Needs `TELEGRAM_BOT_TOKEN` and `TELEGRAM_CHAT_ID`. **Not run yet.** |
| `scenarios/` | `demo_sim`, `deck_sim`, `pitch_in_5` (+ `pitch_world.py` workspace/server, `pitch_content.py` Claude copy, `pitch_pages/` editor + composer pages) |
| `testpages/form.html` | Local page the demo_sim agents work on; records real click coordinates for verification |
| `tools/ws_tail.py` | Debug client that prints or records events |
| `live/` | 👁 live view. `stream.py`: per-agent Chrome screencast (starts automatically in `BrowserAgent.open`, `HIVE_LIVE=0` to disable). `relay.py`: `ws://127.0.0.1:8767`, follows the bus, maps cursors to page fractions, latest-wins frames. `web/index.html`: phone page at **http://127.0.0.1:8766/live/** (tile grid, cursors, tap to focus + chat log; Telegram WebApp-aware) |
| `messenger/` | iMessage thread ⇄ bus (a bus client). `core.py` routing, `fmt.py` question formatting + reply parsing, `transports.py` fake Messages page (:8769) and Photon REST (send + poll), `web/chat.html`. See CONTRACT "iMessage thread" |
| `memory.py` | Per-agent JSONL memory in `engine/memory/` (texts, call transcripts/summaries), read by the Messenger to answer `@Agent …` after the agent finished |
| `tools/chat_check.py` | Plays the owner's phone against the fake thread: texts `start`, answers questions (number + free text), `@Social make it shorter`, `@Web show me`; prints the transcript |
| `tools/live_check.py` | Run during a scenario: per-agent fps / size / latency over the relay + a headless screenshot of the live page |

## Verified (Oct 17, on this Mac: macOS 26.4, Retina, Chrome)
- **Cursor ↔ real click alignment:** in demo_sim, each agent's final cursor target matched where Chrome actually received the click to within **0.06 pt**. Chrome's reported window position matched the OS window list (CGWindowList) exactly. The page area starts 87 pt below the window's top edge (tabs + toolbar).
- **3 agents in parallel:** each agent drove its own window, 6 real clicks per agent. 69 events reached a client: spawn 3, moving_to 21, click 12, typing 6, highlight 3, status 12, chat 3, done 3, summary 1.
- **Deck rendering:** first LibreOffice render ~3.5s (cold start), then **~0.55–0.6s per re-render** for a 4-slide deck (PDF ~0.53s + PNG ~0.03s). The viewer crossfades and draws selection handles on the edited shape.

- **pitch_in_5 (Oct 17):** 6 runs end to end, 0 agent errors. Tests 2 pass/1 fail/2 todo → **5/5**. $39 vs $29 caught and fixed on the site; post ≤280 chars with the price. 16 deck boxes filled, ~0.6–0.9s per render. **18 real clicks per run, each within ≤1.2 pt of the ghost cursor** (Chrome reports integer click coords; element centers are fractional). Native Deck Viewer path (simulated `deck_viewer`/`deck_box` client): 16 Deck cursor moves landed on the `deck_box` centers (≤0.08 pt), no duplicate selection highlights. Timing: ~2:00 normal with instant answers (~2:10 with timeouts), ~1 min `--fast --auto-human`.

- **Live view (👁):** demo_sim with 3 windows (500×359 viewports), 22s: ~4.5 fps per agent (Chrome only sends frames on repaint; capped at 8), ~27 KB per JPEG, **capture → client latency ~5 ms median, ~11 ms p95** on localhost. Cursor fractions land on the right buttons in the page's frames (headless screenshot checked).

- **iMessage thread (fake transport, Oct 17):** pitch_in_5 started by texting `start`; Deck's market question answered in free text, Checker's price question with `1` ($29 applied on the site), `@Social make it shorter` honored, `@Web show me` answered with the live URL; ~30 texts total, status chatter batched. With a key, Claude mapped "go with the bigger one, matcha plus specialty tea" → $4B and "just matcha" → $2B, and answered "@Cake did they say it'd be ready by 6?" from a stored call transcript. Photon transport written against Photon's OpenAPI but **not run** (no keys).

### Live view on a phone
- **Same Wi-Fi:** run with `HIVE_LIVE_HOST=0.0.0.0` and also bind the static server to `0.0.0.0` (it's `127.0.0.1` now, in `http_server.py`), then open `http://<Mac LAN IP>:8766/live/`. The page connects to port 8767 on the same host. Campus Wi-Fi often blocks device-to-device traffic, so a phone hotspot is safer.
- **Telegram Mini App:** Telegram requires HTTPS. Put both ports behind one tunnel (e.g. `cloudflared`/`ngrok`) and open `https://<tunnel>/live/?ws=wss://<tunnel-for-8767>`. The `?ws=` parameter overrides the relay URL.

## Not done / TODO
- **browser-use is not added.** It pins `websockets==15`, which conflicts with 17. Add it later in a separate process, or pin websockets ≤15.
- **`unoserver` is not set up.** Plain `soffice` is already ~0.55s warm, which is probably fast enough.
- Telegram relay untested against the real API. One bot only; one bot per agent / Photon later.
- pitch_in_5 gaps: no Design/iPad agent (Web uses the finished kit's logo), no real deploy (the "live URL" is the local server), slide 10's QR slot stays empty, Telegram not wired.
- Agent screen positions assume the main display. Multi-display setups are untested.
