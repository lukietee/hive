"""A positioned Chrome window that a non-browser worker (code, checker) renders its workbench into."""

from __future__ import annotations

from playwright.async_api import Browser, BrowserContext, Page

from ..browser_agent import Rect, page_screen_rect
from .base import DynamicAgent
from .workbench import Workbench, page_html


class AgentWindow:
    def __init__(self, agent: DynamicAgent) -> None:
        self.agent = agent
        self.bench = Workbench()
        self.ctx: BrowserContext | None = None
        self.page: Page | None = None
        self.live = None

    async def open(self, browser: Browser, rect: Rect, title: str) -> None:
        a = self.agent
        self.ctx = await browser.new_context(no_viewport=True)
        self.page = await self.ctx.new_page()
        cdp = await self.ctx.new_cdp_session(self.page)
        try:
            wid = (await cdp.send("Browser.getWindowForTarget"))["windowId"]
            await cdp.send("Browser.setWindowBounds", {"windowId": wid, "bounds": {"windowState": "normal"}})
            await cdp.send("Browser.setWindowBounds", {"windowId": wid, "bounds": {
                "left": rect.left, "top": rect.top, "width": rect.width, "height": rect.height}})
        except Exception:
            pass
        await self.page.set_content(page_html(a.name, title, a.color))
        from ..live import attach
        self.live = await attach(a.id, self.page, cdp)

    async def refresh(self) -> None:
        if self.page:
            try:
                await self.page.evaluate(self.bench.js())
            except Exception:
                pass

    async def point(self, selector: str, label: str | None = None, typing: str | None = None,
                    click: bool = False) -> None:
        """Glide the agent's ghost cursor to an element in this window (cosmetic, never raises)."""
        if not self.page:
            return
        try:
            loc = self.page.locator(selector).first
            if await loc.count() == 0:
                return
            x, y, w, h = await page_screen_rect(self.page, loc)
            px, py = x + min(w / 2, 160), y + h / 2
            if typing is not None:
                await self.agent.typing(px, py, typing, 380)
            elif click:
                await self.agent.click_at(px, py, 380, label)
            else:
                await self.agent.move_to(px, py, 380, label)
                self.agent.highlight(x, y, min(w, 520), h, style="box")
        except Exception:
            pass

    async def close(self) -> None:
        if self.live:
            try:
                await self.live.stop()
            except Exception:
                pass
        if self.ctx:
            try:
                await self.ctx.close()
            except Exception:
                pass
