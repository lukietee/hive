"""Words the pitch_in_5 agents write: from Claude when ANTHROPIC_API_KEY is set, else canned.

Every function returns canned text on any failure or slow response, so the live demo never stalls.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re

log = logging.getLogger("hive.content")

MODEL = "claude-opus-5-5"
TIMEOUT_S = 12.0

BRIEF = ("Whisk is a fictional startup: ceremonial-grade matcha (sourced from Uji, Kyoto), delivered weekly to "
         "college dorms, timed to class schedules. Standard plan $29/mo (4 tins), student plan $19/mo with a .edu "
         "email. Referrals earn 5 free credits. Launching at UCLA. All numbers are illustrative demo data.")

CANNED = {
    "s3_title": "A matcha subscription built for campus life.",
    "s3_body": ["Ceremonial-grade matcha, sourced from Uji, Kyoto",
                "Delivered weekly to dorms, timed to class schedules",
                "Referral credits turn every customer into a sales channel"],
    "post_long": ("Matcha, delivered to your dorm. 🍵 We built Whisk because campus cafés charge $7 a latte and the "
                  "lines during finals are brutal. Ceremonial-grade matcha from Uji, Kyoto, shipped weekly and timed "
                  "to your class schedule. {price}/mo, or $19 for students. Join the waitlist → {url} #matcha #LAHacks"),
    "post_short": "Matcha, delivered to your dorm. 🍵\nCeremonial-grade, shipped weekly, $19/mo for students.\nJoin the waitlist → {url}",
}


def enabled() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


async def _ask(prompt: str, max_tokens: int = 400) -> str | None:
    if not enabled():
        return None

    def call() -> str:
        import anthropic

        client = anthropic.Anthropic(timeout=TIMEOUT_S)
        msg = client.messages.create(model=MODEL, max_tokens=max_tokens,
                                     system=f"You write launch copy for a hackathon demo. {BRIEF} Reply with only what is asked.",
                                     messages=[{"role": "user", "content": prompt}])
        return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()

    try:
        return await asyncio.wait_for(asyncio.to_thread(call), TIMEOUT_S + 2)
    except Exception as exc:  # network, auth, timeout: fall back silently
        log.warning("claude call failed, using canned text: %s", exc)
        return None


async def solution_slide() -> tuple[str, list[str], str]:
    """(title, 3 bullets, source) for deck slide 3."""
    text = await _ask('For the "Our solution" pitch slide, return JSON {"title": "<= 8 words", "bullets": '
                      '["<= 9 words", "<= 9 words", "<= 9 words"]}.')
    try:
        data = json.loads(re.search(r"\{.*\}", text or "", re.S).group(0))  # type: ignore[union-attr]
        title, bullets = str(data["title"]).strip(), [str(b).strip() for b in data["bullets"]][:3]
        if title and len(bullets) == 3:
            return title, bullets, "claude"
    except Exception:
        pass
    return CANNED["s3_title"], CANNED["s3_body"], "canned"


async def launch_post(url: str, price: str) -> tuple[str, str]:
    """A first draft that is deliberately a bit too long (> 280 chars), so the 'make it shorter' moment is real."""
    text = await _ask(f"Write a launch post for X announcing Whisk's waitlist. Include the URL {url} and the price "
                      f"{price}/mo ($19 for students). Make it 300-340 characters (slightly too long on purpose), "
                      f"1-2 hashtags, one emoji. Return only the post.")
    if text and 200 < len(text) < 420 and url in text:
        return text, "claude"
    return CANNED["post_long"].format(url=url, price=price), "canned"


async def shorten_post(post: str, url: str, request: str) -> tuple[str, str]:
    text = await _ask(f'The human said: "{request}". Rewrite this post to under 200 characters, keep the URL {url} '
                      f"and the student price. Return only the post.\n\n{post}")
    if text and len(text) <= 280 and url in text:
        return text, "claude"
    return CANNED["post_short"].format(url=url), "canned"
