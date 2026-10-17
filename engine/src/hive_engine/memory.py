"""Per-agent text memory: one JSON line per record in engine/state/messages/<agent>.jsonl (gitignored).

The iMessage side of an agent's memory: what the human texted it and what it texted back. Phone calls
live next to it in engine/state/calls/<agent>.json (hive_engine.calls.CallMemory). The Messenger reads
both, so a voice agent "remembers the call" when the conversation moves to text.

Record shape (extra keys allowed):
    {"ts": 1792260000.1, "agent": "cake", "kind": "text_in" | "text_out", "text": "...", ...}

HIVE_MEMORY_DIR overrides the location (else $HIVE_STATE_DIR/messages).
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

MEMORY_DIR = Path(os.environ.get("HIVE_MEMORY_DIR")
                  or Path(os.environ.get("HIVE_STATE_DIR") or Path(__file__).resolve().parents[2] / "state") / "messages")


def _path(agent: str) -> Path:
    safe = "".join(c for c in agent.lower() if c.isalnum() or c in "-_") or "hive"
    return MEMORY_DIR / f"{safe}.jsonl"


def append(agent: str, kind: str, text: str, **extra: Any) -> dict[str, Any]:
    rec = {"ts": time.time(), "agent": agent, "kind": kind, "text": text, **extra}
    MEMORY_DIR.mkdir(parents=True, exist_ok=True)
    with _path(agent).open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    return rec


def read(agent: str, limit: int = 200) -> list[dict[str, Any]]:
    p = _path(agent)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def has(agent: str) -> bool:
    return _path(agent).exists()
