"""demo_sim — proves the cursor-sync pipeline end to end.

Three agents each get their own real Chrome window (tiled across the screen), working on a local
test page. Every click/keystroke is preceded by moving_to + click/typing events with the element's
true screen position, so the Mac overlay's ghost cursors land exactly where Chrome receives input.
"""

from __future__ import annotations

import asyncio

from playwright.async_api import async_playwright

from ..browser_agent import BrowserAgent, Rect, launch_chrome
from ..bus import Bus
from ..http_server import HTTP_PORT

URL = f"http://127.0.0.1:{HTTP_PORT}/test/form.html"


async def _screen_size(browser) -> tuple[int, int, int, int]:
    ctx = await browser.new_context()
    page = await ctx.new_page()
    s = await page.evaluate("() => [screen.availLeft || 0, screen.availTop || 0, screen.availWidth, screen.availHeight]")
    await ctx.close()
    return tuple(s)  # type: ignore[return-value]


async def _work(agent: BrowserAgent, name: str, email: str, options: list[str], rounds: int) -> None:
    p = agent.page
    assert p
    agent.status("Filling the waitlist form", 0.1)
    agent.chat(f"Starting on the form for {name}")
    await agent.type(p.locator("#name"), name)
    await agent.type(p.locator("#email"), email)
    agent.status("Choosing a plan", 0.4)
    await agent.point_at(p.locator("#plan"), label="reading plans")
    await agent.click(p.locator("#pricing"), label="Show pricing")
    for i in range(rounds):
        for opt in options:
            await agent.click(p.locator(f"#{opt}"), label=f"Option {opt.upper()}")
            await asyncio.sleep(0.15)
        agent.status(f"Round {i + 1}/{rounds}", 0.4 + 0.5 * (i + 1) / rounds)
        for msg in agent.drain_inbox():  # redirects from the human take effect between actions
            agent.chat(f"Got it: {msg['text']!r}")
    await agent.click(p.locator("#join"), label="Join waitlist")
    agent.status("Done", 1.0)


async def run(bus: Bus, rounds: int = 2, keep_open: float = 2.0, **_) -> dict:
    results: dict = {}
    async with async_playwright() as pw:
        browser = await launch_chrome(pw)
        left, top, sw, sh = await _screen_size(browser)
        cols, w, h = 3, sw // 3, int(sh * 0.62)
        specs = [("web", "Ada Lovelace", "ada@acme.dev", ["a", "b"]),
                 ("social", "Grace Hopper", "grace@acme.dev", ["b", "c"]),
                 ("fixer", "Alan Turing", "alan@acme.dev", ["c", "a"])]
        agents: list[BrowserAgent] = []
        for i, (aid, *_rest) in enumerate(specs):
            a = BrowserAgent(bus, aid)
            await a.open(browser, Rect(left + i * w, top + 60, w, h), URL)
            ox, oy = await a.viewport_origin()
            a.spawn(ox + 40, oy + 40)
            agents.append(a)
        bus.emit(None, "countdown", {"seconds_left": 30})

        await asyncio.gather(*[_work(a, n, e, o, rounds) for a, (_id, n, e, o) in zip(agents, specs)])

        # verify: compare the last real click (viewport coords) with where we sent the cursor
        for a in agents:
            clicks = await a.page.evaluate("() => window.__clicks || []")  # type: ignore[union-attr]
            ox, oy = await a.viewport_origin()
            last = clicks[-1] if clicks else None
            results[a.id] = {"real_clicks": len(clicks),
                             "last_click_screen": [ox + last[0], oy + last[1]] if last else None,
                             "last_cursor": list(a.pos) if a.pos else None}
            a.done("Waitlist form finished")
        bus.emit(None, "swarm_summary", {"title": "demo_sim complete",
                                         "lines": [f"{a.emoji} {a.name}: {results[a.id]['real_clicks']} real clicks" for a in agents]})
        await asyncio.sleep(keep_open)
        for a in agents:
            await a.close()
        await browser.close()
    return results
