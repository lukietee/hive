"""Conductor: turns a human request into a per-agent task list.

Uses Claude (model `claude-opus-5-5`) when ANTHROPIC_API_KEY is set; otherwise (or on any error / slow
response) falls back to a canned plan so the demo runs offline. The returned plan carries
`"source": "claude" | "canned"`.
"""

from __future__ import annotations

import asyncio
import copy
import json
import logging
import os
import re

from .agents import AGENTS

log = logging.getLogger("hive.conductor")

MODEL = "claude-opus-5-5"
TIMEOUT_S = 15.0

SYSTEM = """You are Hive's Conductor. Split the user's request into tasks for a team of agents.
Available agents (id: role): {roster}
Reply with ONLY a JSON object: {{"agents": {{"<id>": ["task", ...]}}, "dependencies": [["<id>", "waits_for", "<id>", "<what>"]]}}.
Use only the agent ids listed. Give each agent 2-4 tasks. Keep each task one short imperative sentence (<= 9 words)."""

ROLES = {
    "builder": "finishes product code", "fixer": "fixes the failing test and finishes the signup code",
    "web": "fixes and finishes the landing page", "deck": "fills in the blank pitch-deck slides",
    "social": "drafts the launch post", "checker": "cross-checks facts (prices) across site, deck and post",
    "design": "makes the logo on the iPad", "treasurer": "owns the budget and approvals", "guests": "texts guests",
    "cake": "calls the bakery", "food": "orders food on DoorDash",
}

CANNED = {
    "pitch_in_5": {
        "agents": {
            "fixer": ["Run the tests and read the failure", "Patch the null-referrer bug",
                      "Finish student plan, welcome email, session token", "Get the tests to 5/5"],
            "web": ["Fix the overflowing hero", "Re-align the buttons and add the logo",
                    "Fill in pricing", "Wire the waitlist form"],
            "deck": ["Fill slides 3, 6 and 7", "Drop product screenshots into slide 5",
                     "Put the logo and live URL in the deck"],
            "social": ["Draft the launch post with the live URL", "Keep it under 280 characters"],
            "checker": ["Make sure pricing matches across the site, deck and post"],
        },
        "dependencies": [["deck", "waits_for", "fixer", "test screenshot"],
                         ["deck", "waits_for", "web", "site screenshot"],
                         ["social", "waits_for", "checker", "confirmed price"]],
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


def canned(scenario: str) -> dict:
    plan_ = copy.deepcopy(CANNED.get(scenario, CANNED["pitch_in_5"]))
    plan_["source"] = "canned"
    return plan_


def plan(request: str, scenario: str = "pitch_in_5", agents: list[str] | None = None) -> dict:
    agents = agents or list(CANNED.get(scenario, CANNED["pitch_in_5"])["agents"])
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return canned(scenario)

    try:
        import anthropic  # imported lazily so offline runs don't need network setup

        client = anthropic.Anthropic(timeout=TIMEOUT_S)
        roster = ", ".join(f"{a}: {ROLES.get(a, AGENTS[a]['name'])}" for a in agents)
        msg = client.messages.create(
            model=MODEL,
            max_tokens=1500,
            system=SYSTEM.format(roster=roster),
            messages=[{"role": "user", "content": request}],
        )
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        match = re.search(r"\{.*\}", text, re.S)
        data = json.loads(match.group(0)) if match else {}
        data["agents"] = {k: [str(t) for t in v][:4] for k, v in data.get("agents", {}).items() if k in agents}
        if not data["agents"]:
            return canned(scenario)
        data["source"] = "claude"
        return data
    except Exception as exc:  # network, auth, bad JSON: never block the demo
        log.warning("conductor fell back to the canned plan: %s", exc)
        return canned(scenario)


async def plan_async(request: str, scenario: str = "pitch_in_5", agents: list[str] | None = None) -> dict:
    try:
        return await asyncio.wait_for(asyncio.to_thread(plan, request, scenario, agents), TIMEOUT_S + 3)
    except asyncio.TimeoutError:
        return canned(scenario)
