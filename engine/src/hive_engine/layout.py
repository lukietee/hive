"""Screen layout: an even grid of equal windows that fills the usable screen with no overlap.

Every scenario places its windows through `grid()`: Chrome windows (agents), plus the Mac app's
Deck Viewer and Call window via the `window_place` event. Coordinates are global screen points,
top-left origin (the contract's space). The usable area comes from Chrome's `screen.avail*`
(the visible frame: below the menu bar, above the Dock).
"""

from __future__ import annotations

import asyncio
import json
import math

from .browser_agent import Rect

GAP = 8       # between windows
MARGIN = 8    # around the edge of the usable area
MIN_W = 420   # narrower and websites switch to cramped mobile layouts
MIN_H = 280   # shorter and a window shows little more than its toolbar


_JXA = ('ObjC.import("AppKit"); const s = $.NSScreen.screens.objectAtIndex(0);'
        ' const f = s.frame, v = s.visibleFrame;'
        ' JSON.stringify([f.size.height, v.origin.x, v.origin.y, v.size.width, v.size.height])')


async def usable_area() -> tuple[float, float, float, float]:
    """The main display's visible frame (below the menu bar, above the Dock) as (left, top, w, h)
    in global top-left points. Asks macOS directly: Chrome's screen.avail* can report a default
    1280×720 for automation contexts."""
    try:
        proc = await asyncio.create_subprocess_exec("osascript", "-l", "JavaScript", "-e", _JXA,
                                                    stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        out, _ = await asyncio.wait_for(proc.communicate(), 5)
        full_h, vx, vy, vw, vh = json.loads(out.decode())
        return float(vx), float(full_h - (vy + vh)), float(vw), float(vh)
    except Exception:
        return 0.0, 33.0, 1512.0, 851.0   # 14" MacBook Pro default (menu bar 33, Dock visible)


def shape(n: int, width: float, height: float) -> tuple[int, int]:
    """(cols, rows) for n windows: no more empty cells than needed, cells close to a landscape 3:2."""
    if n <= 1:
        return 1, 1
    best: tuple[float, int, int] | None = None
    for cols in range(1, n + 1):
        rows = math.ceil(n / cols)
        if (cols - 1) * rows >= n:      # a whole column would be empty
            continue
        cw, ch = width / cols, height / rows
        empty = cols * rows - n
        score = 1.2 * empty + abs(math.log((cw / ch) / 1.5)) + (10 if cw < MIN_W else 0) + (10 if ch < MIN_H else 0)
        if best is None or score < best[0]:
            best = (score, cols, rows)
    assert best
    return best[1], best[2]


def grid(n: int, area: tuple[float, float, float, float], gap: int = GAP, margin: int = MARGIN) -> list[Rect]:
    """n equal, non-overlapping rects tiling `area` (left, top, width, height), row by row.
    A partial last row is centered, its windows the same size as the others."""
    left, top, width, height = area
    left, top, width, height = left + margin, top + margin, width - 2 * margin, height - 2 * margin
    cols, rows = shape(n, width, height)
    cw = (width - gap * (cols - 1)) / cols
    ch = (height - gap * (rows - 1)) / rows
    rects: list[Rect] = []
    for i in range(n):
        r, c = divmod(i, cols)
        in_row = min(cols, n - r * cols)
        offset = (cols - in_row) * (cw + gap) / 2   # center a partial last row
        rects.append(Rect(int(round(left + offset + c * (cw + gap))), int(round(top + r * (ch + gap))),
                          int(cw), int(ch)))
    return rects


def place_native(bus, window: str, rect: Rect) -> None:
    """Asks the Mac app to put one of its windows ("deck", "call") in a layout cell."""
    bus.emit(None, "window_place", {"window": window, "x": rect.left, "y": rect.top,
                                    "w": rect.width, "h": rect.height})


async def check_bounds(agents) -> list[str]:
    """Reads back each Chrome window's real bounds; returns warnings for any that overlap."""
    boxes = []
    for a in agents:
        try:
            b = (await a.cdp.send("Browser.getWindowBounds", {"windowId": a.window_id}))["bounds"]
            boxes.append((a.id, b["left"], b["top"], b["width"], b["height"]))
        except Exception:
            pass
    warn = []
    for i, (ia, x1, y1, w1, h1) in enumerate(boxes):
        for ib, x2, y2, w2, h2 in boxes[i + 1:]:
            if x1 < x2 + w2 and x2 < x1 + w1 and y1 < y2 + h2 and y2 < y1 + h1:
                warn.append(f"{ia} overlaps {ib}")
    return warn


__all__ = ["grid", "shape", "usable_area", "place_native", "check_bounds", "GAP", "MARGIN"]
