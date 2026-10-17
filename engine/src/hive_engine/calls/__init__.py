"""Phone calls: an ElevenLabs hosted voice agent dialing out through Photon's SIP voice line.

    await place_call(agent, to=..., label=..., goal=..., context=...)   → CallResult

Bus events (docs/CONTRACT.md, "Calls"): call_started, call_state, call_transcript, call_ended.
Each finished call is stored by calls/memory.py so the iMessage layer can answer follow-ups.
"""

from .caller import CallResult, place_call
from .memory import CallMemory

__all__ = ["CallMemory", "CallResult", "place_call"]
