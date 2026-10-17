"""Run the iMessage bridge next to the engine.

    uv run python -m hive_engine.messenger --fake      # local Messages page at http://127.0.0.1:8769/
    uv run python -m hive_engine.messenger --photon    # real iMessage via Photon (keys in engine/.env)
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os

from ..env import load_env
from .core import Messenger
from .transports import FakeTransport, PhotonTransport


def main() -> None:
    p = argparse.ArgumentParser(prog="hive_engine.messenger")
    g = p.add_mutually_exclusive_group(required=True)
    g.add_argument("--fake", action="store_true", help="local Messages-style page instead of iMessage")
    g.add_argument("--photon", action="store_true", help="real iMessage through Photon")
    p.add_argument("--port", type=int, default=int(os.environ.get("HIVE_CHAT_PORT", "8769")))
    p.add_argument("--host", default=os.environ.get("HIVE_CHAT_HOST", "127.0.0.1"))
    p.add_argument("-v", "--verbose", action="store_true")
    args = p.parse_args()
    load_env()
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(asctime)s %(name)s %(message)s")

    if args.fake:
        transport = FakeTransport(args.host, args.port)
        print(f"fake iMessage thread: http://{args.host}:{args.port}/")
    else:
        missing = [k for k in ("PHOTON_PROJECT_ID", "PHOTON_PROJECT_SECRET", "HIVE_OWNER_PHONE") if not os.environ.get(k)]
        if missing:
            raise SystemExit(f"missing in engine/.env: {', '.join(missing)} (see docs/PHOTON_SETUP.md)")
        transport = PhotonTransport(os.environ["PHOTON_PROJECT_ID"], os.environ["PHOTON_PROJECT_SECRET"],
                                    os.environ["HIVE_OWNER_PHONE"])
        print(f"iMessage via Photon for {os.environ['HIVE_OWNER_PHONE']}")
    try:
        asyncio.run(Messenger(transport).run())
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
