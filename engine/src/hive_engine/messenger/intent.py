"""What does a free-form text to Hive mean? Claude reads it and picks one intent.

    pitch   — get the startup ready to pitch (the saved Pitch in 5 demo)
    party   — plan / throw a party or celebration for someone
    goal    — any other task for the agent team (the dynamic orchestrator)
    chat    — small talk, thanks, questions about Hive: reply, don't start anything

Falls back to simple keyword rules when there is no API key or Claude is slow.
"""

from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass

from ..orchestrator import llm

INTENT_MODEL = "claude-haiku-5-5"   # fast; a texted reply shouldn't wait on a big model
TIMEOUT_S = 8.0

SYSTEM = """You route text messages sent to Hive, a team of AI agents run from iMessage.
Pick the single intent that best matches what the person wants Hive to do right now:
- "pitch": get the startup (Whisk, the matcha startup) ready to pitch / demo / present — finishing
  its site, deck, launch post, product. Casual phrasings count ("we pitch in 5", "get whisk ready").
- "party": plan or throw a party, birthday, surprise, celebration or get-together for someone.
- "goal": any other concrete task for the agents (research, compare, build, find, write...).
- "chat": not a task — greetings, thanks, reactions, questions about Hive itself.
Set rehearsal=true only if they explicitly ask for a test, practice, dry run or rehearsal.
Give a short reply Hive can text back (under 12 words) when intent is "chat"."""

SCHEMA = {
    "type": "object",
    "properties": {
        "intent": {"type": "string", "enum": ["pitch", "party", "goal", "chat"]},
        "rehearsal": {"type": "boolean"},
        "reply": {"type": "string", "description": "only for chat: a short friendly reply"},
    },
    "required": ["intent"],
}


@dataclass
class Intent:
    kind: str              # pitch | party | goal | chat
    rehearsal: bool = False
    reply: str = ""
    source: str = "rules"  # claude | rules


_PITCH = re.compile(r"(?i)\b(pitch|demo day|whisk|present(ation)?|investors?)\b")
_PARTY = re.compile(r"(?i)\b(party|birthday|bday|b-day|surprise|celebrat\w*|get-?together)\b")
_TEST = re.compile(r"(?i)\b(test|practice|dry ?run|rehears\w*)\b")
_CHAT = re.compile(r"(?i)^\s*(hi|hey|hello|yo|thanks?|thank you|ty|ok(ay)?|cool|nice|lol|haha|👍|❤️)\W*$")


def rules(text: str) -> Intent:
    t = text.strip()
    if _CHAT.match(t):
        return Intent("chat", reply="Hey! Text me a task and I'll put a team on it.")
    rehearsal = bool(_TEST.search(t))
    if _PARTY.search(t):
        return Intent("party", rehearsal)
    if _PITCH.search(t):
        return Intent("pitch", rehearsal)
    return Intent("goal", rehearsal)


async def classify(text: str) -> Intent:
    if not llm.available():
        return rules(text)
    try:
        raw = await asyncio.wait_for(
            llm.call_tool(SYSTEM, f"Message: {text!r}", "route", SCHEMA, "Route the message.",
                          model=INTENT_MODEL, max_tokens=200, timeout=TIMEOUT_S), TIMEOUT_S + 1)
    except Exception:
        raw = None
    if not raw or raw.get("intent") not in ("pitch", "party", "goal", "chat"):
        return rules(text)
    return Intent(raw["intent"], bool(raw.get("rehearsal")), str(raw.get("reply") or "").strip(), "claude")
