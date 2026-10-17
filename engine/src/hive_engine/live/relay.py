"""Live-view relay: WebSocket server on ws://127.0.0.1:8767 for the 👁 page (see docs/CONTRACT.md).

It is just another bus client: it subscribes to ws://127.0.0.1:8765 for agent meta, status and
cursor events, and receives JPEG frames in-process from the screencast streamers. Each viewer gets:

  text   {"t": "hello", "agents": {id: {...state}}}            once, on connect
  text   {"t": "bus", "e": <bus event>}                          spawn / status / chat / done / needs_human ...
  text   {"t": "cursor", "agent", "fx", "fy", "kind": "move"|"click"|"typing", "duration_ms"?, "label"?, "text"?}
  binary [u16 big-endian header length][header JSON][JPEG]       header = {"agent", "seq", "ts", "cap"?, "w", "h"}
         (ts = relayed, cap = captured by Chrome, both epoch ms; w/h = page viewport in CSS px)

fx/fy are fractions (0–1) of the agent's page viewport. Frames are "latest wins" per viewer, so a
slow phone never builds up a backlog; text messages are delivered in order.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import struct
import time
from dataclasses import dataclass, field
from typing import Any

import websockets
from websockets.asyncio.server import ServerConnection, serve

from ..agents import AGENTS

log = logging.getLogger("hive.live")

LIVE_HOST = os.environ.get("HIVE_LIVE_HOST", "127.0.0.1")  # 0.0.0.0 to reach it from a phone on the LAN
LIVE_PORT = int(os.environ.get("HIVE_LIVE_PORT", "8767"))
BUS_URL = os.environ.get("HIVE_BUS_URL", "ws://127.0.0.1:8765")

FORWARD = {"agent_spawn", "agent_status", "chat", "agent_done", "needs_human", "swarm_summary", "countdown", "budget"}
CURSOR = {"moving_to": "move", "click": "click", "typing": "typing"}


@dataclass
class Geometry:
    """Where an agent's page viewport sits on screen (global points, top-left origin)."""
    ox: float
    oy: float
    w: float
    h: float


@dataclass
class AgentState:
    id: str
    name: str
    color: str
    emoji: str
    status: str = ""
    progress: float | None = None
    done: bool = False
    streaming: bool = False
    cursor: tuple[float, float] | None = None  # last fractions
    frame: bytes | None = None  # last packed frame message

    def public(self) -> dict[str, Any]:
        return {"id": self.id, "name": self.name, "color": self.color, "emoji": self.emoji,
                "status": self.status, "progress": self.progress, "done": self.done,
                "streaming": self.streaming, "cursor": list(self.cursor) if self.cursor else None}


@dataclass(eq=False)  # identity-hashed: lives in a set
class _Viewer:
    ws: ServerConnection
    texts: asyncio.Queue[str] = field(default_factory=asyncio.Queue)
    frames: dict[str, bytes] = field(default_factory=dict)  # agent -> latest packed frame
    wake: asyncio.Event = field(default_factory=asyncio.Event)
    sent_frames: int = 0


def pack_frame(header: dict[str, Any], jpeg: bytes) -> bytes:
    h = json.dumps(header, separators=(",", ":")).encode()
    return struct.pack(">H", len(h)) + h + jpeg


class LiveRelay:
    def __init__(self, host: str = LIVE_HOST, port: int = LIVE_PORT, bus_url: str = BUS_URL) -> None:
        self.host, self.port, self.bus_url = host, port, bus_url
        self.agents: dict[str, AgentState] = {}
        self.geometry: dict[str, Geometry] = {}
        self.viewers: set[_Viewer] = set()
        self.frames_in = 0
        self._server = None
        self._tasks: list[asyncio.Task] = []

    # ---- lifecycle -------------------------------------------------------
    async def start(self) -> None:
        self._server = await serve(self._handler, self.host, self.port, max_size=2**20)
        self._tasks.append(asyncio.create_task(self._follow_bus()))
        log.info("live relay on ws://%s:%d (bus %s)", self.host, self.port, self.bus_url)

    async def close(self) -> None:
        for t in self._tasks:
            t.cancel()
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    # ---- state -------------------------------------------------------------
    def _agent(self, agent_id: str) -> AgentState:
        st = self.agents.get(agent_id)
        if st is None:
            meta = AGENTS.get(agent_id, {"name": agent_id, "color": "#8E8E93", "emoji": "•"})
            st = self.agents[agent_id] = AgentState(agent_id, meta["name"], meta["color"], meta["emoji"])
        return st

    def set_geometry(self, agent_id: str, geo: Geometry) -> None:
        self.geometry[agent_id] = geo

    def set_streaming(self, agent_id: str, on: bool) -> None:
        st = self._agent(agent_id)
        st.streaming = on
        self._broadcast_text({"t": "stream", "agent": agent_id, "on": on})

    # ---- frames (from streamers, in-process) ---------------------------------
    def push_frame(self, agent_id: str, jpeg: bytes, w: int, h: int, seq: int, cap_ms: int | None = None) -> None:
        self.frames_in += 1
        header = {"agent": agent_id, "seq": seq, "ts": round(time.time() * 1000), "w": w, "h": h}
        if cap_ms:
            header["cap"] = cap_ms  # when Chrome captured the frame (epoch ms)
        msg = pack_frame(header, jpeg)
        self._agent(agent_id).frame = msg
        for v in self.viewers:
            v.frames[agent_id] = msg  # latest wins
            v.wake.set()

    # ---- bus events ----------------------------------------------------------
    def on_bus_event(self, e: dict[str, Any]) -> None:
        aid, typ, data = e.get("agent"), e.get("type"), e.get("data") or {}
        if typ in CURSOR and aid:
            geo = self.geometry.get(aid)
            if geo and geo.w > 0 and geo.h > 0 and "x" in data:
                fx, fy = (data["x"] - geo.ox) / geo.w, (data["y"] - geo.oy) / geo.h
                st = self._agent(aid)
                st.cursor = (round(fx, 4), round(fy, 4))
                msg = {"t": "cursor", "agent": aid, "fx": st.cursor[0], "fy": st.cursor[1], "kind": CURSOR[typ]}
                for k in ("duration_ms", "label", "text"):
                    if k in data:
                        msg[k] = data[k]
                self._broadcast_text(msg)
            return
        if typ not in FORWARD:
            return
        if aid:
            st = self._agent(aid)
            if typ == "agent_spawn":
                st.done = False
                for k in ("name", "color", "emoji"):
                    if data.get(k):
                        setattr(st, k, data[k])
            elif typ == "agent_status":
                st.status = data.get("text", st.status)
                if "progress" in data:
                    st.progress = data["progress"]
            elif typ == "agent_done":
                st.done = True
                st.status = data.get("summary") or "Done"
                st.progress = 1.0
        self._broadcast_text({"t": "bus", "e": e})

    async def _follow_bus(self) -> None:
        while True:
            try:
                async with websockets.connect(self.bus_url, max_size=2**22) as ws:
                    log.info("live relay subscribed to %s", self.bus_url)
                    async for raw in ws:
                        try:
                            self.on_bus_event(json.loads(raw))
                        except Exception as exc:  # never drop the subscription on one bad event
                            log.warning("live relay: bad bus event: %s", exc)
            except (OSError, websockets.ConnectionClosed):
                pass
            await asyncio.sleep(0.5)

    # ---- viewers -------------------------------------------------------------
    def _broadcast_text(self, msg: dict[str, Any]) -> None:
        raw = json.dumps(msg, ensure_ascii=False)
        for v in self.viewers:
            v.texts.put_nowait(raw)
            v.wake.set()

    async def _handler(self, ws: ServerConnection) -> None:
        v = _Viewer(ws)
        self.viewers.add(v)
        log.info("live viewer connected (%d)", len(self.viewers))
        await ws.send(json.dumps({"t": "hello", "agents": {k: s.public() for k, s in self.agents.items()}},
                                 ensure_ascii=False))
        for aid, st in self.agents.items():
            if st.frame:
                v.frames[aid] = st.frame
        v.wake.set()
        sender = asyncio.create_task(self._send_loop(v))
        try:
            async for raw in ws:  # viewers may send {"t":"ping"}; commands go to the bus, not here
                if isinstance(raw, str) and '"ping"' in raw:
                    await ws.send(json.dumps({"t": "pong", "ts": round(time.time() * 1000)}))
        except websockets.ConnectionClosed:
            pass
        finally:
            sender.cancel()
            self.viewers.discard(v)
            log.info("live viewer disconnected (%d)", len(self.viewers))

    async def _send_loop(self, v: _Viewer) -> None:
        try:
            while True:
                await v.wake.wait()
                v.wake.clear()
                while not v.texts.empty():
                    await v.ws.send(v.texts.get_nowait())
                while v.frames:
                    aid, msg = next(iter(v.frames.items()))
                    del v.frames[aid]
                    await v.ws.send(msg)  # awaits socket drain → natural backpressure
                    v.sent_frames += 1
                    if not v.texts.empty():
                        break
                if not v.texts.empty() or v.frames:
                    v.wake.set()
        except (websockets.ConnectionClosed, asyncio.CancelledError):
            pass


_relay: LiveRelay | None = None
_lock: asyncio.Lock | None = None


async def get_relay() -> LiveRelay:
    """Process-wide relay, started on first use (the first agent that streams)."""
    global _relay, _lock
    if _lock is None:
        _lock = asyncio.Lock()
    async with _lock:
        if _relay is None:
            r = LiveRelay()
            await r.start()
            _relay = r
    return _relay
