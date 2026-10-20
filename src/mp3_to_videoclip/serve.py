"""Live layer: a loopback server that streams the durable spine, read-only by default.

Deliberately small and boring: no framework and no build step. Every GET is a
read-only projection; every write verb is refused except the single parked
``POST /api/create``, which calls the same kernel entry points as ``clip init`` and
``clip budget`` under the project lock. Nothing here approves, selects or spends.

Threat model: loopback only, and a per-session token so another local page cannot
read the studio. Nothing is served from the project directory except JSON and
in-memory thumbnails resolved through ``storage.inside``.
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
from urllib.parse import parse_qs, unquote, urlparse

from . import appdata, sources, spine, studio

STREAM_INTERVAL = 0.5
HEARTBEAT_SECONDS = 10.0

JS_HELPERS = """
function el(tag, cls, text){const n=document.createElement(tag); if(cls)n.className=cls; if(text!==undefined)n.textContent=text; return n;}
function eventPayload(ev){
  if(ev && ev.payload && typeof ev.payload === 'object') return ev.payload;
  try { return JSON.parse((ev && ev.payload_json) || '{}') || {}; } catch(e){ return {}; }
}
"""


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
__JS_HELPERS__
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
    const payload = eventPayload(ev);
    line.textContent = '[' + (ev.type) + '] ' + (payload.line !== undefined ? payload.line : JSON.stringify(payload));
    log.append(line); log.scrollTop = log.scrollHeight;
  };
  es.onerror = () => { es.close(); setTimeout(stream, 2000); };
}
refresh(); setInterval(refresh, 5000); stream();
</script></body></html>""".replace("__JS_HELPERS__", JS_HELPERS)


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

    def _bytes(self, body: bytes, content_type: str, status=HTTPStatus.OK):
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "private, max-age=30")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(body)

    def _project_root(self, slug: str) -> Path | None:
        """Resolve a slug inside the projects directory, never through ``..``."""
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", slug or ""):
            return None
        projects = self.server.projects_dir.resolve()
        root = (projects / slug).resolve()
        if root.parent != projects or not (root / "project.json").is_file():
            return None
        return root

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
        if parsed.path.startswith("/api/project/"):
            segments = [unquote(part) for part in parsed.path.strip("/").split("/")]
            if len(segments) < 3 or segments[:2] != ["api", "project"]:
                return self._json({"error": "unknown production"}, HTTPStatus.NOT_FOUND)
            root = self._project_root(segments[2])
            if root is None:
                return self._json({"error": "unknown production"}, HTTPStatus.NOT_FOUND)
            from . import production as P

            rest = segments[3:]
            if not rest:
                return self._json({"status": P.status(root), "entry": studio.scan_project(root)})
            if rest == ["stills"]:
                return self._json(appdata.stills(root))
            if rest == ["board"]:
                return self._json(appdata.board(root))
            if rest == ["approvals"]:
                return self._json(appdata.approvals(root))
            if len(rest) == 2 and rest[0] == "shot":
                try:
                    return self._json(appdata.shot_detail(root, rest[1]))
                except LookupError:
                    return self._json({"error": "unknown shot"}, HTTPStatus.NOT_FOUND)
            if len(rest) == 2 and rest[0] == "thumb":
                raw = (query.get("version") or [None])[0]
                try:
                    version = int(raw) if raw not in (None, "") else None
                except ValueError:
                    return self._json(
                        {"error": "version must be an integer"}, HTTPStatus.BAD_REQUEST
                    )
                try:
                    body = appdata.thumbnail(root, rest[1], version)
                except (LookupError, FileNotFoundError, ValueError):
                    return self._json({"error": "image unavailable"}, HTTPStatus.NOT_FOUND)
                return self._bytes(body, "image/jpeg")
            return self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)
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
            return self._json(
                {"error": "unsupported write: only /api/create"}, HTTPStatus.METHOD_NOT_ALLOWED
            )
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
:root{--bg:#0a0f14;--panel:#111a22;--panel2:#16222c;--ink:#f2efe6;--muted:#8fa0ae;--gold:#d4ae6a;
--teal:#688f9d;--line:#1f2c37;--ok:#6fb585;--warn:#d9a441;--bad:#d4655f}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:1380px;margin:0 auto;padding:26px 22px 80px}
.kicker{color:var(--gold);text-transform:uppercase;letter-spacing:.15em;font-size:11px;font-weight:700}
h1{font-size:30px;margin:4px 0 18px;letter-spacing:-.02em}
h2{font-size:12px;text-transform:uppercase;letter-spacing:.1em;color:var(--muted);margin:0 0 12px}
h3{font-size:15px;margin:18px 0 8px}
.grid{display:grid;grid-template-columns:380px 1fr;gap:18px}@media(max-width:1000px){.grid{grid-template-columns:1fr}}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px}
label{display:block;font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin:10px 0 4px}
input,select{width:100%;background:#0e161d;color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:8px 10px;font:inherit}
button{background:var(--gold);color:#0a0f14;border:0;border-radius:8px;padding:9px 14px;font:inherit;font-weight:700;cursor:pointer;margin-top:14px}
button:disabled{background:#2a3540;color:#7b8b98}
.row{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.card{border:1px solid var(--line);border-radius:12px;padding:14px;margin-bottom:10px;background:linear-gradient(180deg,#16222c,#111a22);cursor:pointer}
.card:hover,.card.on{border-color:var(--gold)}
.card b{font-size:16px}.meta{color:var(--muted);font-size:12px;margin-top:4px}
.tag{font-size:10px;text-transform:uppercase;letter-spacing:.06em;border:1px solid var(--line);border-radius:999px;padding:1px 7px;color:var(--muted);margin-right:4px;display:inline-block}
.tag.ok{color:var(--ok);border-color:#2c5240}.tag.warn{color:var(--gold);border-color:#4a3d25}.tag.bad{color:var(--bad);border-color:#5b2f2f}
#msg{font-size:12px;margin-top:10px;min-height:18px}#msg.err{color:var(--bad)}#msg.ok{color:var(--ok)}
.mono,.code{font-family:ui-monospace,Menlo,monospace;font-size:11px;color:var(--muted)}
.tabbar{display:flex;gap:6px;flex-wrap:wrap;margin:12px 0 16px;border-bottom:1px solid var(--line);padding-bottom:12px}
button.tab{background:#0f1820;color:var(--muted);border:1px solid var(--line);border-radius:999px;padding:6px 13px;font:inherit;font-size:12px;font-weight:500;margin:0}
button.tab.on{background:var(--gold);border-color:var(--gold);color:#0a0f14;font-weight:700}
.stats{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0 14px}
.stat{background:#0e161d;border:1px solid var(--line);border-radius:10px;padding:7px 11px;min-width:82px}
.stat b{display:block;font-size:18px}.stat span{color:var(--muted);font-size:9px;text-transform:uppercase;letter-spacing:.09em}
.stillgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(148px,1fr));gap:10px}
.still{background:#0e161d;border:1px solid var(--line);border-radius:10px;padding:0;margin:0;overflow:hidden;text-align:left;cursor:pointer;font-weight:400;color:var(--ink)}
.still:hover,.still.on{border-color:var(--gold)}
.still img{display:block;width:100%;aspect-ratio:16/9;object-fit:cover;background:#0b1218}
.still .noimg{aspect-ratio:16/9;display:flex;align-items:center;justify-content:center;color:var(--muted);font-size:11px;text-align:center;padding:6px}
.still .cap{padding:7px 8px;font-size:11px;line-height:1.35}
.still .cap b{font-size:12px}
.still .cap .p{color:var(--muted);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.badge{display:inline-block;font-size:9px;text-transform:uppercase;letter-spacing:.07em;padding:1px 6px;border-radius:999px;border:1px solid var(--line);color:var(--muted);margin-left:4px}
.badge.accept{color:var(--ok);border-color:#2c5240}.badge.reject{color:var(--bad);border-color:#5b2f2f}
.badge.uncertain{color:var(--warn);border-color:#5b4a2a}.badge.approved{color:var(--ok);border-color:#2c5240}
.badge.stale{color:var(--bad);border-color:#5b2f2f}.badge.missing{color:var(--muted)}
.badge.unavailable{color:#5d6b77;border-style:dashed}.badge.recorded{color:var(--gold);border-color:#4a3d25}
.filters{display:flex;gap:6px;flex-wrap:wrap;margin:4px 0 12px}
button.chip{background:#0f1820;color:var(--muted);border:1px solid var(--line);border-radius:999px;padding:4px 10px;font:inherit;font-size:11px;font-weight:500;margin:0}
button.chip.on{background:var(--gold);border-color:var(--gold);color:#0a0f14;font-weight:700}
.detailbox{border:1px solid var(--line);border-radius:12px;padding:14px;margin:14px 0;background:#0e161d}
.detailbox .cols{display:grid;grid-template-columns:220px 1fr;gap:14px}@media(max-width:700px){.detailbox .cols{grid-template-columns:1fr}}
.detailbox img{width:100%;border-radius:8px;border:1px solid var(--line)}
dl{display:grid;grid-template-columns:112px 1fr;gap:4px 10px;margin:0;font-size:12px}
dt{color:var(--muted)}dd{margin:0}
pre{background:#0a1117;border:1px solid var(--line);border-radius:8px;padding:10px;font:11px/1.5 ui-monospace,Menlo,monospace;white-space:pre-wrap;word-break:break-word;max-height:340px;overflow:auto}
.bands{display:flex;height:22px;border-radius:6px;overflow:hidden;border:1px solid var(--line);margin:10px 0}
.band{display:flex;align-items:center;justify-content:center;font-size:9px;color:#0a0f14;overflow:hidden;white-space:nowrap;border-right:1px solid #0a0f14}
.band.section{background:#688f9d}.band.accent{background:#d4ae6a}.band.build{background:#7fae8a}.band.release{background:#c9a37a}.band.vocal{background:#8d9fc4}.band.instrumental{background:#9a8db5}
.track{position:relative;height:28px;background:#0e161d;border:1px solid var(--line);border-radius:6px;overflow:hidden;margin:10px 0 16px}
.shotbar{position:absolute;top:0;bottom:0;border-right:1px solid #0a0f14;background:#26414d}
.shotbar.wide{background:#2c4d5e}.shotbar.medium{background:#315a4b}.shotbar.close_up{background:#5a4a31}.shotbar.detail{background:#4a3b5c}
table{width:100%;border-collapse:collapse;font-size:12px}
th,td{text-align:left;padding:6px 8px;border-bottom:1px solid var(--line);vertical-align:top}
th{color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.07em;position:sticky;top:0;background:var(--panel)}
.scroll{max-height:46vh;overflow:auto;border:1px solid var(--line);border-radius:10px}
.run{display:flex;gap:8px;align-items:center;padding:7px 0;border-bottom:1px solid var(--line);font-size:12px;cursor:pointer}
.run:last-child{border:0}.run b{font-weight:600}.run.on{color:var(--gold)}
#log{height:32vh;overflow:auto;background:#0e161d;border:1px solid var(--line);border-radius:9px;padding:9px;font:11px/1.5 ui-monospace,Menlo,monospace}
#log div{padding:1px 0;border-bottom:1px solid #121c24}
.ev{color:var(--teal)}.out{color:var(--muted)}.err{color:var(--bad)}.gold{color:var(--gold)}
button.mini{background:#0f1820;color:var(--muted);border:1px solid var(--line);border-radius:6px;padding:3px 8px;font:inherit;font-size:10px;font-weight:500;margin:0}
.empty{color:var(--muted);padding:30px;border:1px dashed var(--line);border-radius:12px;text-align:center}
</style></head><body><div class="wrap">
<div class="kicker">Studio</div><h1>Library, stills and runs</h1>
<div class="grid">
<div class="panel">
<h2>New production</h2>
<label for="src">Source (liked, real tracks)</label><select id="src"></select>
<label for="title">Film title</label><input id="title" placeholder="Forward Ever">
<div class="row"><div><label for="aspect">Aspect</label><select id="aspect"><option>16:9</option><option>9:16</option></select></div>
<div><label for="fps">FPS</label><select id="fps"><option>24</option><option>30</option></select></div></div>
<div class="row"><div><label for="mode">Mode</label><select id="mode"><option>vocal</option><option>instrumental</option><option>music-led</option></select></div>
<div><label for="cap">Cap USD</label><input id="cap" type="number" value="5.00" step="0.01" min="0.01"></div></div>
<button id="create">Create production</button><div id="msg"></div>
<p class="mono" style="margin-top:12px">Creates via the clip kernel: byte-identical copy, project.json, budget. Nothing is generated or spent.</p>
<h2 style="margin-top:22px">Productions</h2><div id="list">loading…</div>
</div>
<div class="panel">
<div id="detailTitle" class="mono">Select a production</div>
<div class="tabbar" id="tabs">
<button class="tab on" data-tab="overview">Overview</button>
<button class="tab" data-tab="stills">Stills</button>
<button class="tab" data-tab="board">Board</button>
<button class="tab" data-tab="approvals">Approvals</button>
<button class="tab" data-tab="runs">Runs</button>
</div>
<div id="view"><div class="empty">Choose a production on the left. This page is read-only: it cannot approve, select, spend or edit.</div></div>
</div>
</div></div>
<script>
const token=new URLSearchParams(location.search).get('token')||'';
const q=token?('?token='+encodeURIComponent(token)):'';
const hdr=token?{'X-Studio-Token':token}:{};
const view=document.getElementById('view');
let current=null, tab='overview', stillsData=null, stillFilter=null, cockpitSource=null, cockpitRun=null, viewGen=0;
__JS_HELPERS__
function withToken(path){if(!token)return path;return path+(path.includes('?')?'&':'?')+'token='+encodeURIComponent(token);}
async function api(path){const r=await fetch(withToken(path));const d=await r.json();if(!r.ok)throw new Error(d.error||('HTTP '+r.status));return d;}
function badge(v){const t=v||'unreviewed';return el('span','badge '+t,t);}
function stateTag(state){const cls=(state==='approved'||state==='recorded')?'ok':(state==='stale'?'bad':(state==='missing'?'':'warn'));return el('span','tag '+cls,state);}
function clear(node){while(node.firstChild)node.removeChild(node.firstChild);}
function stat(b,label){const n=el('div','stat');n.append(el('b',null,String(b)));n.append(el('span',null,label));return n;}
function stopCockpit(){if(cockpitSource){cockpitSource.close();cockpitSource=null;}cockpitRun=null;}
function setTab(name){tab=name;document.querySelectorAll('button.tab').forEach(function(b){b.classList.toggle('on',b.getAttribute('data-tab')===name);});}
async function loadSources(){
 const r=await fetch(withToken('/api/sources')); const d=await r.json();
 const sel=document.getElementById('src'); sel.textContent='';
 if(!d.tracks||!d.tracks.length){sel.append(el('option',null,'no source tracks found'));return;}
 for(const t of d.tracks){const o=el('option');o.value=t.audio;o.textContent=t.title+' · '+(t.seconds)+'s';sel.append(o);}
}
async function loadProjects(){
 const d=await api('/api/studio');
 const box=document.getElementById('list'); box.textContent='';
 for(const p of d.productions){
  const c=el('div','card'); c.append(el('b',null,p.title));
  const m=el('div','meta'); m.textContent=p.duration.toFixed(0)+'s · '+p.shots+' shots · '+(p.spend.accounted_usd||'—')+' / '+(p.spend.cap_usd||'no cap')+' USD';
  c.append(m);
  const tags=el('div','meta');
  for(const [stage,state] of Object.entries(p.stages)){const t=stateTag(state);t.textContent=stage+' '+t.textContent;tags.append(t);}
  c.append(tags);
  const n=el('div','meta'); n.textContent='next: '+p.next_step; c.append(n);
  c.addEventListener('click',function(){
   document.querySelectorAll('#list .card').forEach(function(x){x.classList.remove('on');});
   c.classList.add('on'); openProject(p.slug,p.title);
  });
  box.append(c);
 }
 if(!d.productions.length) box.append(el('div','meta','nothing yet'));
}
function openProject(slug,title){
 current={slug:slug,title:title}; stillsData=null; stillFilter=null; stopCockpit();
 document.getElementById('detailTitle').textContent=title+' · '+slug;
 showTab('overview');
}
const loaders={overview:loadOverview,stills:loadStills,board:loadBoard,approvals:loadApprovals,runs:loadRuns};
function showTab(name){
 if(!current)return;
 const gen=++viewGen;
 setTab(name); view.textContent='';
 if(name!=='runs')stopCockpit();
 loaders[name](gen).catch(function(e){if(gen!==viewGen)return;view.textContent='';view.append(el('div','empty',e.message));});
}
async function loadOverview(gen){
 const d=await api('/api/project/'+current.slug); if(gen!==viewGen)return; const s=d.status||{}; const e=d.entry||{};
 clear(view);
 const stats=el('div','stats');
 stats.append(stat((s.duration||0).toFixed(0)+'s','duration'));
 stats.append(stat((s.shots||[]).length,'shots'));
 stats.append(stat((s.total_frames||0),'frames'));
 stats.append(stat((e.spend&&e.spend.accounted_usd)||'—','spent'));
 view.append(stats);
 const tags=el('div','');
 for(const [stage,state] of Object.entries(s.approvals||{})){tags.append(el('span','tag '+(state==='approved'?'ok':'bad'),stage+': '+state));}
 view.append(tags);
 const n=el('p','meta','next: '+(e.next_step||'—')); view.append(n);
 const blockers=(e.blockers||[]);
 if(blockers.length){const ul=el('ul','');for(const b of blockers){const li=el('li',null,b[1]);li.className=b[0];ul.append(li);}view.append(ul);}
 else view.append(el('p','meta','no blockers'));
 const go=el('button','mini','Open stills'); go.style.marginTop='14px';
 go.addEventListener('click',function(){showTab('stills');}); view.append(go);
}
async function fetchStills(){stillsData=await api('/api/project/'+current.slug+'/stills');}
async function loadStills(gen){
 await fetchStills(); if(gen!==viewGen)return; renderStills();
}
function renderStills(){
 clear(view); const d=stillsData;
 if(!d.available){view.append(el('div','empty',d.warning||'no storyboard'));return;}
 const stats=el('div','stats');
 stats.append(stat(d.shots.length,'shots'));
 stats.append(stat(d.counts.accept||0,'accepted'));
 stats.append(stat(d.counts.reject||0,'rejected'));
 stats.append(stat(d.counts.uncertain||0,'uncertain'));
 stats.append(stat(d.counts.unreviewed||0,'unreviewed'));
 view.append(stats);
 const filters=el('div','filters');
 const choices=[['all','All'],['accept','Accepted'],['reject','Rejected'],['uncertain','Uncertain'],['unreviewed','Unreviewed']];
 for(const pair of choices){
  const b=el('button','chip'+(stillFilter===pair[0]||(!stillFilter&&pair[0]==='all')?' on':''),pair[1]);
  b.addEventListener('click',function(){stillFilter=pair[0]==='all'?null:pair[0];renderStills();});
  filters.append(b);
 }
 view.append(filters);
 const panel=el('div','detailbox'); panel.id='shotPanel'; view.append(panel);
 const grid=el('div','stillgrid'); view.append(grid);
 let shown=0;
 for(const s of d.shots){
  const verdict=s.verdict||'unreviewed';
  if(stillFilter&&verdict!==stillFilter)continue;
  shown++;
  const card=el('button','still');
  if(s.has_image){
   const img=document.createElement('img'); img.loading='lazy'; img.alt=s.id+' still'; img.src=withToken(s.thumb);
   img.addEventListener('error',function(){img.replaceWith(el('div','noimg','image unreadable'));});
   card.append(img);
  } else card.append(el('div','noimg','no selected still'));
  const cap=el('div','cap'); const line=el('div',''); line.append(el('b',null,s.id)); line.append(badge(verdict)); cap.append(line);
  const meta=el('div','p'); meta.textContent=(s.version?('v'+String(s.version).padStart(3,'0')):'no version')+' · '+s.seconds.toFixed(1)+'s · '+(s.framing||'no framing');
  cap.append(meta);
  if(s.alias_of)cap.append(el('div','mono','reuses '+s.alias_of));
  card.append(cap);
  card.addEventListener('click',function(){document.querySelectorAll('.still').forEach(function(x){x.classList.remove('on');});card.classList.add('on');showShot(s.id);});
  grid.append(card);
 }
 if(!shown)grid.append(el('div','empty','nothing matches this filter'));
}
async function showShot(id){
 const panel=document.getElementById('shotPanel'); panel.textContent='Loading '+id+'…';
 try{
  const d=await api('/api/project/'+current.slug+'/shot/'+encodeURIComponent(id));
  clear(panel);
  const cols=el('div','cols');
  const left=el('div','');
  if(d.version){const img=document.createElement('img');img.alt=d.id+' selected still';img.src=withToken(d.thumb);left.append(img);}
  const line=el('div','meta');line.append(el('b',null,d.id));line.append(badge(d.verdict));left.append(line);
  left.append(el('div','mono','v'+String(d.version||0).padStart(3,'0')+' · '+d.seconds.toFixed(2)+'s · sha '+(d.sha256||'—').slice(0,12)));
  if(d.alias_of)left.append(el('div','mono','reuses '+d.alias_of));
  if(d.verdict_note)left.append(el('div','meta','“'+d.verdict_note+'”'));
  cols.append(left);
  const right=el('div','');
  right.append(el('h3',null,'Contract'));
  const dl=document.createElement('dl');
  const c=d.contract||{};
  const rows=[['purpose',c.purpose],['framing',c.framing||'—'],['camera',c.camera||'—'],['transition',c.transition||'cut'],['dissolve',(c.dissolve_frames||0)+' frames'],['scene',c.scene||'—'],['characters',(c.characters||[]).join(', ')||'—'],['references',(c.references||[]).join(', ')||'—'],['must show',(c.must_show||[]).join('; ')||'—'],['music',c.music_context||'—']];
  for(const pair of rows){dl.append(el('dt',null,pair[0]));dl.append(el('dd',null,String(pair[1])));}
  right.append(dl);
  right.append(el('h3',null,'Compiled prompt'));
  if(d.prompt_error)right.append(el('p','meta','prompt unavailable: '+d.prompt_error));
  const pre=el('pre',null,d.prompt||'no compiled prompt recorded');
  right.append(pre);
  cols.append(right); panel.append(cols);
 }catch(e){panel.textContent='';panel.append(el('div','empty',e.message));}
}
async function loadBoard(gen){
 const d=await api('/api/project/'+current.slug+'/board'); if(gen!==viewGen)return; clear(view);
 if(!d.available){view.append(el('div','empty',d.warning||'no storyboard'));return;}
 const stats=el('div','stats');
 stats.append(stat(d.shots.length,'shots')); stats.append(stat(d.total_frames,'frames'));
 stats.append(stat(d.duration.toFixed(0)+'s','duration')); stats.append(stat(d.fps,'fps'));
 view.append(stats);
 view.append(el('p','meta','bar grid: '+(d.grid.enabled?'enabled':'not claimed — '+(d.grid.reason||'no approved grid'))));
 if(d.bands.length){
  const bands=el('div','bands');
  for(const b of d.bands){
   const seg=el('div','band '+b.kind,b.label+' · '+(b.timing_basis==='estimated'?'est.':'manual'));
   seg.title=b.label+' · '+b.start_seconds+'s–'+b.end_seconds+'s · '+b.confidence;
   seg.style.flex=String(Math.max(0.01,b.end_seconds-b.start_seconds)); bands.append(seg);
  }
  view.append(bands);
 }
 const track=el('div','track');
 for(const s of d.shots){
  const bar=el('div','shotbar '+s.framing); bar.title=s.id+' · '+s.start_seconds+'s–'+s.end_seconds+'s · '+s.purpose;
  bar.style.left=(s.start_frame/d.total_frames*100)+'%'; bar.style.width=(s.seconds/d.duration*100)+'%'; track.append(bar);
 }
 view.append(track);
 const scroll=el('div','scroll'); const table=el('table'); const head=el('tr');
 for(const label of ['shot','seconds','frames','framing','transition','purpose']){head.append(el('th',null,label));}
 table.append(head);
 for(const s of d.shots){
  const tr=el('tr'); tr.append(el('td','mono',s.id)); tr.append(el('td',null,s.seconds.toFixed(1)));
  tr.append(el('td','mono',s.start_frame+'–'+s.end_frame)); tr.append(el('td',null,s.framing||'—'));
  tr.append(el('td',null,s.transition+(s.dissolve_frames?(' +'+s.dissolve_frames):''))); tr.append(el('td',null,s.purpose));
  table.append(tr);
 }
 scroll.append(table); view.append(scroll);
}
async function loadApprovals(gen){
 const d=await api('/api/project/'+current.slug+'/approvals'); if(gen!==viewGen)return; clear(view);
 view.append(el('p','meta',d.current+' of '+d.total+' stages would pass now. Live hashes are recomputed; nothing is approved here.'));
 const scroll=el('div','scroll'); const table=el('table'); const head=el('tr');
 for(const label of ['stage','state','current hash','approved hash','at','would pass','command']){head.append(el('th',null,label));}
 table.append(head);
 for(const s of d.stages){
  const tr=el('tr');
  tr.append(el('td',null,s.stage)); const state=el('td',''); state.append(el('span','badge '+s.state,s.state)); tr.append(state);
  tr.append(el('td','mono',(s.hash||'—').slice(0,16))); tr.append(el('td','mono',(s.approved_hash||'—').slice(0,16)));
  tr.append(el('td','mono',s.at||'—')); tr.append(el('td',null,s.would_pass_now?'yes':'no'));
  const cmd=el('td',''); const btn=el('button','mini','copy'); btn.addEventListener('click',function(){if(navigator.clipboard)navigator.clipboard.writeText(s.approve_command);btn.textContent='copied';}); cmd.append(btn); tr.append(cmd);
  table.append(tr);
 }
 scroll.append(table); view.append(scroll);
}
async function loadRuns(gen){
 clear(view); stopCockpit();
 const d=await api('/api/runs?limit=20'); if(gen!==viewGen)return; const list=el('div',''); const panel=el('div','panel'); panel.style.marginTop='12px';
 const head=el('h2',null,'Live events'); const log=el('div'); log.id='log'; panel.append(head,log);
 if(!d.runs.length){view.append(el('div','empty','no runs yet — start one with a clip command'));return;}
 for(const run of d.runs){
  const row=el('div','run'); row.append(el('b',null,run.intent||run.id)); row.append(el('span','tag '+run.status,run.status));
  if(run.production)row.append(el('span','mono',run.production));
  row.addEventListener('click',function(){document.querySelectorAll('.run').forEach(function(x){x.classList.remove('on');});row.classList.add('on');selectRun(run.id);});
  list.append(row);
 }
 view.append(list,panel);
 selectRun(d.runs[0].id);
}
async function selectRun(id){
 stopCockpit(); cockpitRun=id;
 const d=await api('/api/events?run='+encodeURIComponent(id)+'&after=0&limit=200');
 if(cockpitRun!==id)return;
 const log=document.getElementById('log'); if(!log)return; log.textContent='';
 let last=0;
 for(const ev of d.events){last=Math.max(last,ev.seq);appendEvent(ev);}
 const url='/api/stream?after='+last+'&run='+encodeURIComponent(id)+(token?'&token='+encodeURIComponent(token):'');
 const es=new EventSource(url); cockpitSource=es;
 es.onmessage=function(m){try{appendEvent(JSON.parse(m.data));}catch(e){}};
 es.onerror=function(){es.close();if(cockpitSource===es)cockpitSource=null;};
}
function appendEvent(ev){
 const log=document.getElementById('log'); if(!log)return;
 const payload=eventPayload(ev);
 const line=el('div',ev.type==='command.output'?'out':((ev.type.includes('failed')||ev.type.includes('interrupted'))?'err':'ev'));
 line.textContent='['+ev.type+'] '+(payload.line!==undefined?payload.line:JSON.stringify(payload));
 log.append(line); while(log.childNodes.length>400)log.removeChild(log.firstChild); log.scrollTop=log.scrollHeight;
}
document.getElementById('tabs').addEventListener('click',function(e){const b=e.target.closest('button.tab');if(b)showTab(b.getAttribute('data-tab'));});
document.getElementById('create').addEventListener('click',async function(){
 const body={audio:document.getElementById('src').value,title:document.getElementById('title').value.trim(),
  aspect:document.getElementById('aspect').value,fps:Number(document.getElementById('fps').value),
  music_mode:document.getElementById('mode').value,cap:document.getElementById('cap').value};
 const msg=document.getElementById('msg'); msg.className='';msg.textContent='creating…';
 const r=await fetch(withToken('/api/create'),{method:'POST',headers:Object.assign({},hdr,{'Content-Type':'application/json'}),body:JSON.stringify(body)});
 const d=await r.json();
 if(!r.ok){msg.className='err';msg.textContent=d.error||('HTTP '+r.status);return;}
 msg.className='ok';msg.textContent='created '+d.created+' — opening project';
 setTimeout(function(){location.href='/app?token='+encodeURIComponent(token)+'#projects';},700);
 loadProjects();
});
loadSources();loadProjects();
</script></body></html>""".replace("__JS_HELPERS__", JS_HELPERS)


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
    httpd.sources_dir = (
        Path(sources_dir).expanduser()
        if sources_dir
        else Path.home() / "Downloads" / "Suno Downloads"
    )
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
