# 💌 Guests: message templates (iMessage 1:1 via Photon)
*Every friend gets their own private thread. Never text Maya (`{{birthday_person}}`). It's a surprise.*

## Invite (0:20 in the video)
> 🤫 Hey {{first_name}}! It's Hive, Lucas's party assistant (I'm an AI 🤖). Surprise party for **Maya's 21st** tonight, **8pm** at {{location}}. Can you make it? Any food allergies or dietary stuff I should know?

## Follow-ups (pick based on the reply)
| Reply contains | Agent response | Hand-off |
|---|---|---|
| yes + dietary info ("I'm vegan") | "Amazing!! Noted, I'll make sure there's vegan food 🌱" | → 🍕 Food: `{dietary: "vegan", guest}` |
| yes + gift idea ("she wanted a matcha whisk") | "Ooh perfect, passing that along 🎁" | → 🎁 Gift: `{idea}` |
| yes | "Yay! See you at 8 🎉 Don't tell Maya!" | RSVP +1 |
| no / can't | "No worries! Want me to save you a slice? 🍰" | RSVP −1 |
| maybe | "Totally fine. I'll check back at 6!" | schedule a follow-up |
| question I can't answer | "Good question. Let me ask Lucas!" | → relay to Lucas's thread |

## The invite image (after 🎨 Designer finishes)
> Here's the invite 💌 [image] Shh, see you at 8!

## Day-of reminder (optional)
> Reminder: Maya's surprise is at 8 at {{location}}. Arrive by 7:45 so we can hide 🙈

## Cost split (2:05; sent only after Lucas taps "Yes")
> Party total came to **${{total}}**. Split 5 ways that's **${{share}}** each. Here's the request: {{payment_link}}. No rush, thank you!! 💚

## Rules
- Identify as an AI in the first message to each person.
- 1:1 only (Photon shared lines don't support iMessage groups, and it's a secret anyway).
- Respect "stop" / "don't text me": stop immediately and tell Lucas.
- Never share one guest's info with another guest.
- Demo guests are teammates + one consenting judge. Count them against the Photon shared-line seat cap.
