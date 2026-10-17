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

- **Quit:** 🐝 menu-bar item → Quit Hive, or Ctrl-C in the terminal.
- **The 🐝 menu also has:** Run / Stop Simulation and Reconnect to Engine.
- **Permissions:** none are needed. The overlay only draws; it never clicks.

## Files
| File | What |
|---|---|
| `main.swift` | App delegate, menu-bar item, launch flags, one overlay window per display, rebuild when displays change |
| `HiveStore.swift` | `@MainActor ObservableObject`, the single state store; handles every contract event type |
| `EngineClient.swift` | `URLSessionWebSocketTask` client; auto-reconnect every 2s; `send(cmd:args:)` for commands |
| `Notch.swift` | Non-activating `NSPanel` above the menu bar; idle pill → expanded (agent pills with progress rings, countdown, budget bar, question row, last chat line) → summary card; spring animations |
| `Overlay.swift` | Transparent, click-through `.screenSaver`-level windows; cursors (arrow + name tag + caption), eased glides, click ripples, typing bubble, highlights (circle / box / select handles), dashed link lines, `needs_human` pulse ring, `agent_done` flies back into the notch |
| `Geometry.swift` | Contract coordinates (global, top-left, y down) ⇄ AppKit coordinates; notch size/anchor via `auxiliaryTopLeft/RightArea` + `safeAreaInsets` |
| `Simulator.swift` | Scripted demo emitting real contract envelopes: 5 agents, Sentry fix, a Checker conflict link, a Deck question, wrap-up + summary |

## Implemented
- [x] All event types in the contract
- [x] Multi-display: each display gets its own overlay; coordinates are global
- [x] Spawning from and returning to the notch
- [x] Engine connection status (dot next to the notch when idle: green = connected)

## TODO / known gaps
- **The notch panel can't be clicked** (`ignoresMouseEvents = true`), so it never blocks the menu bar. Answering `needs_human` happens through chat or the engine, not by clicking in the notch.
- **No commands are sent from the UI yet.** `EngineClient.send` exists but isn't wired to anything.
- **Not tested on a real notched display** in this session. Check that the notch width/height detection is right and that the top of the black shape lines up flush.
- **Not built yet:** the iPad mirror pop-up, the phone mirror tile, window dimming/enlarging, the Deck Viewer window, the Call window, and the cursor morphing into the iPadOS pointer.
- **Highlights and links can't be removed early:** non-sticky ones fade after 2.5s / 4s, and there's no event for removing them sooner.
