"""Where the thread's texts actually go.

FakeTransport   — a local "Messages" page + WebSocket at http://127.0.0.1:8769/ (no keys; for testing).
PhotonTransport — Photon's REST API: send via POST /messages, receive by polling
                  GET /messages?direction=received. No public URL or webhook needed on the Mac.
                  Shared line  → one 1:1 thread that opens when the owner texts first.
                  Dedicated line → Hive can text first and open group chats (open_session).

Both expose: start(), close(), send_text(text), send_image(path_or_url, caption),
open_session(title, members) -> space id or None, resume(space_id), `group_capable`, and call
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

    group_capable = True
    space_id: str | None = "fake-direct"

    async def send_text(self, text: str) -> None:
        await self._push({"from": "hive", "text": text})

    async def send_image(self, src: str, caption: str | None = None) -> None:
        got = await asyncio.to_thread(_image_bytes, src)
        if not got:
            return
        data, ctype, _ = got
        await self._push({"from": "hive", "text": caption or "", "image": f"data:{ctype};base64,{base64.b64encode(data).decode()}"})

    async def open_session(self, title: str, members: list[str]) -> str | None:
        """Stands in for a new group chat: a divider line in the fake thread."""
        self.space_id = f"fake-group-{uuid.uuid4().hex[:6]}"
        who = "you" + (f" + {len(members)}" if members else "")
        await self._push({"from": "system", "text": f"New group: {title} ({who})"})
        return self.space_id

    async def resume(self, space_id: str) -> bool:
        self.space_id = space_id
        return True


# ---------------------------------------------------------------------------------------------
def _digits(s: str) -> str:
    return re.sub(r"\D", "", s or "")


def _same_phone(a: str, b: str) -> bool:
    da, db = _digits(a), _digits(b)
    return bool(da and db) and (da == db or da[-10:] == db[-10:])


class PhotonTransport:
    """Photon REST (https://api.photon.codes, see /openapi.json).

    Shared line (GET /platforms/imessage → mode "shared"): sends only in a direct Space, and only
    after the owner has texted the line since their Assignment. The thread "opens" when the owner
    texts first; replies use that Space and the line's Agent user as sender.

    Dedicated line (mode "dedicated"): the line's Agent user can create Spaces itself
    (POST /spaces, first participant = our Agent). Two participants make a direct chat, three or
    more a native group. Photon reuses an existing chat with exactly the same participants, and
    REST can't rename a group (spectrum-ts can), so a "new session" with the same members lands
    in the same group and is marked with a header text instead.
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
        self.mode = "shared"                 # or "dedicated" (GET /platforms/imessage)
        self.line_number: str | None = None  # dedicated line's phone number
        self.owner_user_id: str | None = None
        self.direct_space_id: str | None = None  # owner's 1:1 on the dedicated line
        self.member_ids: dict[str, str] = {}     # user id → handle, for the active group

    @property
    def group_capable(self) -> bool:
        return self.mode == "dedicated"

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
        self._client = httpx.AsyncClient(timeout=20)
        await self._detect_mode()
        if self.mode == "dedicated":
            await self._bootstrap_dedicated()
        else:
            await self._bootstrap()
        self._task = asyncio.create_task(self._poll_loop())
        if not self.space_id:
            log.warning("Photon: no thread yet. Text the Hive line once from %s to open it.", self.owner)

    async def _detect_mode(self) -> None:
        try:
            r = await self._client.get(self._url("/platforms/imessage"), headers=self._headers())
            if r.status_code < 400:
                self.mode = (r.json() or {}).get("mode") or "shared"
        except Exception as exc:
            log.warning("Photon mode check failed (%s); assuming a shared line", exc)
        if os.environ.get("HIVE_PHOTON_MODE") in ("shared", "dedicated"):
            self.mode = os.environ["HIVE_PHOTON_MODE"]
        log.info("Photon iMessage mode: %s", self.mode)

    async def _user_id(self, handle: str) -> str | None:
        r = await self._client.post(self._url("/users"), json={"handle": handle, "platform": "imessage"},
                                    headers=self._headers(idem=True))
        if r.status_code >= 400:
            log.warning("Photon user %s: %s %s", handle, r.status_code, r.text[:300])
            return None
        return r.json().get("id")

    async def _bootstrap_dedicated(self) -> None:
        """Find our dedicated line's Agent user and the owner's 1:1 Space on it (created if needed)."""
        self.line_number = os.environ.get("HIVE_IMESSAGE_LINE") or None
        if not self.line_number:
            r = await self._client.get(self._url("/platforms/resources"), headers=self._headers())
            for res in (r.json() or {}).get("resources", []) if r.status_code < 400 else []:
                if "imessage" in (res.get("abilities") or []) and res.get("state") == "active":
                    self.line_number = (res.get("detail") or {}).get("phoneNumber")
                    break
        if not self.line_number:
            log.warning("Photon: dedicated mode but no active iMessage line found; falling back to shared")
            self.mode = "shared"
            await self._bootstrap()
            return
        self.sender_id = await self._user_id(self.line_number)
        self.owner_user_id = await self._user_id(self.owner)
        if not (self.sender_id and self.owner_user_id):
            log.warning("Photon: couldn't resolve the line/owner users; falling back to shared")
            self.mode = "shared"
            await self._bootstrap()
            return
        self.direct_space_id = await self._create_space([self.sender_id, self.owner_user_id])
        self.space_id = self.space_id or self.direct_space_id
        for m in await self._list_received(order="desc", pageSize=20):
            self._seen.add(m.get("id", ""))
        log.info("Photon dedicated line %s: sender=%s owner 1:1 space=%s", self.line_number, self.sender_id,
                 self.direct_space_id)

    async def _create_space(self, participant_ids: list[str]) -> str | None:
        """POST /spaces (create or get). Retries the same Idempotency-Key while the operation runs."""
        key = str(uuid.uuid4())
        body = {"platform": "imessage", "participantIds": participant_ids}
        for attempt in range(8):
            h = self._headers() | {"Idempotency-Key": key}
            try:
                r = await self._client.post(self._url("/spaces"), json=body, headers=h)
            except Exception as exc:
                log.warning("Photon create space: %s (retrying)", exc)
                await asyncio.sleep(2)
                continue
            data = r.json() if r.content else {}
            if r.status_code < 300 and str(data.get("id", "")).startswith("pho_spc_"):
                return data["id"]
            if r.status_code in (202, 409, 503, 504) or (r.status_code < 300 and not data.get("id")):
                await asyncio.sleep(1.5 + attempt)
                continue
            log.warning("Photon create space %s: %s", r.status_code, r.text[:400])
            return None
        log.warning("Photon create space: still pending after retries")
        return None

    async def open_session(self, title: str, members: list[str]) -> str | None:
        """Dedicated line: open the chat for a new run — a group with the owner plus `members`
        (phone numbers), or the owner's 1:1 when there are no members. Shared line: None."""
        if self.mode != "dedicated":
            return None
        ids = [self.sender_id, self.owner_user_id]
        handles: dict[str, str] = {}
        for ph in members:
            if _same_phone(ph, self.owner):
                continue
            uid = await self._user_id(ph)
            if uid and uid not in ids:
                ids.append(uid)
                handles[uid] = ph
        space = await self._create_space(ids) if len(ids) > 2 else self.direct_space_id
        if not space:
            return None
        self.space_id, self.member_ids = space, handles
        await self._flush()
        return space

    async def resume(self, space_id: str) -> bool:
        if self.mode != "dedicated":
            return False
        try:
            r = await self._client.get(self._url(f"/spaces/{space_id}"), headers=self._headers())
        except Exception:
            return False
        if r.status_code >= 400 or self.sender_id not in (r.json().get("participantIds") or []):
            return False
        self.space_id = space_id
        return True

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
                        sp = (m.get("space") or {}).get("id")
                        if sp and sp == self.space_id:
                            who = (m.get("sentBy") or {}).get("handle", "?")
                            log.info("group member %s: %s", who, ((m.get("content") or {}).get("text") or "")[:120])
                        continue  # only the owner can steer the swarm
                    if self.mode == "dedicated":
                        # Owner texts in our group, our 1:1, or (legacy) the old shared thread all count;
                        # replies always go to the active space.
                        if not self.space_id:
                            self.space_id = (m.get("space") or {}).get("id")
                    else:
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
