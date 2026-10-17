# Whisk API (demo product)
**Whisk: matcha delivered to your dorm.** A fictional startup for Hive's "Pitch in 5" demo.

Plain Node 24, no dependencies.

```
npm test        # node --test   → test 3 fails on purpose
npm start       # POST http://localhost:3000/signup
```

## The planted state (5 minutes before the pitch)
| What | Where | Owner agent |
|---|---|---|
| Student plan for `.edu` emails not done | `src/signup.js` TODO + test 4 (todo) | 🟢 Builder |
| Welcome email not done | `sendWelcomeEmail` throws "not implemented" | 🟢 Builder |
| Session token not returned | `signup()` TODO + test 5 (todo) | 🟢 Builder |
| **Null-user bug**: signing up without a referral code crashes with `TypeError: Cannot read properties of null (reading 'credits')` | `creditReferrer(referrer)` in `src/signup.js` | 🔴 Fixer (via Sentry) |
| Sentry not initialized | `src/server.js` TODO | 🔴 Fixer / setup |

Current `npm test`: tests 1–2 pass, **test 3 fails**, tests 4–5 are `todo`.

See `SOLUTION.md` for the intended end state (rehearsal only, so agents don't read it during the demo).
