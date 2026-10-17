"""Entry point:  uv run python -m hive_engine --scenario pitch_in_5

Starts the bus (ws://127.0.0.1:8765) and the static server (http://127.0.0.1:8766). The engine always
accepts {"cmd": "start", "args": {"scenario": ...}} from a client (e.g. the notch's Start button); a
second start while one is running is rejected with a chat line.

  (default)  auto-run --scenario after --delay seconds, then exit (add --stay to keep serving starts)
  --wait     don't auto-run; serve start commands until Ctrl-C
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import tempfile
from pathlib import Path

from .bus import Bus
from .env import load_env
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
        return await pitch_in_5.run(bus, render_dir=render_dir, **opts)
    raise ValueError(f"unknown scenario {name!r}; choose from {SCENARIOS}")


async def amain(args: argparse.Namespace) -> None:
    render_dir = Path(args.render_dir)
    bus = Bus()
    await bus.start()
    http = start_http(render_dir)
    print("bus ws://127.0.0.1:8765 · http http://127.0.0.1:8766  (viewer: /viewer/index.html)", flush=True)
    cli_opts = {"rounds": args.rounds, "fast": args.fast, "auto_human": args.auto_human}
    if args.answer_timeout is not None:
        cli_opts["answer_timeout"] = args.answer_timeout

    async def start(name: str, cmd_args: dict) -> None:
        # Options from the start command override the CLI's (e.g. {"scenario": "pitch_in_5", "fast": true}).
        opts = cli_opts | {k: cmd_args[k] for k in ("fast", "auto_human", "answer_timeout") if k in cmd_args}
        result = await bus.run_exclusive(name, lambda: run_scenario(bus, name, render_dir, **opts))
        print(json.dumps(result, indent=2, default=str), flush=True)

    bus.on_start = start
    try:
        if args.wait:
            print('waiting for {"cmd": "start"} commands… (Ctrl-C to quit)', flush=True)
            await asyncio.Event().wait()
        else:
            await asyncio.sleep(args.delay)  # give clients (Mac app) a moment to connect
            if not bus.running:  # a client may already have started something during the delay
                await start(args.scenario, {})
            while bus.running:
                await asyncio.sleep(0.5)
            if args.stay:
                print('still serving {"cmd": "start"} commands… (Ctrl-C to quit)', flush=True)
                await asyncio.Event().wait()
    finally:
        http.shutdown()
        await bus.close()


def main() -> None:
    p = argparse.ArgumentParser(prog="hive_engine")
    p.add_argument("--scenario", default="demo_sim", choices=SCENARIOS)
    p.add_argument("--wait", action="store_true", help="don't auto-run; serve start commands from clients")
    p.add_argument("--stay", action="store_true", help="after the auto-run, keep serving start commands")
    p.add_argument("--delay", type=float, default=1.5, help="seconds before starting (clients connect)")
    p.add_argument("--rounds", type=int, default=2)
    p.add_argument("--fast", action="store_true", help="pitch_in_5: shorter pauses (~1.5 min instead of ~2.5)")
    p.add_argument("--auto-human", action="store_true",
                   help="pitch_in_5 rehearsal: answer questions and send the @Social redirect automatically")
    p.add_argument("--answer-timeout", type=float, default=None,
                   help="pitch_in_5: seconds before a question takes its default answer (default 8)")
    p.add_argument("--render-dir", default=str(Path(tempfile.gettempdir()) / "hive_render"))
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()
    load_env()
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(asctime)s %(name)s %(message)s")
    try:
        asyncio.run(amain(args))
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
