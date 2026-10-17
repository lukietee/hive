"""A small editor + terminal page the code/checker workers show in their own Chrome window, so the
audience can watch them work. The page is rendered from state with page.evaluate (no files, no server),
and the agent's ghost cursor is pointed at the lines it just changed or the command it ran."""

from __future__ import annotations

import html
import json

PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>%TITLE%</title><style>
:root{--bg:#1e1f22;--side:#18191b;--bar:#2b2d30;--line:#2f3135;--text:#d4d4d8;--muted:#7c7f86;--add:#1f3d2a;--acc:%ACC%}
*{box-sizing:border-box}html,body{margin:0;height:100%;background:var(--bg);color:var(--text);
font:13px/1.5 -apple-system,BlinkMacSystemFont,sans-serif}
#app{display:grid;grid-template-rows:36px 1fr 32%;grid-template-columns:190px 1fr;height:100%}
#top{grid-column:1/3;display:flex;align-items:center;gap:10px;padding:0 12px;background:var(--bar);border-bottom:1px solid var(--line)}
#top b{font-weight:600}#dot{width:9px;height:9px;border-radius:50%;background:var(--acc)}#status{color:var(--muted);margin-left:auto;font-size:12px}
#side{background:var(--side);border-right:1px solid var(--line);overflow:auto;padding:6px 0}
#side div{padding:3px 12px;font:12px ui-monospace,Menlo,monospace;color:var(--muted);white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
#side div.on{color:var(--text);background:#ffffff10;border-left:2px solid var(--acc)}
#code{overflow:auto;font:12.5px/1.55 ui-monospace,Menlo,monospace;padding:6px 0}
#code .l{display:flex;white-space:pre}#code .n{width:44px;text-align:right;padding-right:12px;color:#55585e;flex:none}
#code .l.add{background:var(--add);box-shadow:inset 3px 0 var(--acc)}
#term{grid-column:2;border-top:1px solid var(--line);background:#141517;overflow:auto;padding:8px 12px;
font:12px/1.5 ui-monospace,Menlo,monospace;white-space:pre-wrap;color:#b9bcc2}
#term .cmd{color:#fff}#term .cmd:before{content:"$ ";color:var(--acc)}
#file{color:var(--muted);font:12px ui-monospace,Menlo,monospace}
</style></head><body><div id="app"><div id="top"><span id="dot"></span><b>%NAME%</b><span id="file"></span>
<span id="status"></span></div><div id="side"></div><div id="code"></div><div id="term"></div></div>
<script>
window.render=function(s){
 document.getElementById('status').textContent=s.status||'';
 document.getElementById('file').textContent=s.file||'';
 const side=document.getElementById('side');side.innerHTML='';
 (s.files||[]).forEach(f=>{const d=document.createElement('div');d.textContent=f;if(f===s.file)d.className='on';side.appendChild(d)});
 const code=document.getElementById('code');code.innerHTML='';
 const add=new Set(s.added||[]);
 (s.lines||[]).forEach((t,i)=>{const d=document.createElement('div');d.className='l'+(add.has(i+1)?' add':'');d.id='L'+(i+1);
  const n=document.createElement('span');n.className='n';n.textContent=i+1;const c=document.createElement('span');c.textContent=t||' ';
  d.appendChild(n);d.appendChild(c);code.appendChild(d)});
 const term=document.getElementById('term');term.innerHTML='';
 (s.term||[]).forEach(e=>{const d=document.createElement('div');d.className=e.cmd?'cmd':'';d.textContent=e.text;term.appendChild(d)});
 term.scrollTop=term.scrollHeight;
 if(s.focus){const el=document.getElementById(s.focus);if(el)el.scrollIntoView({block:'center'})}
};
</script></body></html>"""


def page_html(name: str, title: str, accent: str) -> str:
    return (PAGE.replace("%TITLE%", html.escape(title)).replace("%NAME%", html.escape(name))
            .replace("%ACC%", accent))


class Workbench:
    """State for one agent's editor window."""

    def __init__(self) -> None:
        self.status = ""
        self.file = ""
        self.files: list[str] = []
        self.lines: list[str] = []
        self.added: list[int] = []
        self.term: list[dict] = []
        self.focus: str | None = None

    def show_file(self, path: str, text: str, added: list[int] | None = None) -> None:
        self.file = path
        if path not in self.files:
            self.files.append(path)
        self.lines = text.splitlines()[:2000]
        self.added = added or []
        self.focus = f"L{self.added[0]}" if self.added else "L1"

    def log(self, text: str, cmd: bool = False) -> None:
        self.term.append({"text": text[-4000:], "cmd": cmd})
        self.term = self.term[-60:]

    def js(self) -> str:
        return "window.render(%s)" % json.dumps({
            "status": self.status, "file": self.file, "files": self.files[-40:], "lines": self.lines,
            "added": self.added, "term": self.term, "focus": self.focus})


def changed_lines(old: str, new: str) -> list[int]:
    """1-based line numbers in `new` that differ from `old`."""
    import difflib
    out: list[int] = []
    sm = difflib.SequenceMatcher(a=old.splitlines(), b=new.splitlines(), autojunk=False)
    for tag, _, _, j1, j2 in sm.get_opcodes():
        if tag in ("replace", "insert"):
            out.extend(range(j1 + 1, j2 + 1))
    return out
