"""Place ONE real test call through ElevenLabs → Photon SIP, with the Call window showing it live.

    cd engine
    uv run python tools/test_call.py --to "$TEST_CALL_NUMBER" --yes-really-call

It refuses to dial without --yes-really-call. Call only your own phone (or someone who agreed).
The agent discloses that it is an AI and that the call is recorded in its first sentence.

Needs in engine/.env: ELEVENLABS_API_KEY, ELEVENLABS_AGENT_ID, and ELEVENLABS_PHONE_NUMBER_ID or
PHOTON_PHONE_NUMBER (see docs/CALLS_SETUP.md). Start the Mac app first to watch the Call window.

    --dry-run   check the config and print the prompt; no call
    --fake      run the simulated call through the same path (no phone, no keys needed)
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from hive_engine.agent import Agent  # noqa: E402
from hive_engine.bus import Bus  # noqa: E402
from hive_engine.calls import place_call  # noqa: E402
from hive_engine.calls.elevenlabs import ElevenLabs, missing_live_config  # noqa: E402
from hive_engine.calls.prompt import build_prompt, first_message  # noqa: E402
from hive_engine.env import load_env  # noqa: E402

GOAL = ("This is a short test call. Introduce yourself, confirm the person can hear you clearly, "
        "ask them to say a favorite dessert, repeat it back, thank them and end the call.")


async def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--to", default=os.environ.get("TEST_CALL_NUMBER"), help="E.164 number, e.g. +13105551234")
    p.add_argument("--label", default="Test call")
    p.add_argument("--yes-really-call", action="store_true", help="required to place a real call")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("--fake", action="store_true")
    args = p.parse_args()
    load_env()
    args.to = args.to or os.environ.get("TEST_CALL_NUMBER")
    user = os.environ.get("HIVE_USER_NAME", "Lucas")

    if args.dry_run:
        missing = missing_live_config()
        print("missing:", missing or "nothing — ready for a live call")
        print("\nfirst message:\n ", first_message(user, args.label))
        print("\nprompt:\n" + build_prompt(GOAL, {}, user))
        if not missing:
            el = ElevenLabs()
            try:
                print("\nphone_number_id:", await el.phone_number_id())
            finally:
                await el.close()
        return 0

    if not args.fake:
        if not args.to or not args.to.startswith("+"):
            sys.exit("--to must be an E.164 number like +13105551234 (or set TEST_CALL_NUMBER)")
        if not args.yes_really_call:
            sys.exit(f"Refusing to call {args.to} without --yes-really-call.")
        if missing := missing_live_config():
            sys.exit("Live call needs: " + ", ".join(missing))

    bus = Bus()
    await bus.start()
    try:
        await asyncio.sleep(2.0)  # let the Mac app connect
        caller = Agent(bus, "caller")
        caller.spawn()
        res = await place_call(caller, to=args.to or "+13105550142", label=args.label, goal=GOAL,
                               fake=args.fake)
        caller.emit("agent_done", summary="Test call finished")
        print(json.dumps(res.as_dict(), indent=2, ensure_ascii=False))
        await asyncio.sleep(1.0)
    finally:
        await bus.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
