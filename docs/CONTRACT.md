# Hive — Engine ⇄ App Contract

This file is shared by the Mac app (`mac/`), the engine (`engine/`) and any chat or streaming clients. **Change it here first**, then update both sides.

## Transport
- The engine runs a WebSocket server at **`ws://127.0.0.1:8765`**.
- Clients (the Mac app, a debug page, later the relay) connect and receive every event as one **JSON object per message**.
- Clients can also send **commands** (below) to the engine over the same socket.

## Coordinates
- Every `x`, `y`, `w`, `h` is in **macOS global screen points**:
  - the origin is the **top-left** of the main display;
  - y grows downward (the same space as `CGEvent` and the Accessibility API).
- The Mac app converts these to AppKit's bottom-left coordinates itself.

## Agents
| id | name | color (hex) | emoji |
|---|---|---|---|
| `builder` | Builder | `#34C759` | 🟢 |
| `fixer` | Fixer | `#FF3B30` | 🔴 |
| `web` | Web | `#0A84FF` | 🔵 |
| `deck` | Deck | `#FFCC00` | 🟡 |
| `social` | Social | `#AF52DE` | 🟣 |
| `checker` | Checker | `#E5E5EA` | ⚪ |
| `design` | Design | `#FF9F0A` | 🎨 |
| `treasurer` | Treasurer | `#30D158` | 💰 |
| `guests` | Guests | `#FF375F` | 💌 |
| `cake` | Cake | `#FFD60A` | 🎂 |
| `food` | Food | `#FF6B35` | 🍕 |

## Event envelope (engine → clients)
```json
{ "v": 1, "ts": 1792260000.123, "agent": "web", "type": "moving_to", "data": { ... } }
```

| type | data | Mac app behavior |
|---|---|---|
| `agent_spawn` | `{ "name", "color", "emoji", "x", "y" }` | Create the cursor at (x,y), or under the notch if omitted; add a pill to the notch |
| `agent_status` | `{ "text", "progress": 0..1? }` | Update the pill text / progress ring |
| `moving_to` | `{ "x", "y", "duration_ms": 300, "label"? }` | Glide the cursor to (x,y) with easing |
| `click` | `{ "x", "y" }` | Click ripple at (x,y) |
| `typing` | `{ "x", "y", "text" }` | Show a small typing indicator by the cursor |
| `highlight` | `{ "x", "y", "w", "h", "style": "circle" \| "box" \| "select" }` | Draw a circle, box or selection handles (fade out after 2.5s unless `"sticky": true`) |
| `link` | `{ "from": [x,y], "to": [x,y], "text"? }` | Draw a line between two points (Checker conflicts) |
| `needs_human` | `{ "question", "options": [..] }` | Pulse the cursor; show the question in the notch |
| `chat` | `{ "text" }` | (For the chat relay; the app may show it in the notch) |
| `agent_done` | `{ "summary"? }` | Cursor flies back into the notch and disappears |
| `swarm_summary` | `{ "title", "lines": [..] }` | Show the summary card in the notch |
| `countdown` | `{ "seconds_left" }` | Update the notch timer |
| `budget` | `{ "spent", "total", "caps": { agent: cap } }` | Update the notch budget bar (party demo) |
| `deck_loaded` | `{ "slides", "base", "version" }` | Deck Viewer loads the slide PNGs from `base` (e.g. `http://127.0.0.1:8766/...`) |
| `deck_focus` | `{ "slide", "box": [x, y, w, h], "label" }` | Deck Viewer scrolls to and zooms the slide; box is in **fractions of the slide** (0–1), for the cursor + selection handles |
| `deck_slide_updated` | `{ "slide", "version", "render_ms" }` | Deck Viewer crossfades to the re-rendered slide PNG |

## Commands (clients → engine)
```json
{ "v": 1, "cmd": "start", "args": { "scenario": "pitch_in_5" } }
```
| cmd | args |
|---|---|
| `start` | `{ "scenario": "pitch_in_5" \| "party" \| "demo_sim", "fast"?, "auto_human"?, "answer_timeout"? }`. Always accepted; while a scenario runs, a second start is rejected with a `chat` line (agent `null`) |
| `pause` / `resume` | `{ "agent"?: id }` (all agents if omitted) |
| `say` | `{ "agent"?: id, "text" }`: a message from the human (chat / @mention) |
| `answer` | `{ "agent": id, "choice" }`: the reply to `needs_human` |
| `deck_viewer` | `{ "x", "y", "w", "h" }`: the native Deck Viewer's big-slide rect at 1× zoom, in screen points. Sent when the viewer appears, moves or resizes, and on (re)connect |
| `deck_box` | `{ "slide", "label", "x", "y", "w", "h" }`: reply to each `deck_focus`, the focused box's **final on-screen rect after the viewer's zoom**, in screen points. Arrives within ~50 ms of `deck_focus` |

### Deck cursor flow
The Deck Viewer zooms toward small boxes, so the engine can't compute the screen point from the slide fractions alone. The flow:
1. The engine emits `deck_focus`.
2. The engine waits for the matching `deck_box` (same `slide`; time out after ~0.5 s and fall back to mapping the box fractions onto the last `deck_viewer` rect).
3. The engine runs the usual sync rule on the box center: `moving_to`, wait, then `typing`/`click`.

In `--sim` (no engine), the viewer drives the Deck cursor itself with the same events. When `deck_box` is available, the engine should skip its own `highlight` of style `select` for deck edits, since the viewer already draws the selection handles.

## Sync rule
Before a real action, an agent emits `moving_to`, waits `duration_ms`, emits `click` (or `typing`), **then** performs the action. The cursor always arrives before the app reacts.

## Live view relay (👁, phone / Telegram Mini App)
A separate socket so video never slows the main bus. Page: **`http://127.0.0.1:8766/live/`**. Relay: **`ws://127.0.0.1:8767`** (`HIVE_LIVE_HOST` / `HIVE_LIVE_PORT` to change; `HIVE_LIVE=0` turns streaming off).
The relay is a bus client: it follows `ws://127.0.0.1:8765`, and each `BrowserAgent` streams its page to it with Chrome's `Page.startScreencast`, so it needs no macOS Screen Recording permission.

| direction | message | data |
|---|---|---|
| relay → viewer (text) | `{"t":"hello","agents":{id:{name,color,emoji,status,progress,done,streaming,cursor}}}` | once on connect (late joiners also get each agent's last frame) |
| relay → viewer (text) | `{"t":"bus","e":<event>}` | bus events `agent_spawn`, `agent_status`, `chat`, `agent_done`, `needs_human`, `swarm_summary`, `countdown`, `budget` |
| relay → viewer (text) | `{"t":"cursor","agent","fx","fy","kind":"move"\|"click"\|"typing","duration_ms"?,"label"?,"text"?}` | `moving_to` / `click` / `typing` mapped to **fractions (0–1) of that agent's page viewport** |
| relay → viewer (text) | `{"t":"stream","agent","on"}` | screencast started / stopped |
| relay → viewer (binary) | `[u16 BE header length][header JSON][JPEG]` | header `{"agent","seq","ts","cap"?,"w","h"}`: `ts` relayed / `cap` captured (epoch ms), `w`×`h` viewport in CSS px |
| viewer → relay | `{"t":"ping"}` → `{"t":"pong","ts"}` | commands still go to the bus (8765), not here |

Frames are "latest wins" per viewer, so a slow phone drops frames instead of lagging behind.
