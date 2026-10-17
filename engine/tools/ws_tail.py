"""Debug client: prints every bus event.   uv run python tools/ws_tail.py [--count] [--out file.jsonl]"""

import argparse
import asyncio
import collections
import json

import websockets


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--url", default="ws://127.0.0.1:8765")
    ap.add_argument("--out")
    ap.add_argument("--quiet", action="store_true")
    a = ap.parse_args()
    counts: collections.Counter = collections.Counter()
    out = open(a.out, "w") if a.out else None
    for _ in range(60):  # wait for the engine to come up
        try:
            ws = await websockets.connect(a.url)
            break
        except OSError:
            await asyncio.sleep(0.25)
    else:
        raise SystemExit("bus not reachable")
    try:
        async for raw in ws:
            e = json.loads(raw)
            counts[e["type"]] += 1
            if out:
                out.write(raw + "\n")
            if not a.quiet:
                print(f"{e['ts']:.3f} {e.get('agent') or '-':8} {e['type']:18} {json.dumps(e['data'], ensure_ascii=False)[:110]}")
    except websockets.ConnectionClosed:
        pass
    finally:
        print("COUNTS", dict(counts))
        if out:
            out.close()


asyncio.run(main())
