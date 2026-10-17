"""call_sim — a simulated bakery call end to end, for the Mac Call window and the call memory.

The Cake agent "calls" a fictional bakery (FakeCall: same bus events as a live call, no phone line),
then, with follow_up=True, makes the short callback that adds a party hat to the writing, using the
first call's stored summary. Pass tts=True (or --tts) to voice the lines with ElevenLabs TTS.
"""

from __future__ import annotations

import asyncio

from ..agent import Agent
from ..bus import Bus
from ..calls import place_call
from ..calls.fake import DEFAULT_CONTEXT

FAKE_NUMBER = "+13105550142"  # 555-01xx: reserved for fiction


async def run(bus: Bus, fast: bool = False, tts: bool = False, follow_up: bool = True, **_) -> dict:
    speed = 2.5 if fast else 1.0
    cake = Agent(bus, "cake")
    cake.spawn()
    cake.status("Getting ready to call the bakery", 0.05)
    await asyncio.sleep(1.0 / speed)

    goal = "Order one matcha cake from the display case for pickup today, with writing on top."
    first = await place_call(cake, to=FAKE_NUMBER, label=DEFAULT_CONTEXT["bakery_name"], goal=goal,
                             context=dict(DEFAULT_CONTEXT), fake=True, tts=tts, speed=speed)
    out = {"first": first.as_dict()}

    if follow_up:
        await asyncio.sleep(6.0 / speed)  # long enough to read the summary card
        cake.chat("Lucas asked to add a party hat to the writing. Calling back.")
        second = await place_call(cake, to=FAKE_NUMBER, label=DEFAULT_CONTEXT["bakery_name"],
                                  goal="Add a small party hat drawing after the writing; change nothing else.",
                                  context={"change_request": "add a little party hat drawing after the writing"},
                                  follow_up=True, fake=True, tts=tts, speed=speed)
        out["follow_up"] = second.as_dict()

    await asyncio.sleep(4.0 / speed)
    cake.emit("agent_done", summary="Cake ordered")
    return {k: {kk: v[kk] for kk in ("call_id", "mode", "outcome", "summary", "duration_s")}
            | {"turns": len(v["transcript"])} for k, v in out.items()}
