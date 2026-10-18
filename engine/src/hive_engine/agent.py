"""Agent base class. Enforces the sync rule from docs/CONTRACT.md:

    moving_to → wait duration_ms → click/typing event → THEN the real action.
"""

from __future__ import annotations

import asyncio
from typing import Any

from .agents import AGENTS
from .bus import Bus


class Agent:
    def __init__(self, bus: Bus, agent_id: str) -> None:
        meta = AGENTS[agent_id]
        self.bus = bus
        self.id = agent_id
        self.name = meta["name"]
        self.color = meta["color"]
        self.emoji = meta["emoji"]
        self.inbox: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        self._running = asyncio.Event()
        self._running.set()
        self._pending_answer: asyncio.Future[Any] | None = None
        self.pos: tuple[float, float] | None = None
        bus.register(self)

    # ---- low level -------------------------------------------------------
    def emit(self, type_: str, **data: Any) -> None:
        self.bus.emit(self.id, type_, {k: v for k, v in data.items() if v is not None})

    async def gate(self) -> None:
        """Blocks while the agent is paused. Call between actions."""
        await self._running.wait()

    def pause(self) -> None:
        self._running.clear()
        self.emit("agent_status", text="Paused")

    def resume(self) -> None:
        self._running.set()
        self.emit("agent_status", text="Resumed")

    def answer(self, choice: Any) -> None:
        if self._pending_answer and not self._pending_answer.done():
            self._pending_answer.set_result(choice)

    def drain_inbox(self) -> list[dict[str, Any]]:
        """Messages the human sent this agent since the last check (redirects)."""
        out = []
        while not self.inbox.empty():
            out.append(self.inbox.get_nowait())
        return out

    # ---- helpers matching the contract -------------------------------------
    def spawn(self, x: float | None = None, y: float | None = None) -> None:
        self.emit("agent_spawn", name=self.name, color=self.color, emoji=self.emoji, x=x, y=y)
        if x is not None and y is not None:
            self.pos = (x, y)

    def status(self, text: str, progress: float | None = None) -> None:
        self.emit("agent_status", text=text, progress=progress)

    def chat(self, text: str) -> None:
        self.emit("chat", text=f"{self.emoji} {self.name}: {text}")

    async def move_to(self, x: float, y: float, duration_ms: int = 300, label: str | None = None) -> None:
        await self.gate()
        self.emit("moving_to", x=round(x, 1), y=round(y, 1), duration_ms=duration_ms, label=label)
        await asyncio.sleep(duration_ms / 1000)
        self.pos = (x, y)

    async def click_at(self, x: float, y: float, duration_ms: int = 300, label: str | None = None) -> None:
        """Glide + ripple. The caller performs the real click right after this returns."""
        await self.move_to(x, y, duration_ms, label)
        self.emit("click", x=round(x, 1), y=round(y, 1))

    async def typing(self, x: float, y: float, text: str, duration_ms: int = 300) -> None:
        """Glide + typing indicator. The caller types right after this returns."""
        await self.move_to(x, y, duration_ms)
        self.emit("typing", x=round(x, 1), y=round(y, 1), text=text)

    def highlight(self, x: float, y: float, w: float, h: float, style: str = "box", sticky: bool = False) -> None:
        self.emit("highlight", x=round(x, 1), y=round(y, 1), w=round(w, 1), h=round(h, 1), style=style,
                  sticky=sticky or None)

    def link(self, frm: tuple[float, float], to: tuple[float, float], text: str | None = None) -> None:
        self.emit("link", **{"from": list(frm), "to": list(to)}, text=text)

    async def ask_human(self, question: str, options: list[str], timeout: float | None = None,
                        **extra: Any) -> Any:
        """extra: additive needs_human fields, e.g. kind="post" (explicit YES/NO in iMessage)."""
        loop = asyncio.get_running_loop()
        self._pending_answer = loop.create_future()
        self.emit("needs_human", question=question, options=options, **extra)
        try:
            return await asyncio.wait_for(self._pending_answer, timeout)
        finally:
            self._pending_answer = None

    def done(self, summary: str | None = None) -> None:
        self.emit("agent_done", summary=summary)
