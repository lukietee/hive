"""Messenger: bridges the engine bus ⇄ one iMessage thread with the owner.

It is just another bus client (like the live relay), so the engine needs no changes:
  bus events  → plain-text texts ("Checker: …"), batched so status chatter isn't spammy
  owner texts → bus commands: answer / say / start / pause / resume

Questions follow the Claude Code pattern: numbered best options plus "or tell me something else".
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import re
import socket
import time
from typing import Any

import websockets

from .. import memory
from ..agents import AGENTS, find_agent_by_name
from .fmt import Question, classify, format_question, parse_reply, prefix, question_from_event, strip_emoji

log = logging.getLogger("hive.messenger")

BUS_URL = os.environ.get("HIVE_BUS_URL", "ws://127.0.0.1:8765")
MODEL = os.environ.get("HIVE_MESSENGER_MODEL", "claude-opus-5-5")
BATCH_S = float(os.environ.get("HIVE_MESSENGER_BATCH_S", "2.0"))
# Events that become texts. agent_status / cursor events never do (that's what 👁 live view is for).
TEXTED = {"chat", "needs_human", "agent_done", "swarm_summary", "call_summary"}
ACTIVITY = {"agent_status", "moving_to", "click", "typing", "agent_done"}


def lan_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("10.255.255.255", 1))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except OSError:
        return "127.0.0.1"


def live_url(agent: str | None = None) -> str:
    base = os.environ.get("HIVE_PUBLIC_LIVE_URL") or f"http://{lan_ip()}:8766/live/"
    return base + (f"#{agent}" if agent else "")


class Messenger:
    def __init__(self, transport: Any, bus_url: str = BUS_URL) -> None:
        self.t = transport
        self.t.on_text = self.on_text
        self.bus_url = bus_url
        self.ws = None
        self.names: dict[str, str] = {}          # agent id → display name (from spawns)
        self.active: set[str] = set()            # spawned and not done
        self.questions: dict[str, Question] = {} # pending, by agent
        self._batch: list[str] = []
        self._batch_task: asyncio.Task | None = None
        self._connected_at = 0.0
        self._send_lock = asyncio.Lock()

    # ---- lifecycle -------------------------------------------------------------------------
    async def run(self) -> None:
        await self.t.start()
        while True:
            try:
                async with websockets.connect(self.bus_url, max_size=None) as ws:
                    self.ws = ws
                    self._connected_at = time.time()
                    log.info("connected to bus %s", self.bus_url)
                    async for raw in ws:
                        if isinstance(raw, bytes):
                            continue
                        try:
                            await self.on_event(json.loads(raw))
                        except Exception as exc:
                            log.exception("event failed: %s", exc)
            except (OSError, websockets.ConnectionClosed) as exc:
                log.info("bus unavailable (%s); retrying", exc)
            self.ws = None
            await asyncio.sleep(2)

    async def command(self, cmd: str, **args: Any) -> None:
        if not self.ws:
            await self.say_as("Hive", "The engine isn't running, so I can't do that yet.")
            return
        await self.ws.send(json.dumps({"v": 1, "cmd": cmd, "args": args}))

    # ---- outbound --------------------------------------------------------------------------
    def name_of(self, agent: str | None) -> str:
        if not agent:
            return "Hive"
        return self.names.get(agent) or AGENTS.get(agent, {}).get("name") or agent.capitalize()

    async def _send(self, text: str, agent: str | None = None) -> None:
        async with self._send_lock:
            await self.t.send_text(text)
        if agent:
            memory.append(agent, "text_out", text)

    def _known(self) -> set[str]:
        return set(self.names.values()) | {a["name"] for a in AGENTS.values()}

    async def say_as(self, name: str, text: str, agent: str | None = None) -> None:
        await self._send(prefix(name, text, self._known()), agent)

    def _queue(self, text: str) -> None:
        self._batch.append(text)
        if not self._batch_task or self._batch_task.done():
            self._batch_task = asyncio.create_task(self._flush_later())

    async def _flush_later(self) -> None:
        await asyncio.sleep(BATCH_S)
        await self.flush()

    async def flush(self) -> None:
        if not self._batch:
            return
        lines, self._batch = self._batch, []
        await self._send("\n".join(lines))

    # ---- bus events ------------------------------------------------------------------------
    async def on_event(self, e: dict[str, Any]) -> None:
        typ, agent, d = e.get("type"), e.get("agent"), e.get("data") or {}
        replay = float(e.get("ts") or 0) < self._connected_at - 0.5  # history sent on connect

        if typ == "agent_spawn" and agent:
            self.names[agent] = strip_emoji(str(d.get("name") or self.name_of(agent)))
            self.active.add(agent)
            return
        if agent and typ in ACTIVITY and agent in self.questions and typ != "agent_done":
            # Answered somewhere else (the notch) — the agent moved on.
            self.questions.pop(agent, None)
        if typ == "agent_done" and agent:
            self.active.discard(agent)
            self.questions.pop(agent, None)
        if replay or typ not in TEXTED:
            return

        name = self.name_of(agent)
        if typ == "chat":
            text = strip_emoji(str(d.get("text", "")))
            if text:
                self._queue(prefix(name, text, self._known()))
                if agent:
                    memory.append(agent, "text_out", text)
        elif typ == "agent_done":
            if d.get("summary"):
                self._queue(f"{name}: Done. {strip_emoji(str(d['summary']))}")
        elif typ == "needs_human" and agent:
            q = question_from_event(agent, name, d, float(e.get("ts") or time.time()))
            self.questions[agent] = q
            await self.flush()  # keep order: context first, then the question
            if q.image:
                await self.t.send_image(q.image)
            await self._send(format_question(q), agent)
        elif typ == "swarm_summary":
            await self.flush()
            lines = [strip_emoji(str(x)) for x in d.get("lines") or []]
            body = "\n".join(f"- {x}" for x in lines if x)
            await self._send(f"Hive: {strip_emoji(str(d.get('title', 'Done')))}" + (f"\n\n{body}" if body else ""))
        elif typ == "call_summary":
            await self.flush()
            to = d.get("to") or d.get("callee") or "the call"
            await self.say_as(name, f"Call with {to} ended. {strip_emoji(str(d.get('summary', '')))}".strip(), agent)

    # ---- inbound texts ---------------------------------------------------------------------
    def resolve(self, who: str) -> str | None:
        w = who.strip().lstrip("@").lower()
        for aid, n in self.names.items():
            if w in (aid, n.lower()):
                return aid
        return find_agent_by_name(w)

    def _latest_question(self) -> Question | None:
        return max(self.questions.values(), key=lambda q: q.asked_at, default=None)

    async def on_text(self, text: str) -> None:
        text = text.strip()
        if not text:
            return
        log.info("owner: %s", text)
        inb = classify(text, self.resolve)

        if inb.kind == "start":
            await self.command("start", scenario=inb.scenario)
            await self.say_as("Hive", f"Starting {'Pitch in 5' if inb.scenario == 'pitch_in_5' else inb.scenario}.")
        elif inb.kind in ("pause", "resume"):
            await self.command(inb.kind)
            await self.say_as("Hive", "Paused everyone." if inb.kind == "pause" else "Back to work.")
        elif inb.kind == "show":
            await self.say_as(self.name_of(inb.agent), f"Watch me live: {live_url(inb.agent)}", inb.agent)
        elif inb.kind == "everyone":
            await self.command("say", text=inb.text)
            await self.say_as("Hive", "Got it, passing that to everyone.")
        elif inb.kind == "mention":
            await self._to_agent(inb.agent, inb.text)
        else:
            q = self._latest_question()
            if q:
                await self._answer(q, text)
            elif self.active:
                await self.command("say", text=text)
                await self.say_as("Hive", "Got it, passing that to the team.")
            else:
                await self.say_as("Hive", 'Nothing is running right now. Text "start" to run Pitch in 5, '
                                          'or @ an agent to ask about earlier work.')

    async def _to_agent(self, agent: str, text: str) -> None:
        memory.append(agent, "text_in", text)
        if agent in self.questions:
            await self._answer(self.questions[agent], text)
        elif agent in self.active:
            await self.command("say", agent=agent, text=text)
            await self.say_as(self.name_of(agent), "On it.", agent)
        elif memory.has(agent):
            await self.say_as(self.name_of(agent), await self._recall(agent, text), agent)
        else:
            await self.say_as("Hive", f"{self.name_of(agent)} isn't running right now.")

    async def _answer(self, q: Question, text: str) -> None:
        r = parse_reply(q, text)
        if r.rejected:
            await self._send(f"{q.name}: I need an explicit YES to spend money. Reply YES to approve or NO.", q.agent)
            return
        choice, free = r.choice, r.free_text
        if free and q.options:
            mapped = await self._interpret(q, text)
            if mapped is not None:
                choice, free = mapped, False
        self.questions.pop(q.agent, None)
        args: dict[str, Any] = {"agent": q.agent, "choice": choice}
        if free:
            args["free_text"] = True
        await self.command("answer", **args)
        if q.kind == "approval":
            ack = "Approved." if choice == "YES" else "Cancelled, nothing was charged."
        elif free:
            ack = "Got it, I'll work with that."
        else:
            ack = f"Got it, going with {choice}."
        await self.say_as(q.name, ack, q.agent)

    # ---- Claude helpers (optional; the thread still works without a key) -------------------
    def _claude(self):
        if not os.environ.get("ANTHROPIC_API_KEY"):
            return None
        import anthropic
        return anthropic.AsyncAnthropic(timeout=20)

    async def _interpret(self, q: Question, text: str) -> str | None:
        """Map a free-text reply onto one of the options when it clearly picks one."""
        client = self._claude()
        if not client:
            return None
        opts = "\n".join(f"{i}. {o}" for i, o in enumerate(q.options, 1))
        prompt = (f"An AI agent asked a human: {q.question}\nOptions:\n{opts}\n\nThe human replied: {text!r}\n\n"
                  "If the reply clearly chooses one of the options, answer with just that option's number. "
                  "If it asks for something different or is ambiguous, answer NONE.")
        try:
            msg = await client.messages.create(model=MODEL, max_tokens=300,
                                               messages=[{"role": "user", "content": prompt}])
            out = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
            m = re.match(r"\s*(\d+)", out)
            if m and 1 <= int(m.group(1)) <= len(q.options):
                return q.options[int(m.group(1)) - 1]
        except Exception as exc:
            log.warning("interpret failed: %s", exc)
        return None

    async def _recall(self, agent: str, text: str) -> str:
        """Answer a question about an agent's past work (e.g. a finished call) from its memory."""
        recs = memory.read(agent, limit=120)
        client = self._claude()
        if not client:
            last = next((r for r in reversed(recs) if r.get("kind") in ("call_summary", "summary")), None)
            return (f"Here's what I have: {last['text']}" if last else "I don't have anything on that yet.")
        notes = "\n".join(f"[{r.get('kind')}] {r.get('text')}" for r in recs)
        prompt = (f"You are {self.name_of(agent)}, one agent in a team of AI agents. Here is your memory "
                  f"(texts, call transcripts and summaries):\n{notes}\n\nThe human now texts you: {text!r}\n"
                  "Reply in one or two short plain-text sentences, like a text message, without a name prefix. "
                  "If your memory doesn't cover it, say so.")
        try:
            msg = await client.messages.create(model=MODEL, max_tokens=600,
                                               messages=[{"role": "user", "content": prompt}])
            return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
        except Exception as exc:
            log.warning("recall failed: %s", exc)
            return "I couldn't look that up just now."
