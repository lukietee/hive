"""Thin Claude helpers shared by the Conductor and the workers: one client, token accounting,
and a "call this tool" request that works on current models (which reject a forced tool_choice)."""

from __future__ import annotations

import asyncio
import json
import os
import re
from dataclasses import dataclass, field
from typing import Any

CONDUCTOR_MODEL = os.environ.get("HIVE_CONDUCTOR_MODEL", "claude-opus-5-5")
WORKER_MODEL = os.environ.get("HIVE_WORKER_MODEL", "claude-sonnet-5-5")


@dataclass
class Usage:
    by_model: dict[str, dict[str, int]] = field(default_factory=dict)

    def add(self, model: str, usage: Any) -> None:
        if usage is None:
            return
        m = self.by_model.setdefault(model, {"input": 0, "output": 0, "cache_read": 0})
        m["input"] += int(getattr(usage, "input_tokens", 0) or 0)
        m["output"] += int(getattr(usage, "output_tokens", 0) or 0)
        m["cache_read"] += int(getattr(usage, "cache_read_input_tokens", 0) or 0)


USAGE = Usage()


def available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


_client = None


def client():
    global _client
    if _client is None:
        import anthropic
        _client = anthropic.AsyncAnthropic(timeout=120, max_retries=2)
    return _client


def text_of(msg: Any) -> str:
    return "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")


def tool_input(msg: Any, name: str) -> dict[str, Any] | None:
    for b in msg.content:
        if getattr(b, "type", "") == "tool_use" and b.name == name:
            return dict(b.input)
    return None


def json_from_text(text: str) -> dict[str, Any] | None:
    m = re.search(r"\{.*\}", text, re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


async def call_tool(system: str, prompt: str, tool_name: str, schema: dict[str, Any], description: str,
                    model: str = CONDUCTOR_MODEL, max_tokens: int = 4000, timeout: float = 90) -> dict[str, Any] | None:
    """Ask Claude to answer by calling `tool_name` once. Falls back to JSON in the text."""
    tools = [{"name": tool_name, "description": description, "input_schema": schema}]
    msg = await asyncio.wait_for(client().messages.create(
        model=model, max_tokens=max_tokens, system=system, tools=tools,
        messages=[{"role": "user", "content": prompt + f"\n\nAnswer by calling the {tool_name} tool exactly once."}],
    ), timeout)
    USAGE.add(model, msg.usage)
    return tool_input(msg, tool_name) or json_from_text(text_of(msg))
