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
| `caller` | Caller | `#64D2FF` | 📞 |

## Event envelope (engine → clients)
```json
{ "v": 1, "ts": 1792260000.123, "agent": "web", "type": "moving_to", "data": { ... } }
```

| type | data | Mac app behavior |
|---|---|---|
| `agent_spawn` | `{ "name", "color", "emoji"?, "symbol"?, "x", "y" }` — dynamic (goal) agents send an SF Symbol name in `symbol` and no emoji; their ids are not in the table above | Create the cursor at (x,y), or under the notch if omitted; add a pill to the notch |
| `agent_status` | `{ "text", "progress": 0..1? }` | Update the pill text / progress ring |
| `moving_to` | `{ "x", "y", "duration_ms": 300, "label"? }` | Glide the cursor to (x,y) with easing |
| `click` | `{ "x", "y" }` | Click ripple at (x,y) |
| `typing` | `{ "x", "y", "text" }` | Show a small typing indicator by the cursor |
| `highlight` | `{ "x", "y", "w", "h", "style": "circle" \| "box" \| "select" }` | Draw a circle, box or selection handles (fade out after 2.5s unless `"sticky": true`) |
| `link` | `{ "from": [x,y], "to": [x,y], "text"? }` | Draw a line between two points (Checker conflicts) |
| `needs_human` | `{ "question", "options": [..], "allow_other"?: true, "details"?: [..], "image"?, "kind"?: "choice" \| "approval", "amount"? }` — options are the agent's own 2–4 best choices, best first | Pulse the cursor; show the question card in the notch. `allow_other` (default `true`) adds an "Other…" button for a typed answer; `answer.choice` may then be any string (or an option number like `"1"`). iMessage: `details[i]` is a short note shown after option *i*; `image` (local path or URL, e.g. a screenshot) is attached before the question; `kind: "approval"` + `amount` asks for an explicit YES before spending |
| `chat` | `{ "text", "image"? }` | (For the chat relay; the app may show it in the notch.) Optional `image` (local path or URL) is sent as an attachment in the iMessage chat right after the text |
| `agent_done` | `{ "summary"? }` | Cursor flies back into the notch and disappears |
| `swarm_summary` | `{ "title", "lines": [..] }` | Show the summary card in the notch |
| `countdown` | `{ "seconds_left" }` | Update the notch timer |
| `run_reset` | `{ "scenario" }` (agent `null`) | A new run is starting: drop every cursor, highlight, question and window left from earlier runs |
| `budget` | `{ "spent", "total", "caps": { agent: cap } }` | Update the notch budget bar (party demo) |
| `deck_loaded` | `{ "slides", "base", "version" }` | Deck Viewer loads the slide PNGs from `base` (e.g. `http://127.0.0.1:8766/...`) |
| `deck_focus` | `{ "slide", "box": [x, y, w, h], "label" }` | Deck Viewer scrolls to and zooms the slide; box is in **fractions of the slide** (0–1), for the cursor + selection handles |
| `deck_slide_updated` | `{ "slide", "version", "render_ms" }` | Deck Viewer crossfades to the re-rendered slide PNG |
| `window_place` | `{ "window": "deck" \| "call", "x", "y", "w", "h" }` | Moves/resizes the Deck Viewer or Call window into the engine's layout cell (now, or when it next appears) |
| `call_started` | `{ "call_id", "to", "label", "mode": "live"\|"fake" }` | Call window appears (caller ID = label + formatted number) |
| `call_state` | `{ "call_id", "state": "ringing"\|"connected"\|"ended" }` | Status line: Ringing… → live timer → Call ended |
| `call_transcript` | `{ "call_id", "speaker": "agent"\|"them", "text", "final" }` | Caption bubble; a non-final line is replaced by the next update from the same speaker |
| `call_ended` | `{ "call_id", "duration_s", "outcome": "success"\|"failure"\|"unknown", "summary", "details": {…} }` | Summary card + fact chips; window fades out ~9s later |

## Commands (clients → engine)
```json
{ "v": 1, "cmd": "start", "args": { "scenario": "pitch_in_5" } }
```
| cmd | args |
|---|---|
| `start` | `{ "scenario": "pitch_in_5" \| "party" \| "demo_sim" \| "goal", "goal"?, "fast"?, "auto_human"?, "answer_timeout"? }`. `scenario: "goal"` carries the human's typed `goal` (notch "Ask Hive to…" box) for the dynamic orchestrator, plus optional `"workspace": path` (agents edit a temp copy) and `"urls": [str]`. Always accepted; while a scenario runs, a second start is rejected with a `chat` line (agent `null`) |
| `pause` / `resume` | `{ "agent"?: id }` (all agents if omitted) |
| `say` | `{ "agent"?: id, "text" }`: a message from the human (chat / @mention) |
| `cancel` | `{}` | The safe word: stop the running scenario now, close every agent window (agent Chrome, agent VS Code), then `run_reset` |
| `answer` | `{ "agent": id, "choice", "free_text"?: true }`: the reply to `needs_human`. `free_text: true` means the human typed `choice` in their own words (notch "Other…" or an iMessage reply that isn't one of the options); interpret it rather than matching it to an option. For `kind: "approval"`, `choice` is `"YES"` or `"NO"` |
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

## iMessage thread (Messenger)
`uv run python -m hive_engine.messenger --fake | --photon` — a bus client (no engine changes) that bridges the bus to one plain-text iMessage thread with the owner (`HIVE_OWNER_PHONE`). Fake transport: Messages-style page + WS at **`http://127.0.0.1:8769/`** (`HIVE_CHAT_PORT`). Photon transport: REST, see `docs/PHOTON_SETUP.md`.

- **Out:** `chat`, `agent_done` (with a summary), `swarm_summary`, `call_ended` ("Call with Bakery ended. <summary>") → `"Name: …"` texts, batched over `HIVE_MESSENGER_BATCH_S` (2s). `agent_status` and cursor events are never texted. Emoji are stripped.
- **Questions:** `needs_human` → numbered options + "Reply 1 or 2, or tell me something else." The reply `1`/`2`/the option text maps to that option; anything else is mapped by Claude when it clearly picks an option, otherwise sent as `answer {choice: <text>, free_text: true}`. Approvals accept only `YES` / `NO`.
- **In:** `@Name …` → `say {agent}` (or answers that agent's pending question); `@everyone …` → `say {}`; `@Web show me` → reply with the live view URL (`HIVE_PUBLIC_LIVE_URL`, else `http://<LAN IP>:8766/live/`); `start` / `start party` / `pause` / `resume` → those commands; unaddressed text answers the latest pending question, else goes to `say {}`.

### Sessions and group chats (dedicated Photon line)
On a **dedicated** iMessage line (Photon `GET /platforms/imessage` → `mode: "dedicated"`), every run gets its own chat:

| type | data | Messenger behavior |
|---|---|---|
| `session_start` | `{ "title", "goal"?, "summary"?, "members"?: ["+1…"], "team"?: [{id, name, role}] }` (agent `null`) | Opens the run's chat: a **group** with the owner + `members` + `HIVE_GROUP_MEMBERS` (nobody else), or the owner's 1:1 on the dedicated line when there are no members. Posts `Hive: New run: <title>` (+ goal). |

- **Emit it first** (before the run's `agent_spawn`s), e.g. `bus.emit(None, "session_start", {"title": "Maya's Surprise Party", "goal": "...", "members": [...]})`. Without it, a `start` texted by the owner opens a session titled after the scenario, and otherwise the first non-replayed `agent_spawn` after idle opens `Hive run 9:47 PM`.
- **Joining:** each `agent_spawn` is announced, batched over `HIVE_ANNOUNCE_S` (1.5s): `Hive added Cake: calling the bakery`. The text after the colon is `agent_spawn.data.goal` / `role` / `task` / `text`, else the agent's first `agent_status.text`.
- **Leaving:** `agent_done` → `Name: Done.` (+ summary). `swarm_summary` closes the session; the next run opens a new chat.
- **Inbound:** only the owner steers (from the group, their 1:1 on either line); other group members' texts are logged, not acted on. Replies always go to the active chat.
- **State:** `engine/state/messenger_session.json` (`space_id`, `title`, `goal`, `members`, `done`), so a restarted Messenger rejoins the open chat.
- **Limits (Photon REST):** a chat with exactly the same participants is reused (no second group with the same people), and REST can't rename a group or set its photo (spectrum-ts can), so the title appears as the header text, not the chat name. A real group needs at least one member besides the owner. On a shared line all of this is skipped and everything stays in the 1:1 thread.

## Agent memory (text side)
`engine/state/messages/<agent>.jsonl` (gitignored with `engine/state/`; `HIVE_STATE_DIR` / `HIVE_MEMORY_DIR` override), via `hive_engine.memory.append(agent, kind, text)` / `read(agent)`: one `{ts, agent, kind: "text_in"|"text_out", text}` per line. When the owner texts `@Cake …` after that agent has finished, the Messenger answers with Claude from this text memory **plus** `CallMemory().context_text("cake")` (below), so a phone call carries over into text.

## Calls (phone, via ElevenLabs ⇄ Photon SIP)
Any agent can place a call: `await hive_engine.calls.place_call(agent, to="+1…", label="Bakery", goal="…", context={…}, follow_up=False)`.
It emits the four `call_*` events above (with `agent` = the calling agent) and returns a `CallResult`.

- **Live mode** (keys present): sets the hosted ElevenLabs agent's prompt + first message for this call
  (`PATCH /v1/convai/agents/{id}`), dials with `POST /v1/convai/sip-trunk/outbound-call` through the Photon
  number imported as a SIP trunk, and polls `GET /v1/convai/conversations/{id}` about once a second for
  status, transcript turns and the post-call analysis. Setup: [`docs/CALLS_SETUP.md`](CALLS_SETUP.md).
- **Fake mode** (`fake=True`, or no keys): a scripted call through the same events (`call_sim` scenario).
- **Disclosure:** every prompt and first message says it's an AI and that the call is recorded.

**Call memory (for the iMessage layer):** each finished call is appended to
`engine/state/calls/<agent>.json` (`$HIVE_STATE_DIR` overrides `engine/state`; gitignored):
```json
{"agent": "cake", "calls": [{"call_id", "mode", "to", "label", "goal", "context", "follow_up",
  "started_at", "ended_at", "duration_s", "outcome", "summary", "details": {…},
  "transcript": [{"speaker": "agent"|"them", "text", "t"}], "conversation_id"}]}
```
Read it with `from hive_engine.calls import CallMemory`: `CallMemory().latest("cake")`, `.history("cake")`,
or `.context_text("cake")` (a short recap to paste into an LLM prompt when the user texts "@Cake did they
say 6?"). A change request becomes a follow-up call with `follow_up=True`, which feeds the last call's
summary into the voice prompt.
