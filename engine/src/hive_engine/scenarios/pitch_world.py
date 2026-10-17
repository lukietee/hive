"""The pitch_in_5 workspace: a fresh temp COPY of demo-world plus a small local server.

The repo's demo-world/ is never modified. Every run copies it to a temp dir; agents edit the copy.

  http://127.0.0.1:8767/site/...      → <copy>/site/            (🔵 Web's landing page)
  http://127.0.0.1:8767/hive/...      → scenarios/pitch_pages/  (🔴 Fixer's editor, 🟣 Social's composer)
  GET  /api/file?path=product/src/signup.js → file text (inside the copy only)
  POST /api/test                       → runs `node --test` in <copy>/product, returns output + counts
"""

from __future__ import annotations

import difflib
import json
import re
import shutil
import subprocess
import tempfile
import threading
import time
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

DEMO_WORLD = Path(__file__).resolve().parents[4] / "demo-world"
PAGES = Path(__file__).resolve().parent / "pitch_pages"
WORLD_PORT = 8767
WORLD_URL = f"http://127.0.0.1:{WORLD_PORT}"


def make_workspace() -> Path:
    """Copies demo-world (minus the rehearsal-only SOLUTION.md) into a fresh temp dir."""
    root = Path(tempfile.mkdtemp(prefix="hive_pitch_"))
    ws = root / "whisk"
    shutil.copytree(DEMO_WORLD, ws, ignore=shutil.ignore_patterns("SOLUTION.md", "node_modules", ".DS_Store"))
    (ws / "shots").mkdir()
    return ws


# ---- node tests -------------------------------------------------------------------------------
def run_node_tests(product: Path) -> dict:
    t0 = time.perf_counter()
    proc = subprocess.run(["node", "--test"], cwd=product, capture_output=True, text=True, timeout=60)
    out = proc.stdout + proc.stderr
    counts = {k: int(v) for k, v in re.findall(r"^ℹ (pass|fail|todo|tests) (\d+)", out, re.M)}
    # Keep it readable on screen: the per-test lines, the first error, and the summary.
    lines = out.splitlines()
    short = [l for l in lines if re.match(r"^(✔|✖|⚠|ℹ (tests|pass|fail|todo))", l)]
    err = next((l.strip() for l in lines if "Error:" in l), None)
    if err and counts.get("fail"):
        short.insert(0, err)
    seen, uniq = set(), []
    for l in short:  # node repeats failing tests in a trailer
        if l not in seen:
            seen.add(l)
            uniq.append(l)
    return {"output": "\n".join(uniq), "pass": counts.get("pass", 0), "fail": counts.get("fail", 0),
            "todo": counts.get("todo", 0), "tests": counts.get("tests", 0), "error": err,
            "ms": int((time.perf_counter() - t0) * 1000)}


# ---- edits ------------------------------------------------------------------------------------
def edit(path: Path, old: str, new: str) -> list[int]:
    """Exact replace; returns the 1-based line numbers that changed in the NEW file (for highlights)."""
    text = path.read_text()
    if old not in text:
        raise ValueError(f"{path.name}: expected text not found: {old[:60]!r}")
    updated = text.replace(old, new, 1)
    path.write_text(updated)
    return changed_lines(text, updated)


def changed_lines(a: str, b: str) -> list[int]:
    out: list[int] = []
    sm = difflib.SequenceMatcher(a=a.splitlines(), b=b.splitlines())
    for tag, _i1, _i2, j1, j2 in sm.get_opcodes():
        if tag in ("replace", "insert"):
            out.extend(range(j1 + 1, j2 + 1))
    return out


def find_line(path: Path, needle: str) -> int:
    for i, line in enumerate(path.read_text().splitlines(), 1):
        if needle in line:
            return i
    raise ValueError(f"{needle!r} not in {path.name}")


def section(html: str, sid: str) -> str:
    """The <section ... id="sid">…</section> block (or <header>/<footer> by tag name)."""
    if sid in ("header", "footer"):
        m = re.search(rf"<{sid}\b.*?</{sid}>", html, re.S)
    else:
        m = re.search(rf'<section[^>]*id="{sid}".*?</section>', html, re.S)
    if not m:
        raise ValueError(f"section {sid!r} not found")
    return m.group(0)


# ---- server -----------------------------------------------------------------------------------
class _Handler(SimpleHTTPRequestHandler):
    workspace: Path = Path(".")
    waitlist: list[str] = []

    def translate_path(self, path: str) -> str:
        clean = urlparse(path).path
        for prefix, root in (("/site", self.workspace / "site"), ("/hive", PAGES),
                             ("/shots", self.workspace / "shots")):
            if clean == prefix or clean.startswith(prefix + "/"):
                rel = clean[len(prefix):].lstrip("/") or "index.html"
                target = (root / rel).resolve()
                if target == root.resolve() or root.resolve() in target.parents:
                    return str(target)
        return str(self.workspace / "__nope__")

    def _json(self, code: int, obj: dict) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("content-type", "application/json")
        self.send_header("content-length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        u = urlparse(self.path)
        if u.path == "/api/file":
            rel = parse_qs(u.query).get("path", [""])[0]
            target = (self.workspace / rel).resolve()
            if self.workspace.resolve() not in target.parents or not target.is_file():
                return self._json(404, {"error": "not found"})
            return self._json(200, {"path": rel, "text": target.read_text()})
        return super().do_GET()

    def do_POST(self) -> None:  # noqa: N802
        u = urlparse(self.path)
        if u.path == "/api/test":
            return self._json(200, run_node_tests(self.workspace / "product"))
        if u.path == "/api/waitlist":
            n = int(self.headers.get("content-length") or 0)
            email = json.loads(self.rfile.read(n) or b"{}").get("email", "")
            self.waitlist.append(email)
            return self._json(200, {"ok": True, "count": len(self.waitlist)})
        return self._json(404, {"error": "not found"})

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *args) -> None:
        pass


def start_world_server(workspace: Path, port: int = WORLD_PORT) -> ThreadingHTTPServer:
    handler = type("WorldHandler", (_Handler,), {"workspace": workspace, "waitlist": []})
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def svg_to_png(svg: Path, png: Path, size: int = 512) -> Path:
    import pymupdf as fitz

    with fitz.open(svg) as doc:
        page = doc[0]
        zoom = size / max(page.rect.width, page.rect.height)
        page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=True).save(png)
    return png
