# Hive

A swarm of AI agents that works your computer, your phone and the real world, and you manage them by text. Built for LA Hacks 2026.

The full plan is in [`docs/PROJECT_OVERVIEW.md`](docs/PROJECT_OVERVIEW.md). The engine ⇄ app protocol is in [`docs/CONTRACT.md`](docs/CONTRACT.md).

## Layout
| Folder | What |
|---|---|
| `mac/` | Swift Package: the notch panel + ghost-cursor overlay (`swift build`, run with `--sim` to preview) |
| `engine/` | Python 3.12 (uv): WebSocket event bus, agents, Playwright browser agent with cursor sync, Deck agent + render, Conductor, Telegram bot skeleton |
| `demo-world/` | The half-built "Pitch in 5" startup: product repo, broken site, `pitch.pptx`, social draft, logo brief |
| `party/` | Surprise-party demo prep: bakery call scripts, voice agent prompt, guest messages, Treasurer rules, recording checklist, the live judge call |
| `docs/` | Master plan (`PROJECT_OVERVIEW.md`), engine⇄app contract, `LUCAS_TODO.md`, `uc_test.swift` (iPad Universal Control test), scraped LA Hacks tracks |

## Setup (teammates, first time)
Requirements: a Mac (Apple Silicon, macOS 15+), Google Chrome, Homebrew.
```bash
git clone https://github.com/lukietee/hive.git && cd hive

# Tools
xcode-select --install                      # Swift toolchain (full Xcode only needed for the iPad Plan B)
curl -LsSf https://astral.sh/uv/install.sh | sh
brew install --cask libreoffice             # deck rendering
brew install node                           # demo-world/product tests

# Engine
cd engine && uv sync
cp .env.example .env                        # then fill in keys — .env is gitignored, never commit it
cd ..

# Mac app
cd mac && swift build && cd ..
```
macOS permissions (System Settings → Privacy & Security): give your terminal **Accessibility** (iPad / native-app clicks) and **Screen & System Audio Recording** (screenshots, live views).

## Run
```bash
# UI preview only, no engine (~40s scripted demo; quit from the 🐝 menu-bar item)
mac/.build/debug/Hive --sim

# Real agents: start the app first, then the engine
mac/.build/debug/Hive
cd engine && uv run python -m hive_engine --scenario demo_sim --delay 4

# Deck agent re-rendering slides; open http://127.0.0.1:8766/viewer/ within ~6s
cd engine && uv run python -m hive_engine --scenario deck_sim --delay 6
```

## Working together
- `main` is shared, so pull before you start: `git pull --rebase`.
- Change the protocol in `docs/CONTRACT.md` first, then update both sides.
- Roles and the 24h plan: `docs/PROJECT_OVERVIEW.md` §15. Status and open items: `docs/LUCAS_TODO.md`.
