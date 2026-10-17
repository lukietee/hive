// Tiny HTTP server so the signup bug can surface as a real 500 (and in Sentry, once wired up).
// Run: node src/server.js   →   POST http://localhost:3000/signup  {"email","password","referralCode"?}
const http = require("node:http");
const { signup } = require("./signup");

// TODO(fixer): initialize Sentry here (SENTRY_DSN env var) so unhandled errors are reported.

const server = http.createServer((req, res) => {
  if (req.method === "POST" && req.url === "/signup") {
    let body = "";
    req.on("data", (chunk) => (body += chunk));
    req.on("end", () => {
      try {
        const user = signup(JSON.parse(body || "{}"));
        res.writeHead(201, { "content-type": "application/json" });
        res.end(JSON.stringify(user));
      } catch (err) {
        console.error(err);
        res.writeHead(500, { "content-type": "application/json" });
        res.end(JSON.stringify({ error: err.message }));
      }
    });
    return;
  }
  res.writeHead(404);
  res.end();
});

const port = Number(process.env.PORT) || 3000;
server.listen(port, () => console.log(`Whisk API on http://localhost:${port}`));
