"""👁 Live agent view: Chrome screencasts of each agent's window + cursor, relayed to a phone page.

Page:  http://127.0.0.1:8766/live/      Relay: ws://127.0.0.1:8767   (see relay.py for the wire format)
"""

from .relay import LiveRelay, get_relay
from .stream import Screencast, attach, live_enabled

__all__ = ["LiveRelay", "Screencast", "attach", "get_relay", "live_enabled"]
