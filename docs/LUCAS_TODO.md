# Things only you can do (in priority order)

## Right away
- [ ] **Install Xcode** from the App Store (10GB+, takes a while). It's needed for WebDriverAgent (iPad Plan B). Only the Command Line Tools are installed now.
- [ ] **Run the Universal Control test** with the iPad: `swift docs/uc_test.swift right` (from the repo root). It needs Accessibility permission for your terminal.
- [ ] **Pick and visit the bakery near UCLA.** Arrange the AI call for the **Saturday recording** (before they close). Scripts are in `party/BAKERY_CALL.md`.
- [ ] **Sign up for Photon 2.0** (free) at app.photon.codes → create a project → add iMessage (shared line) + an SMS number + a Voice profile. In the dashboard, check:
  - [ ] the **seat cap** on the shared iMessage line (how many friends Guests can text)
  - [ ] whether each project gets its own handle (separate contact per agent?)

## API keys (put them in `engine/.env`, never commit)
- [ ] `ANTHROPIC_API_KEY`
- [ ] `GEMINI_API_KEY` (logo / invite autocomplete)
- [ ] `ELEVENLABS_API_KEY` (or Retell) for the voice agent
- [ ] `TELEGRAM_BOT_TOKEN`(s) from @BotFather: one per agent if we want separate identities in the group
- [ ] Photon project API key (`pho_sk_...`)
- [ ] Sentry DSN for `demo-world/product`

## Accounts for the demos
- [ ] Demo X/LinkedIn account for the Social agent
- [ ] Vercel project for `demo-world/site`
- [ ] Supabase project for the waitlist (or any form backend)
- [ ] DoorDash + Target logged in on a **dedicated Chrome profile** for agents, with a saved payment method or a **hard-limit virtual card** (~$100 cap)

## Team
- [ ] Assign roles A–D (overview §15)
- [ ] Decide the startup name / domain (demo-world has a placeholder)
- [ ] Line up the 4 "friends" phones + ask a judge if they're up for the live call

## iPad status (2026-10-17)
- The iPad shows up over USB (A14 chip, supports Universal Control). Accessibility is granted for the terminal.
- `uc_test.swift` ran 3× → **nothing appeared on the iPad**. But the **real trackpad doesn't cross either**, so Universal Control isn't linked yet; the test result doesn't count.
- To do: make sure the iPad uses the same Apple ID as the Mac; turn on Handoff on both; turn on iPad Settings → AirPlay & Continuity → Cursor and Keyboard; try Control Center → Display → "Link Keyboard and Mouse". Then rerun the test. If it still fails → Plan B (Xcode + WebDriverAgent).
