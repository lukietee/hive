"""Conductor: turns a human request into a per-agent task list.

Uses Claude (model `claude-opus-5-5`) when ANTHROPIC_API_KEY is set; otherwise falls back to a
canned plan so the demo runs offline.
"""

from __future__ import annotations

import json
import os
import re

from .agents import AGENTS

MODEL = "claude-opus-5-5"

SYSTEM = """You are Hive's Conductor. Split the user's request into tasks for a team of agents.
Available agents (id: role): {roster}
Reply with ONLY a JSON object: {{"agents": {{"<id>": ["task", ...]}}, "dependencies": [["<id>", "waits_for", "<id>", "<what>"]]}}.
Use only the agent ids listed. Keep each task one short imperative sentence."""

ROLES = {
    "builder": "finishes product code", "fixer": "fixes bugs using Sentry", "web": "edits/deploys the landing page",
    "deck": "fills in the pitch deck", "social": "writes and posts the launch post", "checker": "cross-checks facts",
    "design": "makes the logo on the iPad", "treasurer": "owns the budget and approvals", "guests": "texts guests",
    "cake": "calls the bakery", "food": "orders food on DoorDash",
}

CANNED = {
    "pitch_in_5": {
        "agents": {
            "builder": ["Finish the half-written signup feature", "Run the tests", "Take product screenshots"],
            "fixer": ["Open the Sentry issue for the failing test", "Patch the null-user bug", "Re-run tests"],
            "web": ["Fix the hero section", "Fill in pricing", "Wire the waitlist form", "Insert the logo", "Deploy"],
            "deck": ["Fill slides 3, 5, 6, 7", "Insert product screenshots", "Put the logo on the title slide"],
            "design": ["Turn the rough Procreate sketch into a clean logo"],
            "social": ["Write the launch post with the URL and logo"],
            "checker": ["Make sure pricing matches across the site, deck and post"],
        },
        "dependencies": [["deck", "waits_for", "builder", "screenshots"], ["web", "waits_for", "design", "logo"],
                         ["social", "waits_for", "web", "live URL"]],
    },
    "party": {
        "agents": {
            "treasurer": ["Split the budget into caps", "Approve purchases under cap, ask above"],
            "guests": ["Text each friend privately", "Collect RSVPs and allergies"],
            "cake": ["Call the bakery and order a matcha cake"],
            "food": ["Build the DoorDash order", "Adapt it to allergies"],
        },
        "dependencies": [["food", "waits_for", "guests", "allergies"]],
    },
}


def plan(request: str, scenario: str = "pitch_in_5", agents: list[str] | None = None) -> dict:
    agents = agents or list(CANNED.get(scenario, CANNED["pitch_in_5"])["agents"])
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return CANNED.get(scenario, CANNED["pitch_in_5"])

    import anthropic  # imported lazily so offline runs don't need network setup

    client = anthropic.Anthropic()
    roster = ", ".join(f"{a}: {ROLES.get(a, AGENTS[a]['name'])}" for a in agents)
    msg = client.messages.create(
        model=MODEL,
        max_tokens=1500,
        system=SYSTEM.format(roster=roster),
        messages=[{"role": "user", "content": request}],
    )
    text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
    match = re.search(r"\{.*\}", text, re.S)
    try:
        data = json.loads(match.group(0)) if match else {}
        data["agents"] = {k: v for k, v in data.get("agents", {}).items() if k in AGENTS}
        return data if data["agents"] else CANNED.get(scenario, CANNED["pitch_in_5"])
    except (json.JSONDecodeError, AttributeError):
        return CANNED.get(scenario, CANNED["pitch_in_5"])
