"""Minimal async client for the ElevenLabs Agents API calls Hive needs.

Endpoints (https://elevenlabs.io/docs/eleven-agents/api-reference):
    PATCH /v1/convai/agents/{agent_id}               set this call's prompt + first message
    GET   /v1/convai/phone-numbers                   find the imported Photon number's id
    POST  /v1/convai/sip-trunk/outbound-call         dial out through the SIP trunk (Photon)
    GET   /v1/convai/conversations/{conversation_id} poll status + transcript + analysis
    POST  /v1/text-to-speech/{voice_id}              (fake calls only) voice the agent's lines

Env (engine/.env): ELEVENLABS_API_KEY, ELEVENLABS_AGENT_ID, ELEVENLABS_PHONE_NUMBER_ID
(or PHOTON_PHONE_NUMBER to look the id up), ELEVENLABS_VOICE_ID.
"""

from __future__ import annotations

import os
from typing import Any

import httpx

API = os.environ.get("ELEVENLABS_API_BASE", "https://api.elevenlabs.io")


MAX_DURATION_S = 180      # hard cap per call
SILENCE_END_S = 20.0      # hang up after this long with nobody speaking


class ElevenLabsError(RuntimeError):
    pass


def builtin_tools(voicemail_message: str | None = None) -> dict[str, Any]:
    """System tools: end_call (agent may hang up) and voicemail_detection (leave a short message, hang up)."""
    vm = voicemail_message or ("Hi, this is Hive, an AI assistant calling for {{user_name}}. "
                               "Sorry we missed you. We'll try again later. Bye!")
    return {
        "end_call": {"type": "system", "name": "end_call",
                     "description": "End the call once the goal is done, the person says goodbye, or they ask you to stop.",
                     "params": {"system_tool_type": "end_call"}},
        "voicemail_detection": {"type": "system", "name": "voicemail_detection",
                                "description": "Use when you reach a voicemail greeting or answering machine.",
                                "params": {"system_tool_type": "voicemail_detection", "voicemail_message": vm}},
    }


def missing_live_config() -> list[str]:
    """Env vars a live call still needs (empty list = ready)."""
    need = ["ELEVENLABS_API_KEY", "ELEVENLABS_AGENT_ID"]
    out = [k for k in need if not os.environ.get(k)]
    if not (os.environ.get("ELEVENLABS_PHONE_NUMBER_ID") or os.environ.get("PHOTON_PHONE_NUMBER")):
        out.append("ELEVENLABS_PHONE_NUMBER_ID (or PHOTON_PHONE_NUMBER)")
    return out


class ElevenLabs:
    def __init__(self, api_key: str | None = None, timeout: float = 20.0) -> None:
        key = api_key or os.environ.get("ELEVENLABS_API_KEY")
        if not key:
            raise ElevenLabsError("ELEVENLABS_API_KEY is not set")
        self.http = httpx.AsyncClient(base_url=API, headers={"xi-api-key": key}, timeout=timeout)

    async def close(self) -> None:
        await self.http.aclose()

    async def _req(self, method: str, path: str, **kw: Any) -> Any:
        r = await self.http.request(method, path, **kw)
        if r.status_code >= 400:
            raise ElevenLabsError(f"{method} {path} → {r.status_code}: {r.text[:400]}")
        return r.json() if r.headers.get("content-type", "").startswith("application/json") else r.content

    async def configure_agent(self, agent_id: str, prompt: str, first_message: str,
                              voice_id: str | None = None, max_duration_s: int = MAX_DURATION_S,
                              voicemail_message: str | None = None) -> None:
        """Sets this call's instructions on the hosted agent (no Security-tab overrides needed).

        Also caps the call length, lets the agent hang up (end_call) and detect voicemail, and ends
        the call after a long silence, so a voicemail box can't keep it talking for minutes.
        """
        conv: dict[str, Any] = {
            "agent": {"first_message": first_message,
                      "prompt": {"prompt": prompt, "built_in_tools": builtin_tools(voicemail_message)}},
            "conversation": {"max_duration_seconds": max_duration_s},
            "turn": {"silence_end_call_timeout": SILENCE_END_S},
        }
        if voice_id:
            conv["tts"] = {"voice_id": voice_id}
        await self._req("PATCH", f"/v1/convai/agents/{agent_id}", json={"conversation_config": conv})

    async def agent(self, agent_id: str) -> dict[str, Any]:
        return await self._req("GET", f"/v1/convai/agents/{agent_id}")

    async def phone_number_id(self, e164: str | None = None) -> str:
        if pid := os.environ.get("ELEVENLABS_PHONE_NUMBER_ID"):
            return pid
        want = (e164 or os.environ.get("PHOTON_PHONE_NUMBER") or "").replace(" ", "")
        numbers = await self._req("GET", "/v1/convai/phone-numbers")
        for n in numbers if isinstance(numbers, list) else []:
            if n.get("phone_number", "").replace(" ", "") == want:
                return n["phone_number_id"]
        raise ElevenLabsError(f"no imported phone number matches {want!r}; import the Photon number "
                              "(Phone Numbers → Import number → From SIP Trunk) or set ELEVENLABS_PHONE_NUMBER_ID")

    async def outbound_call(self, agent_id: str, phone_number_id: str, to: str,
                            dynamic_variables: dict[str, Any] | None = None) -> dict[str, Any]:
        body: dict[str, Any] = {"agent_id": agent_id, "agent_phone_number_id": phone_number_id, "to_number": to,
                                "telephony_call_config": {"ringing_timeout_secs": 45}}
        if dynamic_variables:
            body["conversation_initiation_client_data"] = {
                "dynamic_variables": {k: v for k, v in dynamic_variables.items()
                                      if isinstance(v, (str, int, float, bool))}}
        res = await self._req("POST", "/v1/convai/sip-trunk/outbound-call", json=body)
        if not res.get("success"):
            raise ElevenLabsError(f"outbound call rejected: {res.get('message')}")
        return res

    async def conversation(self, conversation_id: str) -> dict[str, Any]:
        return await self._req("GET", f"/v1/convai/conversations/{conversation_id}")

    async def tts(self, text: str, voice_id: str, model_id: str = "eleven_flash_v2_5") -> bytes:
        return await self._req("POST", f"/v1/text-to-speech/{voice_id}", params={"output_format": "mp3_44100_64"},
                               json={"text": text, "model_id": model_id})
