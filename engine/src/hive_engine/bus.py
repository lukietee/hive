"""Event bus: WebSocket server on ws://127.0.0.1:8765 (see docs/CONTRACT.md).

Engine → clients: one JSON event envelope per message.
Clients → engine: {"v": 1, "cmd": ..., "args": {...}} commands.
"""

from __future__ import annotations

import asyncio
import signal
import os
import json
import logging
import re
import time
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from websockets.asyncio.server import ServerConnection, broadcast, serve

from .agents import find_agent_by_name

if TYPE_CHECKING:
    from .agent import Agent

log = logging.getLogger("hive.bus")

HOST = "127.0.0.1"
PORT = 8765


def _waiting(agent: Agent) -> bool:
    fut = getattr(agent, "_pending_answer", None)
    return fut is not None and not fut.done()


async def close_automation_windows() -> None:
    """Closes windows our agents opened that a cancelled run left behind: Chrome launched by
    Playwright (it uses --remote-debugging-pipe; a person's own Chrome never does), the agents'
    Chrome profile, and the agents' VS Code instance. Only those app processes are matched (by
    their executable path), so the user's own apps and any other program are never touched."""
    try:
        proc = await asyncio.create_subprocess_exec("ps", "-axo", "pid=,command=", stdout=asyncio.subprocess.PIPE)
        out, _ = await proc.communicate()
    except Exception:
        return
    me = os.getpid()
    for line in out.decode(errors="replace").splitlines():
        pid_s, _, cmd = line.strip().partition(" ")
        if not pid_s.isdigit() or int(pid_s) == me:
            continue
        chrome = cmd.startswith(("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                                 os.path.expanduser("~/Library/Caches/ms-playwright")))
        vscode = cmd.startswith("/Applications/Visual Studio Code.app/") and "HiveVSCode" in cmd
        if (chrome and ("--remote-debugging-pipe" in cmd or "HiveAgentsChrome" in cmd)) or vscode:
            try:
                os.kill(int(pid_s), signal.SIGTERM)
            except Exception:
                pass


class Bus:
    def __init__(self, host: str = HOST, port: int = PORT) -> None:
        self.host = host
        self.port = port
        self.clients: set[ServerConnection] = set()
        self.agents: dict[str, Agent] = {}
        # Messages from the human not addressed to a specific agent (e.g. "@everyone ...").
        self.conductor_inbox: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        # Runs a scenario by name on {"cmd": "start"}; set by __main__. args = the command's args.
        self.on_start: Callable[[str, dict[str, Any]], Awaitable[Any]] | None = None
        self.running: str | None = None  # name of the scenario in progress; a second "start" is rejected
        self.history: list[dict[str, Any]] = []  # replayed to late joiners (spawns etc.)
        # Native Deck Viewer geometry (screen points): its 1× slide rect, and replies to each deck_focus.
        self.deck_viewer: dict[str, float] | None = None
        self._deck_box: dict[str, Any] | None = None
        self._deck_box_seq = 0
        self._deck_box_changed = asyncio.Event()
        self._server = None

    # ---- lifecycle -------------------------------------------------------
    async def start(self) -> None:
        self._server = await serve(self._handler, self.host, self.port)
        log.info("bus listening on ws://%s:%d", self.host, self.port)

    async def close(self) -> None:
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    # ---- events ----------------------------------------------------------
    def emit(self, agent: str | None, type_: str, data: dict[str, Any] | None = None) -> dict[str, Any]:
        event = {"v": 1, "ts": round(time.time(), 3), "agent": agent, "type": type_, "data": data or {}}
        msg = json.dumps(event, ensure_ascii=False)
        if type_ in ("budget", "countdown"):  # only the latest one matters to a late joiner
            self.history = [e for e in self.history if e["type"] != type_] + [event]
        elif type_ == "agent_spawn":
            self.history.append(event)
        elif type_ == "agent_done":
            self.history = [e for e in self.history if not (e["type"] == "agent_spawn" and e["agent"] == agent)]
        broadcast(self.clients, msg)
        return event

    # ---- native Deck Viewer ------------------------------------------------
    def deck_box_mark(self) -> int:
        """Call before emitting deck_focus; pass the result to wait_deck_box."""
        return self._deck_box_seq

    async def wait_deck_box(self, slide: int, since: int, timeout: float = 0.5) -> tuple[float, float, float, float] | None:
        """The viewer's reply to a deck_focus for `slide` (screen rect after its zoom), or None on timeout."""
        loop = asyncio.get_running_loop()
        deadline = loop.time() + timeout
        while True:
            box = self._deck_box
            if self._deck_box_seq > since and box and int(box.get("slide", -1)) == slide:
                return float(box["x"]), float(box["y"]), float(box["w"]), float(box["h"])
            remaining = deadline - loop.time()
            if remaining <= 0:
                return None
            self._deck_box_changed.clear()
            try:
                await asyncio.wait_for(self._deck_box_changed.wait(), remaining)
            except asyncio.TimeoutError:
                return None

    # ---- runs ------------------------------------------------------------
    async def run_exclusive(self, name: str, factory: Callable[[], Awaitable[Any]]) -> Any:
        """Runs one scenario at a time: fresh agent registry + history, `running` set throughout."""
        if self.running and self.running != name:
            raise RuntimeError(f"{self.running} is already running")
        self.running = name
        self.agents.clear()
        self.history.clear()
        # Clients drop any cursors/windows left over from a run that ended without cleaning up.
        self.emit(None, "run_reset", {"scenario": name})
        try:
            return await factory()
        finally:
            self.running = None

    async def cancel_run(self) -> None:
        """The safe word: stop the running scenario now. Cancelling the task unwinds every agent
        (browser contexts, VS Code, worker subprocesses close in their finally blocks); then any
        automation windows still open are closed and clients clear their cursors."""
        task = getattr(self, "_run_task", None)
        name = self.running
        if task and not task.done():
            task.cancel()
            try:
                await asyncio.wait_for(asyncio.shield(task), 15)
            except BaseException:
                pass
        await close_automation_windows()
        await asyncio.sleep(3)              # a window that was still launching gets a second sweep
        await close_automation_windows()
        self.running = None
        self.agents.clear()
        self.emit(None, "run_reset", {"scenario": name, "cancelled": True})
        self.emit(None, "chat", {"text": "Hive: Cancelled. Every agent stopped and their windows are closed."
                                 if name else "Hive: Nothing was running."})

    async def _run_start(self, name: str, args: dict[str, Any]) -> None:
        assert self.on_start
        try:
            await self.on_start(name, args)
        except asyncio.CancelledError:
            log.info("scenario %s cancelled", name)
        except Exception as exc:  # report, never crash the bus
            log.exception("scenario %s failed", name)
            self.emit(None, "chat", {"text": f"🐝 Hive: {name} failed: {exc}"})
        finally:
            self.running = None

    # ---- agents ----------------------------------------------------------
    def register(self, agent: Agent) -> None:
        self.agents[agent.id] = agent

    # ---- websocket handler -----------------------------------------------
    async def _handler(self, ws: ServerConnection) -> None:
        self.clients.add(ws)
        log.info("client connected (%d total)", len(self.clients))
        try:
            for event in list(self.history):  # bring late joiners up to date
                await ws.send(json.dumps(event, ensure_ascii=False))
            async for raw in ws:
                try:
                    await self._command(json.loads(raw))
                except Exception as exc:  # never kill the connection on a bad command
                    log.warning("bad command %r: %s", raw, exc)
        finally:
            self.clients.discard(ws)
            log.info("client disconnected (%d left)", len(self.clients))

    async def _command(self, msg: dict[str, Any]) -> None:
        cmd = msg.get("cmd")
        args = msg.get("args") or {}
        target = args.get("agent")
        agents = [self.agents[target]] if target in self.agents else list(self.agents.values())

        if cmd == "start":
            name = args.get("scenario") or "pitch_in_5"
            if self.running:
                self.emit(None, "chat", {"text": f"🐝 Hive: {self.running} is already running, so I ignored that start."})
            elif self.on_start:
                self.running = name  # set synchronously so a double-click can't start two runs
                self._run_task = asyncio.create_task(self._run_start(name, args))
            else:
                log.warning("start ignored: no on_start handler")
        elif cmd == "cancel":
            await self.cancel_run()
        elif cmd == "pause":
            for a in agents:
                a.pause()
        elif cmd == "resume":
            for a in agents:
                a.resume()
        elif cmd == "say":
            text = args.get("text", "")
            if target not in self.agents:  # "@Social make it shorter" → route by mention
                m = re.match(r"\s*@(\w+)[\s,:]*(.*)", text, re.S)
                if m and (aid := find_agent_by_name(m.group(1))) in self.agents:
                    target, text = aid, m.group(2).strip() or text
            if target in self.agents:
                await self.agents[target].inbox.put({"from": "human", "text": text})
            else:
                await self.conductor_inbox.put({"from": "human", "text": text})
        elif cmd == "answer":
            # Without a (known) agent, answer whichever agent is currently waiting on the human.
            if target not in self.agents:
                target = next((a.id for a in self.agents.values() if _waiting(a)), None)
            if target in self.agents:
                self.agents[target].answer(args.get("choice"))
        elif cmd == "deck_viewer":
            self.deck_viewer = {k: float(args[k]) for k in ("x", "y", "w", "h")}
        elif cmd == "deck_box":
            self._deck_box = args
            self._deck_box_seq += 1
            self._deck_box_changed.set()
        else:
            log.warning("unknown command %r", cmd)
