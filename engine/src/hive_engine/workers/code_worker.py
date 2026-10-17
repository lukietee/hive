"""Code worker: a Claude tool-use loop that reads/edits files and runs commands inside a temp copy of
the workspace, shown live in its own editor window with the ghost cursor on each change."""

from __future__ import annotations

import asyncio
import os
import re
import time
from pathlib import Path
from typing import Any

from ..orchestrator import llm
from .base import DynamicAgent, WorkerResult
from .window import AgentWindow
from .workbench import changed_lines

MAX_TURNS = 24
BLOCKED = re.compile(r"\b(sudo|git\s+push|npm\s+publish|ssh|scp)\b|rm\s+-rf\s+[/~]|curl[^|]*\|\s*(ba)?sh|wget[^|]*\|\s*(ba)?sh")
SECRET_ENV = ("ANTHROPIC_API_KEY", "ELEVENLABS_API_KEY", "DEEPGRAM_API_KEY", "PHOTON_PROJECT_SECRET",
              "TELEGRAM_BOT_TOKEN", "LIVEKIT_API_SECRET", "DEVIN_API_KEY", "GEMINI_API_KEY")

TOOLS: list[dict[str, Any]] = [
    {"name": "list_files", "description": "List files under a workspace directory (recursive, max 200).",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string", "default": "."}}}},
    {"name": "read_file", "description": "Read a text file in the workspace.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}},
    {"name": "write_file", "description": "Create or overwrite a text file in the workspace.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}},
                      "required": ["path", "content"]}},
    {"name": "replace_in_file", "description": "Replace one exact occurrence of old with new in a file.",
     "input_schema": {"type": "object", "properties": {"path": {"type": "string"}, "old": {"type": "string"},
                                                        "new": {"type": "string"}}, "required": ["path", "old", "new"]}},
    {"name": "run_command", "description": "Run a shell command in the workspace root (60s timeout). "
                                           "For tests/builds only; no network installs, no git push.",
     "input_schema": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}},
    {"name": "ask_human", "description": "Ask the human a decision you can't make yourself. Give 2-4 concrete "
                                         "options (best first); they may also answer in their own words.",
     "input_schema": {"type": "object", "properties": {"question": {"type": "string"},
                                                        "options": {"type": "array", "items": {"type": "string"}}},
                      "required": ["question", "options"]}},
    {"name": "finish", "description": "Call when done. summary = one or two sentences of what you changed and the result.",
     "input_schema": {"type": "object", "properties": {"summary": {"type": "string"}, "ok": {"type": "boolean"}},
                      "required": ["summary"]}},
]

SYSTEM = """You are {name}, a coding agent on the Hive team. You work ONLY inside the workspace (a temp copy; paths
are relative to it). Be efficient: look around briefly, make focused edits, verify (run tests if there are any),
then call finish. Keep edits minimal and production-quality. Don't ask the human unless a real decision is needed."""


class CodeWorker:
    def __init__(self, agent: DynamicAgent, ws: Path, window: AgentWindow | None, answer_timeout: float = 30) -> None:
        self.agent = agent
        self.ws = ws.resolve()
        self.win = window
        self.answer_timeout = answer_timeout
        self.changed: list[str] = []
        self.human_notes: list[str] = []

    # ---- sandboxed tools -------------------------------------------------------
    def _path(self, rel: str) -> Path:
        p = (self.ws / (rel or ".")).resolve()
        if p != self.ws and self.ws not in p.parents:
            raise ValueError("path escapes the workspace")
        return p

    async def _show(self, rel: str, text: str, added: list[int] | None = None) -> None:
        if not self.win:
            return
        self.win.bench.show_file(rel, text, added)
        await self.win.refresh()
        if added:
            await asyncio.sleep(0.15)
            first = text.splitlines()[added[0] - 1] if added[0] - 1 < len(text.splitlines()) else ""
            await self.win.point(f"#L{added[0]}", typing=first.strip()[:50] or "…")
        else:
            await self.win.point("#code .l", label=rel)

    async def _run(self, name: str, inp: dict[str, Any]) -> str:
        a = self.agent
        await a.gate()
        if name == "list_files":
            base = self._path(inp.get("path", "."))
            files = [str(p.relative_to(self.ws)) for p in sorted(base.rglob("*")) if p.is_file()
                     and "node_modules" not in p.parts and ".git" not in p.parts][:200]
            if self.win:
                self.win.bench.files = files[:40]
                await self.win.refresh()
            return "\n".join(files) or "(empty)"
        if name == "read_file":
            rel = inp["path"]
            text = self._path(rel).read_text(errors="replace")
            a.status(f"Reading {rel}")
            await self._show(rel, text)
            return text[:20000]
        if name in ("write_file", "replace_in_file"):
            rel = inp["path"]
            p = self._path(rel)
            old = p.read_text(errors="replace") if p.exists() else ""
            if name == "write_file":
                new = inp["content"]
            else:
                if inp["old"] not in old:
                    return "error: old text not found (read the file again and copy it exactly)"
                new = old.replace(inp["old"], inp["new"], 1)
            p.parent.mkdir(parents=True, exist_ok=True)
            a.status(f"Editing {rel}")
            await self._show(rel, new, changed_lines(old, new) or [1])
            p.write_text(new)
            if rel not in self.changed:
                self.changed.append(rel)
            return f"ok: wrote {rel} ({len(new)} chars)"
        if name == "run_command":
            cmd = inp["command"]
            if BLOCKED.search(cmd):
                return "error: command not allowed"
            a.status(f"$ {cmd[:60]}")
            if self.win:
                self.win.bench.log(cmd, cmd=True)
                await self.win.refresh()
                await self.win.point("#term .cmd:last-of-type", click=True, label="run")
            env = {k: v for k, v in os.environ.items() if k not in SECRET_ENV}
            proc = await asyncio.create_subprocess_shell(cmd, cwd=self.ws, env=env, stdout=asyncio.subprocess.PIPE,
                                                         stderr=asyncio.subprocess.STDOUT)
            try:
                out, _ = await asyncio.wait_for(proc.communicate(), 60)
            except asyncio.TimeoutError:
                proc.kill()
                out = b"(timed out after 60s)"
            text = out.decode(errors="replace")
            if self.win:
                self.win.bench.log(text[-3000:] + f"\n(exit {proc.returncode})")
                await self.win.refresh()
            return f"exit {proc.returncode}\n{text[-8000:]}"
        if name == "ask_human":
            ans = await a.ask(inp["question"], inp.get("options") or [], timeout=self.answer_timeout)
            self.human_notes.append(f"{a.name} asked: {inp['question']} → {ans}")
            return f"The human answered: {ans}"
        return f"error: unknown tool {name}"

    # ---- loop --------------------------------------------------------------------
    async def run(self, goal: str, context: str = "") -> WorkerResult:
        a = self.agent
        t0 = time.monotonic()
        if not llm.available():
            return WorkerResult(a.id, False, "No ANTHROPIC_API_KEY", seconds=0)
        messages: list[dict[str, Any]] = [{"role": "user", "content": (
            f"GOAL: {goal}\n\n" + (f"Context from teammates:\n{context}\n\n" if context else "")
            + "Start by listing the files.")}]
        summary, ok = "", False
        for turn in range(MAX_TURNS):
            await a.gate()
            for m in a.drain_inbox():  # "@Fixer use the other approach" mid-run
                messages.append({"role": "user", "content": f"Message from the human: {m.get('text')}"})
            if messages[-1]["role"] == "assistant":
                messages.append({"role": "user", "content": "Continue."})
            a.status("Thinking…", min(0.9, 0.05 + turn / MAX_TURNS))
            msg = await llm.client().messages.create(model=llm.WORKER_MODEL, max_tokens=8000,
                                                     system=SYSTEM.format(name=a.name), tools=TOOLS, messages=messages)
            llm.USAGE.add(llm.WORKER_MODEL, msg.usage)
            messages.append({"role": "assistant", "content": msg.content})
            uses = [b for b in msg.content if getattr(b, "type", "") == "tool_use"]
            if not uses:
                summary, ok = llm.text_of(msg).strip()[:400] or "Done.", True
                break
            results = []
            finished = False
            for u in uses:
                if u.name == "finish":
                    summary = str(u.input.get("summary", "")).strip()
                    ok = bool(u.input.get("ok", True))
                    finished = True
                    results.append({"type": "tool_result", "tool_use_id": u.id, "content": "ok"})
                    continue
                try:
                    out = await self._run(u.name, dict(u.input))
                except Exception as exc:
                    out = f"error: {exc}"
                results.append({"type": "tool_result", "tool_use_id": u.id, "content": out[:20000]})
            messages.append({"role": "user", "content": results})
            if finished:
                break
        else:
            summary = summary or "Ran out of turns before finishing."
        a.status("Done" if ok else "Stopped", 1.0)
        detail = summary + (f"\nChanged files: {', '.join(self.changed)}" if self.changed else "")
        return WorkerResult(a.id, ok, summary, detail=detail, files=self.changed, seconds=time.monotonic() - t0)
