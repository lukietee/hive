# Hive — Mac app

A SwiftUI/AppKit accessory app (no Dock icon) with two parts: the **notch panel** and the **ghost-cursor overlay**. Everything it shows is driven by engine events defined in [`../docs/CONTRACT.md`](../docs/CONTRACT.md).

## Build & run
Requires macOS 14+. The Command Line Tools are enough; Xcode is not needed.

```bash
cd hive/mac
swift build
./.build/debug/Hive                  # connect to the engine at ws://127.0.0.1:8765
./.build/debug/Hive --sim            # scripted 40s demo, no engine needed
./.build/debug/Hive --sim-fallback   # try the engine; run the demo if it's not up after 3s
```

- **Quit:** hexagon menu-bar item → Quit Hive, or Ctrl-C in the terminal.
- **The hexagon menu also has:** Start Pitch in 5, Start demo_sim, Pause/Resume All Agents, Run / Stop Simulation (no engine) and Reconnect to Engine.
- **Permissions:** none are needed. The overlay only draws; it never clicks.
- **Other engine:** `HIVE_ENGINE_URL=ws://host:port ./.build/debug/Hive`.

## Notch controls
The panel is click-through everywhere except over the black shape you can see, so the menu bar and apps underneath keep working.
- **Hover the notch** while idle → it peeks open with **▶ Pitch in 5** (sends `start {scenario: "pitch_in_5"}`). **⌥-click** starts `demo_sim` instead.
- **Click an agent pill** → `pause {agent}` / `resume {agent}` (paused pills dim with a dashed border).
- **⏸ in the header** → `pause {}` / `resume {}` for all agents.
- **Question options** (from `needs_human`) → `answer {agent, choice}`; the row collapses.
- **✕ on the summary card** dismisses it.
- In `--sim` mode commands are logged to stderr and Start restarts the simulation.
- `--selftest-commands`: once connected, fires every command through the same code paths as the buttons, then quits (pair with a WS echo server to check the JSON).

## Files
| File | What |
|---|---|
| `main.swift` | App delegate, menu-bar item, launch flags, one overlay window per display, rebuild when displays change |
| `HiveStore.swift` | `@MainActor ObservableObject`, the single state store; handles every contract event type |
| `EngineClient.swift` | `URLSessionWebSocketTask` client; auto-reconnect every 2s; `send(cmd:args:)` for commands |
| `Notch.swift` | Non-activating `NSPanel` above the menu bar, hit-tested to its visible shape; idle pill → peek (hover, Start button) → expanded (clickable agent pills with progress rings, pause-all, countdown, budget bar, answerable question row, last chat line) → summary card; spring animations |
| `NotchActions.swift` | Human → engine commands (`start`, `pause`/`resume`, `answer`) used by the notch and the hexagon menu |
| `Overlay.swift` | Transparent, click-through `.screenSaver`-level windows; cursors (arrow + name tag + caption), eased glides, click ripples, typing bubble, highlights (circle / box / select handles), dashed link lines, `needs_human` pulse ring, `agent_done` flies back into the notch |
| `Geometry.swift` | Contract coordinates (global, top-left, y down) ⇄ AppKit coordinates; notch size/anchor via `auxiliaryTopLeft/RightArea` + `safeAreaInsets` |
| `Simulator.swift` | Scripted demo emitting real contract envelopes: 5 agents, Sentry fix, a Checker conflict link, a Deck question, wrap-up + summary |
| `DeckViewerModel.swift` | Deck Viewer state: handles `deck_loaded` / `deck_focus` / `deck_slide_updated`, fetches `{base}/slide-{i}.png?v={version}`, zoom + anchor math, synthetic slides for `--sim` |
| `DeckViewer.swift` | Deck Viewer window (bottom-left, floating): thumbnail strip, big slide with crossfades, yellow selection handles; sends `deck_viewer` / `deck_box` so the Deck cursor lands on the edited box. `HIVE_DECK_DEBUG=<dir>` logs geometry and saves window snapshots (no Screen Recording needed) |

## Implemented
- [x] All event types in the contract
- [x] Multi-display: each display gets its own overlay; coordinates are global
- [x] Spawning from and returning to the notch
- [x] Engine connection status (dot next to the notch when idle: green = connected)

## TODO / known gaps
- **The engine must handle the commands.** The app sends `start`, `pause`, `resume` and `answer`; if the engine ignores one, nothing happens. Pause state is shown optimistically in the notch.
- **Hover effects** (pill/option highlight) rely on SwiftUI `onHover` in a non-key panel and are unverified visually.
- **Not tested on a real notched display** in this session. Check that the notch width/height detection is right and that the top of the black shape lines up flush.
- **Not built yet:** the iPad mirror pop-up, the phone mirror tile, window dimming/enlarging, the Call window, and the cursor morphing into the iPadOS pointer.
- **Highlights and links can't be removed early:** non-sticky ones fade after 2.5s / 4s, and there's no event for removing them sooner.
