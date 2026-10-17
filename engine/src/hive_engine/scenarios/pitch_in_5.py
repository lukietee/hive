"""pitch_in_5 — OUTLINE (not implemented yet). See PROJECT_OVERVIEW.md §5 and §10.

Demo world lives in ../../../../demo-world (hive/demo-world):
  demo-world/product/        → Builder + Fixer (Claude Code in VS Code's terminal)
  demo-world/landing/        → Web (Chrome window ②, then Vercel)
  demo-world/pitch.pptx      → Deck (Deck Viewer ③)
  demo-world/social_draft.md → Social (Chrome window ④, X tab)
  iPad Procreate sketch      → Design

Layout (2×2): ① VS Code top-left · ② Chrome landing top-right · ③ Deck Viewer bottom-left ·
④ Chrome Sentry→X bottom-right.  Checker draws on the overlay.

Order of operations (dependencies drive handoffs; each is a chat line):
  1. countdown(300); conductor.plan(...)
  2. parallel: builder.finish_feature() | web.fix_hero(), web.fill_pricing() | deck.fill(3), deck.fill(7)
  3. builder.run_tests() → fails → fixer.open_sentry() → fixer.patch() → tests green
  4. builder.screenshots() → deck.insert_image(5, ...)  ("@Deck screenshots ready")
  5. design.logo_autocomplete() (iPad)  → web.insert_logo(); deck.insert_image(0, ...)
  6. deck.ask_human("Market size: $2B or $4B?") → set slide 6
  7. checker.compare(web price, deck price) → link() → web.fix_price()
  8. web.deploy() → social.post(url, logo); human redirect "@Social make it shorter"
  9. swarm_summary(); agents fly home
"""

from __future__ import annotations

from pathlib import Path

from ..bus import Bus

DEMO_WORLD = Path(__file__).resolve().parents[4] / "demo-world"


async def run(bus: Bus, **_) -> dict:
    bus.emit(None, "swarm_summary", {"title": "pitch_in_5 not implemented yet",
                                     "lines": [f"demo world: {DEMO_WORLD}"]})
    return {"implemented": False, "demo_world": str(DEMO_WORLD), "exists": DEMO_WORLD.exists()}
