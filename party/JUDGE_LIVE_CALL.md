# Live segment: Hive calls the judge (~20 seconds, after the party video)
*Goal: live, un-fakeable proof of the Photon voice agent + voice → text continuity. No third party involved.*

## Setup (before the judge arrives)
- Cake agent's voice profile loaded with the **judge-demo prompt** (below)
- The party's real call summary loaded as context (so it can reference the matcha cake)
- A text field in the Hive app to enter the judge's number (don't store it after the demo)

## Script
**You:** "That bakery call was recorded yesterday. Want to see it live? If you're okay with it, Hive can call your phone right now. It'll say it's an AI, and I won't keep your number."
→ judge agrees → type the number → **Call**.

**Hive (on the judge's phone):**
> "Hi! This is Hive's Cake agent. I'm an AI, calling as part of Lucas's LA Hacks demo. I just ordered a matcha cake for Maya's surprise party. Is there anything you'd like me to add to the order, like a message on the cake?"

Judge says something (e.g. "add 'congrats on winning'") →
> "Love it, I'll add that. I'll text you a summary now. Thanks for judging!"

**~5 seconds later, a text arrives on the judge's phone (Photon SMS):**
> 🎂 Hive: Thanks for the chat! Summary: matcha cake for Maya, writing now "Happy 21st Maya 🎉" + your note "congrats on winning". (Demo only, nothing new was ordered.)

**You:** "Same agent, same memory, from a call to a text, live."

## Judge-demo voice prompt (differences from VOICE_AGENT_PROMPT.md)
- First sentence: AI disclosure + "part of Lucas's LA Hacks demo". **No recording.**
- Do NOT place or change any real order. Just acknowledge the request.
- Max 30 seconds. End warmly.
- Pass the judge's request into the text summary (proves the memory handoff).

## Visa-table variant (instead of a call)
Text the judge an approval request from Treasurer:
> 💰 Hive: The gift agent found a matcha whisk set for $19 (over its $15 cap). Approve or skip? (Demo, no real purchase.)

Their reply appears live on the projector (Treasurer's thread / notch), and the notch budget bar updates.

## Rules
- Ask before calling. Respect a "no."
- Delete the number from the engine after the segment.
- If the call fails: switch to the text variant immediately ("let's do it by text instead").
