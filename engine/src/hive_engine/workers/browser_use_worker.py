"""Browser worker = Browser Use, one subprocess per agent (workers/browser_use/hive_bu_worker.py).

The engine launches a real Chrome window per agent (temp profile, remote-debugging port), places it,
starts the 👁 live screencast on it, then runs Browser Use in its own uv project attached to that
Chrome over CDP. The subprocess streams JSON lines: cursor events (already in sync-rule order),
step status, questions for the human and the final result. We re-emit them on the bus as this agent.
"""

from __future__ import annotations

import asyncio
import json
import os
import shutil
import socket
import sys
import tempfile
import time
from pathlib import Path

from playwright.async_api import Playwright

from ..browser_agent import CHROME_ARGS, Rect
from .base import DynamicAgent, WorkerResult

REPO = Path(__file__).resolve().parents[4]
WORKER_DIR = REPO / "workers" / "browser_use"
WORKER_SCRIPT = WORKER_DIR / "hive_bu_worker.py"


def _uv() -> str:
    return shutil.which("uv") or str(Path.home() / ".local" / "bin" / "uv")


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class BrowserUseWorker:
    def __init__(self, agent: DynamicAgent, pw: Playwright, rect: Rect, max_steps: int = 20,
                 answer_timeout: float = 30.0) -> None:
        self.agent = agent
        self.pw = pw
        self.rect = rect
        self.max_steps = max_steps
        self.answer_timeout = answer_timeout
        self.context = None
        self.live = None
        self.clicks: list[tuple[float, float]] = []

    async def _open_chrome(self) -> str:
        port = _free_port()
        r = self.rect
        args = CHROME_ARGS + [f"--remote-debugging-port={port}", f"--window-position={r.left},{r.top}",
                              f"--window-size={r.width},{r.height}"]
        profile = tempfile.mkdtemp(prefix=f"hive_bu_{self.agent.id}_")
        try:
            self.context = await self.pw.chromium.launch_persistent_context(
                profile, channel="chrome", headless=False, args=args, no_viewport=True)
        except Exception:
            self.context = await self.pw.chromium.launch_persistent_context(
                profile, headless=False, args=args, no_viewport=True)
        page = self.context.pages[0] if self.context.pages else await self.context.new_page()
        cdp = await self.context.new_cdp_session(page)
        try:  # the window flags are a hint; make the bounds exact
            wid = (await cdp.send("Browser.getWindowForTarget"))["windowId"]
            await cdp.send("Browser.setWindowBounds", {"windowId": wid, "bounds": {
                "left": r.left, "top": r.top, "width": r.width, "height": r.height}})
        except Exception:
            pass
        url = self.agent.spec.start_url or "about:blank"
        if url != "about:blank":
            try:
                await page.goto(url, timeout=15000)
            except Exception:
                pass
        from ..live import attach
        self.live = await attach(self.agent.id, page, cdp)
        return f"http://127.0.0.1:{port}"

    async def run(self, task: str) -> WorkerResult:
        a = self.agent
        t0 = time.monotonic()
        a.status("Opening Chrome…", 0.02)
        cdp_url = await self._open_chrome()
        cmd = [_uv(), "run", "--quiet", "--project", str(WORKER_DIR), "python", str(WORKER_SCRIPT),
               "--cdp-url", cdp_url, "--task", task, "--max-steps", str(self.max_steps)]
        env = dict(os.environ)
        env.pop("VIRTUAL_ENV", None)  # don't leak the engine's venv into the worker's uv project
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE, env=env, cwd=str(WORKER_DIR), limit=4 * 1024 * 1024)
        stderr_tail: list[str] = []

        async def drain_stderr() -> None:
            assert proc.stderr
            async for line in proc.stderr:
                stderr_tail.append(line.decode(errors="replace").rstrip())
                del stderr_tail[:-40]

        err_task = asyncio.create_task(drain_stderr())
        done: dict | None = None
        a.status("Thinking…", 0.05)
        try:
            assert proc.stdout
            async for raw in proc.stdout:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                ev = msg.get("ev")
                if ev == "cursor":
                    await a.gate()
                    t = msg.get("type")
                    data = {k: v for k, v in msg.items() if k not in ("ev", "type") and v is not None}
                    a.emit(t, **data)
                    if t in ("click", "typing"):
                        a.pos = (msg["x"], msg["y"])
                        self.clicks.append((msg["x"], msg["y"]))
                elif ev == "status":
                    a.status(msg.get("text", ""), msg.get("progress"))
                elif ev == "ask":
                    answer = await a.ask(msg.get("question", "?"), msg.get("options") or [],
                                         timeout=self.answer_timeout)
                    assert proc.stdin
                    proc.stdin.write((json.dumps({"answer": answer}) + "\n").encode())
                    await proc.stdin.drain()
                elif ev == "done":
                    done = msg
                elif ev == "log":
                    stderr_tail.append("[worker] " + str(msg.get("text")))
            await proc.wait()
        finally:
            if proc.returncode is None:
                proc.kill()
            err_task.cancel()
            await self.close()
        secs = time.monotonic() - t0
        if not done:
            tail = "\n".join(stderr_tail[-8:])
            return WorkerResult(a.id, False, "Browser worker crashed", detail=tail, seconds=secs)
        result = str(done.get("result") or "").strip()
        ok = bool(done.get("ok"))
        detail = result if ok else result + "\n--- worker stderr ---\n" + "\n".join(stderr_tail[-15:])
        return WorkerResult(a.id, ok, result[:300] or "(no result)", detail=detail,
                            tokens=done.get("tokens") or {}, seconds=secs)

    async def close(self) -> None:
        if self.live:
            try:
                await self.live.stop()
            except Exception:
                pass
            self.live = None
        if self.context:
            try:
                await self.context.close()
            except Exception:
                pass
            self.context = None


def worker_available() -> bool:
    return WORKER_SCRIPT.exists() and (WORKER_DIR / "pyproject.toml").exists() and sys.platform == "darwin"
