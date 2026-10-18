// Hive bridge: a tiny HTTP server inside VS Code so the Hive engine can drive this window exactly
// (scroll a line to the top, select lines, type an edit visibly, run a command in the terminal)
// instead of sending fragile keystrokes. Plain JS, no dependencies, loaded from a dedicated
// --extensions-dir, so the user's own VS Code setup is never touched.
const vscode = require("vscode");
const http = require("http");

let server;
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

function state(editor) {
  editor = editor || vscode.window.activeTextEditor;
  const cfg = vscode.workspace.getConfiguration("editor");
  const vr = editor && editor.visibleRanges.length ? editor.visibleRanges[0] : null;
  return {
    file: editor ? editor.document.uri.fsPath : null,
    top: vr ? vr.start.line + 1 : null,           // 1-based first visible line
    bottom: vr ? vr.end.line + 1 : null,
    lineHeight: cfg.get("lineHeight"),
    fontSize: cfg.get("fontSize"),
    terminalOpen: !!vscode.window.activeTerminal,
  };
}

async function open(path, line, above) {
  const doc = await vscode.workspace.openTextDocument(vscode.Uri.file(path));
  const editor = await vscode.window.showTextDocument(doc, { preview: false, preserveFocus: false });
  if (line) {
    const top = Math.max(0, line - 1 - (above ?? 2));
    editor.revealRange(new vscode.Range(top, 0, top, 0), vscode.TextEditorRevealType.AtTop);
    const p = new vscode.Position(line - 1, 0);
    editor.selection = new vscode.Selection(p, p);
    await sleep(120); // let visibleRanges catch up with the scroll
  }
  return editor;
}

async function typeEdit(body) {
  const editor = await open(body.path, null);
  const doc = editor.document;
  const text = doc.getText();
  const at = text.indexOf(body.old);
  if (at < 0) throw new Error(`text not found in ${body.path}: ${String(body.old).slice(0, 60)}`);
  const start = doc.positionAt(at);
  const end = doc.positionAt(at + body.old.length);
  const top = Math.max(0, start.line - (body.above ?? 2));
  editor.revealRange(new vscode.Range(top, 0, top, 0), vscode.TextEditorRevealType.AtTop);
  // 1) select what's being replaced, so the change reads on screen
  editor.selection = new vscode.Selection(start, end);
  await sleep(body.selectMs ?? 500);
  // 2) delete it, then type the new text a few characters at a time
  await editor.edit((e) => e.delete(new vscode.Range(start, end)), { undoStopBefore: true, undoStopAfter: false });
  let pos = start;
  const chunk = Math.max(1, body.chunk ?? 3);
  const delay = body.delayMs ?? 18;
  for (let i = 0; i < body.new.length; i += chunk) {
    const piece = body.new.slice(i, i + chunk);
    await editor.edit((e) => e.insert(pos, piece), { undoStopBefore: false, undoStopAfter: false });
    const off = doc.offsetAt(pos) + piece.length;
    pos = doc.positionAt(off);
    editor.selection = new vscode.Selection(pos, pos);
    if (delay) await sleep(delay);
  }
  if (body.save !== false) await doc.save();
  return { startLine: start.line + 1, endLine: pos.line + 1, ...state(editor) };
}

function terminal(name) {
  let t = vscode.window.terminals.find((x) => x.name === name);
  if (!t) t = vscode.window.createTerminal({ name, cwd: vscode.workspace.workspaceFolders?.[0]?.uri });
  return t;
}

const routes = {
  "GET /ping": async () => ({ ok: true, folder: vscode.workspace.workspaceFolders?.[0]?.uri.fsPath ?? null }),
  "GET /state": async () => state(),
  "POST /open": async (b) => state(await open(b.path, b.line, b.above)),
  "POST /select": async (b) => {
    const editor = await open(b.path, b.start, b.above);
    const end = b.end ?? b.start;
    const last = editor.document.lineAt(end - 1);
    editor.selection = new vscode.Selection(b.start - 1, 0, end - 1, last.text.length);
    return state(editor);
  },
  "POST /type": async (b) => typeEdit(b),
  "POST /revert": async (b) => {
    // Reload a file from disk (after the engine wrote it directly).
    const editor = await open(b.path, b.line, b.above);
    await vscode.commands.executeCommand("workbench.action.files.revert");
    return state(editor);
  },
  "POST /terminal": async (b) => {
    const t = terminal(b.name || "Hive");
    t.show(b.preserveFocus ?? true);
    if (b.cwd) t.sendText(`cd ${JSON.stringify(b.cwd)}`, true);
    if (b.clear) await vscode.commands.executeCommand("workbench.action.terminal.clear");
    t.sendText(b.cmd, true);
    return { ok: true };
  },
  "POST /hideTerminal": async () => {
    await vscode.commands.executeCommand("workbench.action.closePanel");
    return { ok: true };
  },
  "POST /command": async (b) => ({ result: await vscode.commands.executeCommand(b.id, ...(b.args || [])) ?? null }),
  "POST /close": async () => {
    setTimeout(() => vscode.commands.executeCommand("workbench.action.closeWindow"), 50);
    return { ok: true };
  },
};

function activate(context) {
  const port = vscode.workspace.getConfiguration("hive").get("port") || 8774;
  server = http.createServer((req, res) => {
    let raw = "";
    req.on("data", (c) => (raw += c));
    req.on("end", async () => {
      const route = routes[`${req.method} ${req.url.split("?")[0]}`];
      res.setHeader("Content-Type", "application/json");
      if (!route) {
        res.statusCode = 404;
        return res.end(JSON.stringify({ error: "no route" }));
      }
      try {
        const out = await route(raw ? JSON.parse(raw) : {});
        res.end(JSON.stringify(out));
      } catch (e) {
        res.statusCode = 500;
        res.end(JSON.stringify({ error: String(e && e.message || e) }));
      }
    });
  });
  server.on("error", (e) => console.error("hive bridge:", e));
  server.listen(port, "127.0.0.1");
  context.subscriptions.push({ dispose: () => server && server.close() });
}

function deactivate() {
  if (server) server.close();
}

module.exports = { activate, deactivate };
