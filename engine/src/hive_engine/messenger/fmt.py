"""Text formatting and reply parsing for the iMessage thread (pure functions, no I/O)."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Emoji and pictographs (incl. variation selectors / ZWJ). The thread is plain text: agents are
# identified by a "Name:" prefix, not by colored circles.
_EMOJI = re.compile(
    "["
    "\U0001F000-\U0001FAFF"  # pictographs, emoticons, transport, symbols & pictographs ext.
    "\U00002600-\U00002712\U00002714-\U00002716\U00002718-\U000027BF"  # misc symbols, dingbats (keeps ✓ ✗)
    "\U00002B00-\U00002BFF"  # arrows/stars (⭐ etc.)
    "\U0001F1E6-\U0001F1FF"  # flags
    "‍️⃣"
    "]+"
)


def strip_emoji(text: str) -> str:
    return re.sub(r"[ \t]{2,}", " ", _EMOJI.sub("", text)).strip()


SPEAKERS = {"Hive", "Conductor"}

# Texts stay short and scannable: one sentence per update, a few status emoji at the front only.
ICON = {"added": "➕", "done": "✅", "question": "❓", "approval": "💳", "call": "📞", "warn": "⚠️",
        "finish": "🏁", "ok": "👍", "live": "👀", "post": "📸", "stop": "🛑"}
_WARN = re.compile(r"(?i)\b(couldn'?t|could not|failed|blocked|error|partial|unable|stuck|timed out)\b")


def brief(text: Any, n: int = 120, first_sentence: bool = True) -> str:
    """First sentence (or line) of an agent's text, emoji removed, capped at n characters."""
    t = strip_emoji(str(text or ""))
    t = re.sub(r"\s+", " ", t.split("\n")[0]).strip()
    m = re.match(r"(.+?[.!?])\s+[A-Z]", t) if first_sentence else None
    if m and len(m.group(1)) >= 12:
        t = m.group(1)
    t = t.rstrip(" ") if t.endswith("?") else t.rstrip(" .")
    return t if len(t) <= n else t[: n - 1].rstrip(" ,;:") + "…"


def tagged(icon_key: str, line: str) -> str:
    return f"{ICON[icon_key]} {line}"


def warn_or(line: str, text: str) -> str:
    """Prefix ⚠️ when an update reports a failure or partial result; plain otherwise."""
    return tagged("warn", line) if _WARN.search(text) else line


def prefix(name: str, text: str, known: set[str] | frozenset[str] = frozenset()) -> str:
    """'Checker: …' — unless the text already starts with a speaker prefix ('Conductor: …')."""
    text = strip_emoji(text)
    # Names can have spaces/digits ("Pricer 3", "Candidate Pricer"); don't double them.
    while text.startswith(f"{name}: "):
        text = text[len(name) + 2:]
    if any(text.startswith(f"{k}: ") for k in known if " " in k):
        return text
    m = re.match(r"^([A-Z][\w]{0,20}):\s", text)
    if m and (m.group(1) == name or m.group(1) in SPEAKERS or m.group(1) in known):
        return text
    return f"{name}: {text}"


@dataclass
class Question:
    agent: str
    name: str
    question: str
    options: list[str]
    details: list[str] = field(default_factory=list)
    kind: str = "choice"            # "choice" | "approval"
    amount: float | None = None
    image: str | None = None
    asked_at: float = 0.0


def question_from_event(agent: str, name: str, data: dict[str, Any], ts: float) -> Question:
    opts = [str(o) for o in (data.get("options") or [])]
    details = [str(d) for d in (data.get("details") or [])]
    amount = data.get("amount")
    return Question(
        agent=agent, name=name, question=strip_emoji(str(data.get("question") or "Need your input")),
        options=opts, details=details, kind=str(data.get("kind") or "choice"),
        amount=float(amount) if isinstance(amount, (int, float)) else None,
        image=data.get("image"), asked_at=ts,
    )


def format_question(q: Question) -> str:
    """Claude Code–style: numbered best options, then 'or tell me something else'."""
    if q.kind == "post":  # publishing to a real social account: explicit YES only
        return f"{ICON['post']} {q.name}: {q.question.rstrip('?. ')}?\nReply YES or NO"
    if q.kind == "call":  # dialing a real business: explicit YES only (like spending)
        return f"{ICON['call']} {q.name}: {q.question.rstrip('?. ')}?\nReply YES or NO"
    if q.kind == "approval":
        what = q.question.rstrip("?. ")
        if q.amount is not None and "$" not in what:
            what = f"Approve ${q.amount:,.2f} for {what}"
        return f"{ICON['approval']} {q.name}: {what}?\nReply YES or NO"
    lines = [f"{ICON['question']} {q.name}: {brief(q.question, 200, first_sentence=False)}"]
    if q.options:
        for i, opt in enumerate(q.options, 1):
            note = q.details[i - 1] if i - 1 < len(q.details) and q.details[i - 1] else ""
            lines.append(f"{i}. {brief(opt, 60)}" + (f" ({brief(note, 50)})" if note else ""))
        pick = "1 or 2" if len(q.options) == 2 else f"1–{len(q.options)}"
        lines += ["", f"Reply {pick}, or type your own"]
    return "\n".join(lines)


@dataclass
class Reply:
    """How a human text resolves against a pending question."""
    choice: str | None          # the option (or raw text) to send as `answer`
    free_text: bool = False
    rejected: bool = False      # approval answered with something other than YES/NO
    matched_index: int | None = None


_NUM = re.compile(r"^\s*(?:#|option\s*)?(\d{1,2})\s*[.)!]?\s*$", re.I)


def _price(s: str) -> str | None:
    m = re.search(r"\$?\s*(\d+(?:\.\d+)?)\s*([kKmMbB])?", s)
    return (m.group(1) + (m.group(2) or "").upper()) if m else None


def parse_reply(q: Question, text: str) -> Reply:
    t = text.strip()
    if q.kind in ("approval", "call", "post"):
        if re.fullmatch(r"(?i)\s*yes[.!]*\s*", t):
            return Reply("YES")
        if re.fullmatch(r"(?i)\s*(no|nope|cancel|stop)[.!]*\s*", t):
            return Reply("NO")
        return Reply(None, rejected=True)
    m = _NUM.match(t)
    if m:
        i = int(m.group(1))
        if 1 <= i <= len(q.options):
            return Reply(q.options[i - 1], matched_index=i - 1)
    for i, opt in enumerate(q.options):  # typed the option itself ("$29", "29", "$4b")
        if t.lower() == opt.lower() or (_price(t) and _price(t) == _price(opt) and len(t) <= len(opt) + 4):
            return Reply(opt, matched_index=i)
    return Reply(t, free_text=True)


@dataclass
class Inbound:
    kind: str                   # "mention" | "everyone" | "show" | "start" | "pause" | "resume" | "plain"
    agent: str | None = None    # resolved agent id for mentions
    text: str = ""
    scenario: str | None = None


_MENTION = re.compile(r"^\s*@(\w+)[\s,:]*(.*)$", re.S)
_SHOW = re.compile(r"(?i)^(show me|watch|live|let me see|show)\b")


def classify(text: str, resolve) -> Inbound:
    """resolve(name) -> agent id or None."""
    t = text.strip()
    m = _MENTION.match(t)
    if m:
        who, rest = m.group(1), m.group(2).strip()
        if who.lower() in ("everyone", "all", "hive", "team"):
            if re.fullmatch(r"(?i)(pause|stop|hold on|wait)[.!]*", rest):
                return Inbound("pause", text=rest)
            if re.fullmatch(r"(?i)(resume|go|continue|carry on)[.!]*", rest):
                return Inbound("resume", text=rest)
            return Inbound("everyone", text=rest or t)
        aid = resolve(who)
        if aid and _SHOW.match(rest):
            return Inbound("show", agent=aid, text=rest)
        if aid:
            return Inbound("mention", agent=aid, text=rest)
        return Inbound("plain", text=t)
    low = t.lower()
    if re.fullmatch(r"(start|run|go)( (the )?)?(pitch( in 5| in five)?|demo)?[.!]*", low):
        scen = "demo_sim" if "demo" in low else "pitch_in_5"
        return Inbound("start", text=t, scenario=scen)
    if re.fullmatch(r"(start|run|plan)( the)? (surprise )?party[.!]*", low):
        return Inbound("start", text=t, scenario="party")
    if re.fullmatch(r"(pause|stop|hold on)[.!]*", low):
        return Inbound("pause", text=t)
    if re.fullmatch(r"(resume|continue|carry on)[.!]*", low):
        return Inbound("resume", text=t)
    return Inbound("plain", text=t)
