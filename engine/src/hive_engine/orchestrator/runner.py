"""Runs a goal end to end: copy the workspace → Conductor plans the team → workers run as their
dependencies finish → one re-plan pass → swarm_summary.

    start {"scenario": "goal", "goal": "...", "workspace": "demo-world", "urls": [...]}
    uv run python -m hive_engine --goal "..." [--workspace ../demo-world]
"""

from __future__ import annotations

import asyncio
import functools
import logging
import math
import os
import shutil
import tempfile
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from playwright.async_api import async_playwright

from ..agents import AGENTS
from ..browser_agent import Rect, launch_chrome, open_window, page_screen_rect
from ..bus import Bus
from ..http_server import HTTP_PORT
from ..workers.base import AgentSpec, DynamicAgent, WorkerResult
from ..workers.browser_use_worker import BrowserUseWorker
from ..workers.checker_worker import CheckerWorker
from ..workers.code_worker import CodeWorker
from ..workers.deck_worker import DeckWorker, DynDeck, new_deck, wait_native_viewer
from ..workers.window import AgentWindow
from . import conductor, llm
from .plan import PALETTE

log = logging.getLogger("hive.orchestrator")

REPO = Path(__file__).resolve().parents[4]
WS_PORT = int(os.environ.get("HIVE_WS_PORT", "8770"))  # workspace copy served here (8769 = messenger)
VIEWER_URL = f"http://127.0.0.1:{HTTP_PORT}/viewer/index.html"

# Rough $/1M tokens (input, output) for the cost estimate in the run report.
PRICE = {"claude-opus-5-5": (5.0, 25.0), "claude-sonnet-5-5": (3.0, 15.0)}


class _Quiet(SimpleHTTPRequestHandler):
    def log_message(self, *args) -> None:
        pass

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def serve_dir(path: Path, port: int = WS_PORT) -> ThreadingHTTPServer | None:
    try:
        server = ThreadingHTTPServer(("127.0.0.1", port), functools.partial(_Quiet, directory=str(path)))
    except OSError as exc:
        log.warning("workspace server on :%d failed: %s", port, exc)
        return None
    import threading
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def resolve_workspace(ws: str | None) -> Path | None:
    if not ws:
        return None
    p = Path(ws).expanduser()
    for cand in (p, REPO / ws, Path.cwd() / ws):
        if cand.exists() and cand.is_dir():
            return cand.resolve()
    raise FileNotFoundError(f"workspace {ws!r} not found")


def copy_workspace(src: Path) -> Path:
    """Agents only ever touch a temp copy, never the repo (demo-world stays half-built)."""
    dst = Path(tempfile.mkdtemp(prefix="hive_goal_")) / src.name
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("node_modules", ".git", "FINISHED", "__pycache__"))
    return dst


async def screen_area(browser) -> tuple[int, int, int, int]:
    ctx = await browser.new_context()
    page = await ctx.new_page()
    s = await page.evaluate("() => [screen.availLeft || 0, screen.availTop || 0, screen.availWidth, screen.availHeight]")
    await ctx.close()
    return tuple(int(v) for v in s)  # type: ignore[return-value]


def grid(area: tuple[int, int, int, int], n: int, top_gap: int = 34) -> list[Rect]:
    left, top, sw, sh = area
    cols = 1 if n <= 1 else 2 if n <= 4 else 3
    rows = max(1, math.ceil(n / cols))
    cw, ch = sw // cols, (sh - top_gap) // rows
    return [Rect(left + (i % cols) * cw, top + top_gap + (i // cols) * ch, cw, ch) for i in range(n)]


def cost_estimate(browser_costs: float) -> float:
    total = browser_costs
    for model, u in llm.USAGE.by_model.items():
        pin, pout = PRICE.get(model, (5.0, 25.0))
        total += u["input"] / 1e6 * pin + u["output"] / 1e6 * pout
    return round(total, 3)


async def run(bus: Bus, render_dir: Path, goal: str = "", workspace: str | None = None,
              urls: list[str] | None = None, auto_human: bool = False, answer_timeout: float | None = None,
              max_browser_steps: int = 25, keep_open: float = 3.0, **_: Any) -> dict:
    if not goal:
        raise ValueError("goal scenario needs a goal")
    t0 = time.monotonic()
    timeout = 1.0 if auto_human else (answer_timeout if answer_timeout is not None else 30.0)
    static_agents = {k: dict(v) for k, v in AGENTS.items()}
    src = resolve_workspace(workspace)
    ws = copy_workspace(src) if src else None
    server = serve_dir(ws) if ws else None
    served = f"http://127.0.0.1:{WS_PORT}" if server else None
    out: dict[str, Any] = {"goal": goal, "workspace": str(ws) if ws else None}

    llm.USAGE.by_model.clear()
    bus.emit(None, "chat", {"text": f"Conductor: planning a team for: {goal}"})
    specs, summary, source = await conductor.plan(goal, ws, served, urls or [])
    out.update(plan_source=source, plan_summary=summary,
               agents=[{"id": s.id, "name": s.name, "worker": s.worker, "symbol": s.symbol, "color": s.color,
                        "goal": s.goal, "depends_on": s.depends_on} for s in specs],
               plan_s=round(time.monotonic() - t0, 1))
    bus.emit(None, "chat", {"text": f"Conductor: {summary or 'Plan ready.'} Spawning {len(specs)} agent(s): "
                                    + ", ".join(f'{s.name} ({s.worker})' for s in specs)})

    results: dict[str, WorkerResult] = {}
    done: dict[str, asyncio.Event] = {}
    human_notes: list[str] = []
    clicks: dict[str, int] = {}
    browser_cost = 0.0
    closers: list[Any] = []

    try:
        async with async_playwright() as pw:
            browser = await launch_chrome(pw)
            area = await screen_area(browser)
            native = bus.deck_viewer is not None
            windowed = [s for s in specs if s.worker in ("browser", "code", "checker")]
            needs_viewer = any(s.worker == "deck" for s in specs) and not native
            cells = grid(area, max(1, len(windowed) + (1 if needs_viewer else 0)))
            cell_of = {s.id: cells[i] for i, s in enumerate(windowed)}
            viewer_cell = cells[len(windowed)] if needs_viewer else None

            async def run_one(spec: AgentSpec, cell: Rect | None) -> None:
                nonlocal browser_cost
                for dep in spec.depends_on:
                    if dep in done:
                        await done[dep].wait()
                ctx = "\n".join(f"- {results[d].agent}: {results[d].detail[:1500]}" for d in spec.depends_on if d in results)
                agent: DynamicAgent
                try:
                    if spec.worker == "browser":
                        agent = DynamicAgent(bus, spec)
                        agent.spawn()
                        agent.chat(spec.goal)
                        url = spec.start_url
                        if url and served and url.startswith("/"):
                            spec.start_url = served + url
                        task = spec.goal + (f"\n\nContext from teammates:\n{ctx}" if ctx else "")
                        if spec.start_url:
                            task += f"\n\nThe page {spec.start_url} is already open."
                        w = BrowserUseWorker(agent, pw, cell or cells[0], max_steps=max_browser_steps,
                                             answer_timeout=timeout)
                        res = await w.run(task)
                        clicks[spec.id] = len(w.clicks)
                        browser_cost += float(res.tokens.get("total_cost") or 0)
                    elif spec.worker == "code":
                        agent = DynamicAgent(bus, spec)
                        agent.spawn()
                        agent.chat(spec.goal)
                        win = AgentWindow(agent)
                        closers.append(win)
                        await win.open(browser, cell or cells[0], f"{agent.name} — {ws.name if ws else 'workspace'}")
                        if not ws:
                            res = WorkerResult(spec.id, False, "No workspace to edit")
                        else:
                            cw = CodeWorker(agent, ws, win, answer_timeout=timeout)
                            res = await cw.run(spec.goal, ctx)
                            human_notes.extend(cw.human_notes)
                    elif spec.worker == "deck":
                        decks = sorted(ws.rglob("*.pptx")) if ws else []
                        pptx = decks[0] if decks else Path(tempfile.mkdtemp(prefix="hive_deck_")) / "deck.pptx"
                        if not decks:
                            new_deck(pptx, spec.goal[:60])
                        agent = DynDeck(bus, spec, pptx, render_dir)
                        agent.spawn()
                        agent.chat(spec.goal)
                        await agent.load()
                        if not await wait_native_viewer(bus, 2.0 if not native else 0.1):
                            vctx, vpage = await open_window(browser, viewer_cell or cells[-1], VIEWER_URL)
                            closers.append(vctx)

                            async def mapper(fx, fy, fw, fh, _p=vpage):
                                x, y, w_, h_ = await page_screen_rect(_p, _p.locator("#stage"))
                                return x + fx * w_, y + fy * h_, fw * w_, fh * h_

                            agent.screen_mapper = mapper
                            await asyncio.sleep(0.8)
                            agent.emit("deck_loaded", slides=_slides(pptx), base=agent.base_url, version=agent.version)
                        dw = DeckWorker(agent, answer_timeout=timeout, ws=ws)
                        res = await dw.run(spec.goal, ctx)
                        human_notes.extend(dw.human_notes)
                    else:  # checker: waits for every producer unless told otherwise
                        agent = DynamicAgent(bus, spec)
                        agent.spawn()
                        producers = [s.id for s in specs if s.worker != "checker" and s.id != spec.id]
                        for pid in producers:
                            await done[pid].wait()
                        win = AgentWindow(agent)
                        closers.append(win)
                        await win.open(browser, cell or cells[-1], f"{agent.name} — review")
                        report = "\n".join(f"- {results[p].agent}: {results[p].detail[:1500]}" for p in producers if p in results)
                        files = [f for p in producers if p in results for f in results[p].files]
                        ck = CheckerWorker(agent, ws, win, answer_timeout=timeout)
                        res = await ck.run(goal, report, files)
                        human_notes.extend(ck.human_notes)
                except Exception as exc:
                    log.exception("agent %s failed", spec.id)
                    res = WorkerResult(spec.id, False, f"crashed: {exc}", detail=f"crashed: {exc}")
                    agent = bus.agents.get(spec.id)  # type: ignore[assignment]
                results[spec.id] = res
                if agent:
                    agent.chat(res.summary[:280])
                    agent.done(res.summary[:120])
                done[spec.id].set()

            async def wave(batch: list[AgentSpec]) -> None:
                for s in batch:
                    done[s.id] = asyncio.Event()
                await asyncio.gather(*(run_one(s, cell_of.get(s.id)) for s in batch))

            await wave(specs)

            # One re-plan pass: the Conductor may add up to 2 follow-up agents.
            bus.emit(None, "chat", {"text": "Conductor: checking whether the goal is met…"})
            extra = await conductor.replan(goal, specs, results, human_notes)
            if extra:
                used = {s.color for s in specs}
                for s in extra:
                    if s.color in used:
                        s.color = next((c for c in PALETTE if c not in used), s.color)
                    used.add(s.color)
                bus.emit(None, "chat", {"text": "Conductor: follow-up — " + ", ".join(f"{s.name}: {s.goal}" for s in extra)})
                free = grid(area, len(extra))
                for i, s in enumerate(extra):
                    cell_of[s.id] = free[i]
                specs_all = specs + extra
                specs[:] = specs_all
                await wave(extra)
            out["followups"] = [{"id": s.id, "name": s.name, "worker": s.worker, "goal": s.goal} for s in extra]

            elapsed = time.monotonic() - t0
            ok_n = sum(1 for r in results.values() if r.ok)
            bus.emit(None, "swarm_summary", {
                "title": f"{ok_n}/{len(results)} agents finished in {int(elapsed // 60)}:{int(elapsed % 60):02d}",
                "lines": [f"{AGENTS.get(i, {}).get('name', i)}: {r.summary[:90]}" for i, r in results.items()]})
            await asyncio.sleep(keep_open)
    finally:
        for c in closers:
            try:
                await c.close()
            except Exception:
                pass
        if server:
            server.shutdown()
        # Dynamic agents registered themselves (possibly reusing a static id like "fixer"): restore the table.
        AGENTS.clear()
        AGENTS.update(static_agents)

    out.update(
        elapsed_s=round(time.monotonic() - t0, 1),
        results={i: {"ok": r.ok, "summary": r.summary, "seconds": round(r.seconds, 1), "files": r.files}
                 for i, r in results.items()},
        human_notes=human_notes,
        browser_clicks=clicks,
        tokens=llm.USAGE.by_model,
        cost_estimate_usd=cost_estimate(browser_cost),
    )
    return out


def _slides(pptx: Path) -> int:
    from pptx import Presentation
    return len(Presentation(pptx).slides)
