# Hive

**A swarm of AI agents that works your computer for you, while you're somewhere else.**

Text Hive a task from your phone. A Conductor agent reads it, decides what kind of team it needs, and spawns it right on your Mac. Every agent gets its own ghost cursor and its own windows, and they all work at the same time: one fixing code in VS Code, one finishing a website in Chrome, one building slides, one on the phone with a bakery. You follow along and steer from an iMessage group chat. Agents join the chat as they're spawned, ask you when they need a decision, and never spend money without your YES.

Built at LA Hacks 2026.

---

## Why

AI agents today mostly work one at a time, inside a chat window, on things you watch them do. Real work isn't like that: it's several jobs in parallel, across many apps, and you're usually not sitting at your desk.

Hive treats your computer as a shared workspace for a team:

- **Remote first.** You manage the team from your phone over iMessage. Your Mac does the work.
- **A real swarm on one machine.** Many agents operate your computer at once, each with its own visible cursor and windows, without fighting over your mouse.
- **Real apps, real results.** Agents use the same tools you do: Chrome, VS Code, Messages, Notes, Calendar, Keynote, real websites and real phone calls.
- **You stay in charge.** Agents ask before anything irreversible. Spending needs an explicit YES. One word stops everything.

---

## How it works

```
 You (iPhone, iMessage)
        │  "investors are here in 5, get whisk ready"
        ▼
 Photon iMessage line ──▶ Hive Messenger ──▶ Conductor (Claude)
                                                │  plans the team: who, how many, which tools
                                                ▼
                         ┌─────────────── Event bus (WebSocket) ───────────────┐
                         │                                                     │
         Agents (each its own window + ghost cursor)               Mac app (notch + overlay)
         • Browser agents (Browser Use / Playwright, Chrome)       • Dynamic-Island-style status
         • Code agents (real VS Code)                               • a ghost cursor per agent
         • Deck agent (python-pptx, live renders)                  • Deck Viewer, Call window
         • Caller agent (ElevenLabs voice over Photon SIP)         • question cards with buttons
         • Mac-app agents (Messages, Notes, Calendar, Keynote)
         • Treasurer (budget, caps, approvals)
                         │
                         ▼
         Group chat updates: "➕ Cake: calling the bakery" · "❓ Checker: $29 or $39?" · "✅ Web: live at …"
```

1. **Text a task in plain language.** Claude figures out what you mean; there are no commands to memorize.
2. **The Conductor plans a team** for that task: how many agents, which skills, what each one does, which ones wait on others, and per-agent budgets.
3. **Hive opens a group chat for the task** and announces each agent as it joins.
4. **Agents work in parallel on your Mac.** Each has its own ghost cursor that glides to exactly where it's about to click or type, so you can watch the whole team at once. The screen is tiled so windows never overlap.
5. **Agents ask when they need you.** Questions come as numbered options with "or type your own". Reply `1`, `YES`, your own words, or `@Agent` to talk to one directly.
6. **You get a summary** when the team is done, with links to everything it made.

### Ghost cursors: many agents, one computer
Agents never move your real mouse. Each agent drives its windows through their own channels (Chrome DevTools, a VS Code extension, the macOS Accessibility API, AppleScript), and Hive draws a ghost cursor that lands on the exact element right before the action happens. Measured cursor-to-click accuracy is within about 1 point. You can keep using your Mac while the swarm works.

### Safety
- **Approval gates:** purchases, phone calls and public posts can require an explicit YES. Anything else ("sure", silence) means no.
- **Treasurer agent:** holds the budget, gives each agent a spending cap, tracks every cart, flags anything over its cap, and asks before any money moves.
- **No card data in the AI:** payment methods stay tokenized at the merchant. Agents can fill a cart, but they can't read or copy a card.
- **Safe word:** text `CANCEL` and every agent stops immediately and their windows close.
- **Isolated workspaces:** agents work on temporary copies of your files and in their own browser and editor profiles, never your personal ones.

---

## Use cases

### Pitch in 5: finish a startup before the investors arrive
*"Investors are here in 5 min, finish the startup stuff."*
- **Fixer** opens the product in VS Code, finds the failing test, types the fix and gets the suite to 5/5.
- **Web** finishes the landing page in the same editor and deploys it live to Vercel.
- **Deck** fills the empty slides of the pitch deck live: market chart, screenshots, pricing.
- **Checker** cross-checks the site, deck and post, spots that the price doesn't match, and asks you which is right.
- **Social** generates an illustrated launch graphic with Gemini and posts it to Instagram.

### Surprise party planning: from one text to a planned party
*"Jason's birthday is Oct 19 at 9pm, I want pizza and to invite 3 people."*
- **Cake** finds a bakery that's open on Google Maps, asks if it should call, then phones them with an AI voice to order the cake.
- **Guests** writes the invites in Messages to people from your Contacts and collects RSVPs and allergies.
- **Food** builds a DoorDash order that respects the allergies; **Decor** fills an Amazon cart.
- **Planner** writes the checklist in Notes, sets Reminders, adds the Calendar event, and designs an illustrated invitation in Keynote.
- **Treasurer** keeps it all under budget and asks you to approve or hold the purchases.

### Anything else
*"Find the 3 best-rated boba shops near UCLA and compare prices."* The Conductor builds a team of browser agents and a checker, and reports back in a new group chat.

---

## Models

| Model | Provider | What it does in Hive |
|---|---|---|
| **Claude Opus 5.5** (`claude-opus-5-5`) | Anthropic | The Conductor: reads a task and plans the team (agents, skills, budgets, dependencies); writes slide copy and launch posts; understands free-text replies to agents' questions; answers "@Agent …" questions from memory; summarizes phone calls |
| **Claude Sonnet 5.5** (`claude-sonnet-5-5`) | Anthropic | Code, deck and checker agents: read and edit files, run commands, fill slides, review the team's work |
| **Claude Haiku 5.5** (`claude-haiku-5-5`) | Anthropic | Browser agents (each Browser Use agent's step-by-step decisions); routing texts to the right kind of task in about a second; the phone agent's live conversation |
| **Gemini 3.1 Flash Image** (`gemini-3.1-flash-image`) | Google | Illustrated launch graphics for Instagram and the party invitation art |
| **ElevenLabs v4 Turbo** (`eleven_v4_turbo`) | ElevenLabs | The phone agent's voice (text-to-speech, low latency) |
| **ElevenLabs Scribe Realtime** | ElevenLabs | Speech-to-text: hears the person on the other end of the call |
| **ElevenLabs Flash v2.5** (`eleven_flash_v2_5`) | ElevenLabs | Voices simulated calls for testing |

Each Claude role can be swapped with an environment variable (`HIVE_CONDUCTOR_MODEL`, `HIVE_WORKER_MODEL`, `HIVE_BROWSER_MODEL`, `HIVE_MESSENGER_MODEL`).

---

## APIs and services

| Service | How Hive uses it |
|---|---|
| **Anthropic API** | Every Claude model above (Messages API with tool use) |
| **Photon 2.0** | The iMessage line: users, spaces (1:1 chats and per-task group chats), sending and receiving messages and images through the REST API; a phone number and SIP voice profile for outbound calls |
| **ElevenLabs** | Conversational AI agent for calls (agent config API, SIP-trunk outbound call API, conversation transcripts), plus the text-to-speech API |
| **Browser Use** | Open-source browser agent framework behind every web agent (one process per agent, attached to its own Chrome window) |
| **Google Gemini API** | Image generation for launch graphics and invitations |
| **Vercel** | Deploys finished sites to a live URL (Vercel CLI) |
| **Chrome DevTools Protocol / Playwright** | Drives each agent's Chrome window, streams it to the live view, and syncs the ghost cursor with real clicks |
| **macOS Accessibility API, AppleScript** | Drives Messages, Notes, Reminders, Calendar, Keynote and Contacts; places and measures windows |
| **Web apps agents operate** | Instagram, Google Maps, DoorDash, Amazon (through the browser, in a dedicated agent profile) |

---

## Tech stack

| Layer | Technology |
|---|---|
| **Agent brains** | Anthropic Claude (Opus 5.5, Sonnet 5.5, Haiku 5.5); see [Models](#models) |
| **Browser agents** | Browser Use, Playwright, Chrome DevTools Protocol (each agent in its own Chrome window) |
| **Code agents** | Visual Studio Code driven by a small bundled extension (open, select, type, terminal) |
| **Mac apps** | macOS Accessibility API (pyobjc), AppleScript: Messages, Notes, Reminders, Calendar, Keynote, Contacts |
| **Messaging** | Photon 2.0: dedicated iMessage line, group chats, REST API |
| **Phone calls** | ElevenLabs Conversational AI (Claude Haiku 5.5 brain, v4 Turbo voice, Scribe Realtime ears), connected to a Photon phone number over SIP (TLS) |
| **Images** | Google Gemini 3.1 Flash Image (illustrated launch graphics, party invitations), Pillow for type |
| **Slides** | python-pptx, LibreOffice (headless) + PyMuPDF for live slide renders, Keynote |
| **Deploys** | Vercel CLI |
| **Mac app** | Swift 6, SwiftUI + AppKit: notch panel, transparent click-through overlay for ghost cursors, Deck Viewer, Call window |
| **Engine** | Python 3.12 (uv), asyncio, WebSocket event bus (`websockets`), live view relay (Chrome screencast) |

---

## Repository layout

| Folder | What |
|---|---|
| `mac/` | The macOS app: notch panel, ghost-cursor overlay, Deck Viewer, Call window (Swift Package) |
| `engine/` | The swarm engine: event bus, Conductor and orchestrator, agents and workers, iMessage messenger, calls, live view |
| `workers/` | The Browser Use worker (runs as its own process per agent) |
| `demo-world/` | A sample half-finished startup (product, site, deck) that the Pitch in 5 team finishes |
| `party/` | Voice-agent prompt and notes for the party use case |
| `docs/` | Engine ⇄ app event contract, Photon and calls setup guides |

---

## Setup

Requirements: a Mac (Apple Silicon, macOS 15+), Google Chrome, Visual Studio Code, Homebrew.

```bash
git clone https://github.com/lukietee/hive.git && cd hive

# Tools
xcode-select --install                      # Swift toolchain
curl -LsSf https://astral.sh/uv/install.sh | sh
brew install --cask libreoffice             # slide renders
brew install node                           # sample product's tests

# Engine
cd engine && uv sync
cp .env.example .env                        # fill in your keys (never commit .env)
cd ..

# Mac app
cd mac && swift build && cd ..
```

Keys in `engine/.env`: Anthropic, Photon (project ID + secret), ElevenLabs (key, voice, agent), Gemini. See [`docs/PHOTON_SETUP.md`](docs/PHOTON_SETUP.md) and [`docs/CALLS_SETUP.md`](docs/CALLS_SETUP.md).

macOS permissions (System Settings → Privacy & Security) for your terminal: **Accessibility**, **Automation** (Messages, Notes, Calendar, Keynote), and **Full Disk Access** (reading Messages replies).

## Run

```bash
# 1. The Mac app (notch + ghost cursors)
mac/.build/debug/Hive

# 2. The engine
cd engine && uv run python -m hive_engine --wait

# 3. The iMessage bridge
cd engine && uv run python -m hive_engine.messenger --photon
```

Then text your Hive number a task, or hover the notch and type one into **"Ask Hive to…"**. Text `CANCEL` to stop everything.
