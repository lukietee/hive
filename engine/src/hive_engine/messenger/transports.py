"""Where the thread's texts actually go.

FakeTransport   — a local "Messages" page + WebSocket at http://127.0.0.1:8769/ (no keys; for testing).
PhotonTransport — Photon's REST API (iMessage shared line): send via POST /messages, receive by polling
                  GET /messages?direction=received. No public URL or webhook needed on the Mac.

Both expose: start(), close(), send_text(text), send_image(path_or_url, caption), and call
on_text(text) for each inbound text from the owner.
"""

from __future__ import annotations

import asyncio
import base64
import json
import logging
import mimetypes
import os
import re
import time
import uuid
from datetime import datetime, timedelta, timezone
from http import HTTPStatus
from pathlib import Path
from typing import Any, Awaitable, Callable

log = logging.getLogger("hive.messenger")

OnText = Callable[[str], Awaitable[None]]
WEB_DIR = Path(__file__).resolve().parent / "web"


def _image_bytes(src: str) -> tuple[bytes, str, str] | None:
    """(bytes, content type, filename) for a local path, file:// or data: URL. http(s) URLs are fetched."""
    try:
        if src.startswith("data:"):
            head, b64 = src.split(",", 1)
            ctype = head[5:].split(";")[0] or "image/png"
            return base64.b64decode(b64), ctype, "image" + (mimetypes.guess_extension(ctype) or ".png")
        if src.startswith(("http://", "https://")):
            import httpx
            r = httpx.get(src, timeout=10)
            r.raise_for_status()
            ctype = r.headers.get("content-type", "image/png").split(";")[0]
            return r.content, ctype, Path(src.split("?")[0]).name or "image.png"
        p = Path(src.removeprefix("file://")).expanduser()
        ctype = mimetypes.guess_type(p.name)[0] or "image/png"
        return p.read_bytes(), ctype, p.name
    except Exception as exc:
        log.warning("couldn't load image %s: %s", src, exc)
        return None


# ---------------------------------------------------------------------------------------------
class FakeTransport:
    """A Messages-style web page that stands in for the owner's iPhone.

    WS frames (same port as the page):
      server → phone  {"t": "msg", "id", "from": "hive"|"me", "text", "image"?: data URL, "ts"}
      phone → server  {"t": "send", "text"}
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 8769) -> None:
        self.host, self.port = host, port
        self.on_text: OnText | None = None
        self.clients: set[Any] = set()
        self.log: list[dict[str, Any]] = []  # replayed to new phones
        self._server = None

    async def start(self) -> None:
        from websockets.asyncio.server import serve
        from websockets.datastructures import Headers
        from websockets.http11 import Response

        page = (WEB_DIR / "chat.html").read_bytes()

        def process_request(conn, request):
            if request.headers.get("Upgrade", "").lower() == "websocket":
                return None
            if request.path.split("?")[0] in ("/", "/index.html"):
                return Response(HTTPStatus.OK.value, "OK",
                                Headers([("Content-Type", "text/html; charset=utf-8"),
                                         ("Cache-Control", "no-store")]), page)
            return Response(HTTPStatus.NOT_FOUND.value, "Not Found", Headers([("Content-Type", "text/plain")]), b"")

        self._server = await serve(self._handler, self.host, self.port, process_request=process_request,
                                   max_size=8 * 1024 * 1024)
        log.info("fake iMessage thread at http://%s:%d/", self.host, self.port)

    async def close(self) -> None:
        if self._server:
            self._server.close()

    async def _handler(self, ws) -> None:
        self.clients.add(ws)
        try:
            for m in self.log:
                await ws.send(json.dumps(m))
            async for raw in ws:
                try:
                    msg = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if msg.get("t") == "send" and str(msg.get("text", "")).strip():
                    text = str(msg["text"]).strip()
                    await self._push({"from": "me", "text": text})
                    if self.on_text:
                        asyncio.create_task(self.on_text(text))
        finally:
            self.clients.discard(ws)

    async def _push(self, m: dict[str, Any]) -> None:
        m = {"t": "msg", "id": uuid.uuid4().hex[:10], "ts": time.time(), **m}
        self.log.append(m)
        dead = []
        for ws in list(self.clients):
            try:
                await ws.send(json.dumps(m))
            except Exception:
                dead.append(ws)
        for ws in dead:
            self.clients.discard(ws)

    async def send_text(self, text: str) -> None:
        await self._push({"from": "hive", "text": text})

    async def send_image(self, src: str, caption: str | None = None) -> None:
        got = await asyncio.to_thread(_image_bytes, src)
        if not got:
            return
        data, ctype, _ = got
        await self._push({"from": "hive", "text": caption or "", "image": f"data:{ctype};base64,{base64.b64encode(data).decode()}"})


# ---------------------------------------------------------------------------------------------
def _digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def _same_phone(a: str, b: str) -> bool:
    da, db = _digits(a), _digits(b)
    return bool(da and db) and (da == db or da[-10:] == db[-10:])


class PhotonTransport:
    """Photon REST (https://api.photon.codes, see /openapi.json).

    Shared iMessage lines only send in a direct Space, and only after the owner has texted the
    line since their Assignment was created. So the thread "opens" when the owner texts first;
    replies use that Space and the line's Agent user as sender.
    """

    BASE = os.environ.get("PHOTON_API_BASE", "https://api.photon.codes")

    def __init__(self, project_id: str, api_key: str, owner_phone: str, poll_s: float = 1.5) -> None:
        self.project_id, self.api_key, self.owner = project_id, api_key, owner_phone
        self.poll_s = poll_s
        self.on_text: OnText | None = None
        self.space_id: str | None = None
        self.sender_id: str | None = None   # our line's Agent user id (pho_usr_…)
        self._seen: set[str] = set()
        self._queue: list[tuple[str, Any]] = []  # outbound held until the thread is open
        self._since = datetime.now(timezone.utc) - timedelta(seconds=5)
        self._task: asyncio.Task | None = None
        self._client = None

    # -- http --------------------------------------------------------------------------------
    def _url(self, path: str) -> str:
        return f"{self.BASE}/v1/projects/{self.project_id}{path}"

    def _headers(self, idem: bool = False) -> dict[str, str]:
        h = {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}
        if idem:
            h["Idempotency-Key"] = str(uuid.uuid4())
        return h

    async def start(self) -> None:
        import httpx
        self._client = httpx.AsyncClient(timeout=15)
        await self._bootstrap()
        self._task = asyncio.create_task(self._poll_loop())
        if not self.space_id:
            log.warning("Photon: no thread yet. Text the Hive line once from %s to open it.", self.owner)

    async def close(self) -> None:
        if self._task:
            self._task.cancel()
        if self._client:
            await self._client.aclose()

    async def _list_received(self, **params: Any) -> list[dict[str, Any]]:
        q = {"direction": "received", "platform": "imessage", "pageSize": 50, **params}
        r = await self._client.get(self._url("/messages"), params=q, headers=self._headers())
        if r.status_code >= 400:
            log.warning("Photon list messages %s: %s", r.status_code, r.text[:300])
            return []
        return r.json().get("items", [])

    def _from_owner(self, m: dict[str, Any]) -> bool:
        return _same_phone((m.get("sentBy") or {}).get("handle", ""), self.owner)

    def _adopt(self, m: dict[str, Any]) -> None:
        space = (m.get("space") or {}).get("id")
        me = (m.get("receivedBy") or m.get("addressedTo") or {}).get("id")
        if space and me and (space != self.space_id or me != self.sender_id):
            self.space_id, self.sender_id = space, me
            log.info("Photon thread open: space=%s sender=%s", space, me)

    async def _bootstrap(self) -> None:
        """Reuse the newest owner thread so we can text first after a restart."""
        for m in await self._list_received(order="desc", pageSize=20):
            self._seen.add(m.get("id", ""))
            if self._from_owner(m):
                self._adopt(m)
                break

    async def _poll_loop(self) -> None:
        while True:
            try:
                items = await self._list_received(createdSince=self._since.isoformat(timespec="milliseconds").replace("+00:00", "Z"),
                                                  orderBy="created_at", order="asc")
                for m in items:
                    mid = m.get("id", "")
                    if mid in self._seen:
                        continue
                    self._seen.add(mid)
                    if not self._from_owner(m):
                        continue  # only the owner can steer the swarm
                    self._adopt(m)
                    await self._flush()
                    content = m.get("content") or {}
                    if content.get("type") == "text" and self.on_text:
                        await self.on_text(str(content.get("text", "")))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("Photon poll failed: %s", exc)
            await asyncio.sleep(self.poll_s)

    async def _post_message(self, content: dict[str, Any]) -> bool:
        body = {"senderId": self.sender_id, "spaceId": self.space_id, "content": content}
        r = await self._client.post(self._url("/messages"), json=body, headers=self._headers(idem=True))
        if r.status_code >= 400:
            log.warning("Photon send %s: %s", r.status_code, r.text[:300])
            return False
        return True

    async def _flush(self) -> None:
        while self._queue and self.space_id:
            kind, payload = self._queue.pop(0)
            if kind == "text":
                await self._post_message({"type": "text", "format": "plain", "text": payload})
            else:
                await self._send_image_now(*payload)

    async def send_text(self, text: str) -> None:
        if not self.space_id:
            self._queue.append(("text", text))
            return
        await self._post_message({"type": "text", "format": "plain", "text": text})

    async def send_image(self, src: str, caption: str | None = None) -> None:
        if not self.space_id:
            self._queue.append(("image", (src, caption)))
            return
        await self._send_image_now(src, caption)

    async def _send_image_now(self, src: str, caption: str | None) -> None:
        got = await asyncio.to_thread(_image_bytes, src)
        if not got:
            return
        data, ctype, name = got
        # Upload: multipart/related with exactly two parts — JSON metadata, then the file bytes.
        boundary = "hive" + uuid.uuid4().hex
        meta = json.dumps({"contentType": ctype, "sizeBytes": len(data), "filename": name}).encode()
        body = (f"--{boundary}\r\nContent-Type: application/json\r\n\r\n").encode() + meta + \
               (f"\r\n--{boundary}\r\nContent-Type: {ctype}\r\n\r\n").encode() + data + \
               (f"\r\n--{boundary}--\r\n").encode()
        h = self._headers(idem=True) | {"Content-Type": f'multipart/related; boundary="{boundary}"'}
        r = await self._client.post(self._url("/attachments"), content=body, headers=h)
        if r.status_code >= 400:
            log.warning("Photon attachment upload %s: %s", r.status_code, r.text[:300])
            return
        att = r.json().get("id")
        if att:
            await self._post_message({"type": "attachment", "attachmentId": att})
        if caption:
            await self._post_message({"type": "text", "format": "plain", "text": caption})
