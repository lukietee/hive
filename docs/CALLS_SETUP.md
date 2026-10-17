# Phone calls: ElevenLabs voice agent ⇄ Photon SIP

How a Hive agent's call reaches a real phone:

```
Hive engine ──PATCH prompt──▶ ElevenLabs agent ──POST sip-trunk/outbound-call──▶ ElevenLabs SIP
   ▲                                                                              │ TLS, digest auth
   │ GET conversation (status, transcript, analysis) ~1/s                         ▼
   └──────────────────────────────────────────────────────────────  Photon SIP (sip.photon.codes:5061)
                                                                                  │ caller ID = your Photon number
                                                                                  ▼
                                                                         the bakery's phone
```

Sources: Photon's ElevenLabs cookbook (<https://photon.codes/docs/beta/cookbooks/voice/elevenlabs>),
Photon voice (<https://photon.codes/docs/spectrum-ts/providers/voice>), ElevenLabs SIP trunking
(<https://elevenlabs.io/docs/eleven-agents/phone-numbers/sip-trunking>), and the outbound-call API
(<https://elevenlabs.io/docs/eleven-agents/api-reference/sip-trunk/outbound-call>).

## ⚠️ Read first
- **Photon voice needs an SMS number, a WhatsApp number, or a *dedicated* iMessage line.**
  "Shared iMessage assignments do not support Voice" (Photon cookbook, *Before you start*).
  The free shared iMessage line is fine for texting, but for calls, add an SMS number to the project.
- Calls from an unregistered business "may be flagged" (Photon voice docs). Registration is free but
  takes 1–2 business days, so warn the bakery the call is coming.
- ElevenLabs' live monitoring WebSocket is enterprise-only, so Hive **polls** the conversation. If the
  transcript only fills in after the call, the Call window shows "connected" and a timer during the
  call and fills the bubbles at the end. Check this on the first test call.

## 1. Photon dashboard (app.photon.codes)
1. Open your project → **Voice**. Under **Lines**, find the SMS number (or dedicated line).
2. If there's no profile: **Set up default** → **SIP** → **Create profile**.
3. **Media encryption:** leave **Auto**.
4. **Outbound calls** → **Digest algorithm: SHA-256 (recommended)** → **Enable outbound**.
   Copy the password from **Save the outbound password** (shown once) → **I saved it**.
5. Note from the profile: **SIP connection** server + TLS port (e.g. `sip.photon.codes:5061`) and the
   outbound **Username**.
6. (For inbound, optional) **Inbound calls** → **Enable inbound** → SIP address
   `sips:sip.rtc.elevenlabs.io:5061`, **Transport TLS**, no credentials.

## 2. ElevenLabs dashboard (elevenlabs.io → Agents)
1. **Create an agent** (any name, e.g. "Hive Caller"). Pick the voice (the same one as `ELEVENLABS_VOICE_ID`),
   language English. The prompt doesn't matter: Hive overwrites the prompt and first message before every call.
   Copy the **agent ID** → `ELEVENLABS_AGENT_ID`.
2. **Phone Numbers** (under Deploy) → **Import number** → **From SIP Trunk**:
   - **Label:** `Photon`  ·  **Phone number:** your Photon number, `+1…`
   - **Inbound:** Media Encryption **Allowed**, Allowed Source IPs `0.0.0.0/0`, no username/password.
   - **Outbound:** Address = Photon's server and port **without** `sip:` (e.g. `sip.photon.codes:5061`),
     Transport **TLS**, Media Encryption **Allowed**, codecs G.722 / PCMU / PCMA,
     SIP Trunk Username/Password = Photon's outbound username + saved password.
   - **Import**. Open the number → **Agent** → pick your agent.
3. Copy the imported number's ID → `ELEVENLABS_PHONE_NUMBER_ID`, or just set `PHOTON_PHONE_NUMBER=+1…`
   and Hive looks the ID up.
4. API key: Profile → API keys. It needs the **Agents** permissions (read + write) and **Text to Speech**.
5. Sanity check in ElevenLabs: open the number → **Outbound call** → your agent → your own cell → **Send Test Call**.

## 3. engine/.env
```
ELEVENLABS_API_KEY=…
ELEVENLABS_VOICE_ID=…
ELEVENLABS_AGENT_ID=…
PHOTON_PHONE_NUMBER=+1…          # or ELEVENLABS_PHONE_NUMBER_ID=…
TEST_CALL_NUMBER=+1…             # your own cell
HIVE_USER_NAME=Lucas
```

## 4. Test from Hive (Mac app running, so the Call window shows)
```bash
cd engine
uv run python tools/test_call.py --dry-run                         # checks config, prints the prompt, finds the number id
uv run python tools/test_call.py --fake                            # simulated call through the same path
uv run python tools/test_call.py --to "$TEST_CALL_NUMBER" --yes-really-call   # one real call to YOUR phone
```
Then the simulated bakery demo: `uv run python -m hive_engine --scenario call_sim` (add `--tts` to hear it).

## Troubleshooting (from the Photon cookbook)
| Symptom | Check |
|---|---|
| Request rejected | Agent ID, phone number ID, `to` in E.164 |
| "initiated" but the phone never rings | ElevenLabs **Conversations** for the attempt; outbound hostname vs Photon's **SIP connection** |
| SIP auth fails | Outbound username/password, and **SHA-256** in Photon |
| One-way or no audio | Codecs and media encryption on both sides (Auto / Allowed) |
| Hang-up fails over TLS | Add Photon's SIP domain to **Remote Domains** in ElevenLabs |
