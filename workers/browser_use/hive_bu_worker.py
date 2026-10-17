"""One Browser Use agent, run as a subprocess of the Hive engine.

    uv run --project workers/browser_use python workers/browser_use/hive_bu_worker.py \
        --cdp-url http://127.0.0.1:9301 --task "..." [--model claude-sonnet-5-5] [--max-steps 25]

It lives in its own uv project because browser-use pins an older `websockets` than the engine.

Protocol (newline-delimited JSON):
  stdout → engine   {"ev": "cursor", "type": "moving_to"|"click"|"typing", ...}   ghost cursor, sync rule
                    {"ev": "status", "text": str, "progress": float}               after each step
                    {"ev": "ask", "question": str, "options": [str]}               needs the human
                    {"ev": "done", "ok": bool, "result": str, "steps": int, "tokens": {...}}
                    {"ev": "log", "text": str}
  stdin  ← engine   {"answer": str}                                                  reply to "ask"

Every click/type is preceded by moving_to → wait → click/typing on stdout, *then* the real action
(docs/CONTRACT.md sync rule). Coordinates are global screen points (top-left origin).
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from typing import Any

# Keep browser-use quiet on stdout: our protocol owns stdout.
os.environ.setdefault("BROWSER_USE_LOGGING_LEVEL", "warning")
os.environ.setdefault("ANONYMIZED_TELEMETRY", "false")
os.environ.setdefault("BROWSER_USE_CLOUD_SYNC", "false")

_real_stdout = sys.stdout
sys.stdout = sys.stderr  # anything browser-use prints goes to stderr

from browser_use import Agent, BrowserSession, Tools  # noqa: E402
from browser_use.browser.watchdogs.default_action_watchdog import DefaultActionWatchdog  # noqa: E402
from browser_use.llm.anthropic.chat import ChatAnthropic  # noqa: E402

class HiveChatAnthropic(ChatAnthropic):
    """Sonnet/Opus 5.5 reject a forced tool_choice ("tool"/"any"), so for them browser-use must use
    tool_choice=auto plus its text-recovery path — which sometimes returns malformed actions. Haiku 5.5
    still accepts a forced tool call, so it is the default browser model (reliable action format, cheap)."""

    def _requires_auto_tool_choice(self) -> bool:  # noqa: D401
        return "haiku" not in self.model.lower() or super()._requires_auto_tool_choice()


GLIDE_MS = int(os.environ.get("HIVE_GLIDE_MS", "450"))
SAFETY = (
    "You are one agent in a team (Hive). Rules you must follow: browse read-only. "
    "Never log in, never create accounts, never buy anything, never submit forms on real websites, "
    "never post or send messages. Reading pages, searching, clicking links and typing into search boxes is fine. "
    "If you genuinely need a decision from the human, call ask_human with 2-4 concrete options. "
    "Keep the final answer short and factual."
)


def send(obj: dict[str, Any]) -> None:
    _real_stdout.write(json.dumps(obj, ensure_ascii=False) + "\n")
    _real_stdout.flush()


# ---- ghost cursor: hook the default action watchdog -------------------------------------------

async def _viewport_origin(session, cdp_session) -> tuple[float, float]:
    """Screen point of the page viewport's (0,0), same math as engine/browser_agent.py."""
    res = await cdp_session.cdp_client.send.Runtime.evaluate(
        params={"expression": "JSON.stringify([screenX, screenY, outerWidth, innerWidth, outerHeight, innerHeight])",
                "returnByValue": True},
        session_id=cdp_session.session_id,
    )
    sx, sy, ow, iw, oh, ih = json.loads(res["result"]["value"])
    side = max(0, (ow - iw) / 2)
    return sx + side, sy + (oh - ih) - side


async def _node_screen_point(watchdog, node) -> tuple[float, float] | None:
    session = watchdog.browser_session
    try:
        cdp_session = await session.cdp_client_for_node(node)
        try:
            await cdp_session.cdp_client.send.DOM.scrollIntoViewIfNeeded(
                params={"backendNodeId": node.backend_node_id}, session_id=cdp_session.session_id)
            await asyncio.sleep(0.05)
        except Exception:
            pass
        rect = await session.get_element_coordinates(node.backend_node_id, cdp_session)
        if not rect:
            return None
        ox, oy = await _viewport_origin(session, cdp_session)
        return ox + rect.x + rect.width / 2, oy + rect.y + rect.height / 2
    except Exception as exc:  # cursor is cosmetic; never block the action
        send({"ev": "log", "text": f"cursor point failed: {exc}"})
        return None


def _label(node) -> str | None:
    attrs = getattr(node, "attributes", None) or {}
    for k in ("aria-label", "placeholder", "title", "name", "alt"):
        if attrs.get(k):
            return str(attrs[k])[:40]
    try:
        text = node.get_all_children_text(max_depth=3).strip()
        return text[:40] or None
    except Exception:
        return None


async def _lead(x: float, y: float, kind: str, label: str | None = None, text: str | None = None) -> None:
    send({"ev": "cursor", "type": "moving_to", "x": round(x, 1), "y": round(y, 1), "duration_ms": GLIDE_MS,
          "label": label})
    await asyncio.sleep(GLIDE_MS / 1000)
    if kind == "typing":
        send({"ev": "cursor", "type": "typing", "x": round(x, 1), "y": round(y, 1), "text": text or ""})
    else:
        send({"ev": "cursor", "type": "click", "x": round(x, 1), "y": round(y, 1)})


def install_cursor_hooks() -> None:
    orig_click = DefaultActionWatchdog._click_element_node_impl
    orig_type = DefaultActionWatchdog._input_text_element_node_impl
    orig_coord = DefaultActionWatchdog._click_on_coordinate

    async def click(self, element_node, *a, **kw):
        if (p := await _node_screen_point(self, element_node)):
            await _lead(*p, "click", _label(element_node))
        return await orig_click(self, element_node, *a, **kw)

    async def type_(self, element_node, text, *a, **kw):
        if (p := await _node_screen_point(self, element_node)):
            shown = "••••" if kw.get("is_sensitive") else text
            await _lead(*p, "typing", _label(element_node), shown[:60])
        return await orig_type(self, element_node, text, *a, **kw)

    async def coord(self, coordinate_x, coordinate_y, *a, **kw):
        try:
            cdp_session = await self.browser_session.get_or_create_cdp_session()
            ox, oy = await _viewport_origin(self.browser_session, cdp_session)
            await _lead(ox + coordinate_x, oy + coordinate_y, "click")
        except Exception as exc:
            send({"ev": "log", "text": f"cursor coord failed: {exc}"})
        return await orig_coord(self, coordinate_x, coordinate_y, *a, **kw)

    DefaultActionWatchdog._click_element_node_impl = click
    DefaultActionWatchdog._input_text_element_node_impl = type_
    DefaultActionWatchdog._click_on_coordinate = coord


# ---- human in the loop -----------------------------------------------------------------------

async def _read_answer() -> str:
    loop = asyncio.get_running_loop()
    line = await loop.run_in_executor(None, sys.stdin.readline)
    try:
        return str(json.loads(line).get("answer", "")).strip()
    except Exception:
        return line.strip()


def make_tools() -> Tools:
    tools = Tools()

    @tools.action("Ask the human a question when you truly need their decision. Give 2-4 concrete options; "
                  "they may also answer in their own words.")
    async def ask_human(question: str, options: list[str]) -> str:
        send({"ev": "ask", "question": question, "options": options[:4]})
        answer = await _read_answer()
        return f"The human answered: {answer}"

    return tools


# ---- main --------------------------------------------------------------------------------------

async def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--cdp-url", required=True)
    p.add_argument("--task", required=True)
    p.add_argument("--model", default=os.environ.get("HIVE_BROWSER_MODEL", "claude-haiku-5-5"))
    p.add_argument("--max-steps", type=int, default=25)
    args = p.parse_args()

    logging.getLogger("browser_use").setLevel(logging.WARNING)
    install_cursor_hooks()
    session = BrowserSession(cdp_url=args.cdp_url, keep_alive=True)
    llm = HiveChatAnthropic(model=args.model, api_key=os.environ.get("ANTHROPIC_API_KEY"))
    state = {"steps": 0}

    async def on_step(browser_state, model_output, step: int) -> None:
        state["steps"] = step
        goal = ""
        try:
            goal = (model_output.current_state.next_goal or model_output.current_state.memory or "").strip()
        except Exception:
            pass
        send({"ev": "status", "text": goal[:90] or f"Step {step}", "progress": min(0.95, step / args.max_steps)})

    agent = Agent(task=args.task, llm=llm, browser_session=session, tools=make_tools(),
                  extend_system_message=SAFETY, register_new_step_callback=on_step,
                  use_judge=False, enable_signal_handler=False, max_actions_per_step=4,
                  calculate_cost=True, generate_gif=False)
    try:
        history = await agent.run(max_steps=args.max_steps)
        result = history.final_result() or ""
        usage = getattr(history, "usage", None)
        tokens = {}
        if usage is not None:
            for k in ("total_prompt_tokens", "total_completion_tokens", "total_cost"):
                if hasattr(usage, k):
                    tokens[k] = getattr(usage, k)
        # ok = the agent finished and reported back (it may still say part of the task wasn't possible).
        send({"ev": "done", "ok": bool(history.is_done() and result), "success": history.is_successful(),
              "result": result, "steps": len(history.history), "tokens": tokens})
    except Exception as exc:
        send({"ev": "done", "ok": False, "result": f"error: {exc}", "steps": state["steps"], "tokens": {}})
    finally:
        try:
            await session.stop()
        except Exception:
            pass


if __name__ == "__main__":
    asyncio.run(main())
