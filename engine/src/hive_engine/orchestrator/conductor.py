"""Conductor v2: turns any goal (+ a look at the workspace) into a task graph of agents, and gets one
re-plan pass after the first wave finishes."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ..workers.base import AgentSpec, WorkerResult
from . import llm
from .plan import MAX_AGENTS, PALETTE, PLAN_SCHEMA, SYMBOLS, fallback_plan, validate

log = logging.getLogger("hive.orchestrator")

SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__", ".DS_Store", "FINISHED"}
TEXT_EXT = {".md", ".txt", ".json", ".js", ".ts", ".py", ".html", ".css", ".toml", ".yaml", ".yml"}


def inventory(ws: Path | None, max_files: int = 120, snippet_chars: int = 600) -> str:
    """A compact picture of the workspace for the planner: file tree + the head of key text files."""
    if not ws:
        return "(no workspace: this is a pure web/research task)"
    files = [p for p in sorted(ws.rglob("*"))
             if p.is_file() and not any(part in SKIP_DIRS for part in p.relative_to(ws).parts)]
    lines = [f"Workspace has {len(files)} files:"]
    lines += [f"- {p.relative_to(ws)} ({p.stat().st_size} B)" for p in files[:max_files]]
    keys = [p for p in files if p.suffix in TEXT_EXT and (p.name.lower().startswith("readme") or p.suffix == ".md"
                                                          or p.name == "package.json")][:8]
    for p in keys:
        try:
            lines.append(f"\n--- {p.relative_to(ws)} ---\n{p.read_text(errors='replace')[:snippet_chars]}")
        except OSError:
            pass
    return "\n".join(lines)


SYSTEM = f"""You are the Conductor of Hive, a swarm of AI agents that works a Mac the way a team would.
Given a goal, decide how many agents to spawn (1 to {MAX_AGENTS}; use the fewest that finish the job well,
parallelise independent work) and what each one does. Worker types:
- browser: a real Chrome window driven by Browser Use. Browses, searches, reads pages, fills fields on LOCAL pages.
  Read-only on the public web: never logs in, buys, posts or submits forms on real sites.
- code: edits files in the workspace and runs shell commands there (tests, builds). Use for code, HTML/CSS, docs.
- deck: builds or edits a PowerPoint deck (python-pptx) shown live in the Deck Viewer.
- checker: reviews the other agents' results for contradictions/mistakes and asks the human when a decision is needed.
  Add one only when there are 2+ producing agents whose outputs must agree.
Rules: each goal must be concrete and self-contained (the agent sees nothing else). Name agents by role
(e.g. Fixer, Scout, Designer), 1-2 words. Pick distinct colors from {PALETTE} and SF Symbols from
{sorted(SYMBOLS)}. depends_on lists only earlier agents whose results are needed first.
If the workspace is served over HTTP, browser agents should use that URL for local pages."""


async def plan(goal: str, ws: Path | None, served_url: str | None, urls: list[str]) -> tuple[list[AgentSpec], str, str]:
    """Returns (specs, summary, source) where source is 'claude' or 'fallback'."""
    has_code = bool(ws and any(ws.rglob("*.js")) or ws and any(ws.rglob("*.html")))
    has_deck = bool(ws and any(ws.rglob("*.pptx")))
    raw: dict[str, Any] | None = None
    if llm.available():
        prompt = (f"GOAL: {goal}\n\n{inventory(ws)}\n\n"
                  + (f"The workspace is served at {served_url}/ (e.g. {served_url}/site/index.html).\n" if served_url else "")
                  + (f"Useful URLs: {', '.join(urls)}\n" if urls else ""))
        try:
            raw = await llm.call_tool(SYSTEM, prompt, "submit_plan", PLAN_SCHEMA, "Submit the team plan.")
        except Exception as exc:
            log.warning("conductor plan failed: %s", exc)
    source = "claude"
    specs, summary = validate(raw or {})
    if not specs:
        specs, summary = validate(fallback_plan(goal, has_code, has_deck))
        source = "fallback"
    return specs, summary, source


REPLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "done": {"type": "boolean", "description": "true if the goal is fully met"},
        "reason": {"type": "string"},
        "agents": PLAN_SCHEMA["properties"]["agents"] | {"maxItems": 2, "minItems": 0},
    },
    "required": ["done"],
}


async def replan(goal: str, specs: list[AgentSpec], results: dict[str, WorkerResult],
                 human_notes: list[str]) -> list[AgentSpec]:
    """One follow-up pass: given what each agent reported, add up to 2 agents if something is missing."""
    if not llm.available():
        return []
    report = "\n".join(f"- {s.name} ({s.worker}) goal: {s.goal}\n  result ({'ok' if results[s.id].ok else 'FAILED'}): "
                       f"{results[s.id].detail[:800]}" for s in specs if s.id in results)
    notes = "\n".join(f"- {n}" for n in human_notes) or "(none)"
    prompt = (f"GOAL: {goal}\n\nWhat the team did:\n{report}\n\nDecisions from the human:\n{notes}\n\n"
              "Is the goal fully met? If not, propose at most 2 follow-up agents (new ids) to finish it. "
              "Don't redo work that succeeded. If a failure can't be fixed by another attempt, mark done.")
    try:
        raw = await llm.call_tool(SYSTEM, prompt, "submit_followup", REPLAN_SCHEMA, "Submit the follow-up decision.")
    except Exception as exc:
        log.warning("replan failed: %s", exc)
        return []
    if not raw or raw.get("done"):
        return []
    extra, _ = validate({"agents": raw.get("agents") or []})
    taken = {s.id for s in specs}
    out = []
    for s in extra[:2]:
        while s.id in taken:
            s.id += "2"
        s.depends_on = []
        out.append(s)
        taken.add(s.id)
    return out
