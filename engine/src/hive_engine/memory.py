"""Per-agent memory: one JSON line per record in engine/memory/<agent>.jsonl (gitignored).

Anything that should be remembered across channels goes here: the iMessage thread (what the human
texted an agent, what it texted back) and phone calls (transcripts and summaries from the Caller).
That is what lets a voice agent "remember the call" when the conversation moves to text.

Record shape (extra keys allowed):
    {"ts": 1792260000.1, "agent": "cake", "kind": "call_summary" | "call_transcript" | "text_in" | "text_out",
     "text": "...", ...}

HIVE_MEMORY_DIR overrides the location.
"""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

MEMORY_DIR = Path(os.environ.get("HIVE_MEMORY_DIR") or Path(__file__).resolve().parents[2] / "memory")


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
