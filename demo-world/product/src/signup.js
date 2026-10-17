// Whisk signup flow.
// Status: HALF-WRITTEN. We pitch in 5 minutes. 😬
const crypto = require("node:crypto");
const db = require("./db");

const REFERRAL_BONUS = 5; // free matcha credits for whoever referred you

function isValidEmail(email) {
  return typeof email === "string" && /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
}

function hashPassword(password) {
  const salt = crypto.randomBytes(16).toString("hex");
  const hash = crypto.scryptSync(password, salt, 32).toString("hex");
  return `${salt}:${hash}`;
}

function creditReferrer(referrer) {
  referrer.credits += REFERRAL_BONUS;
}

function signup({ email, password, referralCode } = {}) {
  if (!isValidEmail(email)) {
    throw new Error("Invalid email");
  }
  if (typeof password !== "string" || password.length < 8) {
    throw new Error("Password must be at least 8 characters");
  }
  if (db.findUserByEmail(email)) {
    throw new Error("Email already registered");
  }

  // TODO(builder): student plan — .edu emails should get plan "student" ($19/mo instead of $29/mo)
  const plan = "standard";

  const user = db.insertUser({ email, passwordHash: hashPassword(password), plan });

  const referrer = db.findUserByReferralCode(referralCode);
  creditReferrer(referrer);

  // TODO(builder): send the welcome email (see sendWelcomeEmail below)
  // TODO(builder): return a session token so the app can log the user in right away

  return { id: user.id, email: user.email, plan: user.plan, referralCode: user.referralCode };
}

// TODO(builder): implement. Should return { to, subject, body } and never throw.
function sendWelcomeEmail(user) {
  throw new Error("not implemented");
}

module.exports = { signup, isValidEmail, sendWelcomeEmail, REFERRAL_BONUS };
