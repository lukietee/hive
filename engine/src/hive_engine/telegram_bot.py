"""Telegram relay (skeleton): group chat ⇄ Hive engine bus.

  Human → engine:  "@Web skip that site"   → {"cmd": "say", "args": {"agent": "web", "text": ...}}
                   "@everyone pause"        → {"cmd": "pause"}
                   inline-button tap        → {"cmd": "answer", "args": {"agent": ..., "choice": ...}}
  Engine → human:  chat / needs_human / agent_done / swarm_summary events → messages in the group

Run:  TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=... uv run python -m hive_engine.telegram_bot
(One bot for now; agent names are prefixed. One-bot-per-agent / Photon's Telegram channel later.)
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys

import websockets
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import Application, CallbackQueryHandler, ContextTypes, MessageHandler, filters

from .agents import AGENTS, find_agent_by_name

BUS_URL = os.environ.get("HIVE_BUS_URL", "ws://127.0.0.1:8765")
MENTION = re.compile(r"@(\w+)")

SETUP = """TELEGRAM_BOT_TOKEN is not set.

1. In Telegram, message @BotFather → /newbot → copy the token.
2. /setprivacy → Disable (so the bot sees all group messages).
3. Add the bot to your "Hive Squad" group, send a message, then get the chat id from
   https://api.telegram.org/bot<TOKEN>/getUpdates  (message.chat.id, negative for groups).
4. export TELEGRAM_BOT_TOKEN=... TELEGRAM_CHAT_ID=...
"""


def parse_human(text: str) -> list[dict]:
    """Turn a chat message into bus commands."""
    names = MENTION.findall(text)
    body = MENTION.sub("", text).strip()
    cmds: list[dict] = []
    if any(n.lower() == "everyone" for n in names):
        word = body.split()[0].lower() if body else ""
        if word in ("pause", "resume"):
            return [{"v": 1, "cmd": word, "args": {}}]
        return [{"v": 1, "cmd": "say", "args": {"text": body}}]
    for n in names:
        agent = find_agent_by_name(n)
        if agent:
            word = body.split()[0].lower() if body else ""
            if word in ("pause", "resume"):
                cmds.append({"v": 1, "cmd": word, "args": {"agent": agent}})
            else:
                cmds.append({"v": 1, "cmd": "say", "args": {"agent": agent, "text": body}})
    return cmds or [{"v": 1, "cmd": "say", "args": {"text": text}}]


def format_event(e: dict) -> tuple[str, InlineKeyboardMarkup | None] | None:
    meta = AGENTS.get(e.get("agent") or "", {"emoji": "🐝", "name": "Hive"})
    d = e.get("data", {})
    t = e.get("type")
    if t == "chat":
        return d.get("text", ""), None
    if t == "needs_human":
        kb = InlineKeyboardMarkup([[InlineKeyboardButton(o, callback_data=f"{e['agent']}|{o}")
                                    for o in d.get("options", [])]])
        return f"{meta['emoji']} {meta['name']}: {d.get('question')}", kb
    if t == "agent_done" and d.get("summary"):
        return f"{meta['emoji']} {meta['name']} ✓ {d['summary']}", None
    if t == "swarm_summary":
        return "🐝 " + d.get("title", "Done") + "\n" + "\n".join(d.get("lines", [])), None
    return None


async def main() -> None:
    from .env import load_env
    load_env()
    token, chat_id = os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not token or not chat_id:
        print(SETUP)
        sys.exit(1)

    app = Application.builder().token(token).build()
    bus = await websockets.connect(BUS_URL)

    async def on_message(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        if update.message and update.message.text:
            for cmd in parse_human(update.message.text):
                await bus.send(json.dumps(cmd))

    async def on_button(update: Update, _: ContextTypes.DEFAULT_TYPE) -> None:
        q = update.callback_query
        agent, choice = (q.data or "|").split("|", 1)
        await bus.send(json.dumps({"v": 1, "cmd": "answer", "args": {"agent": agent, "choice": choice}}))
        await q.answer(f"→ {choice}")

    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, on_message))
    app.add_handler(CallbackQueryHandler(on_button))

    async with app:
        await app.start()
        await app.updater.start_polling()
        async for raw in bus:  # engine → group
            out = format_event(json.loads(raw))
            if out:
                text, kb = out
                await app.bot.send_message(chat_id=int(chat_id), text=text, reply_markup=kb)


if __name__ == "__main__":
    asyncio.run(main())
