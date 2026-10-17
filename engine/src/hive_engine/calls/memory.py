"""Per-agent call memory, shared with the iMessage layer.

Stored as JSON at  $HIVE_STATE_DIR/calls/<agent>.json  (default: engine/state/calls/, gitignored):

    {"agent": "cake", "calls": [ {call record}, ... ]}       # newest last

A call record:
    {"call_id", "mode": "live"|"fake", "to", "label", "goal", "context",
     "started_at", "ended_at", "duration_s", "outcome": "success"|"failure"|"unknown",
     "summary": "one-paragraph plain-text summary",
     "details": {structured facts, e.g. cake, writing, pickup_time, price, status},
     "transcript": [{"speaker": "agent"|"them", "text", "t"}],
     "conversation_id": ElevenLabs id or null}

Usage from other modules (iMessage follow-ups, a callback that changes the order):
    from hive_engine.calls import CallMemory
    CallMemory().latest("cake")          # dict or None
    CallMemory().context_text("cake")    # short recap to paste into an LLM prompt
"""

from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any

ENGINE_DIR = Path(__file__).resolve().parents[3]
_lock = threading.Lock()


def state_dir() -> Path:
    return Path(os.environ.get("HIVE_STATE_DIR", ENGINE_DIR / "state"))


class CallMemory:
    def __init__(self, root: Path | None = None) -> None:
        self.root = (root or state_dir()) / "calls"

    def _path(self, agent: str) -> Path:
        return self.root / f"{agent}.json"

    def load(self, agent: str) -> dict[str, Any]:
        p = self._path(agent)
        if not p.exists():
            return {"agent": agent, "calls": []}
        try:
            return json.loads(p.read_text())
        except json.JSONDecodeError:
            return {"agent": agent, "calls": []}

    def record(self, agent: str, call: dict[str, Any]) -> Path:
        with _lock:
            data = self.load(agent)
            data["calls"] = [c for c in data["calls"] if c.get("call_id") != call.get("call_id")] + [call]
            self.root.mkdir(parents=True, exist_ok=True)
            p = self._path(agent)
            tmp = p.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False))
            tmp.replace(p)
            return p

    def history(self, agent: str) -> list[dict[str, Any]]:
        return self.load(agent)["calls"]

    def latest(self, agent: str) -> dict[str, Any] | None:
        calls = self.history(agent)
        return calls[-1] if calls else None

    def context_text(self, agent: str, limit: int = 3) -> str:
        """Compact recap of recent calls for an LLM prompt ('what did the bakery say?')."""
        lines = []
        for c in self.history(agent)[-limit:]:
            lines.append(f"- Call to {c.get('label') or c.get('to')} ({c.get('outcome')}, {c.get('duration_s')}s): "
                         f"{c.get('summary', '')}")
            if c.get("details"):
                lines.append(f"  Facts: {json.dumps(c['details'], ensure_ascii=False)}")
        return "\n".join(lines) or "No calls yet."
