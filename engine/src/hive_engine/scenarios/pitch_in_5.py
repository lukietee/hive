"""pitch_in_5 — the live demo. A half-built startup (Whisk) gets finished by five agents in parallel.

Runs on a fresh temp COPY of demo-world (see pitch_world.py); the repo is never modified.

Windows (2×2, real Chrome on a temp profile, all input over CDP — the OS mouse never moves):
  ① top-left     🔴 Fixer   — editor page: runs `node --test`, patches signup.js, 1 failing → 5/5
  ② top-right    🔵 Web     — the landing page: hero, button, logo, pricing ($39 from an old note), waitlist
  ③ bottom-left  🟡 Deck    — Deck Viewer (the Mac app's native one if it reports deck_viewer, else the
                              Chrome stopgap): fills slides 3/5/6/7/10 of pitch.pptx (+ logo on 1 and 3)
  ④ bottom-right 🟣 Social  — post composer: drafts the launch post (no real posting)
  overlay        ⚪ Checker — compares site vs deck price, links them, asks the human ($29 by default)

Handoffs (asyncio events): Fixer's test screenshot and Web's site screenshot → Deck slide 5;
Web's logo → Deck slides 1/3 + Social; Checker's price decision → Web/Deck fix + Social copy; Web's URL →
Deck slide 10 + Social.

Human moments (both time out so the scripted demo never hangs):
  • Deck:    "Slide 6 market size: $4B or $2B?"   (default $4B after --answer-timeout s)
  • Checker: "Site says $39, deck says $29"       (default $29)
  • Social:  send {"cmd":"say","args":{"text":"@Social make it shorter"}} after the first draft; if nobody
             does, Social trims it itself because the draft is over 280 characters.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import re
import shutil
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from playwright.async_api import Browser, Page, async_playwright
from pptx import Presentation
from pptx.dml.color import RGBColor

from .. import conductor
from ..agent import Agent
from ..browser_agent import BrowserAgent, Rect, launch_chrome, open_window, page_screen_rect
from ..apps.deploy import vercel_deploy
from ..layout import check_bounds, grid, place_native, usable_area
from ..bus import Bus
from ..deck_agent import DeckAgent
from ..http_server import HTTP_PORT
from . import pitch_content as content
from ..apps.vscode import VSCode
from .pitch_world import (WORLD_URL, edit, find_line, image_size, make_workspace, market_chart, run_node_tests,
                          section, start_world_server, svg_to_png)

log = logging.getLogger("hive.pitch")

VIEWER_URL = f"http://127.0.0.1:{HTTP_PORT}/viewer/index.html"
REQUEST = ("Our pitch starts in 5 minutes and nothing is finished. Fix the product's failing test and finish "
           "signup, fix the landing page, fill the blank deck slides, and write the launch post.")

CREAM = RGBColor(0xF6, 0xF1, 0xE7)
MATCHA = RGBColor(0x8D, 0xBF, 0x5A)

# Records every real mousedown (viewport coords) so we can prove the ghost cursor matched the click.
CLICK_RECORDER = ("window.__clicks = []; document.addEventListener('mousedown', "
                  "e => window.__clicks.push([e.clientX, e.clientY]), true);")


# ---- shared state between agents -----------------------------------------------------------------
@dataclass
class Handoffs:
    vs: Any = None            # the shared real VS Code window (Fixer + Web type into it)
    logo_png: Path | None = None
    tests_png: Path | None = None
    site_png: Path | None = None
    pricing_png: Path | None = None
    url: str | None = None
    price: str | None = None  # the decided standard price, e.g. "$29"
    post: str | None = None
    logo_ready: asyncio.Event = field(default_factory=asyncio.Event)
    tests_shot: asyncio.Event = field(default_factory=asyncio.Event)
    site_shot: asyncio.Event = field(default_factory=asyncio.Event)
    pricing_shot: asyncio.Event = field(default_factory=asyncio.Event)
    url_ready: asyncio.Event = field(default_factory=asyncio.Event)
    site_priced: asyncio.Event = field(default_factory=asyncio.Event)
    deck_priced: asyncio.Event = field(default_factory=asyncio.Event)
    price_resolved: asyncio.Event = field(default_factory=asyncio.Event)
    price_applied: asyncio.Event = field(default_factory=asyncio.Event)
    social_saved: asyncio.Event = field(default_factory=asyncio.Event)


@dataclass
class Opts:
    pace: float = 3.0            # multiplies every deliberate pause (fast mode: 1.0)
    dwell: float = 3.8           # seconds after each visible action (fast mode: 1.2)
    glide_ms: int = 650          # ghost-cursor glide duration (fast mode: 400)
    type_delay: int = 40         # ms per keystroke for visible typing
    answer_timeout: float = 8.0  # seconds before a needs_human question takes its default
    redirect_wait: float = 8.0   # how long Social waits for "@Social make it shorter"
    target_s: float = 175.0      # the 5:00 countdown is compressed to this many real seconds (run ≈ 2:10)
    auto_human: bool = False     # rehearsal: answer questions and send the redirect automatically


async def wait_for(ev: asyncio.Event, timeout: float) -> bool:
    try:
        await asyncio.wait_for(ev.wait(), timeout)
        return True
    except asyncio.TimeoutError:
        return False


def price_of(text: str) -> str | None:
    m = re.search(r"\$\s?(\d+)", text)
    return f"${m.group(1)}" if m else None


# ---- agents with click verification ---------------------------------------------------------------
class TrackedBrowserAgent(BrowserAgent):
    """BrowserAgent that records how far each real click landed from the ghost cursor (in points)."""

    def __init__(self, bus: Bus, agent_id: str, dwell: float = 0.0, glide_ms: int = 350) -> None:
        super().__init__(bus, agent_id)
        self.click_errors: list[float] = []
        self.dwell = dwell          # pause after every visible action, so people can follow each window
        self.glide_ms = glide_ms    # ghost-cursor glide duration

    async def point_at(self, locator, style: str = "box", label: str | None = None) -> None:
        x, y, w, h = await self.screen_rect_for(locator)
        await self.move_to(x + w / 2, y + h / 2, self.glide_ms, label)
        self.highlight(x, y, w, h, style=style)
        await asyncio.sleep(self.dwell)

    async def typing(self, x: float, y: float, text: str, duration_ms: int = 300) -> None:
        await super().typing(x, y, text, duration_ms)
        await asyncio.sleep(self.dwell)  # reads as "typing" before the edit lands

    async def open(self, browser: Browser, rect: Rect | None = None, url: str | None = None) -> Page:
        # Reuse BrowserAgent.open (it carries the live-view hooks); add the recorder before navigating.
        page = await super().open(browser, rect, None)
        assert self.context
        await self.context.add_init_script(CLICK_RECORDER)
        if url:
            await page.goto(url)
        return page

    async def click(self, locator, label: str | None = None, duration_ms: int | None = None) -> None:
        await super().click(locator, label, duration_ms or self.glide_ms)
        await self._verify_click()
        await asyncio.sleep(self.dwell)

    async def type(self, locator, text: str, delay_ms: int = 35, duration_ms: int | None = None) -> None:
        x, y = await self.screen_point_for(locator)
        await Agent.typing(self, x, y, text, duration_ms or self.glide_ms)
        await locator.click()
        await self._verify_click()
        await locator.press_sequentially(text, delay=delay_ms)
        await asyncio.sleep(self.dwell)

    async def _verify_click(self) -> None:
        assert self.page and self.pos
        clicks = await self.page.evaluate("() => window.__clicks || []")
        if clicks:
            ox, oy = await self.viewport_origin()
            cx, cy = clicks[-1]
            self.click_errors.append(round(math.hypot(ox + cx - self.pos[0], oy + cy - self.pos[1]), 2))

    async def enter(self, delay: float = 0.0) -> None:
        """Fly out of the notch into this agent's window."""
        await asyncio.sleep(delay)
        self.spawn()
        ox, oy = await self.viewport_origin()
        await self.move_to(ox + 60, oy + 50, 650, "on it")


class PitchDeck(DeckAgent):
    """DeckAgent that keeps the deck's own fonts (size/bold) when filling a TODO box, and serializes
    every viewer action behind a lock so the Checker can borrow the viewer between Deck's edits."""

    def __init__(self, *args, **kw) -> None:
        super().__init__(*args, **kw)
        self.lock = asyncio.Lock()
        self.filled: set[str] = set()
        self.step_pause = 0.5  # seconds after each edit, so each change reads on screen (set from pace)

    async def render(self) -> float:
        dt = await super().render()
        await asyncio.sleep(self.step_pause)
        return dt

    async def _focus(self, slide_idx: int, box: list[float], label: str) -> None:
        # settle: let the stopgap viewer finish its CSS zoom before measuring (the native one replies with deck_box)
        rect, native = await self.focus_rect(slide_idx, box, label, settle=0.5)
        if rect:
            x, y, w, h = rect
            await self.move_to(x + w / 2, y + h / 2, 450, label)
            if not native:
                self.highlight(x, y, w, h, style="select")
        else:
            await asyncio.sleep(0.5)

    async def fill(self, slide_idx: int, key: str, value: str | list[str], label: str,
                   color: RGBColor = CREAM, bullets: bool = False) -> None:
        async with self.lock:
            await self.gate()
            prs = Presentation(self.pptx)
            shape = self._find_shape(prs.slides[slide_idx], key)
            await self._focus(slide_idx, self._box_frac(prs, shape), label)
            if self.pos:
                preview = value if isinstance(value, str) else " · ".join(value)
                self.emit("typing", x=round(self.pos[0], 1), y=round(self.pos[1], 1), text=preview)
            write_styled(shape, value, color, bullets)
            prs.save(self.pptx)
            dt = await self.render()
            self.emit("deck_slide_updated", slide=slide_idx, version=self.version, render_ms=int(dt * 1000))
            self.filled.add(key)

    async def put_image(self, slide_idx: int, key: str, image: Path, label: str) -> None:
        """Fit the image inside the placeholder box (keeping its aspect ratio, centered), then drop the box."""
        async with self.lock:
            await self.gate()
            prs = Presentation(self.pptx)
            slide = prs.slides[slide_idx]
            shape = self._find_shape(slide, key)
            await self._focus(slide_idx, self._box_frac(prs, shape), label)
            iw, ih = image_size(image)
            scale = min(shape.width / iw, shape.height / ih)
            w, hh = int(iw * scale), int(ih * scale)
            slide.shapes.add_picture(str(image), shape.left + (shape.width - w) // 2,
                                     shape.top + (shape.height - hh) // 2, w, hh)
            shape._element.getparent().remove(shape._element)
            prs.save(self.pptx)
            dt = await self.render()
            self.emit("deck_slide_updated", slide=slide_idx, version=self.version, render_ms=int(dt * 1000))
            self.filled.add(key)

    async def show(self, slide_idx: int, key: str, label: str) -> tuple[float, float, float, float] | None:
        """Bring a shape into view for someone else (the Checker); returns its screen rect."""
        async with self.lock:
            prs = Presentation(self.pptx)
            box = self._box_frac(prs, self._find_shape(prs.slides[slide_idx], key))
            rect, _ = await self.focus_rect(slide_idx, box, label, settle=0.6)
            return rect

    def read(self, slide_idx: int, key: str) -> str:
        return self._find_shape(Presentation(self.pptx).slides[slide_idx], key).text_frame.text


def write_styled(shape, value: str | list[str], color: RGBColor, bullets: bool = False) -> None:
    tf = shape.text_frame
    p0 = tf.paragraphs[0]
    r0 = p0.runs[0] if p0.runs else None
    size, bold, name = (r0.font.size, r0.font.bold, r0.font.name) if r0 else (None, None, None)
    space, align = p0.space_after, p0.alignment
    for p in tf.paragraphs[1:]:
        p._p.getparent().remove(p._p)
    for r in list(p0.runs):
        r._r.getparent().remove(r._r)
    lines = value if isinstance(value, list) else [value]
    for i, line in enumerate(lines):
        p = p0 if i == 0 else tf.add_paragraph()
        p.space_after, p.alignment = space, align
        run = p.add_run()
        run.text = f"•  {line}" if bullets else line
        run.font.size, run.font.bold, run.font.name = size, bold, name
        run.font.color.rgb = color


async def ask(agent: Agent, question: str, options: list[str], opts: Opts) -> str:
    if opts.auto_human:
        async def auto() -> None:
            await asyncio.sleep(2.0)
            agent.answer(options[0])
        asyncio.create_task(auto())
    try:
        choice = await agent.ask_human(question, options, timeout=opts.answer_timeout)
    except asyncio.TimeoutError:
        choice = options[0]
        agent.chat(f"No answer yet, so I'm going with {choice} (you can still change it).")
        return choice
    choice = str(choice)
    for o in options:  # accept "29", "$29", "$29/mo"
        if choice == o or (price_of(choice) and price_of(choice) == price_of(o)):
            agent.status(f"Got it: {o}")
            return o
    return options[0]


async def wait_until_no_question(bus: Bus, timeout: float = 20.0) -> None:
    t0 = time.monotonic()
    while time.monotonic() - t0 < timeout:
        if not any(getattr(a, "_pending_answer", None) is not None for a in bus.agents.values()):
            return
        await asyncio.sleep(0.25)


# ---- 🔴 Fixer --------------------------------------------------------------------------------------
SIGNUP = "product/src/signup.js"
TESTS = "product/test/signup.test.js"

FEATURES = [
    ("const plan = \"standard\";", "student plan",
     '  // TODO(builder): student plan — .edu emails should get plan "student" ($19/mo instead of $29/mo)\n'
     '  const plan = "standard";',
     '  // Student plan: .edu emails pay $19/mo instead of $29/mo\n'
     '  const plan = email.toLowerCase().endsWith(".edu") ? "student" : "standard";'),
    ('throw new Error("not implemented");', "welcome email",
     "// TODO(builder): implement. Should return { to, subject, body } and never throw.\n"
     "function sendWelcomeEmail(user) {\n"
     '  throw new Error("not implemented");\n'
     "}",
     "function sendWelcomeEmail(user) {\n"
     "  return {\n"
     "    to: user.email,\n"
     '    subject: "Welcome to Whisk 🍵",\n'
     "    body: `Your first matcha ships this week. Share your code ${user.referralCode} for free credits.`,\n"
     "  };\n"
     "}"),
    ("TODO(builder): return a session token", "session token",
     "  // TODO(builder): send the welcome email (see sendWelcomeEmail below)\n"
     "  // TODO(builder): return a session token so the app can log the user in right away\n"
     "\n"
     "  return { id: user.id, email: user.email, plan: user.plan, referralCode: user.referralCode };",
     "  sendWelcomeEmail(user);\n"
     '  const sessionToken = crypto.randomBytes(24).toString("hex");\n'
     "\n"
     "  return { id: user.id, email: user.email, plan: user.plan, referralCode: user.referralCode, sessionToken };"),
]


class EditorAgent(Agent):
    """An agent that works in the real VS Code window (Fixer): ghost cursor over the editor."""

    def __init__(self, bus: Bus, agent_id: str, vs: VSCode, dwell: float = 0.0, glide_ms: int = 350) -> None:
        super().__init__(bus, agent_id)
        self.vs = vs
        self.dwell = dwell
        self.glide_ms = glide_ms
        self.click_errors: list[float] = []   # no DOM clicks to verify in VS Code

    async def enter(self, delay: float = 0.0) -> None:
        await asyncio.sleep(delay)
        self.spawn()
        x, y, _w, _h = await self.vs.frame()
        await self.move_to(x + 90, y + 80, 650, "on it")

    async def close(self) -> None:
        pass


def terminal_png(result: dict, path: Path, title: str = "npm test") -> Path:
    """The test run as a terminal-style PNG (for the deck), drawn from the real node --test output."""
    from PIL import Image, ImageDraw, ImageFont

    lines = [f"$ {title}"] + result.get("output", "").splitlines()[:16]
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Menlo.ttc", 26)
    except OSError:
        font = ImageFont.load_default()
    w, lh = 1400, 40
    img = Image.new("RGB", (w, 60 + lh * len(lines)), (30, 30, 30))
    d = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        color = ((110, 220, 120) if line.startswith("✔") else (240, 110, 100) if line.startswith("✖") else
                 (230, 200, 90) if line.startswith("⚠") else (200, 200, 200))
        d.text((30, 30 + i * lh), line, font=font, fill=color)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path)
    return path


async def run_tests(f: EditorAgent, product: Path, label: str = "npm test") -> dict:
    """`npm test` typed into VS Code's terminal (visible); the same suite run as a subprocess gives the
    exact counts (node --test is deterministic here)."""
    await f.vs.run_in_terminal(f, "npm test", cwd=product, label=label, glide_ms=f.glide_ms)
    r = await asyncio.to_thread(run_node_tests, product)
    await asyncio.sleep(max(1.2, f.dwell))  # let the terminal output land on screen
    return r


async def fixer_flow(f: EditorAgent, ws: Path, h: Handoffs, opts: Opts, out: dict) -> None:
    vs, pace = f.vs, opts.pace
    product = ws / "product"
    sig, tests = ws / SIGNUP, ws / TESTS

    f.status("Running the test suite in VS Code", 0.05)
    r = await run_tests(f, product)
    out["tests_before"] = {k: r[k] for k in ("pass", "fail", "todo", "tests")}
    f.status(f"{r['fail']} failing · reading the stack trace", 0.15)
    f.chat(f"Test 3 is failing: {r['error'] or 'see terminal'}")
    # the failing test, then the line that throws
    t_ln = find_line(tests, "without a referral code")
    await vs.point_at_line(f, tests, t_ln, "failing test", glide_ms=f.glide_ms, hold_s=0.6 * pace)

    # 1. the null-referrer bug
    ln = find_line(sig, "creditReferrer(referrer);")
    await vs.point_at_line(f, sig, ln - 1, "creditReferrer(null)", end=ln, glide_ms=f.glide_ms, hold_s=0.5 * pace)
    await vs.type_edit(f, sig, "  const referrer = db.findUserByReferralCode(referralCode);\n  creditReferrer(referrer);",
                       "  const referrer = referralCode ? db.findUserByReferralCode(referralCode) : null;\n"
                       "  if (referrer) creditReferrer(referrer);", "null-referrer fix", glide_ms=f.glide_ms)
    f.status("Patched the null-referrer bug · re-running", 0.35)
    await asyncio.sleep(0.4 * pace)
    r = await run_tests(f, product)
    f.chat(f"Null-referrer bug fixed ✓ {r['pass']}/{r['tests']} passing. Finishing the {r['todo']} TODO features.")

    # 2. the half-written features
    for i, (_needle, label, old, new) in enumerate(FEATURES):
        await vs.type_edit(f, sig, old, new, label, glide_ms=f.glide_ms)
        f.status(f"Finished {label}", 0.45 + 0.1 * i)
        await asyncio.sleep(0.4 * pace)

    # 3. turn the todo tests back on
    for todo in (', { todo: "Builder: student plan not implemented yet" }',
                 ', { todo: "Builder: session token not implemented yet" }'):
        await vs.type_edit(f, tests, todo, "", "enable test", glide_ms=f.glide_ms)
    await asyncio.sleep(0.4 * pace)
    f.status("Running the full suite", 0.85)
    r = await run_tests(f, product)
    out["tests_after"] = {k: r[k] for k in ("pass", "fail", "todo", "tests")}
    ok = r["fail"] == 0 and r["todo"] == 0 and r["pass"] == r["tests"]
    f.status(f"{r['pass']}/{r['tests']} tests passing" + (" ✓" if ok else ""), 1.0)
    f.chat(f"{r['pass']}/{r['tests']} tests passing ✓ @Deck screenshot's ready for slide 5." if ok
           else f"Tests: {r['pass']} pass, {r['fail']} fail, {r['todo']} todo")

    h.tests_png = terminal_png(r, ws / "shots" / "tests.png")
    h.tests_shot.set()
    f.done(f"{r['pass']}/{r['tests']} tests passing")


VERCEL_PROJECT = os.environ.get("HIVE_VERCEL_PROJECT", "whisk-demo")


# ---- 🔵 Web ----------------------------------------------------------------------------------------
async def deploy_live(w: TrackedBrowserAgent, site: Path, h: Handoffs, out: dict, expect: str | None = None,
                      first: bool = True) -> str | None:
    """Ships the site to Vercel for real; returns the public URL, or None (stay on the local server)."""
    w.status("Deploying to Vercel…" if first else "Redeploying to Vercel…", None)
    if first:
        w.chat("Deploying to Vercel…")
    r = await vercel_deploy(site, project=VERCEL_PROJECT, timeout=90.0, expect=expect)
    out.setdefault("deploys", []).append({"ok": r.ok, "url": r.url, "seconds": r.seconds, "error": r.error,
                                          "notes": r.notes})
    if not r.ok:
        w.chat(f"Vercel deploy didn't go through ({r.error}). Staying on the local preview.")
        return None
    out["live_url"] = r.url
    return r.url


async def code_edit(agent: Agent, h: "Handoffs", path: Path, old: str, new: str,
                    label: str | None = None) -> list[int]:
    """A site edit typed visibly into the shared VS Code window by `agent` (its ghost cursor leaves
    its own window to do it), or written straight to disk when there's no VS Code."""
    if h.vs is not None:
        try:
            return await h.vs.type_edit(agent, path, old, new, label or path.name,
                                        glide_ms=getattr(agent, "glide_ms", 450), max_type_s=1.6)
        except Exception as exc:  # never let the editor block the demo: fall back to a direct write
            log.warning("VS Code edit failed (%s); writing %s directly", exc, path.name)
    return edit(path, old, new)


async def web_flow(w: TrackedBrowserAgent, ws: Path, h: Handoffs, opts: Opts, out: dict | None = None) -> None:
    p, pace = w.page, opts.pace
    assert p
    site = ws / "site"
    html, css = site / "index.html", site / "styles.css"
    fin = (site / "FINISHED" / "index.html").read_text()
    fin_css = (site / "FINISHED" / "styles.css").read_text()

    def fin_rule(selector: str) -> str:
        return next(l for l in fin_css.splitlines() if l.startswith(selector))

    async def reload() -> None:
        await p.reload()
        await asyncio.sleep(0.35 * pace)

    # 1. hero
    w.status("Inspecting the landing page", 0.05)
    await w.point_at(p.locator(".hero-title"), style="box", label="headline overflows")
    w.chat("The hero headline runs off the screen. Fixing the layout and the copy.")
    await asyncio.sleep(0.6 * pace)
    await w.typing(*w.pos, "Matcha, delivered to your dorm.", 200)  # type: ignore[misc]
    await code_edit(w, h, css, "/* BROKEN: the headline never wraps and runs off the right edge */\n"
              ".hero { padding: 80px 40px; }\n.hero-title {\n  font-size: 96px;\n  white-space: nowrap;\n",
         fin_rule(".hero {") + "\n.hero-title {\n  font-size: clamp(44px, 7vw, 88px);\n  line-height: 1.02;\n")
    await code_edit(w, h, css, ".hero-sub { color: var(--muted); font-size: 20px; }\n.hero-ctas { margin-top: 28px; }",
         fin_rule(".hero-sub") + "\n" + fin_rule(".hero-ctas"))
    await code_edit(w, h, css, ".steps { display: grid; grid-template-columns: repeat(3, 1fr); gap: 24px; }", fin_rule(".steps"))
    old_hero = section(html.read_text(), "hero")
    new_hero = section(fin, "hero").replace('class="btn btn-ghost"', 'class="btn btn-ghost broken-offset"')
    await code_edit(w, h, html, "  <!-- TODO(web): hero is broken: headline overflows off the screen on laptops, buttons are misaligned -->\n"
               + "  " + old_hero, "  " + new_hero)
    await reload()
    await w.point_at(p.locator(".hero-title"), style="select", label="headline fixed")
    w.status("Hero fixed", 0.2)
    await asyncio.sleep(0.5 * pace)

    # 2. the knocked-off button
    await w.point_at(p.locator(".broken-offset"), style="box", label="misaligned button")
    await asyncio.sleep(0.4 * pace)
    await code_edit(w, h, css, "/* BROKEN: someone nudged this button and it ended up off to the side */\n"
              ".broken-offset { position: relative; top: 46px; left: 180px; }\n", "")
    await code_edit(w, h, html, ' broken-offset"', '"')
    await reload()
    await w.click(p.locator(".hero-ctas .btn-ghost"), "See how it works")
    w.status("Buttons re-aligned", 0.3)
    await asyncio.sleep(0.4 * pace)
    await p.evaluate("() => scrollTo(0, 0)")

    # 3. logo (Design's iPad logo isn't in this scenario; Web uses the brand mark from the finished kit)
    shutil.copy(site / "FINISHED" / "logo.svg", site / "logo.svg")
    old_header = section(html.read_text(), "header")
    await code_edit(w, h, html, old_header, section(fin, "header"))
    await code_edit(w, h, css, ".logo { height: 40px; }\n.nav a { margin-left: 24px; color: var(--ink); text-decoration: none; font-weight: 500; }",
         fin_rule(".brand") + "\n" + fin_rule(".logo") + "\n" + fin_rule(".nav nav a"))
    await reload()
    await w.point_at(p.locator("#logo"), style="circle", label="logo in")
    h.logo_png = svg_to_png(site / "logo.svg", ws / "shots" / "logo.png")
    h.logo_ready.set()
    w.status("Logo added", 0.4)

    # 4. pricing — Web trusts the old $39 note in the HTML comment, which is exactly what Checker catches
    await w.click(p.locator('nav a[href="#pricing"]'), "Pricing")
    await w.point_at(p.locator(".pricing .todo"), style="box", label="TODO: pricing")
    w.chat("Filling pricing. Using $39/mo from the old Notion note in the code.")
    await asyncio.sleep(0.5 * pace)
    await w.typing(*w.pos, "Standard $39/mo · Student $19/mo", 200)  # type: ignore[misc]
    pricing = section(fin, "pricing").replace("$29<span>", "$39<span>")
    await code_edit(w, h, html, section(html.read_text(), "pricing"), pricing)
    plans_css = "\n".join(l for l in fin_css.splitlines() if l.startswith((".plans", ".plan", ".price")))
    await code_edit(w, h, css, ".todo {\n  border: 2px dashed #d44; color: #d44; padding: 24px; border-radius: 12px;\n"
              "  font-family: ui-monospace, Menlo, monospace;\n}", plans_css)
    await reload()
    await p.locator("#pricing").scroll_into_view_if_needed()
    await w.point_at(p.locator(".plan .price").first, style="select", label="$39/mo")
    w.status("Pricing filled", 0.55)
    h.site_priced.set()

    # 5. waitlist
    await w.click(p.locator('nav a[href="#waitlist"]'), "Join")
    await w.point_at(p.locator("#waitlist-form"), style="box", label="form not wired")
    old_wait = section(html.read_text(), "waitlist")
    script = re.search(r"\s*<script>.*?</script>", fin, re.S).group(0)  # type: ignore[union-attr]
    await code_edit(w, h, html, old_wait, section(fin, "waitlist"))
    await code_edit(w, h, html, section(html.read_text(), "footer"), section(fin, "footer") + script)
    for sel in (".waitlist form", ".waitlist input", ".waitlist button"):
        old = next(l for l in css.read_text().splitlines() if l.startswith(sel))
        await code_edit(w, h, css, old, fin_rule(sel))
    await code_edit(w, h, css, fin_rule(".waitlist button"), fin_rule(".waitlist button") + "\n" + fin_rule(".status"))
    await reload()
    await p.locator("#waitlist").scroll_into_view_if_needed()
    await w.type(p.locator("#waitlist-email"), "first@ucla.edu", delay_ms=opts.type_delay * 2)
    await w.click(p.locator("#waitlist-form button"), "Join the waitlist")
    await p.wait_for_function("() => document.getElementById('waitlist-status').textContent.length > 0")
    status = await p.locator("#waitlist-status").inner_text()
    w.chat(f"Waitlist wired and tested: “{status}”")
    w.status("Waitlist works", 0.7)

    # 5b. ship it: a real production deploy, then the same click-through on the live site
    out = out if out is not None else {}
    live = await deploy_live(w, site, h, out)
    h.url = live or f"{WORLD_URL}/site/"
    h.url_ready.set()
    if live:
        w.chat(f"Live at {live} @Social @Deck")
        await p.goto(live, wait_until="domcontentloaded")
        await asyncio.sleep(0.6 * pace)
        await w.point_at(p.locator(".hero-title"), style="select", label="live on Vercel")
        await w.click(p.locator('nav a[href="#pricing"]'), "Pricing")
        await asyncio.sleep(0.4 * pace)
        await w.click(p.locator('nav a[href="#waitlist"]'), "Join")
        await w.type(p.locator("#waitlist-email"), "first@ucla.edu", delay_ms=opts.type_delay * 2)
        await w.click(p.locator("#waitlist-form button"), "Join the waitlist")
        try:
            await p.wait_for_function("() => document.getElementById('waitlist-status').textContent.length > 0",
                                      timeout=5000)
        except Exception:
            pass
        w.status("Live on Vercel", 0.75)
    else:
        w.chat(f"Site is up at {h.url} @Social @Deck")

    async def reload() -> None:  # from here on the page may be the live URL: redeploy, then load it
        if live:
            await deploy_live(w, site, h, out, expect=h.price + "<span>" if h.price else None, first=False)
            await p.goto(f"{live}/?v={int(time.time())}", wait_until="domcontentloaded")
        else:
            await p.reload()
        await asyncio.sleep(0.35 * pace)

    # 6. price decision from Checker
    if await wait_for(h.price_resolved, 60) and h.price and h.price != "$39":
        await w.click(p.locator('nav a[href="#pricing"]'), "Pricing")
        await w.point_at(p.locator(".plan .price").first, style="box", label=f"$39 → {h.price}")
        await w.typing(*w.pos, h.price + "/mo", 200)  # type: ignore[misc]
        await code_edit(w, h, html, "$39<span>", f"{h.price}<span>")
        await reload()
        await p.locator("#pricing").scroll_into_view_if_needed()
        await w.point_at(p.locator(".plan .price").first, style="select", label=f"{h.price}/mo ✓")
        w.chat(f"Pricing updated to {h.price}/mo" + (f" and redeployed to {live}." if live else "."))
        h.price_applied.set()

    # 7. screenshots for the deck (slide 7 pricing table, slide 5 landing page)
    h.pricing_png = ws / "shots" / "pricing.png"
    await p.locator("#pricing").screenshot(path=str(h.pricing_png))
    h.pricing_shot.set()
    await p.evaluate("() => scrollTo(0, 0)")
    await asyncio.sleep(0.3)
    h.site_png = ws / "shots" / "site.png"
    await p.screenshot(path=str(h.site_png))
    h.site_shot.set()
    w.status("Landing page done", 1.0)
    w.done(f"Site live at {live}" if live else "Hero, logo, pricing and waitlist finished")


# ---- 🟡 Deck ---------------------------------------------------------------------------------------
async def deck_flow(d: PitchDeck, h: Handoffs, opts: Opts, viewer_origin: tuple[float, float], out: dict) -> None:
    pace = opts.pace
    d.spawn()
    await d.move_to(viewer_origin[0] + 60, viewer_origin[1] + 50, 650, "on it")
    d.status("Filling slide 3", 0.05)
    title, bullets, src = await content.solution_slide()
    out["deck_copy"] = src
    await d.fill(2, "s3_title", title, "slide 3 · headline")
    await asyncio.sleep(0.5 * pace)
    await d.fill(2, "s3_body", bullets, "slide 3 · what Whisk does", bullets=True)

    d.status("Filling slide 7 (pricing)", 0.2)
    await asyncio.sleep(0.4 * pace)
    await d.fill(6, "s7_title", "Simple, student-friendly pricing.", "slide 7 · title")
    await d.fill(6, "s7_stat", "$29/mo", "slide 7 · price", color=MATCHA)
    await d.fill(6, "s7_body", ["Standard: $29/mo, 4 tins", "Student (.edu): $19/mo",
                                "~62% gross margin at scale (illustrative)"], "slide 7 · plans", bullets=True)
    h.deck_priced.set()

    d.status("Slide 6 needs a number", 0.35)
    d.chat("Market notes disagree: $2B (matcha only) vs $4B (matcha + specialty tea).")
    market = await ask(d, "Slide 6 market size: $4B (matcha + specialty tea) or $2B (matcha only)?", ["$4B", "$2B"], opts)
    out["market"] = market
    await d.fill(5, "s6_title", f"A {market} market, and growing.", "slide 6 · title")
    await d.fill(5, "s6_stat", market, "slide 6 · market size", color=MATCHA)
    basis = "matcha + specialty tea" if market == "$4B" else "matcha-only retail + café"
    await d.fill(5, "s6_body", f"US {basis} spend by 18–24-year-olds (illustrative; see research notes).",
                 "slide 6 · source")
    chart = market_chart(Path(d.pptx).parent.parent / "shots" / "market.png", market)
    await d.put_image(5, "s6_img_slot", chart, "slide 6 · chart")

    d.status("Waiting on the logo", 0.5)
    if await wait_for(h.logo_ready, 90) and h.logo_png:
        await d.put_image(0, "s1_img_slot", h.logo_png, "slide 1 · logo")
        await d.put_image(2, "s3_img_slot", h.logo_png, "slide 3 · logo")

    await d.fill(4, "s5_title", "Live today.", "slide 5 · title")
    d.status("Waiting on product screenshots", 0.65)
    if await wait_for(h.tests_shot, 120) and h.tests_png:
        await d.put_image(4, "s5_img_slot", h.tests_png, "slide 5 · tests passing")
    if await wait_for(h.site_shot, 120) and h.site_png:
        await d.put_image(4, "s5_img_slot_2", h.site_png, "slide 5 · landing page")

    if await wait_for(h.price_resolved, 60) and h.price and h.price != "$29":
        await d.fill(6, "s7_stat", f"{h.price}/mo", f"slide 7 · {h.price}", color=MATCHA)
        await d.fill(6, "s7_body", [f"Standard: {h.price}/mo, 4 tins", "Student (.edu): $19/mo",
                                    "~62% gross margin at scale (illustrative)"], "slide 7 · plans", bullets=True)
        h.price_applied.set()
    if await wait_for(h.pricing_shot, 90) and h.pricing_png:
        await d.put_image(6, "s7_img_slot", h.pricing_png, "slide 7 · pricing table")

    if await wait_for(h.url_ready, 60) and h.url:
        await d.fill(9, "s10_body", h.url, "slide 10 · live URL")
    d.status("Deck finished", 1.0)
    t = d.render_times
    out["deck"] = {"renders": len(t), "first_s": round(t[0], 2),
                   "avg_s": round(sum(t[1:]) / max(1, len(t) - 1), 2), "filled": sorted(d.filled)}
    d.chat(f"Deck done: {len(d.filled)} boxes filled across slides 1, 3, 5, 6, 7 and 10.")
    d.done("Slides 3, 5, 6, 7 and 10 filled")


# ---- ⚪ Checker ------------------------------------------------------------------------------------
async def checker_flow(c: Agent, web: TrackedBrowserAgent, d: PitchDeck, h: Handoffs, opts: Opts, out: dict) -> None:
    await wait_for(h.site_priced, 120)
    await wait_for(h.deck_priced, 120)
    assert web.page
    c.spawn()
    c.status("Cross-checking prices: site vs deck", 0.2)
    loc = web.page.locator(".plan .price").first
    site_price = price_of(await loc.inner_text())
    deck_price = price_of(d.read(6, "s7_stat"))
    sx, sy, sw, sh = await web.screen_rect_for(loc)
    await c.move_to(sx + sw / 2, sy + sh / 2, 600, f"site: {site_price}/mo")
    c.highlight(sx - 6, sy - 6, sw + 12, sh + 12, style="circle")
    await asyncio.sleep(0.6 * opts.pace)
    rect = await d.show(6, "s7_stat", "⚪ Checker · price")
    dx, dy = (rect[0] + rect[2] * 0.3, rect[1] + rect[3] / 2) if rect else (sx, sy + 300)
    await c.move_to(dx, dy, 600, f"deck: {deck_price}/mo")
    if rect:
        c.highlight(rect[0], rect[1], rect[2] * 0.6, rect[3], style="circle")
    out["mismatch"] = [site_price, deck_price]

    if site_price != deck_price:
        c.link((round(sx + sw / 2, 1), round(sy + sh / 2, 1)), (round(dx, 1), round(dy, 1)),
               f"{site_price} ≠ {deck_price}")
        c.chat(f"Price mismatch: the site says {site_price}/mo, the deck says {deck_price}/mo.")
        await wait_until_no_question(c.bus)
        choice = await ask(c, f"The site says {site_price}/mo but the deck says {deck_price}/mo. Which is right?",
                           [f"{deck_price}/mo", f"{site_price}/mo"], opts)
        h.price = price_of(choice)
    else:
        h.price = deck_price
    out["price"] = h.price
    h.price_resolved.set()
    if site_price != deck_price:
        fixer = "@Web" if h.price != site_price else "@Deck"
        c.chat(f"Going with {h.price}/mo. {fixer} please update.")
        c.status(f"Waiting for {fixer} to apply {h.price}", 0.6)
        await wait_for(h.price_applied, 60)

    # re-verify everywhere
    site_now = price_of(await web.page.locator(".plan .price").first.inner_text())
    deck_now = price_of(d.read(6, "s7_stat"))
    await wait_for(h.social_saved, 90)
    post_ok = bool(h.post) and (h.price in (h.post or "") or "$19" in (h.post or ""))
    out["verified"] = {"site": site_now, "deck": deck_now, "post_has_price": post_ok}
    consistent = site_now == deck_now == h.price
    c.status("Prices match everywhere ✓" if consistent else "Prices still differ", 1.0)
    c.chat(f"✓ Site {site_now}, deck {deck_now}, post {'✓' if post_ok else '✗'}. All consistent." if consistent
           else f"Still inconsistent: site {site_now}, deck {deck_now}")
    c.done("Prices consistent" if consistent else "Prices inconsistent")


# ---- 🟣 Social -------------------------------------------------------------------------------------
async def social_flow(s: TrackedBrowserAgent, ws: Path, h: Handoffs, opts: Opts, out: dict) -> None:
    p = s.page
    assert p
    s.status("Reading the rough draft", 0.05)
    await s.point_at(p.locator("#post"), style="box", label="draft.md")
    s.chat("The draft is one long run-on with no link and no price. Rewriting once Web has a URL.")
    s.status("Waiting on the live URL and the price", 0.15)
    await wait_for(h.url_ready, 120)
    await wait_for(h.price_resolved, 120)
    url, price = h.url or f"{WORLD_URL}/site/", h.price or "$29"

    post, src = await content.launch_post(url, price)
    out["post_copy"] = src
    s.status("Writing the launch post", 0.4)
    await s.type(p.locator("#post"), post, delay_ms=opts.type_delay)
    await p.evaluate("u => hive.attach(u)", f"{WORLD_URL}/site/logo.svg")
    n = await p.evaluate("() => hive.length()")
    s.chat(f"First draft is {n} characters" + (" (over the 280 limit)." if n > 280 else "."))
    out["post_first_len"] = n

    if opts.auto_human:
        async def redirect() -> None:
            await asyncio.sleep(1.5)
            await s.bus._command({"cmd": "say", "args": {"text": "@Social make it shorter"}})
        asyncio.create_task(redirect())
    try:
        msg = await asyncio.wait_for(s.inbox.get(), opts.redirect_wait)
    except asyncio.TimeoutError:
        msg = None
    if msg or n > 280:
        request = msg["text"] if msg else "it's over 280 characters, trim it"
        s.chat(f"Got it: “{request}”" if msg else "Trimming it to fit.")
        out["redirect"] = request
        short, _ = await content.shorten_post(post, url, request)
        await p.evaluate("() => hive.clear()")
        await s.type(p.locator("#post"), short, delay_ms=opts.type_delay)
        post = short
    await s.click(p.locator("#save"), "Save draft")
    h.post = await p.evaluate("() => window.__saved")
    (ws / "social" / "post.md").write_text((h.post or post) + "\n")
    out["post"] = h.post
    h.social_saved.set()
    if os.environ.get("HIVE_INSTAGRAM", "1") == "0":
        s.status(f"Post drafted ({len(h.post or '')} chars), waiting for your OK", 1.0)
        s.done("Launch post drafted (not posted)")
        return
    await instagram_flow(s, ws, h, opts, out)


async def instagram_flow(s: TrackedBrowserAgent, ws: Path, h: Handoffs, opts: Opts, out: dict) -> None:
    """Real post on Instagram (agents' HiveAgentsChrome profile), only after an explicit human YES.
    The composer window closes first so the Instagram window takes the same grid cell."""
    from ..apps.instagram import InstagramError, InstagramSession, clean_caption, make_square, gemini_square

    rect = None
    try:
        b = (await s.cdp.send("Browser.getWindowBounds", {"windowId": s.window_id}))["bounds"]
        rect = Rect(b["left"], b["top"], b["width"], b["height"])
    except Exception:
        pass
    caption = clean_caption(h.post or "")
    # A different graphic every run (Gemini), falling back to the drawn square.
    image = (await gemini_square(ws / "social" / "launch.png", price=h.price or "$29")
             or make_square(ws / "social" / "launch.png", price=h.price or "$29"))
    out["instagram"] = {"caption": caption, "image": str(image)}
    await s.close()                      # the composer window; the Social cursor moves to Instagram
    s.status("Opening Instagram", 0.5)
    ig = None
    try:
        async with async_playwright() as pw:
            ig = await InstagramSession.open(pw, s, rect)
            await ig.draft(image, caption)
            out["instagram"]["stage"] = "caption"
            autopost = os.environ.get("HIVE_INSTAGRAM_AUTOPOST", "") == "1"
            if autopost:
                # Opt-in (e.g. a private demo account): share without asking.
                choice, approved = "post", True
            else:
                s.chat("Instagram post is ready to share. Waiting for your OK.")
            if opts.auto_human and not autopost:  # rehearsals never publish
                async def auto() -> None:
                    await asyncio.sleep(2.0)
                    s.answer("Don't post")
                asyncio.create_task(auto())
            if not autopost:
                try:
                    choice = await s.ask_human("Post this to Instagram?", ["Post", "Don't post"],
                                               timeout=90, kind="post")
                except asyncio.TimeoutError:
                    choice = None
                approved = (not opts.auto_human and
                            str(choice or "").strip().lower() in ("yes", "y", "post", "approve", "share"))
            out["instagram"]["approved"] = approved
            if approved:
                url = await ig.share()
                out["instagram_url"] = url
                s.chat(f"Posted to Instagram: {url}" if url else "Posted to Instagram.")
                s.status("Posted to Instagram", 1.0)
                s.done("Launch post is live on Instagram")
            else:
                await ig.discard()
                s.chat("Not posting. I discarded the Instagram draft.")
                s.status("Instagram draft discarded (not posted)", 1.0)
                s.done("Launch post drafted (not posted)")
            await asyncio.sleep(2.0)
            await ig.close()
    except InstagramError as exc:
        out["instagram"]["error"] = str(exc)
        s.chat(f"Couldn't post to Instagram: {exc}")
        s.status("Post drafted, Instagram unavailable", 1.0)
        s.done("Launch post drafted (not posted)")
        if ig:
            try:
                await ig.close()
            except Exception:
                pass


# ---- countdown + orchestration --------------------------------------------------------------------
async def countdown(bus: Bus, opts: Opts, stop: asyncio.Event, state: dict) -> None:
    speed = 300 / opts.target_s
    t0 = time.monotonic()
    while not stop.is_set():
        left = max(0, int(300 - (time.monotonic() - t0) * speed))
        state["left"] = left
        bus.emit(None, "countdown", {"seconds_left": left})
        try:
            await asyncio.wait_for(stop.wait(), 1.0)
        except asyncio.TimeoutError:
            pass


async def screen_area(browser: Browser) -> tuple[int, int, int, int]:
    ctx = await browser.new_context()
    page = await ctx.new_page()
    s = await page.evaluate("() => [screen.availLeft || 0, screen.availTop || 0, screen.availWidth, screen.availHeight]")
    await ctx.close()
    return tuple(int(v) for v in s)  # type: ignore[return-value]


async def run(bus: Bus, render_dir: Path, fast: bool = False, auto_human: bool = False,
              answer_timeout: float | None = None, keep_open: float = 4.0, **_: Any) -> dict:
    opts = (Opts(pace=1.0, dwell=1.2, glide_ms=400, type_delay=18, redirect_wait=5.0, target_s=110.0)
            if fast else Opts())
    opts.auto_human = auto_human
    if answer_timeout is not None:
        opts.answer_timeout = answer_timeout
    t_start = time.monotonic()
    ws = make_workspace()
    world = start_world_server(ws)
    out: dict[str, Any] = {"workspace": str(ws), "fast": fast}
    h = Handoffs()
    stop, clock = asyncio.Event(), {"left": 300}

    try:
        async with async_playwright() as pw:
            browser = await launch_chrome(pw)
            # Four equal, non-overlapping cells: Fixer | Web on top, Deck Viewer | Social below.
            cells = grid(4, await usable_area())
            cell = lambda col, row: cells[row * 2 + col]  # noqa: E731
            place_native(bus, "deck", cell(0, 1))

            # Fixer works in a real VS Code window on the workspace copy; Web and Social in Chrome.
            vs = VSCode()
            await vs.open(ws, cell(0, 0))
            fixer = EditorAgent(bus, "fixer", vs, opts.dwell, opts.glide_ms)
            h.vs = vs
            web, social = (TrackedBrowserAgent(bus, a, opts.dwell, opts.glide_ms) for a in ("web", "social"))
            await web.open(browser, cell(1, 0), f"{WORLD_URL}/site/index.html")
            await social.open(browser, cell(1, 1), f"{WORLD_URL}/hive/composer.html")
            out["layout_warnings"] = await check_bounds([web, social])
            vx, vy, vw, vh = await vs.frame()
            want = cell(0, 0)
            if (vx, vy, vw, vh) != (want.left, want.top, want.width, want.height):
                out["layout_warnings"].append(f"VS Code at {(vx, vy, vw, vh)}, wanted {want}")
            deck = PitchDeck(bus, ws / "deck" / "pitch.pptx", render_dir)
            deck.step_pause = 0.8 * opts.dwell
            checker = Agent(bus, "checker")

            # Deck Viewer: the Mac app's native one shows itself on deck_loaded and reports deck_viewer.
            # If none reports within ~2s, open the stopgap Chrome viewer in the bottom-left cell.
            await deck.load()
            vctx = None
            for _ in range(20):
                if bus.deck_viewer:
                    break
                await asyncio.sleep(0.1)
            if bus.deck_viewer:
                v = bus.deck_viewer
                viewer_origin = (v["x"], v["y"])
                out["deck_viewer"] = "native"
            else:
                vctx, vpage = await open_window(browser, cell(0, 1), VIEWER_URL)

                async def mapper(fx: float, fy: float, fw: float, fh: float):
                    x, y, w, hh = await page_screen_rect(vpage, vpage.locator("#stage"))
                    return x + fx * w, y + fy * hh, fw * w, fh * hh

                deck.screen_mapper = mapper
                await asyncio.sleep(0.8)  # the viewer connects to the bus, then gets the deck again
                deck.emit("deck_loaded", slides=len(Presentation(deck.pptx).slides), base=deck.base_url,
                          version=deck.version)
                viewer_origin = (await page_screen_rect(vpage, vpage.locator("#stage")))[:2]
                out["deck_viewer"] = "chrome"

            # Conductor: plan → one chat line per agent
            bus.emit(None, "chat", {"text": "🐝 Conductor: pitch in 5 minutes. Splitting the work…"})
            plan = await conductor.plan_async(REQUEST, "pitch_in_5", ["fixer", "web", "deck", "social", "checker"])
            out["plan_source"] = plan.get("source")
            clock_task = asyncio.create_task(countdown(bus, opts, stop, clock))
            for a in (fixer, web, deck, social, checker):
                tasks = plan["agents"].get(a.id) or conductor.canned("pitch_in_5")["agents"][a.id]
                a.chat("My plan: " + "; ".join(tasks))

            await asyncio.gather(fixer.enter(0.0), web.enter(0.25), social.enter(0.5))
            results = await asyncio.gather(
                fixer_flow(fixer, ws, h, opts, out),
                web_flow(web, ws, h, opts, out),
                deck_flow(deck, h, opts, viewer_origin, out),
                social_flow(social, ws, h, opts, out),
                checker_flow(checker, web, deck, h, opts, out),
                return_exceptions=True,
            )
            errors = [repr(r) for r in results if isinstance(r, BaseException)]
            stop.set()
            await clock_task
            elapsed = time.monotonic() - t_start

            errs = fixer.click_errors + web.click_errors + social.click_errors
            out.update({
                "elapsed_s": round(elapsed, 1),
                "countdown_left_s": clock["left"],
                "clicks": {a.id: len(a.click_errors) for a in (fixer, web, social)},
                "click_error_max_pt": max(errs) if errs else None,
                "click_errors_pt": {a.id: a.click_errors for a in (fixer, web, social)},
                "errors": errors,
            })
            ta = out.get("tests_after", {})
            mins, secs = divmod(clock["left"], 60)
            bus.emit(None, "swarm_summary", {"title": f"Pitch ready with {mins}:{secs:02d} to spare", "lines": [
                f"🔴 Fixer: {ta.get('pass', '?')}/{ta.get('tests', '?')} tests passing",
                ("🔵 Web: live at " + out["live_url"]) if out.get("live_url") else "🔵 Web: hero, logo, pricing and waitlist fixed",
                f"🟡 Deck: {len(deck.filled)} boxes filled on slides 1, 3, 5, 6, 7, 10",
                ("🟣 Social: launch post live on Instagram" if out.get("instagram_url") or
                 (out.get("instagram") or {}).get("approved") else
                 f"🟣 Social: launch post drafted ({len(h.post or '')} chars), not posted"),
                f"⚪ Checker: price {h.price or '?'}/mo matches everywhere",
            ] + ([f"⚠️ {len(errors)} agent error(s)"] if errors else [])})
            await asyncio.sleep(keep_open)
            for a in (fixer, web, social):
                try:
                    await a.close()
                except Exception:
                    pass  # Social's Instagram window is already closed
            await vs.close()
            if vctx:
                await vctx.close()
            await browser.close()
    finally:
        stop.set()
        world.shutdown()
    return out
