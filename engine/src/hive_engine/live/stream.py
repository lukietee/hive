"""Per-agent screencast: Chrome DevTools `Page.startScreencast` → JPEG frames → LiveRelay.

Chrome renders the frames itself, so this needs no macOS Screen Recording permission and works
for windows that are covered by other windows. Chrome only sends a frame when the page repaints;
we pace the acks to cap the rate at `fps`.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
import time
from typing import Any

from playwright.async_api import CDPSession, Page

from .relay import Geometry, LiveRelay, get_relay

log = logging.getLogger("hive.live")

FPS = float(os.environ.get("HIVE_LIVE_FPS", "8"))
QUALITY = int(os.environ.get("HIVE_LIVE_QUALITY", "60"))
MAX_WIDTH = int(os.environ.get("HIVE_LIVE_MAX_WIDTH", "960"))


def live_enabled() -> bool:
    return os.environ.get("HIVE_LIVE", "1") not in ("0", "false", "off")


class Screencast:
    def __init__(self, agent_id: str, page: Page, cdp: CDPSession, relay: LiveRelay,
                 fps: float = FPS, quality: int = QUALITY, max_width: int = MAX_WIDTH) -> None:
        self.agent_id, self.page, self.cdp, self.relay = agent_id, page, cdp, relay
        self.interval = 1.0 / max(fps, 0.5)
        self.quality, self.max_width = quality, max_width
        self.seq = 0
        self._last = 0.0
        self._running = False
        self._geo_task: asyncio.Task | None = None
        self._pending: set[asyncio.Task] = set()

    async def start(self) -> None:
        await self._update_geometry()
        self.cdp.on("Page.screencastFrame", self._on_frame)
        await self.cdp.send("Page.startScreencast", {"format": "jpeg", "quality": self.quality,
                                                     "maxWidth": self.max_width, "maxHeight": self.max_width,
                                                     "everyNthFrame": 1})
        self._running = True
        self._geo_task = asyncio.create_task(self._geometry_loop())
        self.relay.set_streaming(self.agent_id, True)

    async def stop(self) -> None:
        self._running = False
        if self._geo_task:
            self._geo_task.cancel()
        try:
            self.cdp.remove_listener("Page.screencastFrame", self._on_frame)
            await self.cdp.send("Page.stopScreencast")
        except Exception:
            pass  # page / browser already gone
        self.relay.set_streaming(self.agent_id, False)

    # ---- geometry: screen points → page fractions for the cursor overlay ---------
    async def _update_geometry(self) -> None:
        m = await self.page.evaluate(
            "() => ({sx: window.screenX, sy: window.screenY, ow: window.outerWidth,"
            " iw: window.innerWidth, oh: window.outerHeight, ih: window.innerHeight})"
        )
        side = max(0, (m["ow"] - m["iw"]) / 2)  # same math as browser_agent.page_viewport_origin
        self.relay.set_geometry(self.agent_id, Geometry(m["sx"] + side, m["sy"] + (m["oh"] - m["ih"]) - side,
                                                        m["iw"], m["ih"]))

    async def _geometry_loop(self) -> None:
        while self._running:
            await asyncio.sleep(1.0)  # windows can be moved / resized mid-run
            try:
                await self._update_geometry()
            except Exception:
                return

    # ---- frames -----------------------------------------------------------------
    def _on_frame(self, params: dict[str, Any]) -> None:
        t = asyncio.create_task(self._handle(params))
        self._pending.add(t)
        t.add_done_callback(self._pending.discard)

    async def _handle(self, params: dict[str, Any]) -> None:
        jpeg = base64.b64decode(params["data"])
        meta = params.get("metadata") or {}
        self.seq += 1
        cap = meta.get("timestamp")  # seconds since epoch, when Chrome produced the frame
        self.relay.push_frame(self.agent_id, jpeg, int(meta.get("deviceWidth", 0)),
                              int(meta.get("deviceHeight", 0)), self.seq, round(cap * 1000) if cap else None)
        # Chrome sends the next frame only after the ack, so delaying it caps the frame rate.
        wait = self.interval - (time.monotonic() - self._last)
        if wait > 0:
            await asyncio.sleep(wait)
        self._last = time.monotonic()
        if self._running:
            try:
                await self.cdp.send("Page.screencastFrameAck", {"sessionId": params["sessionId"]})
            except Exception:
                pass


async def attach(agent_id: str, page: Page, cdp: CDPSession) -> Screencast | None:
    """Start streaming an agent's page to the 👁 live view. Never raises: live view is optional."""
    if not live_enabled():
        return None
    try:
        sc = Screencast(agent_id, page, cdp, await get_relay())
        await sc.start()
        return sc
    except Exception as exc:
        log.warning("live view disabled for %s: %s", agent_id, exc)
        return None
