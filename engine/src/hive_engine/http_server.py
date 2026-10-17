"""Static file server on http://127.0.0.1:8766 for the stopgap Deck Viewer, test pages and renders.

  /viewer/...    → engine/viewer/
  /test/...      → engine/testpages/
  /render/...    → the deck render directory (slide-N.png)
"""

from __future__ import annotations

import functools
import threading
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parents[2]
HTTP_PORT = 8766


class _Handler(SimpleHTTPRequestHandler):
    routes: dict[str, Path] = {}

    def translate_path(self, path: str) -> str:
        clean = path.split("?", 1)[0].split("#", 1)[0]
        for prefix, root in self.routes.items():
            if clean.startswith(prefix + "/") or clean == prefix:
                rel = clean[len(prefix):].lstrip("/") or "index.html"
                target = (root / rel).resolve()
                if root.resolve() in target.parents or target == root.resolve():
                    return str(target)
        return str(ENGINE_DIR / "__nope__")

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-store")
        super().end_headers()

    def log_message(self, *args) -> None:  # quiet
        pass


def start_http(render_dir: Path, port: int = HTTP_PORT) -> ThreadingHTTPServer:
    render_dir.mkdir(parents=True, exist_ok=True)
    handler = functools.partial(_Handler)
    _Handler.routes = {
        "/viewer": ENGINE_DIR / "viewer",
        "/test": ENGINE_DIR / "testpages",
        "/render": render_dir,
    }
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server
