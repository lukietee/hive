# Hive — Project Overview
*LA Hacks 2026 · AI Hackathon · Oct 17–18, 2026 · James West Alumni Center, UCLA*
*Hacking window: **Sat Oct 17 12:00 PM → Sun Oct 18 12:00 PM (24 hours)***

---

## 1. One-liner
**Hive is a swarm of AI agents that works your computer the way a team would.** Each agent gets its own visible ghost cursor on your Mac and can jump onto your iPad. You run the whole team from a group chat on your phone, where you can tap any agent and **watch exactly what it's doing in its window, live**.

**Pitch lines**
- *"Clicky shows you how. Hive is a whole team doing it, at the same time, across your devices."*
- *"Remote Control lets you text one coding agent. Hive lets you run a whole team that works your entire computer, and you can watch every one of them do it."*
- *"Claude Code is one of our employees. Hive is the manager."*

## 2. The problem
- AI assistants today are single-threaded. They work like one helper with one cursor and do one task at a time.
- Real work is parallel and spread across many apps. A launch, for example, means a website, the product, a deck, a logo and social posts, all due at once.
- Computer-use agents are also invisible. They run in a hidden browser, and you can't tell what they're doing until they finish.

## 3. What Hive is
One swarm shown through four surfaces. Every agent has **one identity** (name + color + avatar) on all of them.

| Surface | Answers | Where |
|---|---|---|
| **Notch** | "What is the swarm doing right now?" | Expands down out of the MacBook notch: countdown, agent pills, progress rings, summary card |
| **Ghost cursors** | "Where is each agent working?" | A transparent overlay across the Mac desktop, one labeled cursor per agent |
| **Group chat** | "What is each agent doing and why? Change of plans." | Your phone: Telegram "Hive Squad" (upgrade to iMessage via Photon) |
| **Live agent view** | "Show me exactly what @Web is doing right now" | Tap **👁 Watch** on any agent's message to open a live stream of its window, with its cursor, on your phone |
| **iPad** | "The swarm reaches past the Mac" | A cursor jumps off the Mac's edge onto the iPad and works Procreate |

## 4. Positioning — why this isn't a copy

### vs. Clicky (a single voice assistant that points at things on screen; YC Spring 2026)
1. **A team, not a tutor.** Clicky points and explains. Hive's agents do the work, in parallel.
2. **It never takes your mouse.** The cursors are drawn, and the actions go straight into the apps (§6), so you keep using your Mac.
3. **Coordination you can see.** Agents depend on and hand off to each other in the chat.
4. **Managed from your pocket**, with a live view of every agent.
5. **Across devices**: the iPad.
6. **Undo all**: every write goes through one action queue, so you can roll the whole swarm back.

### vs. Claude Code Remote Control (Anthropic, Feb 2026: drive a local Claude Code session from your phone)
| | Remote Control | Hive |
|---|---|---|
| Controls | One coding session in a terminal | A **team** of agents across every app + the iPad |
| Kind of work | Code | Mostly visual work in apps (site, deck, logo, posts); code is one piece |
| What you see | A chat transcript | **Where** each agent works on the real screen + a **live view** per agent on your phone |
| Chat model | 1:1 | **Group chat**: @one, @everyone, and agents talk to each other |
| Coordination | None (single agent) | Dependencies, handoffs, and a Checker that catches contradictions between agents |
| Devices | The computer it runs on | Acts across Mac + iPad |

**How to frame it:** Claude Code is literally one of our agents (the Builder). Hive is the layer above it: it runs Claude Code, browser agents, an image model and an iPad agent as one team.

**Say it first:** put the Remote Control line in the first 20 seconds of the pitch. Never claim to be "first" at any single piece. Defend the combination: **many agents + visible on screen + across apps + across devices + managed and watched from a group chat.**

**Demo choices that support this:**
- keep the VS Code/terminal moments short;
- show agents talking to each other at least twice;
- redirect one agent mid-task with an @mention while the others keep working;
- let the Checker catch a contradiction between two agents.

## 5. The demo — "Pitch in 5"
A fake startup is **half-built** and the pitch starts in 5 minutes. A countdown is on the projector.

### The half-done mess (prepared ahead of time)
| Piece | State at 5:00 | Agent that finishes it |
|---|---|---|
| Product (repo in VS Code) | Feature half-written, 1 failing test, 1 planted bug (reported in Sentry) | 🟢 **Builder** + 🔴 **Fixer** |
| Landing page (Next.js, local Chrome) | Broken hero, "TODO: pricing," waitlist form not wired | 🔵 **Web** |
| Pitch deck (`pitch.pptx`, shown in the Hive Deck Viewer) | 4 of 10 slides blank (placeholders) | 🟡 **Deck** |
| Logo | Rough napkin sketch in **Procreate** on the iPad | 🎨 **Design** (Gemini refines it; inserted back into Procreate) |
| Social post | Rough text draft, no image | 🟣 **Social** |
| Consistency | — | ⚪ **Checker** (compares facts across the deck, site and posts) |

### Dependencies the swarm coordinates (visible in the chat)
- Deck needs product screenshots, so it waits for Builder.
- Web needs the logo, so it waits for Design.
- Social needs the live URL and the logo, so it waits for Web and Design.
- Web's pricing must match the Deck's pricing, which Checker enforces.

### 2-minute script
| Time | Moment |
|---|---|
| 0:00 | "Our pitch is in 5 minutes and nothing's done." Show the mess. Walk away from the laptop holding only the phone. |
| 0:10 | Text the group chat: **"@everyone we pitch in 5. Finish it."** The notch drops down and the agent pills spill out into ghost cursors. |
| 0:20 | **Watch moment:** tap **👁 Watch** on 🔵 Web's message. Your phone, AirPlayed to a corner tile on the projector, shows Web's live window with its cursor moving. *"I'm not even looking at my laptop."* |
| 0:30 | 🟢 Builder: "test 3 fails." 🔴 Fixer opens the Sentry issue, patches the bug, and the tests go green. |
| 0:45 | 🟢 → "@Deck screenshots ready." The screenshots drop into slide 5. |
| 0:50 | **iPad moment:** 🎨 Design's cursor glides off the Mac's right edge onto the iPad. The rough sketch goes to Gemini, the polished logo is AirDropped back, the agent inserts it as a layer in Procreate, and the sketch layer fades out. |
| 1:05 | 🔵 Web puts the logo in the hero and deploys. 🟡 Deck puts it on the title slide. |
| 1:15 | **Check-in:** 🟡 "Slide 6 market size, $2B or $4B?" You tap **$4B**. |
| 1:25 | ⚪ Checker circles the site's $39 and draws a line to the deck's $29. 🔵 Web fixes it. |
| 1:30 | 🟣 Social drafts the post. **Redirect:** "@Social make it shorter" → it rewrites and posts. |
| 1:35 | Clock hits 0:00. The cursors fly back into the notch. Summary card: "6 agents · 5 deliverables · 4m 48s." |
| 1:40 | A QR code appears on the landing page. Judges scan it and join the waitlist. Chat: "🎉 first 5 signups." |
| 1:50 | Double-click `pitch.pptx` → it opens in Keynote → pitch from the deck the agents just finished. |

## 6. How the ghost cursors work (the core mechanism)
**The real cursor does none of the agents' work. It stays yours.** Every agent acts through a channel that doesn't need the mouse, so they really do run in parallel. Each ghost cursor is a drawing of exactly where its agent is acting, the same idea as multiplayer cursors in Figma.

### What actually performs each action
| Agent | App | Real action goes through | Real mouse? |
|---|---|---|---|
| Builder / Fixer | VS Code | Claude Code edits files on disk; VS Code updates on its own | No |
| Web | Chrome | Claude Code edits the site; Playwright over DevTools for clicks and typing | No |
| Fixer / Social | Chrome (Sentry, X) | Playwright / Browser Use over DevTools | No |
| Deck | Hive Deck Viewer | python-pptx edits the file, then a re-render (§8) | No |
| Checker | Overlay | Draws circles, lines and notes | No |
| Design | iPad | **Universal Control borrows the real cursor (Plan A)**; WebDriverAgent doesn't (Plan B) | Plan A only |

### It's real computer use, just without the shared mouse
```
screenshot of the agent's own window → Claude picks (x, y) → ghost cursor glides to (x, y)
→ click delivered to (x, y) in that window only
```
- **Chrome:** `Input.dispatchMouseEvent(x, y)` through DevTools, for that window only.
- **Native apps:** `AXUIElementCopyElementAtPosition(x, y)` then press it through Accessibility, or `CGEvent.postToPid` (sends to one app without moving the cursor).
- **When to use which:** structured actions (CSS selectors, AppleScript) where they're more reliable; coordinate actions from screenshots where they look more impressive or nothing else works.
- **So the ghost cursor is the model's actual click target, made visible.**

### Keeping a cursor in sync with a real action
1. The agent decides on a target.
2. Look up its screen position:
   - Chrome: element box + window position + browser UI offset;
   - native apps: Accessibility position and size;
   - Deck Viewer: the shape's box from python-pptx.
3. Glide the cursor there (~300ms, eased) and show a click ripple.
4. **Then** fire the real action. The cursor arrives first and the app reacts, so it reads as cause and effect.

**For actions that aren't clicks:**
- **Code edits:** the cursor parks on the VS Code window or on the file name in the sidebar; it doesn't trace each line.
- **Typing:** the cursor sits in the field while the text appears.

### Overlay window
A borderless, transparent `NSWindow` at `.screenSaver` level with `ignoresMouseEvents = true`, set to appear on all Spaces and over full-screen apps. It draws N cursors with name tags, plus circles and lines. Clicks pass through to your apps.

### Parallel without fighting
- Each Chrome window is driven independently through DevTools.
- Writes to any one native app go one at a time through that app's queue.
- Launch Chrome with `--disable-backgrounding-occluded-windows --disable-renderer-backgrounding --disable-background-timer-throttling` so windows it thinks are hidden aren't throttled.

### If a judge asks "are the cursors real?"
*"The cursors show where each agent is acting. The actions go straight into the apps, which is why six of them can work at once without fighting over your mouse."*

## 7. Live agent view on your phone 👁
From the group chat you can see what **each individual agent** is doing in its window, live.

### What you see in the chat
```
Hive Squad 🐝
──────────────────────────────────────────
🔵 Web       Fixing the hero section  [thumbnail]
             [ 👁 Watch ]  [ ⏸ Pause ]  [ ↪ Redirect ]
🔴 Fixer     Opened Sentry issue: null user on signup  [thumbnail]
             [ 👁 Watch ]
📌 Pinned:   [ 🐝 Live board ]  ← grid of all agents at once
```
- **👁 Watch** on any agent's message opens a full-screen live stream of *that agent's window*, with its ghost cursor and a status line ("clicking 'Pricing'…").
- **🐝 Live board** (pinned) shows every agent as a live tile with its name, color and current step. Tap a tile to watch that agent.
- **Thumbnails:** every milestone message carries a fresh screenshot of the agent's window.
- **Commands:** `/watch @Web`, `/board`, `@Web pause`, `@everyone status`.
- **iPad agent:** 🎨 Design's view streams the iPad screen feed.

### How it works
```
Mac: ScreenCaptureKit, one capture stream per agent window (single-window content filter)
  → JPEG frames at 5–10 fps, ~720p
  → WebSocket → cloud relay
  → Telegram Mini App (a web page that opens inside Telegram) draws the frames on a <canvas>
  + the relay also forwards that agent's cursor events → the Mini App draws the ghost cursor on top
```
- **Telegram Mini App:** the 👁 button is an inline button that opens a small web app in Telegram's own viewer. It can be a single HTML page.
- **Cursor drawn on the phone, not baked into the video:** sending cursor positions separately keeps the cursor smooth even when the frame rate drops.
- **iPad:** frames come from the AVFoundation capture of the wired iPad.
- **Security:** check Telegram's sign-in data (`initData`) on every request, and only stream to your own Telegram user ID.
- **Bandwidth:** about 100–300 KB/s per stream. The Live board uses small tiles at 2 fps.
- **If Photon/iMessage replaces Telegram:** iMessage can't embed a web app, so 👁 becomes a link that opens the same page in Safari.

### Showing the phone to the audience
Turn on **AirPlay Receiver** on the Mac (System Settings → General → AirDrop & Handoff) and mirror the phone to it. Hive shows the phone mirror as a corner tile on the projector during phone moments (0:10, 0:20, 1:15, 1:30, 1:40). That way the audience sees the chat and the live view while you hold the phone.

## 8. The Deck Viewer (python-pptx that looks like design work)
The Deck agent edits the real `pitch.pptx` with **python-pptx**. Hive's own **Deck Viewer** shows it live.

- **Small steps:** title → render → body → render → image → render → nudge → render. Each step crossfades in, so the slide comes together piece by piece.
- **Exact cursor targets:** python-pptx knows every shape's position and size, which converts directly to preview pixels.
- **Selection handles:** a blue box with corner handles around the shape being edited, like Figma or Keynote.
- **Scroll and zoom:** a strip of slide thumbnails on the left; the viewer scrolls to the active slide, zooms in while it's edited, then zooms out.
- **Rendering:**
  - LibreOffice kept running in the background via `unoserver` (`unoconvert` → PDF, ~0.5–1s);
  - PyMuPDF → PNG (~50ms per page);
  - use installed fonts (Inter or Helvetica) and simple effects so LibreOffice's rendering matches PowerPoint's.
- **Use a template:** the 4 "blank" slides already have their layout, placeholder text and image boxes. The agent fills them in; it doesn't do layout.
- **The reveal:** at the end, double-click `pitch.pptx` and it opens in Keynote. It's a real file.
- **If a judge asks:** "That's Hive's deck view, rendered live from the real .pptx."

## 9. The iPad
### Control (cable only)
- **Plan A, Universal Control:** synthetic `CGEvent` movement pushes the real cursor over the Mac's edge onto the iPad. **Test with `uc_test.swift`.**
- **Plan B, WebDriverAgent over USB-C:** Developer Mode + an Xcode-signed WebDriverAgent build.
  - Reliable taps, drags and the element tree.
  - **No visible pointer on the iPad.** The ghost cursor appears in the iPad mirror window on the Mac while the real iPad reacts.
- **Best combination if Plan A works:** WebDriverAgent tells you *where* the buttons are; Universal Control moves the real pointer there and clicks.
- **Eyes:** capture the wired iPad's screen through AVFoundation, the same way QuickTime does.

### Cursor on the iPad?
- **A custom ghost cursor on the iPad: not possible.** iPadOS doesn't let apps draw over other apps, and picture-in-picture is opaque and can't be moved by code.
- **iPadOS's own pointer (gray circle): yes, via Universal Control only.** You can't color or label it, and there's only one.
- **The handoff trick:** as 🎨 Design's ghost cursor reaches the Mac's right edge, it morphs into a gray circle like the iPadOS pointer. It slides off the Mac and an identical circle appears on the iPad.
- **If Plan B:** enlarge the iPad mirror window next to the physical iPad, so the audience sees the cursor in the mirror and the real iPad reacting together.

### Logo autocomplete flow (the AI runs on the Mac; the iPad is just the canvas)
```
① Mac grabs the iPad screen feed → crops the rough sketch
② Sketch → Gemini image model ("clean flat logo, same shapes, no text")
③ Polished PNG back to the Mac (also handed straight to Web + Deck)
④ Mac AirDrops the PNG to the iPad (same Apple ID → accepted automatically → Photos)
⑤ WebDriverAgent taps in Procreate: Actions → Add → Insert a photo → newest image
⑥ Layers → hide the sketch layer → the polished logo replaces the sketch
```
- **Sharper source (optional):** in step ①, have the agent tap Share → PNG → AirDrop to the Mac. It's more agent activity on screen but more taps that can break.
- **No text in the logo:** image models garble lettering. The company name gets added in code (site) or with python-pptx (deck).
- **Cached fallback:** generate a few good results in advance, in case the Wi-Fi is slow.
- **Mac UI:** an iPad mirror window pops out of the notch at 0:50 with a shimmer while Gemini works, then slides back at 1:05. The other windows dim.

## 10. Screens, windows & storyboard

### Physical setup
```
            ┌──────────── PROJECTOR (mirrors MacBook) ────────────┐
            └─────────────────────────────────────────────────────┘
   ┌───────────────────────────┐  ┌──────────┐
   │        MacBook            │──│   iPad   │ ← stand, RIGHT of Mac (USB-C to Mac)
   │ Hive: notch + overlay +   │  │ Procreate│
   │ 4 tiled windows           │  └──────────┘
   └───────────────────────────┘
   📱 You, standing: Telegram "Hive Squad" (AirPlayed to the Mac → corner tile)
   📱📱 Judges' phones: scan the QR at the end
```

### Mac layout (2×2; never more than 4 working windows)
```
┌──────────────────────────── MacBook ─────────────────────────────┐
│                 ╭── notch ▾  ⏱ 3:12  🟢🔴🔵🟡🟣⚪🎨 ──╮              │
│ ┌─ ① VS Code ───────────────┐  ┌─ ② Chrome: landing ───────────┐ │
│ │ 🟢 Builder  🔴 Fixer       │  │ 🔵 Web                        │ │
│ └────────────────────────────┘  └───────────────────────────────┘ │
│ ┌─ ③ Hive Deck Viewer ──────┐  ┌─ ④ Chrome: [Sentry] [X] ──────┐ │
│ │ 🟡 Deck                    │  │ 🔴 Fixer → 🟣 Social           │ │
│ └────────────────────────────┘  └───────────────────────────────┘ │
│  ⚪ Checker roams (overlay)        [📱 phone mirror tile, corner]  │
└────────────────────────────────────────────────────────────────────┘
  pops up 0:50–1:05: ⑤ iPad mirror window      finale: ⑥ Keynote fullscreen
```

### Every window: before → after
| # | Window | Agent(s) | Before | After |
|---|---|---|---|---|
| ① | VS Code: product repo (top-left) | 🟢 Builder, 🔴 Fixer | Half-written feature, failing test 3, planted bug | Feature done, tests green, screenshots taken |
| ② | Chrome: landing page (top-right) | 🔵 Web | Broken hero, TODO pricing, dead form | Live on Vercel with logo, $29 pricing, waitlist, QR |
| ③ | Hive Deck Viewer (bottom-left) | 🟡 Deck | 4 blank slides | Finished deck; opened in Keynote at the end |
| ④ | Chrome: tab 1 Sentry → tab 2 X (bottom-right) | 🔴 Fixer → 🟣 Social | Sentry issue; empty compose box | Bug understood; launch post published (demo account) |
| — | Overlay | ⚪ Checker | — | Circles $39 ↔ $29 with a connecting line |
| — | Notch | Hive | Black pill | Countdown → pills → summary card |
| — | Phone mirror tile (corner) | — | Hidden | Shown during phone moments |
| ⑤ | iPad mirror (pop-up on Mac) + **iPad: Procreate** | 🎨 Design | Rough sketch | Gemini logo inserted as a layer, sketch hidden |
| ⑥ | Keynote (finale) | — | — | Fullscreen pitch from `pitch.pptx` |
| 📱 | Phone: Telegram + Mini App | All | Empty group | Commands, 👁 live views, check-ins, "🎉 5 signups" |
| 📱 | Judges' phones | — | — | QR → live site → waitlist |

### Master timeline
| Time | ① VS Code | ② Landing | ③ Deck Viewer | ④ Sentry / X | iPad | 📱 Phone |
|---|---|---|---|---|---|---|
| 0:00 | Messy code | Broken page | Blank slides | Sentry tab | Sketch | Step away |
| 0:10 | — | — | — | — | — | "@everyone we pitch in 5" → notch drops, cursors pour out |
| 0:15 | Claude Code writing feature | Fixing hero | Slide 3 title | — | — | 🟣 "Draft ready, waiting on URL + logo" |
| 0:20 | — | (being watched) | — | — | — | **👁 Watch @Web** → live view (corner tile) |
| 0:30 | Test 3 fails | Pricing appears | Slide 3 body | 🔴 opens Sentry issue | — | "test 3 fails" |
| 0:40 | 🔴 patch → green ✓ | Form connected | — | Stack trace highlighted | — | "Patched ✓" |
| 0:45 | Screenshots | — | Slide 5 screenshots | — | — | "@Deck screenshots ready" |
| 0:50 | dimmed | dimmed | Slide 7 $29 | dimmed | **Cursor jumps → Gemini → AirDrop → insert layer** | 🎨 "Finishing the logo" |
| 1:05 | — | Logo → deploy | Logo on title slide | — | Logo ✓ | 🔵 "Live → URL" |
| 1:15 | — | — | Slide 6 waiting | — | — | 🟡 "$2B or $4B?" → tap **$4B** |
| 1:20 | — | — | $4B appears | — | — | — |
| 1:25 | — | ⚪ circles $39 | ⚪ circles $29 | — | — | "Mismatch" → 🔵 fixes it |
| 1:30 | — | Reload $29 | — | **X tab:** 🟣 drafts post | — | "@Social make it shorter" → posts → link |
| 1:35 | — | — | — | — | — | 0:00 → cursors fly home → summary |
| 1:40 | — | **QR** | — | — | — | "🎉 5 signups" |
| 1:50 | hidden | hidden | **→ Keynote fullscreen, pitch** | hidden | — | — |

### Where the audience should look
| Time | Focus | How Hive points them there |
|---|---|---|
| 0:10 | Notch | Drop-down animation + cursors pouring out |
| 0:20 | Phone tile | The corner tile grows briefly while you hold up the phone |
| 0:30–0:45 | ① + ④ | Hive briefly enlarges VS Code, then Sentry |
| 0:50–1:05 | **iPad** | Cursor exits the right edge; other windows dim; mirror pops up |
| 1:15, 1:30 | Phone tile | You tap the answer / send the redirect |
| 1:25 | ② + ③ | The Checker's line connecting the two windows |
| 1:35–1:50 | Notch → QR → Keynote | Summary card, then the reveal |

## 11. Architecture
```
                        ┌───────────────────────── Mac app (Swift/SwiftUI) ──────────────────────────┐
 📱 Telegram group      │                                                                             │
   + Mini App (👁)  ◄──►│  Relay client ◄──► Conductor (Claude: plan + task graph + @mention routing)  │
        ▲               │                          │                                                  │
        │               │                          ▼                                                  │
 Cloud relay            │     Agents ─► events: moving_to · reading · wrote · needs_human · done      │
 (WebSocket:            │     ├─ 🔵 Web / 🟣 Social / 🔴 Fixer: local Chrome via Playwright/Browser Use│
  @mention router,      │     ├─ 🟢 Builder / 🔴 Fixer: Claude Code (or Devin) on the repo            │
  frame relay,          │     ├─ 🟡 Deck: python-pptx → unoserver → PyMuPDF → Deck Viewer             │
  cursor events)        │     ├─ 🎨 Design: iPad via Universal Control / WebDriverAgent + Gemini      │
                        │     └─ ⚪ Checker: reads all outputs, flags conflicts                       │
                        │                          │                                                  │
                        │   Action queue (one per app) ─► cursor glides THEN action fires             │
                        │                          │                                                  │
                        │   Event bus ─► Notch UI · Ghost-cursor overlay · milestones → chat          │
                        │   ScreenCaptureKit (per-agent window) + AVFoundation (iPad) ─► frames → relay│
                        └──────────────────────────────────────────────────────────────────────────────┘
```

**Chat routing:**
- The relay parses @mentions into that agent's inbox.
- Agents check their inbox between actions, so redirects take effect mid-task.
- Only milestones get posted to the chat, never every click.

## 12. Tech stack
| Layer | Choice |
|---|---|
| Mac app | Swift + SwiftUI; `NSPanel` (notch), `NSWindow` overlay, ScreenCaptureKit, Accessibility API, AppleScript |
| Orchestration | Python or TypeScript service (local); Claude (Opus 5.5 / Sonnet 5.5) as Conductor + agent brains |
| Browser agents | Playwright over DevTools against local headed Chrome; Browser Use for the agent loop |
| Code agents | Claude Code (CLI) or Devin |
| Deck | python-pptx + unoserver (LibreOffice) + PyMuPDF; SwiftUI Deck Viewer |
| Design | Gemini image model; Procreate on the iPad; AirDrop via `NSSharingService` |
| iPad control | Universal Control (CGEvent) and/or WebDriverAgent; AVFoundation screen capture |
| Chat | Telegram bots (one per agent) + Telegram Mini App for 👁 live views; upgrade to Photon/iMessage if it supports one identity per agent |
| Streaming | ScreenCaptureKit → JPEG → WebSocket relay → `<canvas>` |
| Observability | Sentry (Tracing + AI agent monitoring + Logs) |
| Demo startup | Next.js on Vercel, Supabase waitlist, `pitch.pptx`, domain via GoDaddy (MLH) |

## 13. Hardware
- MacBook with a notch (macOS 15+), with **AirPlay Receiver** turned on (for the phone mirror tile)
- iPad (2018+, latest iPadOS; **same Apple ID** as the Mac) + a USB-C data cable
- iPad stand, placed to the **right** of the MacBook, matching the Displays arrangement
- Phone, for the group chat and live views
- Procreate ($12.99 if not already installed)
- *No ESP32, HDMI adapter or capture card needed.*

## 14. Prize targets (updated Oct 17)
Main track: **Track 4 · Applied Intelligence.** Check Devpost for a cap on sponsor prizes per project; if capped, rank **Photon → Visa → Browser Use → ElevenLabs → Devin/Paper**.

### Core (actively building on)
| Sponsor | What we use |
|---|---|
| **Photon** (iMessage $700 / $300, **Best Voice Agent $400**) | iMessage control thread with @agent routing + question cards; the bakery call over Photon's SIP voice line. Must be built on Photon 2.0 and live on a Photon channel |
| **Browser Use** | The Browser worker in the dynamic orchestrator (Web, Food, Gifts, Social agents) |
| **Visa** ($2,000) | Party demo shopping: compare → decide → checkout, Treasurer spending caps + approvals. No Visa API required |
| **MLH · ElevenLabs** | The Caller's voice (ElevenLabs hosted voice agent ⇄ Photon SIP) |

### Cheap add-ons
| Sponsor | What it takes |
|---|---|
| **Cognition · Devin** | A Devin worker type for coding tasks, and/or use Devin to build parts of Hive |
| **Paper · Best Designed Hack** | Notch, cursors, Deck Viewer. Check whether the design must be made in Paper |
| **MLH · Gemini** | Logo autocomplete / party invite images |
| **MLH · GoDaddy** | Register the product domain |

### Maybe / skip
- **Sentry:** needs 2+ products beyond errors (tracing, logs). Only if stable overnight.
- **Creao:** pitch angle only.
- Not a fit: Fetch.ai, QNX, Espressif, Even Realities, Workday, Intuit, StepFun, Base44, veri.studio, other MLH challenges.

## 15. 24-hour build plan (team of 4 assumed)

### Roles
| Person | Owns |
|---|---|
| **A · Mac UI** | Notch states, ghost-cursor overlay + animations, Deck Viewer UI, iPad mirror pop-up, phone tile, summary card |
| **B · Swarm engine** | Conductor, agent loop, event bus, action queues, Playwright/Browser Use agents, python-pptx Deck agent, Checker |
| **C · Chat + streaming** | Telegram bots + @mention router, 👁 Mini App + Live board, ScreenCaptureKit frame relay, Sentry, Vercel deploy, waitlist + QR |
| **D · iPad + demo world** | `uc_test` → WebDriverAgent, iPad capture, Procreate + Gemini + AirDrop flow, building the half-done startup, pitch |

### Timeline
| When | Milestone |
|---|---|
| **Sat 12–2 PM** | Day-one tests (§16). Repo scaffolded. Event schema agreed (`agent_id, type, x, y, window_id, target, text`). |
| **Sat 2–6 PM** | One ghost cursor synced to one real Chrome click. Notch opens and closes. Telegram bot echoes messages. Deck Viewer renders one python-pptx edit. Half-done startup assets drafted. |
| **Sat 6–10 PM** | 3 agents in parallel with 3 synced cursors. @mentions reach agent inboxes. On-demand screenshot per agent in the chat. iPad: one tap driven from the Mac. |
| **Sat 10 PM–2 AM** | All agents. Dependencies + check-ins. Sentry → Fixer. Logo autocomplete. 👁 live view Mini App. |
| **Sun 2–6 AM** | Full demo run end to end. Fix the top 3 breakages. **Record a backup video.** |
| **Sun 6–10 AM** | Polish (animations, handoff morph, sounds, summary card, Live board). Rehearse 5+ times, timing each step. Devpost writeup. |
| **Sun 10 AM–12 PM** | Freeze code. Submit to Devpost before 12:00. |

### Scope tiers — cut from the bottom
1. **Must:** notch + overlay + 3–4 agents with synced cursors + Telegram chat with @mentions + **a screenshot per agent on request** + Deck Viewer + the "Pitch in 5" world
2. **Should:** **👁 live view Mini App + Live board**, iPad jump + logo autocomplete, Sentry → Fixer, Checker conflicts, QR waitlist, phone mirror tile
3. **Nice:** Photon/iMessage, ElevenLabs voices, Undo all, handoff morph, "teach once" mode

## 16. Day-one test checklist
- [ ] `swift uc_test.swift right`: does synthetic input cross into the iPad via Universal Control?
- [ ] Is the iPad screen capture working on the Mac (AVFoundation) while Universal Control is on?
- [ ] WebDriverAgent builds, installs and taps on the iPad
- [ ] Procreate: does pointer or WebDriverAgent touch input work? Does "Insert a photo" list the newest image first?
- [ ] AirDrop Mac → iPad accepts automatically (same Apple ID)
- [ ] python-pptx edit → unoserver → PNG in under ~1s; fonts look right
- [ ] Gemini sketch → logo quality on the real sketch (cache the best few)
- [ ] Telegram: multiple bots in one group, inline buttons, and a Mini App opening a test WebSocket stream
- [ ] ScreenCaptureKit single-window capture at 5–10 fps
- [ ] AirPlay phone → Mac mirroring works on the venue Wi-Fi (or a hotspot)

## 17. Risks & fallbacks
| Risk | Fallback |
|---|---|
| Universal Control ignores synthetic input | WebDriverAgent + iPad mirror window with the ghost cursor |
| WebDriverAgent signing eats hours | Start Saturday afternoon. If it isn't working by midnight, move the iPad to "Should" and keep the Mac demo. |
| AirDrop/Procreate import flaky | Reveal the logo in the iPad mirror on the Mac only |
| Cursor coordinates drift (scroll, Retina scaling) | Recompute positions before every glide; test on the actual demo Mac and display |
| Live stream laggy on venue Wi-Fi | Lower fps/resolution, use a phone hotspot, or fall back to screenshots in the chat |
| AirPlay phone mirror fails | A teammate holds the phone under a document camera, or skip the tile and narrate |
| LLM agents unpredictable on stage | Fixed, rehearsed demo world; cached model calls on the demo path; be honest about what's live |
| "It's just Claude Code Remote Control" | §4: say it first; Claude Code is one employee, Hive is the manager |
| Photon can't do one identity per agent | Stay on Telegram |
| Too much scope for 24h | Follow the tiers in §15, without exceptions |

## 18. Open questions
- [ ] Universal Control test result
- [ ] iPad model + iPadOS version
- [ ] Team size and who owns what
- [x] Photon iMessage groups: **not supported on the free shared lines** (`shared-line-group-unsupported`); use 1:1 threads + Telegram via Photon for the group view
- [ ] Photon: seat cap on the shared line (how many friends can Guests text)? Does each project get its own handle?
- [ ] Which bakery near UCLA agrees to take the demo call?
- [ ] Which demo is the main one? (recommended: Demo 2)
- [ ] Max sponsor prizes per project? Must Paper's entry be designed in Paper?
- [ ] Product name ("Hive" is a placeholder; check the domain)

## 19. Files in this folder
- `PROJECT_OVERVIEW.md` — this doc
- `lahacks-tracks.md` / `lahacks-content.json` — scraped tracks + sponsor challenges
- `uc_test.swift` — Universal Control synthetic-input test (`swift uc_test.swift right`)

## 20. Demo 2 — "Surprise Party Tonight" (Photon + Visa)
*Recommended as the **main** demo; "Pitch in 5" becomes a 30-second clip or is cut. Same engine.*

**Setup:** "Maya's surprise 21st is tonight and we forgot everything." You iMessage Hive: *"Plan Maya's surprise party tonight, 8pm, ~12 people, $150 budget, she loves matcha."*

### Sponsor requirements (from their docs)
- **Photon:**
  - Must be built on Photon 2.0 and live on ≥1 Photon channel. iMessage is home base for text agents.
  - **Voice runs on a Photon SMS number,** connected over SIP to ElevenLabs, Retell, LiveKit or Twilio (cookbooks at photon.codes/docs/beta/cookbooks).
  - **iMessage group chats need a dedicated line and are unsupported on free shared lines,** so everything on iMessage is 1:1.
  - One agent profile (name + avatar) per project.
  - Judged on Vision, Craft, Depth, Traction. They want human-in-the-loop, context that persists across channels, and voice agents that remember the call when the conversation moves to text.
- **Visa:**
  - No required API.
  - Criteria: innovation 25%, UX 25%, technical 20%, commerce impact 15%, trust & responsibility 15%.

### Agents
| Agent | Channel | Does |
|---|---|---|
| 💰 Treasurer | Notch + iMessage | Splits the budget into per-agent caps, approves or blocks purchases, keeps receipts, splits the cost among friends |
| 💌 Guests | iMessage 1:1 per friend (Photon) | Private invites, RSVPs, allergies, gift ideas; passes facts to the other agents |
| 🎂 Cake | Phone call (Photon SMS number + ElevenLabs) | Calls a real bakery, orders, texts a summary, calls back with full context |
| 🍕 Food | Chrome: DoorDash | Builds the order; adapts to allergies |
| 🎈 Supplies | Chrome: DoorDash (Target/CVS) | Balloons, plates, candles |
| 🎁 Gift | Chrome: Target | Finds a gift within its cap, same-day pickup |
| 🎨 Designer | iPad: Procreate | Sketch → Gemini → invite image → sent to guests |

### Script (~2.5 min)
| Time | Moment |
|---|---|
| 0:00 | iMessage the request to Hive |
| 0:10 | Notch drops; Treasurer splits the budget (Cake $45 · Food $60 · Supplies $25 · Gift $20); cursors pour out |
| 0:20 | Guests texts 4 friends 1:1; their phones buzz |
| 0:30 | "yes!! I'm vegan" → Food adds a vegan item (cross-agent context) |
| 0:35 | Cake calls the bakery on speaker; live transcript on the Mac |
| 0:55 | Designer: iPad sketch → Gemini → invite texted to the guests |
| 1:10 | Food $54 auto-approved; Supplies $31 > $25 → Treasurer asks "approve or swap balloons for streamers?" → "swap" |
| 1:25 | Gift: "Matcha whisk set $19, Target pickup. Buy?" → Yes |
| 1:35 | Cake texts the confirmation; you ask to add 🎉 → **Cake calls back, picking up from the first call** |
| 1:55 | Real DoorDash order placed → "Arriving 6:42pm" tracking page |
| 2:05 | Treasurer: "$136/$150. Split 5 ways = $27.20 each. Send requests?" → summary card |

### Mac windows
- Chrome ×3 (DoorDash Food, DoorDash Supplies, Target Gift)
- A Hive call window (live transcript + waveform)
- The notch with a Treasurer budget bar

**Plus:** the iPad (Procreate), your phone (iMessage threads), friends' phones (invites).

### Trust & responsibility (Visa 15%)
- Per-agent spending caps.
- Approval in iMessage for anything over a cap.
- **The model never sees the card number:** checkout uses the saved account payment method, or a hard-limit virtual card.
- Receipts plus a ledger.
- The AI says it's an AI on calls, and announces recording or transcription (California needs all-party consent).

### Real-world safety
- **Bakery:** arrange it ahead of time so they expect the call. Order a cake from the case plus writing. A teammate plays the bakery as backup.
- **DoorDash:** a browser agent on a logged-in persistent profile, at human pace. Phone approval before "Place order." Delivery to JWAC arrives ~30–40 min later, so invite the judges back for a slice.
- **Cap total real spending** at about $100 with a virtual card.
- **Guests** = teammates + a consenting judge. Check the shared-line seat cap.
- **The DIAL overlap is only the call.** Differentiate with call → text → callback continuity and coordination.

### Chat design
- **iMessage via Photon:**
  - your control thread with Hive is 1:1, with agent name prefixes (or one Photon project per agent for separate contacts);
  - Guests uses 1:1 threads per friend.
- **Telegram via Photon:** the full group view + 👁 live views.

### Extra build cost vs. Demo 1 (~12–18 h)
- Photon iMessage + Telegram setup
- The voice agent (SIP + ElevenLabs/Retell)
- The DoorDash/Target browser flows
- The Treasurer logic
- Guest outreach + passing facts between agents
- The call window UI
- Preparing and rehearsing the second demo world

## 21. Demo 2 storyboard — windows, agents & channels

### Physical setup
- MacBook (projected): notch + overlay + 4 tiled windows; the speakers play the bakery call
- iPad on a stand to the right: Procreate with the rough invite sketch
- Your phone: iMessage thread with Hive (1:1), AirPlayed to a corner tile
- 4 "friends'" phones (teammates + 1 consenting judge): receive invites, reply
- A real, pre-arranged bakery near UCLA: receives the call

### Mac layout
| Slot | Window | Agent |
|---|---|---|
| Top | Notch: 💰 budget bar ($0/$150), per-agent cap chips, RSVP counter | 💰 Treasurer, 💌 Guests |
| ① top-left | Chrome: DoorDash (restaurant) | 🍕 Food |
| ② top-right | Chrome: DoorDash (Target/CVS store) | 🎈 Supplies |
| ③ bottom-left | Chrome: Target | 🎁 Gift |
| ④ bottom-right | Hive Call window: dialing state, waveform, live transcript, summary card | 🎂 Cake |
| Overlay | ✓/✗ approval stamps on carts | 💰 Treasurer |
| Pop-up 0:55–1:10 | iPad mirror | 🎨 Designer |
| Corner tile | Your iMessage thread (AirPlay) | — |
| 2:05 | Receipt + split card | 💰 Treasurer |

### Agents
| Agent | Works in | Actions | Real-world effect |
|---|---|---|---|
| 💰 Treasurer | Notch, overlay, your iMessage | Caps → check carts → auto-approve under cap / ask if over → ledger → split | Approvals, payment requests |
| 💌 Guests | iMessage 1:1 ×4 (Photon) | Invites → RSVPs, allergies, gift ideas → passes facts to Food/Gift → sends the invite image | Friends' phones buzz |
| 🎂 Cake | Call (Photon SMS number → SIP → ElevenLabs) + ④ + your iMessage | Call → AI disclosure → order → text summary → callback with context | A real cake order |
| 🍕 Food | ① DoorDash | Items → vegan add-on after a guest's reply → checkout → approval → Place order | A real delivery to JWAC |
| 🎈 Supplies | ② DoorDash | Cart → over cap → swaps balloons for streamers | Order |
| 🎁 Gift | ③ Target | Uses a guest's gift idea → $19 matcha whisk → pickup after your Yes | Pickup order |
| 🎨 Designer | iPad Procreate | Sketch → Gemini → invite → to Guests | Invite on the friends' phones |

### Channels
- **Your control thread with Hive (1:1):** agent name prefixes. Photon iMessage, shared line.
- **Friend threads (1:1 ×4):** Photon iMessage.
- **Bakery call:** Photon SMS number + Voice profile → SIP → ElevenLabs/Retell. Audio + transcript are sent to the Mac via a LiveKit listen-only participant or the provider's live stream (verify on day one; fall back to transcript only).
- **Optional:** Telegram via Photon for a group view + 👁 live views.

### Master timeline
| Time | Mac ①–④ | Notch / 💰 | iPad | 📱 You | 📱 Friends | ☎️ Bakery |
|---|---|---|---|---|---|---|
| 0:00 | Empty | $0/$150 | Sketch | "Plan Maya's surprise party tonight…" | — | — |
| 0:10 | Cursors pour out | Caps: 🍕60 🎈25 🎁20 🎂45 | — | 💰 "Budget set" | — | — |
| 0:20 | ①②③ searching | RSVPs 0/4 | — | 💌 "Texting 4 friends" | 📳 invites | — |
| 0:30 | ① adds vegan pizza | 2/4 | — | 💌 "Jess is vegan → told 🍕" | "yes!! I'm vegan" | — |
| 0:35 | ④ dialing | — | — | 🎂 "Calling the bakery" | — | Rings → answers |
| 0:40–0:55 | ④ live transcript | 🎂 $42 reserved | — | — | "she wanted a matcha whisk" | Live call |
| 0:55 | Dimmed; iPad mirror pops up | — | Sketch → Gemini → invite | 🎨 "Making the invite" | — | — |
| 1:10 | ① $54 ✓ · ② $31 ✗ | Stamps | — | 💰 "$6 over: approve or swap?" → "swap" | 📳 invite image | — |
| 1:20 | ② $24 ✓ | $78 | — | — | 4/4 | — |
| 1:25 | ③ whisk $19 | — | — | 🎁 "Buy?" → "Yes" | — | — |
| 1:35 | ④ call summary | — | — | 🎂 "Confirmed, 6pm" → "add 🎉?" | — | — |
| 1:40–1:50 | ④ callback with context | — | — | 🎂 "Done ✓" | — | Callback |
| 1:55 | ① Place order → tracking | $136/$150 | — | 💰 "Arriving 6:42" | — | — |
| 2:05 | Receipt + split | Summary | — | 💰 "$27.20 each. Send?" → "Yes" | 📳 requests | — |
| 2:15 | Cursors return to the notch | — | — | — | — | — |

### Audience focus
- 0:00–0:10: phone tile → notch
- 0:20: friends' phones
- 0:30: ① Food
- **0:35–0:55: ④ + room audio**
- 0:55–1:10: iPad
- 1:10: ✗ stamp + "swap"
- **1:40: callback**
- 1:55–2:15: tracking → summary

### Pre-demo setup
- Chrome ×3 logged in (saved payment method / virtual card)
- Call window ready
- Procreate open with the sketch
- iMessage thread open
- AirPlay on
- Friends' phones unlocked
- Bakery expecting the call

## 22. Demo format (decided): live "Pitch in 5" + party video + live judge call
| Segment | Time | What |
|---|---|---|
| Hook | 0:15 | "Hive is a team of AI agents that works for you across your computer, your phone and the real world, and you manage them by text." |
| **Live:** Pitch in 5 | ~2:00 | Full live demo (cursors, Deck Viewer, iPad logo, chat) |
| **Video:** Surprise party | ~0:60 | The 5 beats, edited: invites → vegan reply changes the cart → bakery call → over budget "swap" → callback → real order + split |
| **Live:** judge's phone | ~0:20 | Hive's voice agent **calls the judge's phone**, then **texts them a summary** (voice → text continuity). For Visa tables: text the judge an approval request instead. |
| Close | 0:10 | Summary card + QR |

**Per table:**
- **Photon / Visa:** shorten Pitch in 5 to ~60s; play the full party video; do the live call or approval.
- **Paper / Sentry / Devin:** the full Pitch in 5 + a short video.

**Party video rules:**
- One continuous take, or split-screen (Mac screen + camera on the phones).
- Clock visible.
- Label it "Recorded Sat [time]."
- End on the real receipt + the bakery confirmation.
- Bring the cake to judging as a prop.
- It doubles as the **Devpost video**.

**Planning impact:**
- **Record the party Saturday afternoon/early evening while the bakery is open** (hard deadline).
- The party flow only needs to work once: build it rough, no polish. All polish goes into Pitch in 5.
- The party can drop to 4 beats: cut the iPad invite, since the iPad is shown live in Pitch in 5.
- The live judge call/text satisfies Photon's "live on at least one Photon channel" requirement.


## 23. Decisions (Oct 17, afternoon)
- **Chat surface = iMessage via Photon. No custom native phone app.**
  - One 1:1 "Hive" thread (free shared lines can't do groups). Address agents with @Name / @everyone; replies are prefixed with the agent's name.
  - Our custom UI lives on web pages linked from iMessage: the **question card** (big option buttons, context, live view) and the **👁 live view** (`/live/`). Tapback reactions work as a fallback answer.
  - A Telegram group (native inline buttons + Mini App) is optional later; a native SwiftUI iPhone app is out (needs Xcode, weakens the Photon story).
- **Voice: ElevenLabs hosted voice agent ⇄ Photon SIP** instead of LiveKit (fewer moving parts before tonight's bakery recording). Transcript is pulled into the engine for the Mac Call window and the iMessage memory.
- **Browser worker = Browser Use** (separate process per agent, reports to the bus; its click/type actions emit ghost-cursor events first).
- **Dynamic orchestrator:** the Conductor picks the agents and their tasks per goal. Scripted Pitch in 5 stays as the stage-safe playbook.
- **Notch UI:** Apple-style redesign — SF Symbols instead of emoji, hexagon mark, compact Live Activity unless hovered, question cards with buttons.
- **iPad:** parked. Universal Control didn't link (even the real trackpad didn't cross). Revisit after the party recording.
