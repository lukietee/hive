"""Browser agents: one headed Chrome window per agent, driven over CDP via Playwright.

Real input goes through the DevTools protocol (never the OS mouse), so many agents can work
in parallel. Before every action the agent's ghost cursor is sent to the element's *screen*
position (global points, top-left origin), per the sync rule.
"""

from __future__ import annotations

from dataclasses import dataclass

from playwright.async_api import Browser, BrowserContext, CDPSession, Locator, Page, Playwright

from .agent import Agent
from .bus import Bus

CHROME_ARGS = [
    "--disable-backgrounding-occluded-windows",
    "--disable-renderer-backgrounding",
    "--disable-background-timer-throttling",
    "--no-first-run",
    "--no-default-browser-check",
]


async def launch_chrome(pw: Playwright, headless: bool = False) -> Browser:
    """Launches the user's installed Google Chrome with a fresh temporary profile
    (Playwright's default for launch()), never the user's real profile."""
    try:
        return await pw.chromium.launch(channel="chrome", headless=headless, args=CHROME_ARGS)
    except Exception:
        # Fallback to Playwright's bundled Chromium (`uv run playwright install chromium`).
        return await pw.chromium.launch(headless=headless, args=CHROME_ARGS)


@dataclass
class Rect:
    left: int
    top: int
    width: int
    height: int


async def page_viewport_origin(page: Page) -> tuple[float, float]:
    """Screen point (global, top-left origin) of a page viewport's (0,0)."""
    m = await page.evaluate(
        "() => ({sx: window.screenX, sy: window.screenY, ow: window.outerWidth,"
        " iw: window.innerWidth, oh: window.outerHeight, ih: window.innerHeight})"
    )
    side = max(0, (m["ow"] - m["iw"]) / 2)
    return m["sx"] + side, m["sy"] + (m["oh"] - m["ih"]) - side


async def page_screen_rect(page: Page, locator: Locator) -> tuple[float, float, float, float]:
    """Screen rect (x, y, w, h in global points) of an element."""
    box = await locator.bounding_box()
    if box is None:
        raise RuntimeError("element not visible")
    ox, oy = await page_viewport_origin(page)
    return ox + box["x"], oy + box["y"], box["width"], box["height"]


async def open_window(browser: Browser, rect: "Rect | None" = None, url: str | None = None) -> tuple[BrowserContext, Page]:
    """A plain positioned Chrome window (no agent) — e.g. for the stopgap Deck Viewer."""
    ctx = await browser.new_context(no_viewport=True)
    page = await ctx.new_page()
    if rect:
        cdp = await ctx.new_cdp_session(page)
        wid = (await cdp.send("Browser.getWindowForTarget"))["windowId"]
        await cdp.send("Browser.setWindowBounds", {"windowId": wid, "bounds": {
            "left": rect.left, "top": rect.top, "width": rect.width, "height": rect.height}})
    if url:
        await page.goto(url)
    return ctx, page


class BrowserAgent(Agent):
    def __init__(self, bus: Bus, agent_id: str) -> None:
        super().__init__(bus, agent_id)
        self.context: BrowserContext | None = None
        self.page: Page | None = None
        self.cdp: CDPSession | None = None
        self.window_id: int | None = None

    # ---- window ------------------------------------------------------------
    async def open(self, browser: Browser, rect: Rect | None = None, url: str | None = None) -> Page:
        # no_viewport: the page fills the real window so CSS px map 1:1 onto screen points.
        self.context = await browser.new_context(no_viewport=True)
        self.page = await self.context.new_page()
        self.cdp = await self.context.new_cdp_session(self.page)
        win = await self.cdp.send("Browser.getWindowForTarget")
        self.window_id = win["windowId"]
        if rect:
            await self.set_window(rect)
        if url:
            await self.page.goto(url)
        return self.page

    async def set_window(self, rect: Rect) -> None:
        assert self.cdp and self.window_id is not None
        await self.cdp.send("Browser.setWindowBounds", {"windowId": self.window_id,
                                                        "bounds": {"windowState": "normal"}})
        await self.cdp.send("Browser.setWindowBounds", {
            "windowId": self.window_id,
            "bounds": {"left": rect.left, "top": rect.top, "width": rect.width, "height": rect.height},
        })

    async def close(self) -> None:
        if self.context:
            await self.context.close()

    # ---- coordinates -------------------------------------------------------
    async def viewport_origin(self) -> tuple[float, float]:
        """Recomputed on every call so moved windows don't cause cursor drift."""
        assert self.page
        return await page_viewport_origin(self.page)

    async def screen_rect_for(self, locator: Locator) -> tuple[float, float, float, float]:
        await locator.scroll_into_view_if_needed()
        box = await locator.bounding_box()
        if box is None:
            raise RuntimeError("element not visible")
        ox, oy = await self.viewport_origin()
        return ox + box["x"], oy + box["y"], box["width"], box["height"]

    async def screen_point_for(self, locator: Locator) -> tuple[float, float]:
        x, y, w, h = await self.screen_rect_for(locator)
        return x + w / 2, y + h / 2

    # ---- actions (sync rule: cursor first, then the real action) -------------
    async def click(self, locator: Locator, label: str | None = None, duration_ms: int = 350) -> None:
        x, y = await self.screen_point_for(locator)
        await self.click_at(x, y, duration_ms, label)
        await locator.click()

    async def type(self, locator: Locator, text: str, delay_ms: int = 35, duration_ms: int = 350) -> None:
        x, y = await self.screen_point_for(locator)
        await self.typing(x, y, text, duration_ms)
        await locator.click()
        await locator.press_sequentially(text, delay=delay_ms)

    async def point_at(self, locator: Locator, style: str = "box", label: str | None = None) -> None:
        """Glide to an element and outline it, without acting (reading / inspecting)."""
        x, y, w, h = await self.screen_rect_for(locator)
        await self.move_to(x + w / 2, y + h / 2, 350, label)
        self.highlight(x, y, w, h, style=style)

    async def click_xy(self, x: float, y: float, label: str | None = None) -> None:
        """Click at a SCREEN point (e.g. chosen by a model from a screenshot) — delivered only to
        this window via CDP Input.dispatchMouseEvent; the OS cursor never moves."""
        assert self.page
        await self.click_at(x, y, 350, label)
        ox, oy = await self.viewport_origin()
        vx, vy = x - ox, y - oy
        for t in ("mouseMoved", "mousePressed", "mouseReleased"):
            params = {"type": t, "x": vx, "y": vy, "button": "left" if t != "mouseMoved" else "none"}
            if t != "mouseMoved":
                params["clickCount"] = 1
            await self.cdp.send("Input.dispatchMouseEvent", params)  # type: ignore[union-attr]

    async def screenshot(self) -> bytes:
        assert self.page
        return await self.page.screenshot(type="jpeg", quality=60)
