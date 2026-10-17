"""DynamicAgent: an agent whose name, color and SF Symbol come from the Conductor's plan instead of
the static table in agents.py. It registers itself into AGENTS so the base Agent class and the bus's
@mention routing (find_agent_by_name) work unchanged."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import Any

from ..agent import Agent
from ..agents import AGENTS
from ..bus import Bus


@dataclass
class AgentSpec:
    id: str
    name: str
    color: str
    symbol: str
    worker: str               # browser | code | deck | checker
    goal: str
    inputs: list[str] = field(default_factory=list)
    depends_on: list[str] = field(default_factory=list)
    start_url: str | None = None


@dataclass
class WorkerResult:
    agent: str
    ok: bool
    summary: str
    detail: str = ""
    files: list[str] = field(default_factory=list)
    tokens: dict[str, Any] = field(default_factory=dict)
    seconds: float = 0.0


class DynamicAgent(Agent):
    def __init__(self, bus: Bus, spec: AgentSpec) -> None:
        AGENTS[spec.id] = {"name": spec.name, "color": spec.color, "emoji": "", "symbol": spec.symbol}
        super().__init__(bus, spec.id)
        self.spec = spec
        self.symbol = spec.symbol

    def spawn(self, x: float | None = None, y: float | None = None) -> None:
        self.emit("agent_spawn", name=self.name, color=self.color, symbol=self.symbol, x=x, y=y)
        if x is not None and y is not None:
            self.pos = (x, y)

    def chat(self, text: str) -> None:
        self.emit("chat", text=f"{self.name}: {text}")

    async def ask(self, question: str, options: list[str], timeout: float | None = None,
                  default: str | None = None) -> str:
        """needs_human with the agent's own 2–4 best options; the human may also answer in free text
        (allow_other). On timeout the first option (or `default`) is used so a demo never hangs."""
        options = [str(o) for o in options][:4]
        loop = asyncio.get_running_loop()
        self._pending_answer = loop.create_future()
        self.emit("needs_human", question=question, options=options, allow_other=True)
        self.chat(question + "\n" + "\n".join(f"{i + 1}. {o}" for i, o in enumerate(options))
                  + "\nReply with a number, or tell me something else.")
        try:
            raw = await asyncio.wait_for(self._pending_answer, timeout)
        except asyncio.TimeoutError:
            raw = default or (options[0] if options else "")
            self.chat(f"No answer, going with: {raw}")
        finally:
            self._pending_answer = None
        ans = str(raw).strip()
        if ans.isdigit() and 1 <= int(ans) <= len(options):  # "1" → the first option
            ans = options[int(ans) - 1]
        return ans
