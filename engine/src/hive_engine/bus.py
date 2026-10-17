"""Event bus: WebSocket server on ws://127.0.0.1:8765 (see docs/CONTRACT.md).

Engine → clients: one JSON event envelope per message.
Clients → engine: {"v": 1, "cmd": ..., "args": {...}} commands.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import TYPE_CHECKING, Any, Awaitable, Callable

from websockets.asyncio.server import ServerConnection, broadcast, serve

if TYPE_CHECKING:
    from .agent import Agent

log = logging.getLogger("hive.bus")

HOST = "127.0.0.1"
PORT = 8765


class Bus:
    def __init__(self, host: str = HOST, port: int = PORT) -> None:
        self.host = host
        self.port = port
        self.clients: set[ServerConnection] = set()
        self.agents: dict[str, Agent] = {}
        # Messages from the human not addressed to a specific agent (e.g. "@everyone ...").
        self.conductor_inbox: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self.on_start: Callable[[str], Awaitable[None]] | None = None
        self.history: list[dict[str, Any]] = []  # replayed to late joiners (spawns etc.)
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
        if type_ in ("agent_spawn", "budget", "countdown"):
            self.history.append(event)
        elif type_ == "agent_done":
            self.history = [e for e in self.history if not (e["type"] == "agent_spawn" and e["agent"] == agent)]
        broadcast(self.clients, msg)
        return event

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
            if self.on_start:
                asyncio.create_task(self.on_start(args.get("scenario", "demo_sim")))
        elif cmd == "pause":
            for a in agents:
                a.pause()
        elif cmd == "resume":
            for a in agents:
                a.resume()
        elif cmd == "say":
            if target in self.agents:
                await self.agents[target].inbox.put({"from": "human", "text": args.get("text", "")})
            else:
                await self.conductor_inbox.put({"from": "human", "text": args.get("text", "")})
        elif cmd == "answer":
            if target in self.agents:
                self.agents[target].answer(args.get("choice"))
        else:
            log.warning("unknown command %r", cmd)
