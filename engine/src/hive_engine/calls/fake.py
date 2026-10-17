"""Scripted calls for building and demoing the Call UI without a phone line.

The bakery script follows party/BAKERY_CALL.md (disclosure first, order, read-back, close), and a
follow-up variant covers the "add 🎉 to the writing" callback. Optional voicing: ElevenLabs TTS
(ELEVENLABS_VOICE_ID for Hive, ELEVENLABS_THEM_VOICE_ID for the bakery) played with afplay.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import os
import re
import shutil
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .memory import state_dir

log = logging.getLogger("hive.calls.fake")

DEFAULT_CONTEXT = {
    "bakery_name": "Copper Whisk Bakery",
    "contact_name": "Dana",
    "cake_description": "6-inch matcha cake from the case",
    "writing": "Happy 21st Maya",
    "pickup_time": "6:00 PM",
    "price": 38,
}


@dataclass
class Line:
    speaker: str  # "agent" | "them"
    text: str
    pause: float = 0.5  # silence before the line (seconds)


@dataclass
class Script:
    lines: list[Line]
    summary: str
    details: dict[str, Any] = field(default_factory=dict)


def bakery_script(context: dict[str, Any], user_name: str, previous: dict[str, Any] | None = None) -> Script:
    c = DEFAULT_CONTEXT | {k: v for k, v in context.items() if v not in (None, "")}
    bakery, who, cake = c["bakery_name"], c["contact_name"], c["cake_description"]
    writing, pickup, price = c["writing"], c["pickup_time"], c["price"]
    size = "six-inch" if "6" in str(cake) else "one"

    if previous:
        change = context.get("change_request", "add a little party hat drawing after the writing")
        lines = [
            Line("them", f"{bakery}, this is {who}.", 0.2),
            Line("agent", f"Hi {who}, it's Hive again, the AI assistant for {user_name}. This call is still being "
                          f"recorded for our demo. Quick change on the matcha cake for {pickup}: could you {change}?"),
            Line("them", "Oh sure, that's easy. Same pickup time?", 0.7),
            Line("agent", f"Same time, {pickup}. Everything else stays the same. Thank you so much!"),
            Line("them", "No problem. See you then!", 0.5),
        ]
        return Script(lines, f"Done: {who} at {bakery} will {change}. Still ready at {pickup}.",
                      {"status": "confirmed", "bakery": bakery, "contact": who, "change": change,
                       "pickup_time": pickup})

    lines = [
        Line("them", f"Hi, {bakery}, this is {who}.", 0.2),
        Line("agent", f"Hi {who}! This is Hive, an AI assistant calling on behalf of {user_name}, who stopped by "
                      f"earlier today. Just so you know, I'm an AI and this call is being recorded for a hackathon "
                      f"demo. Is now still a good time?"),
        Line("them", "Oh, hi! Yes, I was expecting your call. Go ahead.", 0.8),
        Line("agent", f"Great. {user_name} said you might have a matcha cake in the case today?"),
        Line("them", f"We do. We have a {size} matcha cake left. It's {price} dollars.", 0.9),
        Line("agent", f"Perfect, we'll take it. Could you write \"{writing}\" on top?"),
        Line("them", "Yes, we can do that. When do you want to pick it up?", 0.7),
        Line("agent", f"Would {pickup} work?"),
        Line("them", f"{pickup} is fine.", 0.6),
        Line("agent", f"Just to confirm: one {size} matcha cake, with \"{writing}\", pickup at {pickup}, "
                      f"{price} dollars, paid at pickup. Is that right?"),
        Line("them", "That's right. We'll have it ready.", 0.6),
        Line("agent", "Thank you so much, have a great day!"),
        Line("them", "You too, bye!", 0.4),
    ]
    summary = (f"Confirmed with {who} at {bakery}: {cake}, \"{writing}\", ready at {pickup}, "
               f"${price} at pickup.")
    return Script(lines, summary, {"status": "confirmed", "bakery": bakery, "contact": who, "cake": cake,
                                   "writing": writing, "pickup_time": pickup, "price": price})


class Voice:
    """Voices fake-call lines with ElevenLabs TTS (cached on disk) and plays them with afplay."""

    def __init__(self, voices: dict[str, str]) -> None:
        self.voices = voices
        self.cache = state_dir() / "tts"
        self.files: dict[str, Path] = {}
        self.lengths: dict[str, float] = {}

    @classmethod
    def create(cls, enabled: bool) -> Voice | None:
        if not enabled:
            return None
        if not (os.environ.get("ELEVENLABS_API_KEY") and os.environ.get("ELEVENLABS_VOICE_ID")
                and shutil.which("afplay")):
            log.warning("TTS off: needs ELEVENLABS_API_KEY, ELEVENLABS_VOICE_ID and afplay")
            return None
        voices = {"agent": os.environ["ELEVENLABS_VOICE_ID"]}
        if them := os.environ.get("ELEVENLABS_THEM_VOICE_ID"):
            voices["them"] = them
        return cls(voices)

    def _key(self, line: Line) -> str:
        return hashlib.sha1(f"{self.voices.get(line.speaker)}|{line.text}".encode()).hexdigest()[:16]

    async def prepare(self, lines: list[Line]) -> None:
        from .elevenlabs import ElevenLabs

        self.cache.mkdir(parents=True, exist_ok=True)
        el = ElevenLabs()
        try:
            async def one(line: Line) -> None:
                voice_id = self.voices.get(line.speaker)
                if not voice_id:
                    return
                path = self.cache / f"{self._key(line)}.mp3"
                if not path.exists():
                    path.write_bytes(await el.tts(line.text, voice_id))
                self.files[self._key(line)] = path
                self.lengths[self._key(line)] = await _audio_seconds(path)

            await asyncio.gather(*(one(l) for l in lines))
        except Exception as exc:
            log.warning("TTS failed, continuing silently: %s", exc)
        finally:
            await el.close()

    def duration(self, line: Line) -> float | None:
        return self.lengths.get(self._key(line))

    async def play(self, line: Line) -> None:
        path = self.files.get(self._key(line))
        if path:
            proc = await asyncio.create_subprocess_exec("afplay", str(path))
            await proc.wait()


async def _audio_seconds(path: Path) -> float:
    proc = await asyncio.create_subprocess_exec("afinfo", str(path), stdout=asyncio.subprocess.PIPE,
                                                stderr=asyncio.subprocess.DEVNULL)
    out, _ = await proc.communicate()
    m = re.search(rb"estimated duration: ([\d.]+)", out)
    return float(m.group(1)) if m else 0.0
