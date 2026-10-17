# 💰 Treasurer: spending rules (Visa "Trust & Responsibility" story)

## Budget
| Agent | Cap |
|---|---|
| 🍕 Food (incl. party supplies, same DoorDash order) | $60 + $25 supplies = $85 |
| 🎂 Cake | $45 |
| 🎁 Gift (if kept) | $20 |
| **Total** | **$150** |

*Real money cap for the recording: ≤ $100 actually charged (use a virtual card with a hard limit).*

## Approval rules
1. **Under its cap:** auto-approve, stamp ✓ in the overlay, log it, text a one-liner ("🍕 Food: $54 ✓").
2. **Over its cap by ≤ $10:** **ask the human** with options: approve / swap (cheaper alternative) / cancel item.
   > 💰 Supplies is $6 over its $25 cap. Approve, or swap balloons for streamers?
3. **Over by > $10, or over the total budget:** block; agent must find alternatives first.
4. **Every final checkout** ("Place order") needs a ✓ from the Treasurer. The browser agent can't click it otherwise.
5. **Nothing irreversible without a log entry:** item list, store, total, timestamp, approving rule or human reply.

## Card & data policy
- **The model never sees card numbers.** Checkout uses the payment method already saved in the store account (DoorDash/Target) or a capped virtual card. The browser agent only clicks "Place order"; it never reads or types card fields.
- Redact anything that looks like a card number from screenshots sent to the model or the chat.
- Calls: payment at pickup only; the voice agent never discusses card details.
- Guests' personal info (dietary needs, etc.) is used only for this party.

## Ledger & split
- Live budget bar in the notch: `spent / total`, plus per-agent cap chips.
- End: receipt card (items, stores, totals) + split:
  > 💰 $136 of $150 spent. Split 5 ways = $27.20 each. Send requests?
- On "Yes": Guests texts each friend their share + payment link.

## Demo script beats
- 0:10: caps appear in the notch
- 1:10: ① ✓ / ② ✗ stamps → the "swap" question
- 1:55: approves "Place order"
- 2:05: split
