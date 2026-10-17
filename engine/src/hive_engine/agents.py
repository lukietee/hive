"""Agent registry — mirrors the table in docs/CONTRACT.md."""

AGENTS: dict[str, dict[str, str]] = {
    "builder":   {"name": "Builder",   "color": "#34C759", "emoji": "🟢"},
    "fixer":     {"name": "Fixer",     "color": "#FF3B30", "emoji": "🔴"},
    "web":       {"name": "Web",       "color": "#0A84FF", "emoji": "🔵"},
    "deck":      {"name": "Deck",      "color": "#FFCC00", "emoji": "🟡"},
    "social":    {"name": "Social",    "color": "#AF52DE", "emoji": "🟣"},
    "checker":   {"name": "Checker",   "color": "#E5E5EA", "emoji": "⚪"},
    "design":    {"name": "Design",    "color": "#FF9F0A", "emoji": "🎨"},
    "treasurer": {"name": "Treasurer", "color": "#30D158", "emoji": "💰"},
    "guests":    {"name": "Guests",    "color": "#FF375F", "emoji": "💌"},
    "cake":      {"name": "Cake",      "color": "#FFD60A", "emoji": "🎂"},
    "food":      {"name": "Food",      "color": "#FF6B35", "emoji": "🍕"},
    "caller":    {"name": "Caller",    "color": "#64D2FF", "emoji": "📞"},
}


def find_agent_by_name(text: str) -> str | None:
    """Resolve '@Web' / 'web' / 'Web' to an agent id."""
    t = text.strip().lstrip("@").lower()
    for agent_id, meta in AGENTS.items():
        if t in (agent_id, meta["name"].lower()):
            return agent_id
    return None
