"""Task graph for the dynamic orchestrator: validation + defaults for the Conductor's JSON plan."""

from __future__ import annotations

import re
from typing import Any

from ..workers.base import AgentSpec

MAX_AGENTS = 6
WORKER_TYPES = ("browser", "code", "deck", "checker")

# Apple system colors (dark-mode variants), handed out in order when the plan's color is missing/taken.
PALETTE = ["#0A84FF", "#30D158", "#FF9F0A", "#BF5AF2", "#FF375F", "#64D2FF", "#FFD60A", "#5E5CE6",
           "#66D4CF", "#FF453A", "#AC8E68", "#40C8E0"]

# SF Symbols the Mac app can draw; anything else falls back to the worker type's default.
SYMBOLS = {
    "globe", "magnifyingglass", "safari.fill", "cart.fill", "bag.fill", "creditcard.fill",
    "wrench.and.screwdriver.fill", "hammer.fill", "chevron.left.forwardslash.chevron.right", "terminal.fill",
    "doc.text.fill", "rectangle.on.rectangle.angled.fill", "chart.bar.fill", "chart.pie.fill",
    "megaphone.fill", "checkmark.shield.fill", "paintbrush.pointed.fill", "map.fill", "fork.knife",
    "cup.and.saucer.fill", "gift.fill", "envelope.fill", "phone.fill", "calendar", "clock.fill",
    "list.bullet.clipboard.fill", "building.2.fill", "graduationcap.fill", "book.fill", "person.2.fill",
    "star.fill", "tag.fill", "photo.fill", "sparkle", "lightbulb.fill", "testtube.2", "ladybug.fill",
}
DEFAULT_SYMBOL = {"browser": "globe", "code": "chevron.left.forwardslash.chevron.right",
                  "deck": "rectangle.on.rectangle.angled.fill", "checker": "checkmark.shield.fill"}

# Ids the static demo agents use; dynamic agents must not collide with ones the Mac app styles differently.
RESERVED = {"conductor"}

PLAN_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "description": "One sentence: how the team will tackle the goal."},
        "agents": {
            "type": "array", "minItems": 1, "maxItems": MAX_AGENTS,
            "items": {
                "type": "object",
                "properties": {
                    "id": {"type": "string", "description": "short lowercase slug, unique, e.g. 'scout'"},
                    "name": {"type": "string", "description": "1-2 word display name, e.g. 'Scout'"},
                    "color": {"type": "string", "description": "hex color from the palette"},
                    "symbol": {"type": "string", "description": "SF Symbol name from the allowed list"},
                    "worker": {"type": "string", "enum": list(WORKER_TYPES)},
                    "goal": {"type": "string", "description": "concrete, self-contained instructions"},
                    "start_url": {"type": "string", "description": "browser workers: first URL to open (optional)"},
                    "inputs": {"type": "array", "items": {"type": "string"},
                               "description": "workspace files this agent should look at"},
                    "depends_on": {"type": "array", "items": {"type": "string"},
                                   "description": "ids of agents whose results this agent needs first"},
                },
                "required": ["id", "name", "worker", "goal"],
            },
        },
    },
    "required": ["agents"],
}


def _slug(s: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", s.lower()).strip("_")
    return s[:20] or "agent"


def validate(raw: dict[str, Any]) -> tuple[list[AgentSpec], str]:
    """Normalise the Conductor's plan: unique ids, known worker types, distinct colors, valid symbols,
    dependencies that point at earlier-declared agents only (no cycles)."""
    specs: list[AgentSpec] = []
    used_colors: set[str] = set()
    ids: set[str] = set()
    for item in (raw.get("agents") or [])[:MAX_AGENTS]:
        worker = str(item.get("worker", "")).lower()
        if worker not in WORKER_TYPES:
            continue
        base = _slug(str(item.get("id") or item.get("name") or worker))
        aid, n = base, 2
        while aid in ids or aid in RESERVED:
            aid, n = f"{base}{n}", n + 1
        color = str(item.get("color") or "").upper()
        if not re.fullmatch(r"#[0-9A-F]{6}", color) or color in used_colors:
            color = next((c for c in PALETTE if c not in used_colors), PALETTE[len(specs) % len(PALETTE)])
        symbol = str(item.get("symbol") or "")
        if symbol not in SYMBOLS:
            symbol = DEFAULT_SYMBOL[worker]
        deps = [_slug(d) for d in (item.get("depends_on") or [])]
        deps = [d for d in deps if d in ids]  # only earlier agents → the graph is acyclic by construction
        goal = str(item.get("goal") or "").strip()
        if not goal:
            continue
        specs.append(AgentSpec(
            id=aid, name=str(item.get("name") or aid.title())[:18], color=color, symbol=symbol,
            worker=worker, goal=goal, inputs=[str(i) for i in (item.get("inputs") or [])][:12],
            depends_on=deps, start_url=(str(item["start_url"]) if item.get("start_url") else None)))
        ids.add(aid)
        used_colors.add(color)
    return specs, str(raw.get("summary") or "").strip()


def fallback_plan(goal: str, has_code: bool, has_deck: bool) -> dict[str, Any]:
    """Used when Claude is unavailable: one worker of the most plausible type, plus a checker."""
    g = goal.lower()
    if has_deck and any(w in g for w in ("deck", "slide", "pitch", "presentation")):
        worker, name, symbol = "deck", "Deck", "rectangle.on.rectangle.angled.fill"
    elif has_code and any(w in g for w in ("test", "bug", "fix", "code", "site", "page", "build")):
        worker, name, symbol = "code", "Builder", "hammer.fill"
    else:
        worker, name, symbol = "browser", "Scout", "magnifyingglass"
    return {"summary": "Offline plan (no Claude).", "agents": [
        {"id": name.lower(), "name": name, "worker": worker, "symbol": symbol, "goal": goal},
    ]}
