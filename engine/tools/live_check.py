"""Checks the 👁 live view while a scenario runs:  uv run python tools/live_check.py [--seconds 20] [--shot out.png]

1. A headless WS client counts frames per agent (fps, sizes, Chrome-capture → client latency) and cursor messages.
2. A headless Chromium loads http://127.0.0.1:8766/live/, waits for frames, and screenshots the page.
"""

import argparse
import asyncio
import collections
import json
import statistics
import struct
import time

import websockets
from playwright.async_api import async_playwright


async def ws_client(url: str, seconds: float, out: dict) -> None:
    for _ in range(120):
        try:
            ws = await websockets.connect(url, max_size=2**22)
            break
        except OSError:
            await asyncio.sleep(0.25)
    else:
        raise SystemExit("relay not reachable")
    frames: dict[str, list] = collections.defaultdict(list)
    cursors: collections.Counter = collections.Counter()
    texts: collections.Counter = collections.Counter()
    end = time.time() + seconds
    async with ws:
        while time.time() < end:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=max(0.1, end - time.time()))
            except (asyncio.TimeoutError, websockets.ConnectionClosed):
                break
            now = time.time() * 1000
            if isinstance(raw, bytes):
                hl = struct.unpack(">H", raw[:2])[0]
                h = json.loads(raw[2:2 + hl])
                frames[h["agent"]].append((now, len(raw) - 2 - hl, now - h.get("cap", h["ts"]), h["w"], h["h"]))
            else:
                m = json.loads(raw)
                texts[m["t"]] += 1
                if m["t"] == "cursor":
                    cursors[(m["agent"], m["kind"])] += 1
    for aid, fs in frames.items():
        span = (fs[-1][0] - fs[0][0]) / 1000 if len(fs) > 1 else 0
        out[aid] = {"frames": len(fs), "fps": round((len(fs) - 1) / span, 1) if span else None,
                    "avg_kb": round(statistics.mean(f[1] for f in fs) / 1024, 1),
                    "latency_ms_median": round(statistics.median(f[2] for f in fs), 1),
                    "latency_ms_p95": round(sorted(f[2] for f in fs)[int(len(fs) * .95) - 1], 1),
                    "size": f"{fs[-1][3]}x{fs[-1][4]}",
                    "cursor_msgs": {k: v for (a, k), v in cursors.items() if a == aid}}
    out["_text_msgs"] = dict(texts)


async def page_check(url: str, wait: float, shot: str, out: dict) -> None:
    async with async_playwright() as pw:
        try:  # installed Chrome (fresh temp profile); Playwright's Chromium if missing
            b = await pw.chromium.launch(channel="chrome", headless=True)
        except Exception:
            b = await pw.chromium.launch(headless=True)
        p = await b.new_page(viewport={"width": 390, "height": 844}, device_scale_factor=2)  # iPhone-ish
        for _ in range(60):
            try:
                await p.goto(url)
                break
            except Exception:
                await asyncio.sleep(0.25)
        await asyncio.sleep(wait)
        await p.screenshot(path=shot, full_page=True)
        out["page"] = await p.evaluate("""() => ({frames: window.__live.frames, perAgent: window.__live.perAgent,
            tiles: document.querySelectorAll('#grid .tile').length,
            imgs: [...document.querySelectorAll('#grid .tile img')].filter(i => i.naturalWidth > 0).length,
            latency_med: [...window.__live.latency].sort((a,b)=>a-b)[window.__live.latency.length>>1]})""")
        # focus view
        tiles = await p.query_selector_all("#grid .tile")
        if tiles:
            await tiles[0].click()
            await asyncio.sleep(1.5)
            await p.screenshot(path=shot.replace(".png", "-focus.png"))
        await b.close()


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--ws", default="ws://127.0.0.1:8767")
    ap.add_argument("--page", default="http://127.0.0.1:8766/live/")
    ap.add_argument("--seconds", type=float, default=20)
    ap.add_argument("--shot", default="live.png")
    a = ap.parse_args()
    ws_out: dict = {}
    page_out: dict = {}
    await asyncio.gather(ws_client(a.ws, a.seconds, ws_out), page_check(a.page, a.seconds * 0.5, a.shot, page_out))
    print(json.dumps({"ws": ws_out, **page_out}, indent=2))


if __name__ == "__main__":
    asyncio.run(main())
