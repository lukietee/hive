"""Builds the voice agent's system prompt and first message for one call.

The template is the fenced block in party/VOICE_AGENT_PROMPT.md ({{var}} fields plus one
{{#if previous_call}} … {{/if}} section). Other kinds of calls get a generic prompt built from the
goal and context. Every prompt starts with the non-negotiable AI + recording disclosure.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

REPO_DIR = Path(__file__).resolve().parents[4]
TEMPLATE_FILE = REPO_DIR / "party" / "VOICE_AGENT_PROMPT.md"

DISCLOSURE_RULES = """# Who you are (non-negotiable)
- Your opening line is already said for you (a quick hello, what you're calling about, and a
  short aside that you're an AI assistant and the call is recorded). Don't repeat it or give a
  speech: after it, just talk like a normal friendly caller and get to the order.
- Never claim or imply you are human. If asked, say plainly: "I'm an AI assistant."
- If the person says they don't want to be recorded or talk to an AI, apologize, say
  {user_name} will follow up directly, and end the call politely.
- Never give, ask for, or repeat card numbers or any payment details."""


def _template() -> str | None:
    if not TEMPLATE_FILE.exists():
        return None
    m = re.search(r"```\n(.*?)```", TEMPLATE_FILE.read_text(), re.S)
    return m.group(1) if m else None


def _fill(template: str, values: dict[str, Any]) -> str:
    def if_block(m: re.Match[str]) -> str:
        return m.group(2) if values.get(m.group(1)) else ""

    out = re.sub(r"\{\{#if (\w+)\}\}\n?(.*?)\{\{/if\}\}\n?", if_block, template, flags=re.S)
    out = re.sub(r"\{\{(\w+)\}\}", lambda m: str(values.get(m.group(1), m.group(0))), out)
    # The template's "After the call → return JSON" section can't happen on a phone line; the
    # engine summarizes the transcript instead.
    return re.sub(r"\n# After the call.*", "\n", out, flags=re.S).strip()


def first_message(user_name: str, label: str, previous: dict[str, Any] | None = None,
                  about: str = "") -> str:
    """One short, natural line: what the call is about, with the AI + recording note as a quick aside."""
    if previous:
        return f"Hi, it's {user_name}'s assistant again, quick follow-up on the order. Still recorded. Got a sec?"
    about = about or ("a cake order" if re.search(r"(?i)bak|cake", label or "") else "a quick question")
    return f"Hi! Calling for {user_name} about {about}. Heads up, I'm an AI assistant and this call's recorded. Got a minute?"


def build_prompt(goal: str, context: dict[str, Any], user_name: str,
                 previous: dict[str, Any] | None = None) -> str:
    """System prompt for the call. Uses the cake template when the context looks like a cake order."""
    values = {"user_name": user_name, **context}
    if previous:
        values |= {"previous_call": True, "previous_call_summary": previous.get("summary", ""),
                   "change_request": context.get("change_request", goal)}
    tpl = _template()
    if tpl and "cake_description" in context:
        return _fill(tpl, values)

    facts = "\n".join(f"- {k.replace('_', ' ')}: {v}" for k, v in context.items()) or "- (none)"
    memory = ""
    if previous:
        memory = ("\n\n# Memory\nThis is a FOLLOW-UP call. What was agreed last time:\n"
                  f"{previous.get('summary', '')}\nOnly change: {values['change_request']}. "
                  "Do not re-negotiate anything else.")
    return (f"You are Hive, an AI assistant placing a phone call on behalf of {user_name}.\n\n"
            f"{DISCLOSURE_RULES.format(user_name=user_name)}\n\n"
            f"# Your goal\n{goal}\n\n# Details\n{facts}\n\n"
            "# How to talk\n- Warm, brief, natural. Short sentences. Let them finish.\n"
            "- No long intro: answer like a normal caller and get to the point right away.\n"
            "- Before hanging up, read back what was agreed.\n"
            "- If they're busy, offer to call back later." + memory)
