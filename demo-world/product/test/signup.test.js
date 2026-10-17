const { test, beforeEach } = require("node:test");
const assert = require("node:assert/strict");
const db = require("../src/db");
const { signup, REFERRAL_BONUS } = require("../src/signup");

beforeEach(() => db.reset());

test("1. rejects an invalid email", () => {
  assert.throws(() => signup({ email: "not-an-email", password: "matcha1234" }), /Invalid email/);
});

test("2. a valid referral code credits the referrer", () => {
  const ana = db.insertUser({ email: "ana@example.com", passwordHash: "x" });
  signup({ email: "ben@example.com", password: "matcha1234", referralCode: ana.referralCode });
  assert.equal(db.findUserByEmail("ana@example.com").credits, REFERRAL_BONUS);
});

test("3. signing up without a referral code creates the user", () => {
  const user = signup({ email: "cleo@example.com", password: "matcha1234" });
  assert.equal(user.email, "cleo@example.com");
  assert.equal(user.plan, "standard");
});

test("4. .edu emails get the student plan", { todo: "Builder: student plan not implemented yet" }, () => {
  const user = signup({ email: "dev@ucla.edu", password: "matcha1234" });
  assert.equal(user.plan, "student");
});

test("5. signup returns a session token", { todo: "Builder: session token not implemented yet" }, () => {
  const user = signup({ email: "eli@example.com", password: "matcha1234" });
  assert.equal(typeof user.sessionToken, "string");
});
