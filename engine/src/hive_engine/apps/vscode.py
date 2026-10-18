"""Real Visual Studio Code for the agents, with ghost-cursor sync.

Each run opens its workspace in a separate, isolated VS Code instance (its own --user-data-dir and
--extensions-dir under ~/Library/Application Support/HiveVSCode), so the user's own VS Code setup,
windows and extensions are never touched, and editor metrics are known (font, line height, no
minimap / sticky scroll / sidebar). A tiny bundled extension (`vscode_ext/`) serves a localhost
HTTP bridge: open a file with a line scrolled to a known spot, select lines, type an edit visibly
character by character, run a command in the integrated terminal, close the window.

    vs = VSCode()
    await vs.open(workspace_dir, Rect(...))
    pt = await vs.line_point(path, 42)           # screen point (global top-left) of line 42
    await vs.type_edit(agent, path, old, new)     # cursor glides to the line, then the edit is typed
    await vs.run_in_terminal(agent, "npm test")
    await vs.close()
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import signal
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from ..browser_agent import Rect

log = logging.getLogger("hive.vscode")

CODE_CLI = "/Applications/Visual Studio Code.app/Contents/Resources/app/bin/code"
HOME = Path.home() / "Library" / "Application Support" / "HiveVSCode"
USER_DIR = HOME / "user-data"
EXT_DIR = HOME / "extensions"
EXT_SRC = Path(__file__).resolve().parent / "vscode_ext"
EXT_NAME = "hive.hive-bridge-0.1.0"
PORT = int(os.environ.get("HIVE_VSCODE_PORT", "8774"))

# Editor metrics, fixed by SETTINGS below (window zoom 0 → 1 CSS px = 1 pt).
FONT_SIZE = 13
LINE_H = 20
CHAR_W = 7.83           # Menlo 13px advance width
TITLE_H = 35            # custom title bar
TABS_H = 35             # editor tab strip (breadcrumbs off)
GUTTER_W = 46           # line numbers + decorations, before column 0 (glyph margin & folding off)
ABOVE = 3               # lines kept above a revealed line

SETTINGS: dict[str, Any] = {
    "hive.port": PORT,
    "window.zoomLevel": 0,
    "window.titleBarStyle": "custom",
    "window.commandCenter": False,
    "window.restoreWindows": "none",
    "window.newWindowDimensions": "default",
    "workbench.startupEditor": "none",
    "workbench.tips.enabled": False,
    "workbench.activityBar.location": "hidden",
    "workbench.layoutControl.enabled": False,
    "workbench.welcomePage.walkthroughs.openOnInstall": False,
    "workbench.editor.empty.hint": "hidden",
    "workbench.colorTheme": "Default Dark Modern",
    "editor.fontFamily": "Menlo, Monaco, 'Courier New', monospace",
    "editor.fontSize": FONT_SIZE,
    "editor.lineHeight": LINE_H,
    "editor.minimap.enabled": False,
    "editor.stickyScroll.enabled": False,
    "editor.glyphMargin": False,
    "editor.folding": False,
    "editor.smoothScrolling": False,
    "editor.cursorSmoothCaretAnimation": "off",
    "editor.renderLineHighlight": "all",
    "editor.inlineSuggest.enabled": False,
    "editor.quickSuggestions": {"other": False, "comments": False, "strings": False},
    "editor.suggestOnTriggerCharacters": False,
    "editor.parameterHints.enabled": False,
    "editor.hover.enabled": False,
    "editor.lightbulb.enabled": "off",
    "editor.codeLens": False,
    "editor.inlayHints.enabled": "off",
    "editor.accessibilitySupport": "off",
    "breadcrumbs.enabled": False,
    "security.workspace.trust.enabled": False,
    "telemetry.telemetryLevel": "off",
    "update.mode": "none",
    "extensions.autoUpdate": False,
    "extensions.autoCheckUpdates": False,
    "extensions.ignoreRecommendations": True,
    "git.enabled": False,
    "git.openRepositoryInParentFolders": "never",
    "chat.disableAIFeatures": True,
    "chat.commandCenter.enabled": False,
    "terminal.integrated.fontSize": 12,
    "terminal.integrated.enablePersistentSessions": False,
    "terminal.integrated.showExitAlert": False,
    "files.autoSave": "off",
    "files.hotExit": "off",
}


@dataclass
class LineView:
    top: int        # first visible line (1-based)
    bottom: int


async def osa(script: str, timeout: float = 10.0) -> str:
    proc = await asyncio.create_subprocess_exec("osascript", "-e", script, stdout=asyncio.subprocess.PIPE,
                                                stderr=asyncio.subprocess.PIPE)
    out, err = await asyncio.wait_for(proc.communicate(), timeout)
    if proc.returncode:
        raise RuntimeError(err.decode().strip())
    return out.decode().strip()


def _install() -> None:
    """Writes the isolated profile's settings and the bridge extension (idempotent)."""
    (USER_DIR / "User").mkdir(parents=True, exist_ok=True)
    (USER_DIR / "User" / "settings.json").write_text(json.dumps(SETTINGS, indent=2))
    dst = EXT_DIR / EXT_NAME
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(EXT_SRC, dst)
    # VS Code ≥1.7x lists installed extensions in extensions.json; register ours there too.
    manifest = EXT_DIR / "extensions.json"
    try:
        entries = json.loads(manifest.read_text()) if manifest.exists() else []
    except Exception:
        entries = []
    entries = [e for e in entries if e.get("identifier", {}).get("id") != "hive.hive-bridge"]
    entries.append({"identifier": {"id": "hive.hive-bridge"}, "version": "0.1.0",
                    "location": {"$mid": 1, "path": str(dst), "scheme": "file"},
                    "relativeLocation": EXT_NAME, "metadata": {"installedTimestamp": 0, "source": "vsix"}})
    manifest.write_text(json.dumps(entries))


class VSCode:
    """One isolated VS Code window on a workspace folder."""

    def __init__(self) -> None:
        self.folder: Path | None = None
        self.pid: int | None = None
        self.rect: Rect | None = None
        self._http = httpx.AsyncClient(base_url=f"http://127.0.0.1:{PORT}", timeout=30)

    # ---- lifecycle -------------------------------------------------------------------------------
    async def open(self, folder: Path, rect: Rect | None = None, timeout: float = 45.0) -> None:
        self.folder = Path(folder).resolve()
        await self._kill_stale()
        _install()
        await asyncio.create_subprocess_exec(
            CODE_CLI, "--user-data-dir", str(USER_DIR), "--extensions-dir", str(EXT_DIR),
            "--disable-workspace-trust", "--skip-welcome", "--skip-release-notes", "-n", str(self.folder),
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        loop = asyncio.get_running_loop()
        end = loop.time() + timeout
        while loop.time() < end:
            try:
                r = await self._http.get("/ping")
                if r.status_code == 200 and Path(r.json().get("folder") or "/").resolve() == self.folder:
                    break
            except Exception:
                pass
            await asyncio.sleep(0.4)
        else:
            raise RuntimeError("VS Code bridge didn't come up (is the extension loading?)")
        self.pid = await self._main_pid()
        await self.command("workbench.action.closeSidebar")
        await self.command("workbench.action.closePanel")
        await self.command("workbench.action.closeAllEditors")
        if rect:
            await self.place(rect)

    async def close(self) -> None:
        try:
            await self._http.post("/close")
        except Exception:
            pass
        await asyncio.sleep(1.5)
        await self._kill_stale()
        await self._http.aclose()

    async def _pids(self) -> list[int]:
        proc = await asyncio.create_subprocess_exec("pgrep", "-f", f"user-data-dir.{{0,2}}{USER_DIR}",
                                                    stdout=asyncio.subprocess.PIPE)
        out, _ = await proc.communicate()
        return [int(p) for p in out.split()]

    async def _main_pid(self) -> int | None:
        """The isolated instance's main Electron process (helpers carry --type=…)."""
        pids = await self._pids()
        for pid in pids:
            ps = await asyncio.create_subprocess_exec("ps", "-o", "command=", "-p", str(pid),
                                                      stdout=asyncio.subprocess.PIPE)
            cmd, _ = await ps.communicate()
            if b"--type=" not in cmd and b"Contents/MacOS/" in cmd:
                return pid
        return None

    async def _kill_stale(self) -> None:
        """An isolated instance left over from an earlier run (never the user's own VS Code)."""
        pids = await self._pids()
        for p in pids:
            try:
                os.kill(p, signal.SIGTERM)
            except ProcessLookupError:
                pass
        if pids:
            await asyncio.sleep(1.0)

    # ---- window -------------------------------------------------------------------------------
    def _proc(self) -> str:
        assert self.pid, "VS Code isn't open"
        return f'(first process whose unix id is {self.pid})'

    async def place(self, rect: Rect) -> None:
        self.rect = rect
        for _ in range(3):
            await osa(f'tell application "System Events" to tell window 1 of {self._proc()}\n'
                      f'  set position to {{{rect.left}, {rect.top}}}\n'
                      f'  set size to {{{rect.width}, {rect.height}}}\nend tell')
            await asyncio.sleep(0.3)
            if await self.frame() == (rect.left, rect.top, rect.width, rect.height):
                return

    async def frame(self) -> tuple[int, int, int, int]:
        out = await osa(f'tell application "System Events" to tell window 1 of {self._proc()} to '
                        f'get {{position, size}}')
        x, y, w, h = (int(float(v)) for v in out.replace(" ", "").split(","))
        return x, y, w, h

    async def front(self) -> None:
        await osa(f'tell application "System Events" to set frontmost of {self._proc()} to true')

    # ---- bridge -------------------------------------------------------------------------------
    async def call(self, route: str, **body: Any) -> dict:
        r = await (self._http.post(route, json=body) if body or route != "/state" else self._http.get(route))
        data = r.json()
        if r.status_code != 200:
            raise RuntimeError(f"VS Code {route}: {data.get('error')}")
        return data

    async def command(self, cid: str, *args: Any) -> Any:
        return (await self.call("/command", id=cid, args=list(args))).get("result")

    async def reveal(self, path: Path, line: int) -> LineView:
        s = await self.call("/open", path=str(path), line=line, above=ABOVE)
        return LineView(s["top"] or 1, s["bottom"] or 1)

    async def select(self, path: Path, start: int, end: int | None = None) -> LineView:
        s = await self.call("/select", path=str(path), start=start, end=end or start, above=ABOVE)
        return LineView(s["top"] or 1, s["bottom"] or 1)

    # ---- geometry -----------------------------------------------------------------------------
    async def line_point(self, line: int, view: LineView, col: int = 0) -> tuple[float, float]:
        """Screen point (global top-left) of `line`/`col` in the visible editor."""
        x, y, _w, _h = await self.frame()
        return (x + GUTTER_W + col * CHAR_W + 4,
                y + TITLE_H + TABS_H + (line - view.top + 0.5) * LINE_H)

    # ---- agent helpers ------------------------------------------------------------------------
    async def point_at_line(self, agent, path: Path, line: int, label: str | None = None, col: int = 0,
                            end: int | None = None, glide_ms: int = 450) -> tuple[float, float]:
        """Scroll `line` into view, select it (or line..end), glide the ghost cursor there and click."""
        view = await self.select(path, line, end)
        x, y = await self.line_point(line, view, col)
        await agent.click_at(x, y, glide_ms, label)
        return x, y

    async def type_edit(self, agent, path: Path, old: str, new: str, label: str | None = None,
                        glide_ms: int = 450, chunk: int = 3, delay_ms: int = 16) -> list[int]:
        """Glide to the code being changed, then replace it in the editor, typing the new text
        visibly, and save. Returns the changed line numbers (1-based) in the new file."""
        text = Path(path).read_text()
        at = text.find(old)
        if at < 0:
            raise ValueError(f"{Path(path).name}: expected text not found: {old[:60]!r}")
        line = text.count("\n", 0, at) + 1
        col = at - (text.rfind("\n", 0, at) + 1)
        view = await self.select(path, line, line + old.count("\n"))
        x, y = await self.line_point(line, view, col)
        await agent.click_at(x, y, glide_ms, label)
        agent.emit("typing", x=round(x, 1), y=round(y, 1), text=new.strip().splitlines()[-1][:48] if new.strip() else "…")
        r = await self.call("/type", path=str(path), old=old, new=new, above=ABOVE, chunk=chunk,
                            delayMs=delay_ms, selectMs=350)
        return list(range(r["startLine"], r["endLine"] + 1))

    async def run_in_terminal(self, agent, cmd: str, cwd: Path | None = None, label: str | None = None,
                              glide_ms: int = 450) -> None:
        """Open the integrated terminal (bottom panel) and type `cmd` into it visibly."""
        await self.call("/terminal", name="Tests", cmd=cmd, cwd=str(cwd) if cwd else None, clear=True)
        await asyncio.sleep(0.5)
        x, y, w, h = await self.frame()
        tx, ty = x + 70, y + h - 70  # the panel's prompt area, near the bottom of the window
        await agent.click_at(tx, ty, glide_ms, label or cmd)
        agent.emit("typing", x=round(tx, 1), y=round(ty, 1), text=f"$ {cmd}")

    async def hide_terminal(self) -> None:
        await self.call("/hideTerminal")


__all__ = ["VSCode", "LineView", "CODE_CLI", "PORT"]
