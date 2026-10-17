"""Plays the owner's phone against the fake iMessage thread and prints the transcript.

    # terminal 1: uv run python -m hive_engine --wait --answer-timeout 30
    # terminal 2: uv run python -m hive_engine.messenger --fake
    # terminal 3: uv run python tools/chat_check.py --script pitch

Scripted replies (pitch): texts "start", answers Deck's market question in free text, answers the
Checker with "1", sends "@Social make it shorter" after the first draft, asks "@Web show me".
"""

from __future__ import annotations

import argparse
import asyncio
import json
import time

import websockets

RULES_PITCH = [
    # (trigger substring in an incoming text, reply, once)
    ("Slide 6 market size", "go with the bigger one, matcha plus specialty tea"),
    ("Checker:", "1"),          # the price question (first Checker text that has options)
    ("First draft is", "@Social make it shorter"),
    ("Got it, going with $29", "@Web show me"),
]


async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--url", default="ws://127.0.0.1:8769/")
    p.add_argument("--script", choices=["pitch", "none"], default="pitch")
    p.add_argument("--timeout", type=float, default=240)
    p.add_argument("--out", help="write the transcript here too")
    args = p.parse_args()

    rules = list(RULES_PITCH) if args.script == "pitch" else []
    lines: list[str] = []
    t0 = time.time()

    def show(who: str, text: str) -> None:
        stamp = f"{time.time() - t0:6.1f}s"
        for i, part in enumerate(text.split("\n")):
            line = f"{stamp if i == 0 else ' ' * len(stamp)}  {who:>4} │ {part}"
            print(line, flush=True)
            lines.append(line)

    async with websockets.connect(args.url, max_size=None) as ws:
        if args.script == "pitch":
            await asyncio.sleep(0.5)
            await ws.send(json.dumps({"t": "send", "text": "start"}))
        try:
            async with asyncio.timeout(args.timeout):
                async for raw in ws:
                    m = json.loads(raw)
                    if m.get("t") != "msg":
                        continue
                    text = m.get("text") or ""
                    if m.get("image"):
                        show("hive", f"[image {len(m['image']) // 1024} KB] {text}")
                    else:
                        show("me" if m["from"] == "me" else "hive", text)
                    if m["from"] != "hive":
                        continue
                    for rule in list(rules):
                        trig, reply = rule
                        if trig in text and (trig != "Checker:" or "Reply 1 or 2" in text):
                            rules.remove(rule)
                            await asyncio.sleep(1.0)
                            await ws.send(json.dumps({"t": "send", "text": reply}))
                            break
                    if text.startswith("Hive: Pitch ready") or "to spare" in text:
                        await asyncio.sleep(3)
                        break
        except TimeoutError:
            print("(timed out)")
    if args.out:
        open(args.out, "w").write("\n".join(lines) + "\n")


if __name__ == "__main__":
    asyncio.run(main())
