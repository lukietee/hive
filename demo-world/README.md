# Demo world: "Pitch in 5"
**Whisk: matcha, delivered to your dorm.** A fictional startup whose pitch starts in 5 minutes and nothing is finished. Hive's agents finish it live. All numbers are illustrative demo data.

## Assets & who works on what
| Asset | Path | Planted state | Agent(s) | Mac window |
|---|---|---|---|---|
| Product API | `product/` | Signup half-written (student plan, welcome email, session token TODOs); **test 3 fails**; null-user bug (`creditReferrer(null)`) | 🟢 Builder, 🔴 Fixer | ① VS Code |
| Product solution | `product/SOLUTION.md` | Intended fixes (rehearsal only, keep out of agent context) | — | — |
| Landing page | `site/index.html`, `site/styles.css` | Hero headline overflows; "See how it works" button knocked off; `logo.png` missing; "TODO: pricing" with an old **$39** note; waitlist form unwired | 🔵 Web, ⚪ Checker | ② Chrome |
| Finished site (backup) | `site/FINISHED/` | Target state: fixed hero, logo, $29 / $19 student pricing, waitlist (Supabase or local fallback) | — | — |
| Pitch deck | `deck/pitch.pptx` (from `deck/make_deck.py`) | 10 slides; **slides 3, 5, 6, 7 blank** (red TODO text + dashed `img_slot` boxes); logo slot on slide 1, URL/QR slots on slide 10 | 🟡 Deck | ③ Deck Viewer |
| Deck fill plan | `deck/deck_plan.json` | Final value for every named shape + dependencies + the $2B/$4B check-in | 🟡 Deck | — |
| Market notes | `research/market_notes.md` | Two conflicting estimates ($2B vs $4B) so the check-in is real | 🟡 Deck | — |
| Launch post | `social/draft.md` | Rambling draft, no link/image, "TODO" | 🟣 Social | ④ Chrome (X tab) |
| Logo brief | `logo/BRIEF.md` | What to sketch in Procreate + the Gemini prompt + fallbacks | 🎨 Design | iPad |

## Planted coordination moments
- **Deck ← Builder:** slide 5 needs screenshots of the working product.
- **Web / Deck / Social ← Design:** everyone needs the logo.
- **Social ← Web:** needs the live URL.
- **⚪ Checker:** site starts with the old **$39** note, deck plan says **$29**, so Checker flags it and Web fixes it.
- **🟡 Deck → human:** "Slide 6 market size: $2B or $4B?" (from `research/market_notes.md`).

## Commands
```
cd product && npm test     # 2 pass, test 3 fails, 2 todo
cd product && npm start    # API on :3000 (triggers the bug without a referral code)
cd deck && uv run --no-project --python 3.12 --with python-pptx python make_deck.py   # regenerate pitch.pptx
open site/index.html       # the broken page
```

## Reset before each rehearsal
- `git checkout -- demo-world/` (once committed), or regenerate the deck with `make_deck.py`
- Delete `site/logo.png` if a previous run created it
- In Procreate, show the `sketch` layer again and delete the inserted logo layer
