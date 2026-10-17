"""Entry point:  uv run python -m hive_engine --scenario demo_sim

Starts the bus (ws://127.0.0.1:8765) and the static server (http://127.0.0.1:8766), then runs a
scenario — immediately, or on a {"cmd": "start"} from a client when --wait is given.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import tempfile
from pathlib import Path

from .bus import Bus
from .http_server import start_http

SCENARIOS = ("demo_sim", "deck_sim", "pitch_in_5")


async def run_scenario(bus: Bus, name: str, render_dir: Path, **opts) -> dict:
    if name == "demo_sim":
        from .scenarios import demo_sim
        return await demo_sim.run(bus, **opts)
    if name == "deck_sim":
        from .scenarios import deck_sim
        return await deck_sim.run(bus, render_dir=render_dir, **opts)
    if name == "pitch_in_5":
        from .scenarios import pitch_in_5
        return await pitch_in_5.run(bus, **opts)
    raise SystemExit(f"unknown scenario {name!r}; choose from {SCENARIOS}")


async def amain(args: argparse.Namespace) -> None:
    render_dir = Path(args.render_dir)
    bus = Bus()
    await bus.start()
    http = start_http(render_dir)
    print(f"bus ws://127.0.0.1:8765 · http http://127.0.0.1:8766  (viewer: /viewer/index.html)")
    try:
        if args.wait:
            done = asyncio.Event()

            async def on_start(name: str) -> None:
                print(json.dumps(await run_scenario(bus, name, render_dir), indent=2))
                done.set()

            bus.on_start = on_start
            print("waiting for a {\"cmd\": \"start\"} command…")
            await done.wait()
        else:
            await asyncio.sleep(args.delay)  # give clients (Mac app) a moment to connect
            result = await run_scenario(bus, args.scenario, render_dir, rounds=args.rounds)
            print(json.dumps(result, indent=2))
    finally:
        http.shutdown()
        await bus.close()


def main() -> None:
    p = argparse.ArgumentParser(prog="hive_engine")
    p.add_argument("--scenario", default="demo_sim", choices=SCENARIOS)
    p.add_argument("--wait", action="store_true", help="wait for a start command from a client")
    p.add_argument("--delay", type=float, default=1.5, help="seconds before starting (clients connect)")
    p.add_argument("--rounds", type=int, default=2)
    p.add_argument("--render-dir", default=str(Path(tempfile.gettempdir()) / "hive_render"))
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(asctime)s %(name)s %(message)s")
    asyncio.run(amain(args))


if __name__ == "__main__":
    main()
