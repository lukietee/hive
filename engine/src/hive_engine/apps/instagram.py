"""Real Instagram posting for the Social agent (Pitch in 5).

The post is made on instagram.com (desktop web) in the agents' dedicated, persistent Chrome profile
(~/Library/Application Support/HiveAgentsChrome — never the user's own profile), where a human has
logged into the demo account by hand. Every click follows the sync rule (ghost cursor first).

Nothing is ever published without an explicit human YES: the flow stops on the caption screen,
asks (needs_human kind "post"), and only then clicks Share. NO, a timeout, or an auto-answered
rehearsal discards the draft.

    ig = await InstagramSession.open(pw, agent, rect)     # None if the profile is busy / logged out
    draft = await ig.draft(image_path, caption)           # stops on the caption screen
    url = await ig.share() if approved else await ig.discard()
"""

from __future__ import annotations

import asyncio
import os
import logging
import re
from pathlib import Path
from typing import Any

from playwright.async_api import BrowserContext, Locator, Page, Playwright

from ..browser_agent import CHROME_ARGS, Rect

log = logging.getLogger("hive.instagram")

PROFILE_DIR = Path.home() / "Library" / "Application Support" / "HiveAgentsChrome"
HOME = "https://www.instagram.com/"
MAX_CAPTION = 2200

CLICK_RECORDER = ("window.__clicks = []; document.addEventListener('mousedown', "
                  "e => window.__clicks.push([e.clientX, e.clientY]), true);")

_BLOCK = re.compile(r"(?i)suspicious (login|activity)|confirm it'?s you|help us confirm|"
                    r"we suspended|your account has been|try again later|unusual activity|captcha")


class InstagramError(RuntimeError):
    """Login wall, checkpoint, bot check, or a step that couldn't be found. Reported, never retried."""


# ---- profile -----------------------------------------------------------------------------------
async def open_profile(pw: Playwright, wait_s: float = 30.0) -> BrowserContext:
    """The dedicated logged-in profile. Chrome allows one process per profile, so wait for it."""
    loop = asyncio.get_running_loop()
    end = loop.time() + wait_s
    last: Exception | None = None
    while True:
        try:
            ctx = await pw.chromium.launch_persistent_context(
                str(PROFILE_DIR), channel="chrome", headless=False, args=CHROME_ARGS,
                ignore_default_args=["--enable-automation"], no_viewport=True)
            await ctx.add_init_script(CLICK_RECORDER)
            return ctx
        except Exception as exc:  # ProcessSingleton: another Chrome holds the profile
            last = exc
            if loop.time() > end or ("ProcessSingleton" not in str(exc) and "in use" not in str(exc)):
                raise InstagramError(f"couldn't open the HiveAgentsChrome profile: {str(last)[:160]}") from exc
            await asyncio.sleep(3)


async def attach(agent, ctx: BrowserContext, rect: Rect | None) -> Page:
    """Points a BrowserAgent (the Social agent: same id, same ghost cursor) at the profile's window."""
    page = ctx.pages[0] if ctx.pages else await ctx.new_page()
    for extra in ctx.pages[1:]:          # restored tabs from the user's login session
        try:
            await extra.close()
        except Exception:
            pass
    agent.context, agent.page = ctx, page
    agent.cdp = await ctx.new_cdp_session(page)
    agent.window_id = (await agent.cdp.send("Browser.getWindowForTarget"))["windowId"]
    if rect:
        await agent.set_window(rect)
    try:
        from ..live import attach as live_attach
        agent.live = await live_attach(agent.id, page, agent.cdp)
    except Exception:
        agent.live = None
    return page


# ---- helpers -----------------------------------------------------------------------------------
async def first_visible(cands: list[Locator], timeout: float = 8.0) -> Locator | None:
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while loop.time() < end:
        for c in cands:
            try:
                n = await c.count()
                for i in range(min(n, 6)):
                    el = c.nth(i)
                    if await el.is_visible():
                        return el
            except Exception:
                pass
        await asyncio.sleep(0.25)
    return None


async def check_page(page: Page) -> None:
    """Raises InstagramError on a login wall, checkpoint or bot check."""
    url = page.url
    if "/accounts/login" in url or "/challenge" in url or "/checkpoint" in url:
        raise InstagramError("Instagram wants a login or a security check (log in by hand in the "
                             "HiveAgentsChrome profile)")
    try:
        if await page.locator("input[name='username']").count() and \
                await page.locator("input[name='password']").count():
            raise InstagramError("Instagram is showing its login form (log in by hand first)")
        # Logged-out home: no nav (Home / New post), just "Log in" / "Sign up" links.
        logged_in = await page.locator("svg[aria-label='Home'], svg[aria-label='New post']").count()
        login_cta = await page.get_by_role("link", name=re.compile(r"^(log in|sign up)$", re.I)).count() + \
            await page.get_by_role("button", name=re.compile(r"^(log in|sign up)$", re.I)).count()
        if not logged_in and login_cta:
            raise InstagramError("not logged into Instagram in the HiveAgentsChrome profile (log in by hand first)")
        body = await page.evaluate("() => (document.body && document.body.innerText || '').slice(0, 4000)")
    except InstagramError:
        raise
    except Exception:
        return
    if m := _BLOCK.search(body):
        raise InstagramError(f"Instagram blocked the flow: “{m.group(0)}”")


async def dismiss_popups(agent) -> None:
    """'Turn on notifications' / 'Save your login info' sheets: decline them."""
    page = agent.page
    el = await first_visible([page.get_by_role("button", name=re.compile(r"^not now$", re.I))], 1.5)
    if el:
        try:
            await agent.click(el, "not now")
        except Exception:
            pass


def button(page: Page, name: str) -> list[Locator]:
    """Instagram renders most buttons as div[role=button]; match the visible label exactly."""
    rx = re.compile(rf"^\s*{re.escape(name)}\s*$", re.I)
    return [page.get_by_role("button", name=rx), page.locator("div[role='button']").filter(has_text=rx)]


def clean_caption(text: str) -> str:
    """Instagram captions don't link; drop local URLs and keep it under the limit."""
    t = re.sub(r"https?://(127\.0\.0\.1|localhost)(:\d+)?\S*", "link in bio", text or "")
    t = re.sub(r"\s+\n", "\n", t).strip()
    if "#" not in t:
        t += "\n\n#matcha #LAHacks"
    return t[:MAX_CAPTION]


# ---- the post image ----------------------------------------------------------------------------
# ---- Launch graphic: a fresh Gemini image each run, with the brand text set cleanly on top ----
GEMINI_IMAGE_MODEL = "gemini-3.1-flash-image"
_SCENES = [
    "a ceramic bowl of bright green matcha with a bamboo whisk on a sunny dorm desk next to a laptop and textbooks",
    "an iced matcha latte in a clear glass on a college library table, soft window light",
    "overhead flat lay of matcha powder, a chasen whisk and a chawan bowl on cream linen",
    "a matcha latte with latte art held up against a blurred college campus quad at golden hour",
    "a cozy dorm room shelf with a matcha tin, a mug and string lights, late-night study vibe",
    "matcha being whisked into foam, close-up, steam rising, minimalist Japanese ceramic",
    "a delivery box opened on a dorm bed revealing matcha tins and a whisk, playful and bright",
]
# Illustration only: no photorealism (it reads as AI slop on a brand account).
_STYLES = ["flat vector illustration with bold shapes and a limited palette",
           "cute kawaii cartoon with thick outlines and soft pastel colors",
           "Studio-Ghibli-inspired hand-painted animation still",
           "retro 90s anime cel-shaded illustration",
           "playful 3D clay / claymation render with soft shadows",
           "risograph-style print illustration with grainy texture"]


async def gemini_image(prompt: str, aspect: str = "1:1", timeout: float = 30.0):
    """One image from Gemini (PIL.Image, RGB) or None if there's no key or it fails."""
    import base64
    import io

    import httpx
    from PIL import Image

    key = os.environ.get("GEMINI_API_KEY")
    if not key:
        return None
    body = {"contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": aspect}}}
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_IMAGE_MODEL}:generateContent"
    try:
        async with httpx.AsyncClient(timeout=timeout) as c:
            r = await c.post(url, params={"key": key}, json=body)
        r.raise_for_status()
        parts = r.json()["candidates"][0]["content"]["parts"]
        data = next(p["inlineData"]["data"] for p in parts if "inlineData" in p)
        return Image.open(io.BytesIO(base64.b64decode(data))).convert("RGB")
    except Exception as exc:
        log.warning("gemini image failed (%s)", exc)
        return None


async def gemini_square(out: Path, price: str = "$29", headline: str = "Matcha, delivered to your dorm.",
                        timeout: float = 30.0) -> Path | None:
    """A new 1080x1080 launch image every run: Gemini draws a cartoon/animated scene (no text), then the brand text is
    set on top with Pillow so it's always spelled right. Returns None if Gemini isn't available."""
    import base64
    import io
    import random

    import httpx
    from PIL import Image

    scene, style = random.choice(_SCENES), random.choice(_STYLES)
    prompt = (f"A {style} of {scene}. It must look clearly illustrated or animated, like a cartoon or "
              "an animation frame: NOT a photograph, not photorealistic, no realistic people or skin. "
              "Fresh green matcha is the hero, cheerful and on-brand. Square composition with calm "
              "empty space in the bottom third. Absolutely no text, letters, logos or watermarks.")
    img = await gemini_image(prompt, "1:1", timeout)
    if img is None:
        return None
    img = img.resize((1080, 1080))
    _brand_band(img, price, headline)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG")
    return out


def _brand_band(img, price: str, headline: str) -> None:
    """A translucent band at the bottom with the wordmark, headline and price."""
    from PIL import Image, ImageDraw
    W = img.width
    band = Image.new("RGBA", (W, 300), (20, 28, 22, 190))
    img.paste(band, (0, W - 300), band)
    d = ImageDraw.Draw(img)
    f_big, f_mid, f_small = _font(84, True), _font(44), _font(40, True)
    d.text((64, W - 270), "Whisk", font=f_big, fill=(243, 239, 228))
    d.text((64, W - 165), headline, font=f_mid, fill=(243, 239, 228))
    d.text((64, W - 100), f"{price}/mo  ·  $19 for students", font=f_small, fill=(160, 214, 140))


def _font(size: int, bold: bool = False):
    from PIL import ImageFont
    for path, idx in (("/System/Library/Fonts/Avenir Next.ttc", 8 if bold else 7),
                      ("/System/Library/Fonts/Helvetica.ttc", 1 if bold else 0)):
        try:
            return ImageFont.truetype(path, size, index=idx)
        except Exception:
            continue
    return ImageFont.load_default()


def make_square(out: Path, price: str = "$29", headline: str = "Matcha, delivered to your dorm.") -> Path:
    """A 1080x1080 branded square (Pillow, local, no APIs)."""
    from PIL import Image, ImageDraw, ImageFont

    def font(size: int, bold: bool = False):
        for path, idx in (("/System/Library/Fonts/Avenir Next.ttc", 8 if bold else 7),
                          ("/System/Library/Fonts/Helvetica.ttc", 1 if bold else 0)):
            try:
                return ImageFont.truetype(path, size, index=idx)
            except Exception:
                continue
        return ImageFont.load_default()

    W = 1080
    img = Image.new("RGB", (W, W), (243, 239, 228))            # cream, like the Whisk site
    d = ImageDraw.Draw(img)
    green, dark = (47, 93, 58), (28, 38, 30)
    # Logo: a matcha bowl in a green circle.
    cx, cy, r = W // 2, 330, 150
    d.ellipse((cx - r, cy - r, cx + r, cy + r), fill=green)
    d.pieslice((cx - 95, cy - 55, cx + 95, cy + 125), 0, 180, fill=(243, 239, 228))
    d.rectangle((cx - 95, cy + 33, cx + 95, cy + 37), fill=(243, 239, 228))
    for dx in (-40, 0, 40):  # steam
        d.arc((cx + dx - 14, cy - 95, cx + dx + 14, cy - 55), 100, 260, fill=(243, 239, 228), width=7)
        d.arc((cx + dx - 14, cy - 60, cx + dx + 14, cy - 20), 280, 80, fill=(243, 239, 228), width=7)

    def center(text: str, y: int, f, fill) -> None:
        w = d.textlength(text, font=f)
        d.text(((W - w) / 2, y), text, font=f, fill=fill)

    center("Whisk", 520, font(120, bold=True), dark)
    words, lines, cur = headline.split(), [], ""
    f = font(58)
    for wd in words:
        trial = (cur + " " + wd).strip()
        if d.textlength(trial, font=f) > W - 160 and cur:
            lines.append(cur)
            cur = wd
        else:
            cur = trial
    lines.append(cur)
    for i, ln in enumerate(lines[:2]):
        center(ln, 690 + i * 74, f, dark)
    center(f"{price}/mo  ·  $19 for students", 880, font(48, bold=True), green)
    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out, "PNG")
    return out


# ---- the flow ----------------------------------------------------------------------------------
class InstagramSession:
    def __init__(self, agent, ctx: BrowserContext) -> None:
        self.agent = agent
        self.ctx = ctx
        self.page: Page = agent.page
        self.drafted = False

    @classmethod
    async def open(cls, pw: Playwright, agent, rect: Rect | None) -> "InstagramSession":
        ctx = await open_profile(pw)
        await attach(agent, ctx, rect)
        s = cls(agent, ctx)
        await s.page.goto(HOME, wait_until="domcontentloaded")
        await asyncio.sleep(2.5)
        await check_page(s.page)
        await dismiss_popups(agent)
        return s

    async def step(self, text: str, progress: float, fn, timeout: float = 30.0) -> Any:
        self.agent.status(text, progress)
        out = await asyncio.wait_for(fn(), timeout)
        await check_page(self.page)
        return out

    async def draft(self, image: Path, caption: str) -> dict:
        """Create → Post → upload → Next → Next → caption. Stops before Share."""
        a, p = self.agent, self.page

        async def create():
            el = await first_visible([
                p.locator("svg[aria-label='New post']"),
                p.get_by_role("link", name=re.compile(r"^(new post|create)$", re.I)),
                p.locator("a, div[role='button'], span").filter(has_text=re.compile(r"^\s*Create\s*$")),
            ], 10)
            if not el:
                raise InstagramError("couldn't find Instagram's Create button")
            await a.click(el, "Create")
            await asyncio.sleep(1.2)
            # Newer UI: Create opens a small menu (Post / Reel / AI); older: the dialog directly.
            post = await first_visible([
                p.get_by_role("link", name=re.compile(r"^post$", re.I)),
                p.get_by_role("menuitem", name=re.compile(r"^post$", re.I)),
                p.locator("svg[aria-label='Post']"),
                p.locator("a, div[role='button'], span").filter(has_text=re.compile(r"^\s*Post\s*$")),
            ], 2.5)
            if post and not await p.locator("div[role='dialog'] input[type='file']").count():
                await a.click(post, "Post")
                await asyncio.sleep(1.2)
        await self.step("Opening Instagram's Create → Post", 0.55, create)

        async def upload():
            pick = await first_visible(button(p, "Select from computer") +
                                       [p.locator("button").filter(has_text=re.compile("select from computer", re.I))], 8)
            if pick:
                await a.point_at(pick, style="box", label="Select from computer")
            inp = p.locator("div[role='dialog'] input[type='file'], input[type='file'][accept*='image']").first
            await inp.set_input_files(str(image))
            await asyncio.sleep(2.5)
        await self.step("Uploading the launch image", 0.62, upload)

        async def crop_and_next():
            sel = await first_visible([p.locator("svg[aria-label='Select crop']").locator("xpath=ancestor::*[@role='button' or self::button][1]"),
                                       p.locator("svg[aria-label='Select crop']")], 3)
            if sel:
                try:
                    await a.click(sel, "crop")
                    await asyncio.sleep(0.6)
                    orig = await first_visible([p.locator("div[role='button'], button, span").filter(
                        has_text=re.compile(r"^\s*Original\s*$"))], 2)
                    if orig:
                        await a.click(orig, "Original")
                        await asyncio.sleep(0.5)
                except Exception as exc:
                    log.info("crop: %s", exc)
            for label in ("Next", "Next"):
                nxt = await first_visible(button(p, label), 8)
                if not nxt:
                    raise InstagramError("couldn't find Next in the post dialog")
                await a.click(nxt, label)
                await asyncio.sleep(1.5)
        await self.step("Cropping and skipping filters", 0.7, crop_and_next, 40)

        async def write_caption():
            box = await first_visible([
                p.locator("div[aria-label^='Write a caption'][contenteditable='true']"),
                p.locator("div[role='dialog'] div[contenteditable='true']"),
                p.get_by_role("textbox"),
            ], 8)
            if not box:
                raise InstagramError("couldn't find the caption box")
            x, y = await a.screen_point_for(box)
            await a.typing(x, y, caption[:60] + ("…" if len(caption) > 60 else ""))
            await box.click()
            await a._verify_click()
            # Fast but visible: type the first line key by key, paste the rest.
            first, _, rest = caption.partition("\n")
            await box.press_sequentially(first, delay=12)
            if rest:
                await p.keyboard.press("Shift+Enter")
                await p.keyboard.insert_text(rest)
            await asyncio.sleep(0.8)
        await self.step("Writing the caption", 0.8, write_caption)

        share = await first_visible(button(self.page, "Share"), 6)
        if not share:
            raise InstagramError("reached the caption screen but no Share button")
        await a.point_at(share, style="circle", label="Share (needs your OK)")
        self.drafted = True
        return {"stage": "caption", "url": self.page.url}

    async def recaption(self, caption: str) -> None:
        """Replace the caption in the open post dialog (e.g. after "@Social make it shorter")."""
        a, p = self.agent, self.page
        box = await first_visible([
            p.locator("div[aria-label^='Write a caption'][contenteditable='true']"),
            p.locator("div[role='dialog'] div[contenteditable='true']"),
        ], 6)
        if not box:
            raise InstagramError("couldn't find the caption box")
        x, y = await a.screen_point_for(box)
        await a.typing(x, y, caption[:60] + ("…" if len(caption) > 60 else ""))
        await box.click()
        await p.keyboard.press("Meta+A")
        await p.keyboard.press("Backspace")
        first, _, rest = caption.partition("\n")
        await box.press_sequentially(first, delay=12)
        if rest:
            await p.keyboard.press("Shift+Enter")
            await p.keyboard.insert_text(rest)
        await asyncio.sleep(0.6)

    async def share(self) -> str | None:
        """Clicks Share (call ONLY after an explicit human YES); returns the post URL if found."""
        a, p = self.agent, self.page
        assert self.drafted, "share() without a drafted post"
        btn = await first_visible(button(p, "Share"), 6)
        if not btn:
            raise InstagramError("the Share button disappeared")
        await a.click(btn, "Share")
        a.status("Posting to Instagram…", 0.9)
        done = await first_visible([p.get_by_text(re.compile(r"(post|reel) (has been )?shared|your post has been shared", re.I))], 60)
        if not done:
            raise InstagramError("Instagram didn't confirm the post (check the account)")
        await asyncio.sleep(1.0)
        return await self.latest_post_url()

    async def latest_post_url(self) -> str | None:
        p = self.page
        try:
            await p.keyboard.press("Escape")
            prof = await first_visible([p.get_by_role("link", name=re.compile(r"^profile$", re.I)),
                                        p.locator("a[href^='/'][role='link']").filter(has_text=re.compile(r"^\s*Profile\s*$"))], 5)
            if prof:
                await self.agent.click(prof, "Profile")
                await asyncio.sleep(2.5)
            link = await first_visible([p.locator("a[href*='/p/']")], 10)
            if link:
                href = await link.get_attribute("href")
                return HOME.rstrip("/") + href if href and href.startswith("/") else href
        except Exception as exc:
            log.info("latest post url: %s", exc)
        return None

    async def discard(self) -> None:
        """Closes the draft without posting (Escape → Discard)."""
        p = self.page
        try:
            close = await first_visible([p.locator("svg[aria-label='Close']"), *button(p, "Close")], 2)
            if close:
                await self.agent.click(close, "close")
            else:
                await p.keyboard.press("Escape")
            await asyncio.sleep(0.8)
            disc = await first_visible(button(p, "Discard"), 3)
            if disc:
                await self.agent.click(disc, "Discard")
        except Exception as exc:
            log.info("discard: %s", exc)
        self.drafted = False

    async def close(self) -> None:
        try:
            if self.agent.live:
                await self.agent.live.stop()
                self.agent.live = None
        except Exception:
            pass
        await self.ctx.close()


__all__ = ["InstagramSession", "InstagramError", "make_square", "clean_caption", "PROFILE_DIR"]
