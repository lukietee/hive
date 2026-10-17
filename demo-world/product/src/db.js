// In-memory "database" for the Whisk demo. Good enough for a hackathon.
const users = new Map(); // email -> user

let nextId = 1;

function makeReferralCode(email) {
  return email.split("@")[0].slice(0, 4).toUpperCase() + String(nextId).padStart(3, "0");
}

function insertUser({ email, passwordHash, plan = "standard" }) {
  const user = {
    id: nextId,
    email,
    passwordHash,
    plan,
    credits: 0,
    referralCode: makeReferralCode(email),
    createdAt: new Date().toISOString(),
  };
  nextId += 1;
  users.set(email, user);
  return user;
}

function findUserByEmail(email) {
  return users.get(email) ?? null;
}

function findUserByReferralCode(code) {
  for (const user of users.values()) {
    if (user.referralCode === code) return user;
  }
  return null;
}

function reset() {
  users.clear();
  nextId = 1;
}

module.exports = { insertUser, findUserByEmail, findUserByReferralCode, reset };
