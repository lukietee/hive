# Bakery call: pre-arrangement + call scripts (🎂 Cake agent)

## 1. Pre-arrangement (do this in person, before recording)
**Pick a bakery** within ~15 minutes of JWAC that sells **cakes from the display case** and will add writing. Custom cakes usually need 24–48h, so don't ask for one.

**Check the closing time.** The recording has to happen at least **90 minutes before close** (call + pickup + slack).

**What to say at the counter (≈1 minute):**
> "Hi! We're UCLA students at LA Hacks, a hackathon this weekend. We built an AI assistant that plans parties, and part of it is an AI voice agent that calls a bakery to order a cake. Could we have it call you today at about **[TIME]** to order a real cake for pickup? We'll pay for it and pick it up, it's a real order. It'll say up front that it's an AI and that the call is being recorded for our demo. Would that be okay? Who should we expect to answer?"

**Get / confirm:**
- [ ] Their OK to receive the call **and to be recorded** (ask: "Is it okay if we include your voice in our demo video?" If not, we'll mute their side in the video and show the transcript only.)
- [ ] Phone number the agent should call, and the name of who'll answer
- [ ] Which matcha (or green tea / pistachio fallback) cake is in the case, size, price
- [ ] Writing allowed? Max characters? Can they do "Happy 21st Maya 🎉" (or "Happy 21st Maya!" if no emoji)?
- [ ] Pickup time options (target: ~1 hour after the call)
- [ ] Payment at pickup (simplest; the agent never handles a card on the phone)
- [ ] The best time for a **second, short callback** (to add the 🎉)

Leave a thank-you: bring them the finished demo video link, tag them in the Devpost (with permission).

## 2. The call (agent script: the voice agent improvises, but these beats must happen)
1. **Disclosure, first sentence (required):**
   > "Hi! This is Hive, an AI assistant calling on behalf of Lucas, who stopped by earlier today. Just so you know, I'm an AI and this call is being recorded for a hackathon demo. Is now still a good time?"
2. **Confirm context:** "Lucas mentioned you might have a matcha cake in the case today?"
3. **Order:** size → price → writing "Happy 21st Maya" → pickup time (~6pm or what they offered).
4. **Read-back:** "Just to confirm: one [size] matcha cake, writing 'Happy 21st Maya', pickup at [time], $[price], paid at pickup. Is that right?"
5. **Close:** "Thank you so much, have a great day!"

**Must NOT:** give or ask for card numbers; pretend to be human; agree to anything over the $45 cap without texting Lucas first (Treasurer rule); keep talking if they're busy (offer to call back).

## 3. After the call → text (memory handoff)
The agent texts Lucas (iMessage via Photon):
> 🎂 Cake: Confirmed with [name] at [bakery]: [size] matcha cake, "Happy 21st Maya", ready **[time]**, $[price] at pickup.

## 4. Callback (the Photon voice-continuity moment)
Lucas replies: *"can they add 🎉 to the writing?"* → the agent calls back **using the first call's details**:
> "Hi [name], it's Hive again, the AI assistant, still recording for the demo, about the matcha cake for **[time]** with 'Happy 21st Maya'. Could you add a little 🎉, or a party hat drawing, at the end of the writing? … Perfect, thank you!"

Then texts: *"🎂 Cake: Done. 🎉 added, still ready at [time]. ✓"*

## 5. Backup
If the bakery can't take the call at the recording time, a teammate answers a phone as "the bakery" and the video is labeled accordingly. The **live judge call** (JUDGE_LIVE_CALL.md) is the always-available live proof.

*Recording note: California generally requires the consent of all parties to record a confidential call. Get consent in person and again at the start of the call. Not legal advice; when in doubt, mute their side and show the transcript.*
