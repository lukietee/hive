# Photon setup for the iMessage thread

The Messenger talks to Photon's REST API (`https://api.photon.codes`, schema at `/openapi.json`) from Python: it sends with `POST /v1/projects/{id}/messages` and receives by polling `GET /v1/projects/{id}/messages?direction=received`. That needs no public URL, tunnel or Node sidecar on the Mac. (The `spectrum-ts` SDK is TypeScript-only and would add a second runtime for the same two calls.)

## 1. In the Photon dashboard (app.photon.codes)
1. Create a project. Copy the **project ID** (`pho_prj_…`) into `PHOTON_PROJECT_ID`.
2. Create a **project API key** (`pho_sk_…`, shown once) and put it in `PHOTON_PROJECT_SECRET`.
3. Add the **iMessage** platform with the free **shared line**.
4. Add an **assignment** for your own number (Platforms → iMessage → assignments, or `POST /v1/projects/{id}/platforms/imessage/assignments` with `{"handle": "+1…"}`). Photon gives you the line's phone number to text. One assignment uses one seat.
5. Note the line's number in your contacts as **Hive**.

## 2. engine/.env
```
PHOTON_PROJECT_ID=pho_prj_…
PHOTON_PROJECT_SECRET=pho_sk_…
HIVE_OWNER_PHONE=+13105551234
```
`HIVE_OWNER_PHONE` is the only number whose texts are acted on. Texts from anyone else are ignored.

## 3. Run it
```
cd engine
uv run python -m hive_engine --wait                 # terminal 1: the engine
uv run python -m hive_engine.messenger --photon -v  # terminal 2: the iMessage bridge
```
Then **text the Hive line first** (anything, e.g. "hi"). Photon only lets a shared line send in a 1:1 thread to someone who has texted it since their assignment, so the thread opens with your first text. After a restart the Messenger reuses your newest thread. Texts generated before the thread opens are queued and sent once it does.

Text `start` to run Pitch in 5.

## What works on a shared line
- 1:1 text both ways, and images (screenshots) as attachments.
- **No group chats** (dedicated lines only). That's why it's one thread with "Name:" prefixes and @mentions.
- **No inbound tapbacks.** Photon's received-iMessage content types are text, attachment, read and typing, with no reactions. So answers are typed: `1`, the option, or your own words.

## Test without Photon
```
uv run python -m hive_engine.messenger --fake   # open http://127.0.0.1:8769/
uv run python tools/chat_check.py               # or let a script play the phone
```
