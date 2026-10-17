"""place_call(): one outbound phone call by a Hive agent, live or simulated.

Live:  ElevenLabs hosted agent (prompt set per call) → POST sip-trunk/outbound-call → Photon SIP line
       → the recipient's phone. The engine polls the conversation for status + transcript.
Fake:  a scripted call played through the same bus events, for building/demoing the UI with no keys
       (and optionally voiced with ElevenLabs TTS through the Mac speakers).

Events (docs/CONTRACT.md, "Calls"), all with agent = the calling agent:
    call_started     {call_id, to, label, mode}
    call_state       {call_id, state: "ringing"|"connected"|"ended"}
    call_transcript  {call_id, speaker: "agent"|"them", text, final}
    call_ended       {call_id, duration_s, outcome, summary, details}
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import time
import uuid
from dataclasses import asdict, dataclass, field
from typing import TYPE_CHECKING, Any

from . import fake as fake_script
from .elevenlabs import ElevenLabs, ElevenLabsError, missing_live_config
from .memory import CallMemory
from .prompt import build_prompt, first_message

if TYPE_CHECKING:
    from ..agent import Agent

log = logging.getLogger("hive.calls")
POLL_S = 1.0
MAX_CALL_S = 600
SUMMARY_MODEL = "claude-opus-5-5"


@dataclass
class CallResult:
    call_id: str
    mode: str
    to: str
    label: str
    outcome: str = "unknown"
    summary: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    duration_s: int = 0
    transcript: list[dict[str, Any]] = field(default_factory=list)
    conversation_id: str | None = None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


async def place_call(agent: Agent, *, to: str, label: str, goal: str, context: dict[str, Any] | None = None,
                     user_name: str | None = None, follow_up: bool = False, fake: bool | None = None,
                     tts: bool = False, speed: float = 1.0, memory: CallMemory | None = None) -> CallResult:
    """Places one call and returns when it has ended (and been summarized + stored)."""
    context = dict(context or {})
    user_name = user_name or os.environ.get("HIVE_USER_NAME", "Lucas")
    memory = memory or CallMemory()
    previous = memory.latest(agent.id) if follow_up else None

    missing = missing_live_config()
    if fake is None:
        fake = bool(missing)
    elif not fake and missing:
        raise ElevenLabsError("live call needs: " + ", ".join(missing))

    res = CallResult(call_id=uuid.uuid4().hex[:8], mode="fake" if fake else "live", to=to, label=label)
    started = time.time()
    emit = _emitter(agent, res)
    emit("call_started", to=to, label=label, mode=res.mode)
    agent.status(f"Calling {label}", 0.1)
    agent.chat(f"Calling {label} now" + (" (simulated call)" if fake else "") + ".")

    try:
        if fake:
            await _run_fake(agent, res, emit, context, user_name, previous, tts, speed)
        else:
            await _run_live(agent, res, emit, goal, context, user_name, previous)
    except Exception as exc:  # never leave the Call window hanging
        log.exception("call failed")
        res.error = str(exc)
        res.outcome = "failure"
        res.summary = res.summary or f"The call didn't go through: {exc}"
    res.duration_s = res.duration_s or int(time.time() - started)

    if not res.summary or (res.mode == "live" and not res.details):
        await _summarize(res, goal)
    emit("call_state", state="ended")
    emit("call_ended", duration_s=res.duration_s, outcome=res.outcome, summary=res.summary, details=res.details)
    agent.status(f"Call with {label} {'done' if res.outcome == 'success' else 'ended'}", 1.0)
    agent.chat(res.summary)

    memory.record(agent.id, {**res.as_dict(), "goal": goal, "context": context, "follow_up": follow_up,
                             "started_at": round(started, 3), "ended_at": round(time.time(), 3)})
    return res


def _emitter(agent: Agent, res: CallResult):
    def emit(type_: str, **data: Any) -> None:
        agent.emit(type_, call_id=res.call_id, **data)
    return emit


# ---- live ------------------------------------------------------------------------------------

async def _run_live(agent: Agent, res: CallResult, emit, goal: str, context: dict[str, Any],
                    user_name: str, previous: dict[str, Any] | None) -> None:
    el = ElevenLabs()
    try:
        agent_id = os.environ["ELEVENLABS_AGENT_ID"]
        await el.configure_agent(agent_id, build_prompt(goal, context, user_name, previous),
                                 first_message(user_name, res.label, previous),
                                 voice_id=os.environ.get("ELEVENLABS_VOICE_ID"))
        number_id = await el.phone_number_id()
        dyn = {"user_name": user_name, **{k: v for k, v in context.items() if isinstance(v, (str, int, float))}}
        call = await el.outbound_call(agent_id, number_id, res.to, dyn)
        res.conversation_id = call.get("conversation_id")
        emit("call_state", state="ringing")
        if not res.conversation_id:
            raise ElevenLabsError(f"no conversation_id in response: {call}")

        seen = 0
        connected = False
        t0 = time.monotonic()
        while time.monotonic() - t0 < MAX_CALL_S:
            await asyncio.sleep(POLL_S)
            await agent.gate()
            conv = await el.conversation(res.conversation_id)
            status = conv.get("status")
            if status == "in-progress" and not connected:
                connected = True
                emit("call_state", state="connected")
                agent.status(f"On the phone with {res.label}", 0.4)
            turns = [t for t in conv.get("transcript") or [] if (t.get("message") or "").strip()]
            for t in turns[seen:]:
                speaker = "agent" if t.get("role") == "agent" else "them"
                entry = {"speaker": speaker, "text": t["message"].strip(), "t": t.get("time_in_call_secs")}
                res.transcript.append(entry)
                emit("call_transcript", speaker=speaker, text=entry["text"], final=True)
            seen = len(turns)
            if status in ("processing", "done", "failed"):
                res.duration_s = int((conv.get("metadata") or {}).get("call_duration_secs") or 0)
                if status == "processing":  # call is over; give the analysis a moment
                    for _ in range(20):
                        await asyncio.sleep(1.5)
                        conv = await el.conversation(res.conversation_id)
                        if conv.get("status") in ("done", "failed"):
                            break
                analysis = conv.get("analysis") or {}
                res.outcome = {"success": "success", "failure": "failure"}.get(analysis.get("call_successful"),
                                                                               "failure" if status == "failed" else "unknown")
                res.summary = analysis.get("transcript_summary") or ""
                break
        else:
            res.outcome, res.summary = "unknown", "The call ran past the time limit."
    finally:
        await el.close()


# ---- fake ------------------------------------------------------------------------------------

async def _run_fake(agent: Agent, res: CallResult, emit, context: dict[str, Any], user_name: str,
                    previous: dict[str, Any] | None, tts: bool, speed: float) -> None:
    script = fake_script.bakery_script(context, user_name, previous)
    voice = fake_script.Voice.create(tts)
    if voice:
        await voice.prepare([line for line in script.lines])

    await asyncio.sleep(0.8 / speed)
    emit("call_state", state="ringing")
    await asyncio.sleep(3.2 / speed)  # two rings
    emit("call_state", state="connected")
    agent.status(f"On the phone with {res.label}", 0.4)
    t_call = time.monotonic()

    for i, line in enumerate(script.lines):
        await agent.gate()
        await asyncio.sleep(line.pause / speed)
        duration = (voice.duration(line) if voice else None) or max(1.2, 0.33 * len(line.text.split())) / speed
        play = asyncio.create_task(voice.play(line)) if voice else None
        words = line.text.split()
        # Stream partial captions the way a live transcript fills in, then the final line.
        steps = min(len(words), 6)
        for k in range(1, steps):
            emit("call_transcript", speaker=line.speaker, text=" ".join(words[: max(1, len(words) * k // steps)]),
                 final=False)
            await asyncio.sleep(duration / steps)
        await asyncio.sleep(duration / steps)
        if play:
            await play
        emit("call_transcript", speaker=line.speaker, text=line.text, final=True)
        res.transcript.append({"speaker": line.speaker, "text": line.text,
                               "t": round(time.monotonic() - t_call, 1)})
        agent.status(f"On the phone with {res.label}", min(0.45 + 0.5 * (i + 1) / len(script.lines), 0.95))

    res.duration_s = int((time.monotonic() - t_call) * speed)
    res.outcome, res.summary, res.details = "success", script.summary, script.details


# ---- summary ---------------------------------------------------------------------------------

async def _summarize(res: CallResult, goal: str) -> None:
    """Fills summary/details from the transcript with Claude when available."""
    if not res.transcript or not os.environ.get("ANTHROPIC_API_KEY"):
        if not res.summary:
            res.summary = f"Call with {res.label} ended ({res.outcome})."
        return
    text = "\n".join(f"{'Hive' if t['speaker'] == 'agent' else res.label}: {t['text']}" for t in res.transcript)
    try:
        import anthropic

        client = anthropic.AsyncAnthropic(timeout=30)
        msg = await client.messages.create(
            model=SUMMARY_MODEL, max_tokens=600,
            system=("Summarize a phone call an AI assistant made. Reply with JSON only: "
                    '{"outcome": "success"|"failure"|"unknown", "summary": "1-2 sentences for a text message", '
                    '"details": {key facts agreed, e.g. item, price, time, names; numbers as numbers}}'),
            messages=[{"role": "user", "content": f"Goal: {goal}\n\nTranscript:\n{text}"}])
        raw = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        data = json.loads(re.search(r"\{.*\}", raw, re.S).group(0))  # type: ignore[union-attr]
        res.summary = data.get("summary") or res.summary
        res.details = data.get("details") or res.details
        if res.outcome == "unknown":
            res.outcome = data.get("outcome", "unknown")
    except Exception as exc:
        log.warning("call summary fell back: %s", exc)
        res.summary = res.summary or f"Call with {res.label} ended ({res.outcome})."
