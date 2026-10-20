"""Read-only live layer: a loopback server that streams the durable spine.

Deliberately small and boring: no framework, no build step, no write endpoints. The
server can read the journal, tail events over SSE and serve one live page. Every
mutation still goes through `clip` under the project lock.

Threat model: loopback only, and a per-session token so another local page cannot
read the studio. Nothing is served from the project directory except JSON.
"""

from __future__ import annotations

import json
import queue
import re
import secrets
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

from . import operations, sources, spine, studio

STREAM_INTERVAL = 0.5
HEARTBEAT_SECONDS = 10.0

PAGE = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Studio · live</title>
<style>
:root{--bg:#0a0f14;--panel:#111a22;--ink:#f2efe6;--muted:#8fa0ae;--gold:#d4ae6a;
--teal:#688f9d;--line:#1f2c37;--ok:#6fb585;--warn:#d9a441;--bad:#d4655f}
body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:1180px;margin:0 auto;padding:26px 22px 80px}
.kicker{color:var(--gold);text-transform:uppercase;letter-spacing:.15em;font-size:11px;font-weight:700}
h1{font-size:28px;margin:4px 0 14px}h2{font-size:13px;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);margin:22px 0 8px}
.grid{display:grid;grid-template-columns:340px 1fr;gap:16px}@media(max-width:900px){.grid{grid-template-columns:1fr}}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px}
.run{padding:8px 0;border-bottom:1px solid var(--line);font-size:13px;cursor:pointer}
.run:last-child{border:0}.run b{font-weight:600}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:11px;color:var(--muted)}
.tag{font-size:10px;text-transform:uppercase;letter-spacing:.07em;padding:1px 6px;border-radius:999px;border:1px solid var(--line);color:var(--muted)}
.tag.succeeded,.tag.approved{color:var(--ok);border-color:#2c5240}
.tag.failed,.tag.interrupted{color:var(--bad);border-color:#5b2f2f}
.tag.running{color:var(--teal);border-color:#26414d}.tag.waiting{color:var(--warn);border-color:#5b4a2a}
#log{height:62vh;overflow:auto;background:#0e161d;border:1px solid var(--line);border-radius:9px;padding:10px;font:12px/1.5 ui-monospace,Menlo,monospace}
#log div{padding:1px 0;border-bottom:1px solid #121c24}
.ev{color:var(--teal)}.out{color:var(--muted)}.err{color:var(--bad)}.meta{color:var(--gold)}
footer{margin-top:22px;color:var(--muted);font-size:12px}
</style></head><body><div class="wrap">
<div class="kicker">Studio · live</div><h1>Runs</h1>
<p class="mono">read-only · loopback · token in URL · writes remain CLI-only</p>
<div class="grid">
<div class="panel"><h2>Journal</h2><div id="runs">connecting…</div>
<h2>Projects</h2><div id="projects" class="mono"></div></div>
<div class="panel"><h2>Events</h2><div id="log"></div></div>
</div>
<footer>Every mutation goes through <span class="mono">clip</span> under the project lock and a content hash.
This page cannot approve, select, spend or edit.</footer>
</div>
<script>
const token = new URLSearchParams(location.search).get('token') || '';
const q = token ? ('?token=' + encodeURIComponent(token)) : '';
const log = document.getElementById('log');
let last = 0, selected = null;
function el(tag, cls, text){const n=document.createElement(tag); if(cls)n.className=cls; if(text!==undefined)n.textContent=text; return n;}
async function refresh(){
  const res = await fetch('/api/runs' + q);
  if(!res.ok) return;
  const data = await res.json();
  const box = document.getElementById('runs'); box.textContent='';
  if(!data.runs.length) box.append(el('div','mono','no runs yet — start one with a clip command'));
  for(const run of data.runs){
    const row = el('div','run');
    row.append(el('b',null,run.intent||run.id));
    row.append(document.createTextNode(' '));
    row.append(el('span','tag '+run.status,run.status));
    if(run.production) row.append(el('div','mono',run.production+' · '+run.id));
    row.onclick=()=>{selected=run.id; last=0; log.textContent='';};
    box.append(row);
  }
  const p = await fetch('/api/studio' + q);
  if(p.ok){
    const s = await p.json();
    document.getElementById('projects').textContent =
      s.productions.map(x=>x.slug+' — '+x.next_step).join('\\n');
  }
}
function stream(){
  const url = '/api/stream' + (token?'?token='+encodeURIComponent(token)+'&':'?') + 'after=' + last + (selected?('&run='+encodeURIComponent(selected)):'');
  const es = new EventSource(url);
  es.onmessage = (m) => {
    const ev = JSON.parse(m.data);
    last = Math.max(last, ev.seq);
    if(ev.run_id && !selected) selected = ev.run_id;
    const line = el('div', ev.type==='command.output'?'out':(ev.type.includes('failed')||ev.type.includes('interrupted')?'err':'ev'));
    line.textContent = '[' + (ev.type) + '] ' + (ev.payload && ev.payload.line ? ev.payload.line : JSON.stringify(ev.payload||{}));
    log.append(line); log.scrollTop = log.scrollHeight;
  };
  es.onerror = () => { es.close(); setTimeout(stream, 2000); };
}
refresh(); setInterval(refresh, 5000); stream();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    server_version = "clip-studio/0.1"

    def log_message(self, fmt, *args):  # keep stdout clean for the CLI
        return

    # -- helpers ---------------------------------------------------------- #
    def _authorised(self, query) -> bool:
        token = getattr(self.server, "token", None)
        if not token:
            return True
        supplied = (query.get("token") or [None])[0] or self.headers.get("X-Studio-Token")
        return secrets.compare_digest(str(supplied), token)

    def _json(self, payload, status=HTTPStatus.OK):
        body = json.dumps(payload, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _text(self, body: str, status=HTTPStatus.OK, content_type="text/html; charset=utf-8"):
        data = body.encode()
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(data)

    # -- routing ---------------------------------------------------------- #
    def do_GET(self):  # noqa: N802 - http.server contract
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if parsed.path == "/api/health":
            return self._json({"ok": True, "read_only": True})
        if not self._authorised(query):
            return self._json({"error": "token required"}, HTTPStatus.UNAUTHORIZED)
        if parsed.path == "/":
            return self._text(PAGE)
        if parsed.path == "/app":
            return self._text(APP)
        if parsed.path == "/api/status":
            with spine.connect(self.server.db) as conn:
                return self._json(spine.status(conn))
        if parsed.path == "/api/runs":
            limit = int((query.get("limit") or ["20"])[0])
            with spine.connect(self.server.db) as conn:
                return self._json({"runs": spine.run_list(conn, limit)})
        if parsed.path == "/api/events":
            after = int((query.get("after") or ["0"])[0])
            run = (query.get("run") or [None])[0]
            limit = int((query.get("limit") or ["200"])[0])
            with spine.connect(self.server.db) as conn:
                return self._json({"events": spine.event_list(conn, run, after, limit)})
        if parsed.path == "/api/studio":
            return self._json({"productions": studio.scan(self.server.projects_dir)})
        if parsed.path == "/api/sources":
            try:
                return self._json(
                    sources.scan(
                        self.server.sources_dir,
                        query=(query.get("q") or [None])[0],
                        min_seconds=_float(query, "min"),
                        max_seconds=_float(query, "max"),
                        limit=int((query.get("limit") or ["200"])[0]),
                    )
                )
            except ValueError as exc:
                return self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        if parsed.path == "/api/stream":
            return self._stream(query)
        return self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self):  # noqa: N802
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if not self._authorised(query):
            return self._json({"error": "token required"}, HTTPStatus.UNAUTHORIZED)
        if parsed.path != "/api/create":
            return self._json({"error": "unsupported write: only /api/create"}, HTTPStatus.METHOD_NOT_ALLOWED)
        length = int(self.headers.get("Content-Length") or 0)
        if length > 20_000:
            return self._json({"error": "payload too large"}, HTTPStatus.BAD_REQUEST)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self._json({"error": "invalid JSON"}, HTTPStatus.BAD_REQUEST)
        try:
            return self._json(self._create(body), HTTPStatus.CREATED)
        except (OSError, ValueError, KeyError) as exc:
            return self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def _create(self, body: dict) -> dict:
        """Create a production through the kernel: init copies the audio, then the cap."""
        from . import production as P

        title = str(body.get("title") or "").strip()
        audio = Path(str(body.get("audio") or "")).expanduser()
        if not title or not audio.is_file():
            raise ValueError("a title and an existing audio file are required")
        slug = str(body.get("slug") or "").strip() or title.casefold().replace(" ", "-")
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", slug):
            raise ValueError("slug must be lowercase letters, digits and dashes")
        root = self.server.projects_dir / slug
        if root.exists():
            raise ValueError(f"production {slug!r} already exists")
        P.init_project(
            root,
            audio,
            slug,
            body.get("aspect") or "16:9",
            int(body.get("fps") or 24),
            body.get("music_mode") or "vocal",
            workflow_version=2,
            title=title,
            renderer_backend="remotion",
        )
        cap = body.get("cap")
        if cap:
            from . import budget

            budget.set_budget(root, str(cap), body.get("note") or "created in studio")
        return {"created": slug, "title": title, "cap": cap}

    do_PUT = do_POST
    do_DELETE = do_POST
    do_PATCH = do_POST

    # -- server-sent events ----------------------------------------------- #
    def _stream(self, query):
        after = int((query.get("after") or ["0"])[0])
        run = (query.get("run") or [None])[0]
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        last_beat = time.monotonic()
        try:
            while True:
                with spine.connect(self.server.db) as conn:
                    events = spine.event_list(conn, run, after, 200)
                for event in events:
                    after = max(after, event["seq"])
                    payload = json.dumps(event, default=str)
                    self.wfile.write(f"data: {payload}\n\n".encode())
                if events:
                    last_beat = time.monotonic()
                elif time.monotonic() - last_beat > HEARTBEAT_SECONDS:
                    self.wfile.write(b": keep-alive\n\n")
                    last_beat = time.monotonic()
                self.wfile.flush()
                time.sleep(STREAM_INTERVAL)
        except (BrokenPipeError, ConnectionResetError):
            return


APP = """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Studio</title>
<style>
:root{--bg:#0a0f14;--panel:#111a22;--ink:#f2efe6;--muted:#8fa0ae;--gold:#d4ae6a;--teal:#688f9d;--line:#1f2c37;--ok:#6fb585;--bad:#d4655f}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:1240px;margin:0 auto;padding:26px 22px 80px}
.kicker{color:var(--gold);text-transform:uppercase;letter-spacing:.15em;font-size:11px;font-weight:700}
h1{font-size:30px;margin:4px 0 18px;letter-spacing:-.02em}
.grid{display:grid;grid-template-columns:400px 1fr;gap:18px}@media(max-width:900px){.grid{grid-template-columns:1fr}}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px}
h2{font-size:12px;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);margin:0 0 12px}
label{display:block;font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin:10px 0 4px}
input,select{width:100%;background:#0e161d;color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:8px 10px;font:inherit}
button{background:var(--gold);color:#0a0f14;border:0;border-radius:8px;padding:9px 14px;font:inherit;font-weight:700;cursor:pointer;margin-top:14px}
button:disabled{background:#2a3540;color:#7b8b98}
.row{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.card{border:1px solid var(--line);border-radius:12px;padding:14px;margin-bottom:10px;background:linear-gradient(180deg,#16222c,#111a22);cursor:pointer}
.card:hover{border-color:var(--gold)}
.card b{font-size:16px}.meta{color:var(--muted);font-size:12px;margin-top:4px}
.tag{font-size:10px;text-transform:uppercase;letter-spacing:.06em;border:1px solid var(--line);border-radius:999px;padding:1px 7px;color:var(--muted);margin-right:4px}
.tag.ok{color:var(--ok);border-color:#2c5240}.tag.warn{color:var(--gold);border-color:#4a3d25}.tag.bad{color:var(--bad);border-color:#5b2f2f}
#msg{font-size:12px;margin-top:10px;min-height:18px}#msg.err{color:var(--bad)}#msg.ok{color:var(--ok)}
.mono{font-family:ui-monospace,Menlo,monospace;font-size:11px;color:var(--muted)}
</style></head><body><div class="wrap">
<div class="kicker">Studio</div><h1>Create and organise</h1>
<div class="grid">
<div class="panel"><h2>New production</h2>
<label for="src">Source (liked, real tracks)</label><select id="src"></select>
<label for="title">Film title</label><input id="title" placeholder="Forward Ever">
<div class="row"><div><label for="aspect">Aspect</label><select id="aspect"><option>16:9</option><option>9:16</option></select></div>
<div><label for="fps">FPS</label><select id="fps"><option>24</option><option>30</option></select></div></div>
<div class="row"><div><label for="mode">Mode</label><select id="mode"><option>vocal</option><option>instrumental</option><option>music-led</option></select></div>
<div><label for="cap">Cap USD</label><input id="cap" type="number" value="5.00" step="0.01" min="0.01"></div></div>
<button id="create">Create production</button><div id="msg"></div>
<p class="mono" style="margin-top:12px">Creates via the clip kernel: byte-identical copy, project.json, budget. Nothing is generated or spent.</p>
</div>
<div class="panel"><h2>Productions</h2><div id="list">loading…</div></div>
</div></div>
<script>
const token=new URLSearchParams(location.search).get('token')||'';
const q=token?('?token='+encodeURIComponent(token)):'';
const hdr=token?{'X-Studio-Token':token}:{};
const msg=document.getElementById('msg');
function el(t,c,x){const n=document.createElement(t);if(c)n.className=c;if(x!==undefined)n.textContent=x;return n;}
async function loadSources(){
 const r=await fetch('/api/sources'+q); const d=await r.json();
 const sel=document.getElementById('src'); sel.textContent='';
 if(!d.tracks||!d.tracks.length){sel.append(el('option',null,'no source tracks found'));return;}
 for(const t of d.tracks){const o=el('option');o.value=t.audio;o.textContent=t.title+' · '+(t.seconds)+'s';sel.append(o);}
}
async function loadProjects(){
 const r=await fetch('/api/studio'+q); const d=await r.json();
 const box=document.getElementById('list'); box.textContent='';
 for(const p of d.productions){
  const c=el('div','card'); c.append(el('b',null,p.title));
  const m=el('div','meta'); m.textContent=p.duration.toFixed(0)+'s · '+p.shots+' shots · '+(p.spend.accounted_usd||'—')+' / '+(p.spend.cap_usd||'no cap')+' USD';
  c.append(m);
  const tags=el('div','meta');
  for(const [stage,state] of Object.entries(p.stages)){tags.append(el('span','tag '+(state==='approved'||state==='recorded'?'ok':(state==='stale'?'bad':'')),stage));}
  c.append(tags);
  const n=el('div','meta'); n.textContent='next: '+p.next_step; c.append(n);
  box.append(c);
 }
 if(!d.productions.length) box.append(el('div','meta','nothing yet'));
}
document.getElementById('create').addEventListener('click',async()=>{
 const body={audio:document.getElementById('src').value,title:document.getElementById('title').value.trim(),
  aspect:document.getElementById('aspect').value,fps:Number(document.getElementById('fps').value),
  music_mode:document.getElementById('mode').value,cap:document.getElementById('cap').value};
 msg.className='';msg.textContent='creating…';
 const r=await fetch('/api/create'+q,{method:'POST',headers:{...hdr,'Content-Type':'application/json'},body:JSON.stringify(body)});
 const d=await r.json();
 if(!r.ok){msg.className='err';msg.textContent=d.error||('HTTP '+r.status);return;}
 msg.className='ok';msg.textContent='created '+d.created+' — opening project';
 setTimeout(()=>{location.href='/?token='+encodeURIComponent(token)+'#projects';},700);
 loadProjects();
});
loadSources();loadProjects();
</script></body></html>"""


def _float(query, key):
    raw = (query.get(key) or [None])[0]
    return float(raw) if raw not in (None, "") else None


def build_server(
    projects_dir: str | Path,
    db: str | Path,
    *,
    port: int = 8765,
    token: str | None = None,
    sources_dir: str | Path | None = None,
):
    """Create (but do not start) a loopback server. Returns ``(server, url)``."""
    token = token if token is not None else secrets.token_urlsafe(16)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    httpd.daemon_threads = True
    httpd.projects_dir = Path(projects_dir).resolve()
    httpd.db = Path(db)
    httpd.token = token
    httpd.sources_dir = Path(sources_dir).expanduser() if sources_dir else Path.home() / "Downloads" / "Suno Downloads"
    url = f"http://127.0.0.1:{httpd.server_address[1]}/?token={token}"
    return httpd, url


def serve(
    projects_dir: str | Path,
    db: str | Path,
    *,
    port: int = 8765,
    token: str | None = None,
    ready: queue.Queue | None = None,
) -> None:
    httpd, url = build_server(projects_dir, db, port=port, token=token)
    if ready is not None:
        ready.put(url)
    print(f"Studio live: {url}")
    print("Read-only: writes still go through `clip` under the project lock.")
    try:
        httpd.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


def start_in_thread(projects_dir, db, *, port=0, token="test-token"):
    """Test helper: start the server on an ephemeral port and return (server, url, thread)."""
    httpd, url = build_server(projects_dir, db, port=port, token=token)
    thread = threading.Thread(
        target=httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
    )
    thread.start()
    return httpd, url, thread


def aggregate_operations(projects_dir: Path) -> dict:
    """Per-project operation summaries, for the live page and future clients."""
    result = {}
    for folder in sorted(Path(projects_dir).iterdir()) if Path(projects_dir).is_dir() else []:
        if not (folder / "project.json").is_file():
            continue
        result[folder.name] = operations.summary(folder)
    return result
