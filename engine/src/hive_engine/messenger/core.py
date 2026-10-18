"""Messenger: bridges the engine bus ⇄ the owner's iMessage chat.

Shared Photon line: one 1:1 thread. Dedicated line: every run ("session") gets its own chat — a
group with the owner plus any listed members — announced as agents join ("Hive added Cake: …").

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
from datetime import datetime
from pathlib import Path
from typing import Any

import websockets

from .. import memory
from ..agents import AGENTS, find_agent_by_name
from . import intent
from .fmt import ICON, brief, tagged, warn_or, _WARN as WARN_RE, Question, classify, format_question, parse_reply, prefix, question_from_event, strip_emoji

log = logging.getLogger("hive.messenger")

BUS_URL = os.environ.get("HIVE_BUS_URL", "ws://127.0.0.1:8765")
MODEL = os.environ.get("HIVE_MESSENGER_MODEL", "claude-opus-5-5")
BATCH_S = float(os.environ.get("HIVE_MESSENGER_BATCH_S", "2.0"))
# Events that become texts. agent_status / cursor events never do (that's what 👁 live view is for).
TEXTED = {"chat", "needs_human", "agent_done", "swarm_summary", "call_ended"}
ACTIVITY = {"agent_status", "moving_to", "click", "typing", "agent_done"}
ANNOUNCE_S = float(os.environ.get("HIVE_ANNOUNCE_S", "1.5"))  # collect spawns + first status, then announce
SESSION_FILE = Path(os.environ.get("HIVE_STATE_DIR") or Path(__file__).resolve().parents[3] / "state") \
    / "messenger_session.json"
SCENARIO_TITLES = {"pitch_in_5": "Pitch in 5", "party": "Surprise Party",
                   "demo_sim": "Hive demo", "goal": "Hive"}


def group_members_from_env() -> list[str]:
    return [p.strip() for p in os.environ.get("HIVE_GROUP_MEMBERS", "").split(",") if p.strip()]


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
        self.calls: dict[str, str] = {}          # call_id → who was called ("Bakery")
        self._said: dict[str, tuple[float, str]] = {}  # agent → (when, call summary just texted)
        self._batch: list[str] = []
        self._batch_from: list[str | None] = []   # which agent queued each batch line (for de-duping)
        self._batch_task: asyncio.Task | None = None
        self._connected_at = 0.0
        self._send_lock = asyncio.Lock()
        # Sessions (dedicated line): one chat per run.
        self.session: dict[str, Any] | None = None
        self._session_lock = asyncio.Lock()
        self._intro: dict[str, str] = {}          # agent → first goal/status, for the "added" line
        self._joined: list[str] = []              # spawned, not yet announced
        self._announce_task: asyncio.Task | None = None

    # ---- lifecycle -------------------------------------------------------------------------
    async def run(self) -> None:
        await self.t.start()
        await self._resume_session()
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
        icon = next((i for i in ICON.values() if text.startswith(i + " ")), None)
        if icon:  # our own status icon goes in front of the name: "👍 Hive: Passed to the team"
            await self._send(f"{icon} {prefix(name, text[len(icon) + 1:], self._known())}", agent)
            return
        await self._send(prefix(name, text, self._known()), agent)

    def _queue(self, text: str, agent: str | None = None, progress: bool = False) -> None:
        self._batch.append(text)
        self._batch_from.append(f"progress:{agent}" if progress and agent else agent)
        if not self._batch_task or self._batch_task.done():
            self._batch_task = asyncio.create_task(self._flush_later())

    def _drop_progress(self, agent: str) -> None:
        """An agent's ✅ wrap-up replaces its progress lines still waiting in the batch."""
        keep = [(t, a) for t, a in zip(self._batch, self._batch_from) if a != f"progress:{agent}"]
        self._batch = [t for t, _ in keep]
        self._batch_from = [a for _, a in keep]

    async def _flush_later(self) -> None:
        await asyncio.sleep(BATCH_S)
        await self.flush()

    async def flush(self) -> None:
        if not self._batch:
            return
        lines, self._batch, self._batch_from = self._batch, [], []
        await self._send("\n".join(lines))

    # ---- sessions (one chat per run on a dedicated line) -----------------------------------
    def _groups_on(self) -> bool:
        return bool(getattr(self.t, "group_capable", False))

    def _save_session(self) -> None:
        try:
            SESSION_FILE.parent.mkdir(parents=True, exist_ok=True)
            SESSION_FILE.write_text(json.dumps(self.session or {}, indent=2))
        except OSError as exc:
            log.warning("couldn't save session: %s", exc)

    async def _resume_session(self) -> None:
        if not self._groups_on():
            return
        try:
            saved = json.loads(SESSION_FILE.read_text())
        except (OSError, ValueError):
            return
        if saved.get("space_id") and not saved.get("done") and await self.t.resume(saved["space_id"]):
            self.session = saved
            log.info("rejoined session %r in %s", saved.get("title"), saved["space_id"])

    async def start_session(self, title: str, goal: str = "", members: list[str] | None = None) -> None:
        """Open the chat for a new run. Members: the owner plus HIVE_GROUP_MEMBERS and the event's
        list, nobody else. On a shared line this is a no-op (everything stays in the 1:1)."""
        if not self._groups_on():
            return
        async with self._session_lock:
            if self.session and not self.session.get("done") and self.session.get("title") == title:
                return  # same run (session_start after a start command, or a replay)
            await self.flush()
            mem = list(dict.fromkeys([*group_members_from_env(), *(members or [])]))
            space = await self.t.open_session(title, mem)
            if not space:
                log.warning("couldn't open a chat for %r; staying in the current one", title)
                return
            self.session = {"space_id": space, "title": title, "goal": goal, "members": mem,
                            "group": len(mem) > 0, "created_at": time.time(), "done": False}
            self._save_session()
        header = title if self._has_emoji_prefix(title) else f"🐝 {title}"
        if goal and goal.strip() != title.strip():
            header += f"\n{brief(goal, 100)}"
        await self._send(header)

    async def _ensure_session(self, hint: str | None = None) -> None:
        if not self._groups_on() or (self.session and not self.session.get("done")):
            return
        title = hint or f"Hive run {datetime.now().strftime('%-I:%M %p')}"
        await self.start_session(title)

    def _announce(self, agent: str) -> None:
        if agent not in self._joined:
            self._joined.append(agent)
        if not self._announce_task or self._announce_task.done():
            self._announce_task = asyncio.create_task(self._announce_later())

    async def _announce_later(self) -> None:
        await asyncio.sleep(ANNOUNCE_S)
        joined, self._joined = self._joined, []
        lines = []
        for a in joined:
            what = self._intro.get(a, "")
            lines.append(f"{ICON['added']} {self.name_of(a)}" + (f": {what}" if what else ""))
        if lines:
            await self.flush()
            await self._send("\n".join(lines))

    # ---- bus events ------------------------------------------------------------------------
    async def on_event(self, e: dict[str, Any]) -> None:
        typ, agent, d = e.get("type"), e.get("agent"), e.get("data") or {}
        replay = float(e.get("ts") or 0) < self._connected_at - 0.5  # history sent on connect

        if typ == "session_start":
            if not replay:
                # Optional "emoji" field: the run's icon, shown in front of the title in the chat.
                title = strip_emoji(str(d.get("title") or d.get("goal") or "Hive run"))
                emoji = str(d.get("emoji") or "").strip()[:4]
                await self.start_session(f"{emoji} {title}" if emoji else title,
                                         strip_emoji(str(d.get("goal") or "")),
                                         # Only phone numbers can join the group (never agent dicts or names).
                                         [str(m) for m in d.get("members") or []
                                          if isinstance(m, str) and re.fullmatch(r"\+\d{8,15}", m.strip())])
            return
        if typ == "agent_spawn" and agent:
            self.names[agent] = strip_emoji(str(d.get("name") or self.name_of(agent)))
            self.active.add(agent)
            intro = d.get("goal") or d.get("role") or d.get("task") or d.get("text")
            if intro:
                self._intro[agent] = self._short(intro)
            if not replay and self._groups_on():
                await self._ensure_session()
                self._announce(agent)
            return
        if typ == "agent_status" and agent and agent not in self._intro and d.get("text"):
            self._intro[agent] = self._short(d["text"])
        if agent and typ in ACTIVITY and agent in self.questions and typ != "agent_done":
            # Answered somewhere else (the notch) — the agent moved on.
            self.questions.pop(agent, None)
        if typ == "call_started":
            self.calls[str(d.get("call_id"))] = str(d.get("label") or d.get("to") or "the call")
        if typ == "agent_done" and agent:
            self.active.discard(agent)
            self.questions.pop(agent, None)
        if replay or typ not in TEXTED:
            return

        name = self.name_of(agent)
        if typ == "chat":
            text = strip_emoji(str(d.get("text", "")))
            if text and not self._repeat(agent, text):
                self._queue(warn_or(prefix(name, brief(text), self._known()), text), agent, progress=True)
                if agent:
                    memory.append(agent, "text_out", text)
            if d.get("image"):  # optional local path / URL (e.g. the Keynote invite): send after its caption
                await self.flush()
                await self.t.send_image(str(d["image"]))
        elif typ == "agent_done":
            summ = str(d.get("summary") or "")
            if agent:
                self._drop_progress(agent)
            if summ:
                line = f"{name}: {brief(summ, 90)}"
                self._queue(tagged("warn", line) if WARN_RE.search(summ) else tagged("done", line))
            elif self._groups_on():
                self._queue(tagged("done", f"{name} done"))
        elif typ == "needs_human" and agent:
            q = question_from_event(agent, name, d, float(e.get("ts") or time.time()))
            self.questions[agent] = q
            await self.flush()  # keep order: context first, then the question
            if q.image:
                await self.t.send_image(q.image)
            await self._send(format_question(q), agent)
        elif typ == "swarm_summary":
            await self.flush()
            lines = [brief(x, 70) for x in d.get("lines") or []]
            body = "\n".join(f"• {x}" for x in lines[:6] if x)
            await self._send(tagged("finish", brief(d.get("title", "Done"), 80)) + (f"\n{body}" if body else ""))
            if self.session:
                self.session["done"] = True  # the next run opens a new chat
                self._save_session()
        elif typ == "call_ended":
            await self.flush()
            who = self.calls.pop(str(d.get("call_id")), None) or "the call"
            summary = strip_emoji(str(d.get("summary", "")))
            self._said[agent or ""] = (time.time(), summary)  # the agent often chats the same summary next
            await self._send(tagged("call", f"{name}: call with {who} done. {brief(summary, 110)}".strip()), agent)

    @staticmethod
    def _has_emoji_prefix(title: str) -> bool:
        return bool(title) and strip_emoji(title[:3]) != title[:3].strip()

    @staticmethod
    def _short(text: Any, n: int = 70) -> str:
        t = strip_emoji(str(text)).strip().rstrip(".")
        if re.match(r"^[A-Z][a-z]+ing\b", t):  # "Calling the bakery" → "calling the bakery"
            t = t[0].lower() + t[1:]
        return t if len(t) <= n else t[: n - 1].rstrip() + "…"

    def _repeat(self, agent: str | None, text: str) -> bool:
        """True if this chat line just repeats a summary we already texted for the agent."""
        ts, said = self._said.get(agent or "", (0.0, ""))
        return bool(said) and time.time() - ts < 30 and (text in said or said in text)

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
        if text == "CANCEL":  # the safe word: all caps, nothing else
            self.questions.clear()
            await self.say_as("Hive", "🛑 Stopping every agent and closing their windows…")
            await self.command("cancel")
            return
        inb = classify(text, self.resolve)

        if inb.kind == "start":
            title = SCENARIO_TITLES.get(inb.scenario or "", inb.scenario or "Hive run")
            if self._groups_on():
                if self.session:
                    self.session["done"] = True
                await self.start_session(title)
            await self.command("start", scenario=inb.scenario)
            await self.say_as("Hive", f"Starting {title}")
        elif inb.kind in ("pause", "resume"):
            await self.command(inb.kind)
            await self.say_as("Hive", "Paused everyone." if inb.kind == "pause" else "Back to work.")
        elif inb.kind == "show":
            await self.say_as(self.name_of(inb.agent), f"{ICON['live']} Watch live: {live_url(inb.agent)}", inb.agent)
        elif inb.kind == "everyone":
            await self.command("say", text=inb.text)
            await self.say_as("Hive", tagged("ok", "Sent to everyone"))
        elif inb.kind == "mention":
            await self._to_agent(inb.agent, inb.text)
        else:
            q = self._latest_question()
            if q:
                await self._answer(q, text)
            elif self.active:
                await self.command("say", text=text)
                await self.say_as("Hive", tagged("ok", "Passed to the team"))
            else:
                await self._route_new_task(text)

    async def _route_new_task(self, text: str) -> None:
        """Nothing is running: Claude reads the text and decides what it is (intent.py)."""
        it = await intent.classify(text)
        log.info("intent: %s (rehearsal=%s, %s)", it.kind, it.rehearsal, it.source)
        if it.kind == "chat":
            await self.say_as("Hive", it.reply or "Text me a task and I'll put a team on it.")
            return
        if it.kind == "pitch":
            await self._start_run("pitch_in_5", SCENARIO_TITLES["pitch_in_5"])
            return
        party = os.environ.get("HIVE_PARTY_SCENARIO")  # a local party playbook, if this install has one
        if it.kind == "party" and party:
            args = ({"rehearsal": True} if it.rehearsal else {"real_call": True, "no_send": True})
            await self._start_run(party, "Party", party_goal=text, **args)
            return
        # Anything else (or a party without a playbook): the general orchestrator plans a team for it.
        # Texted goals stay read-only (web browsing, code/slides on temp copies): no calls, no texts
        # to other people, no purchases.
        await self.say_as("Hive", tagged("ok", "On it. Starting a group for this"))
        await self.command("start", scenario="goal", goal=text)

    async def _start_run(self, scenario: str, title: str, **args: Any) -> None:
        if self._groups_on():
            if self.session:
                self.session["done"] = True
            await self.start_session(title)
        await self.command("start", scenario=scenario, **args)
        await self.say_as("Hive", tagged("ok", f"On it: {title}"))

    async def _to_agent(self, agent: str, text: str) -> None:
        memory.append(agent, "text_in", text)
        if agent in self.questions:
            await self._answer(self.questions[agent], text)
        elif agent in self.active:
            await self.command("say", agent=agent, text=text)
            await self.say_as(self.name_of(agent), "On it.", agent)
        elif memory.has(agent) or self._call_context(agent):
            await self.say_as(self.name_of(agent), await self._recall(agent, text), agent)
        else:
            await self.say_as("Hive", f"{self.name_of(agent)} isn't running right now.")

    async def _answer(self, q: Question, text: str) -> None:
        r = parse_reply(q, text)
        if r.rejected:
            need = {"call": "to place the call", "post": "to post it"}.get(q.kind, "to spend money")
            icon = ICON.get(q.kind, ICON["approval"]) if q.kind in ("call", "post") else ICON["approval"]
            await self._send(f"{icon} {q.name}: I need a YES {need}. Reply YES or NO", q.agent)
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
        if q.kind == "call":
            ack = "Calling now." if choice == "YES" else "OK, not calling."
        elif q.kind == "post":
            ack = "Posting now." if choice == "YES" else "OK, not posting."
        elif q.kind == "approval":
            ack = "Approved." if choice == "YES" else "Cancelled, nothing was charged."
        elif free:
            ack = "Got it, I'll work with that."
        else:
            ack = f"Got it: {choice}"
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

    @staticmethod
    def _call_context(agent: str) -> str:
        """Recap of the agent's phone calls (hive_engine.calls.CallMemory), or '' if none."""
        try:
            from ..calls import CallMemory
            mem = CallMemory()
            return mem.context_text(agent) if mem.history(agent) else ""
        except Exception:
            return ""

    @staticmethod
    def _last_transcript(agent: str) -> str:
        try:
            from ..calls import CallMemory
            last = CallMemory().latest(agent) or {}
        except Exception:
            return ""
        return "\n".join(f"{t.get('speaker')}: {t.get('text')}" for t in last.get("transcript") or [])

    async def _recall(self, agent: str, text: str) -> str:
        """Answer a question about an agent's past work (texts + finished calls) from its memory."""
        recs = memory.read(agent, limit=120)
        calls = self._call_context(agent)
        client = self._claude()
        if not client:
            try:
                from ..calls import CallMemory
                last = (CallMemory().latest(agent) or {}).get("summary", "")
            except Exception:
                last = ""
            last = last or (recs[-1]["text"] if recs else "")
            return f"From my last call: {last}" if last else "I don't have anything on that yet."
        notes = "\n".join(f"[{r.get('kind')}] {r.get('text')}" for r in recs)
        prompt = (f"You are {self.name_of(agent)}, one agent in a team of AI agents. Your phone calls:\n"
                  f"{calls or '(none)'}\nTranscript of your latest call:\n{self._last_transcript(agent) or '(none)'}\n\n"
                  f"Your texts with the human:\n{notes or '(none)'}\n\nThe human now texts you: {text!r}\n"
                  "Reply in one or two short plain-text sentences, like a text message, without a name prefix. "
                  "If your memory doesn't cover it, say so.")
        try:
            msg = await client.messages.create(model=MODEL, max_tokens=600,
                                               messages=[{"role": "user", "content": prompt}])
            return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text").strip()
        except Exception as exc:
            log.warning("recall failed: %s", exc)
            return "I couldn't look that up just now."
