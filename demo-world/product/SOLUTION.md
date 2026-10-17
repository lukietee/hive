# SOLUTION (rehearsal reference: keep out of the agents' context during the demo)

## 🔴 Fixer: the null-user bug
**Symptom (Sentry / test 3):** `TypeError: Cannot read properties of null (reading 'credits')` at `creditReferrer`.

**Cause:** `findUserByReferralCode(undefined)` returns `null` when there's no or an unknown referral code, and `creditReferrer` assumes a user.

**Fix in `src/signup.js`:**
```js
const referrer = referralCode ? db.findUserByReferralCode(referralCode) : null;
if (referrer) creditReferrer(referrer);
```

## 🟢 Builder: finish the feature
```js
// student plan
const plan = email.toLowerCase().endsWith(".edu") ? "student" : "standard";

// welcome email
function sendWelcomeEmail(user) {
  return {
    to: user.email,
    subject: "Welcome to Whisk 🍵",
    body: `Your first matcha ships this week. Share your code ${user.referralCode} for free credits.`,
  };
}

// at the end of signup()
const sessionToken = crypto.randomBytes(24).toString("hex");
sendWelcomeEmail(user);
return { id: user.id, email: user.email, plan: user.plan, referralCode: user.referralCode, sessionToken };
```
Then remove `{ todo: ... }` from tests 4 and 5.

**Expected after both:** `npm test` → 5/5 pass.

## Sentry (optional setup before the demo)
`npm i @sentry/node`, then call `Sentry.init({ dsn: process.env.SENTRY_DSN })` at the top of `src/server.js`. Trigger the bug once beforehand with
`curl -XPOST localhost:3000/signup -d '{"email":"a@b.co","password":"matcha1234"}'`
so the issue already exists in Sentry when Fixer opens it.
