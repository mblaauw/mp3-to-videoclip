"""Interim Studio: the loopback review app kept alive until the Phase 4 frontend replaces it.

Deliberately small and boring: no framework and no build step. GETs are review
projections. POST /api/create performs local setup. A separately terminal-enabled
human capability admits two typed content-bound decision routes under the
project lock; neither can upload, generate, execute commands or charge a provider.

Threat model: loopback only, and a per-session token so another local page cannot
read the studio. Nothing is served from the project directory except JSON and
in-memory thumbnails resolved through ``storage.inside``.
"""

from __future__ import annotations

import json
import queue
import re
import secrets
import sys
import threading
import time
import unicodedata
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

from . import appdata, human_actions, human_ui, sources, studio, studio_ui

HEARTBEAT_SECONDS = 10.0
MAX_UPLOAD_BYTES = 250 * 1024 * 1024

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
button.run{display:block;width:100%;text-align:left;color:inherit;background:none;border:0;font:inherit;min-height:32px}
a{color:var(--gold)}:focus-visible{outline:2px solid var(--gold);outline-offset:3px}#projects a{display:block;padding:6px 0}
</style></head><body><main class="wrap">
<div class="kicker">Studio · live</div><h1>Runs</h1>
<a id="openStudio" href="/app">Open Studio library</a>
<p class="mono">Read-only journal · loopback · human decisions require a terminal-enabled Studio session</p>
<div class="grid">
<div class="panel"><h2>Journal</h2><div id="runs">connecting…</div>
<h2>Projects</h2><div id="projects" class="mono"></div></div>
<div class="panel"><h2>Events</h2><div id="log"></div></div>
</div>
<footer>Every mutation goes through <span class="mono">clip</span> under the project lock and a content hash.
This page cannot approve, select, spend or edit.</footer>
</main>
<script>
const token = new URLSearchParams(location.search).get('token') || '';
const q = token ? ('?token=' + encodeURIComponent(token)) : '';
document.getElementById('openStudio').href='/app'+q;
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
    const row = el('button','run');
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
    const projects=document.getElementById('projects');projects.textContent='';
    for(const x of s.productions){const a=el('a',null,x.title+' — '+x.next_step);a.href='/app'+q+'#/'+encodeURIComponent(x.slug)+'/overview';projects.append(a);}
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

    def _host_allowed(self):
        port = self.server.server_address[1]
        allowed = {f"127.0.0.1:{port}", f"localhost:{port}"}
        if port == 80:
            allowed.update({"127.0.0.1", "localhost"})
        return self.headers.get("Host") in allowed

    def _action_allowed(self):
        expected = getattr(self.server, "action_token", None)
        supplied = self.headers.get("X-Studio-Action", "")
        if not expected or not secrets.compare_digest(supplied.encode(), expected.encode()):
            raise human_actions.ActionError(
                "Human actions require a terminal-enabled Studio session", 401
            )
        if self.headers.get("Origin") != f"http://{self.headers.get('Host')}":
            raise human_actions.ActionError(
                "Studio actions require the same local browser origin", 403
            )
        if self.headers.get("Content-Type", "").split(";")[0].strip().lower() != "application/json":
            raise human_actions.ActionError("Studio actions require application/json", 415)

    def end_headers(self):
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        # Inline templates are intentional; no external scripts, frames or services.
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; script-src 'self' 'unsafe-inline'; "
            "style-src 'self' 'unsafe-inline'; img-src 'self' data:; "
            "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
        )
        super().end_headers()

    def _page_error(self, status, message):
        return self._text(
            '<!doctype html><html lang="en"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            "<title>Studio · link unavailable</title><style>"
            "body{color-scheme:dark;background:#0a0f14;color:#f2efe6;"
            "font:16px/1.6 system-ui;padding:8vh 8vw;max-width:50rem}"
            "h1{color:#d4ae6a}code{overflow-wrap:anywhere}</style><main>"
            f"<h1>{message}</h1><p>Reopen the local link printed by "
            "<code>uv run clip serve</code> in your terminal. Keep its session token "
            "in the URL. If the server restarted, use its new link.</p>"
            "<p>No production was changed.</p></main></html>",
            status,
        )

    # -- helpers ---------------------------------------------------------- #
    def _authorised(self, query) -> bool:
        token = getattr(self.server, "token", None)
        if not token:
            return True
        supplied = (query.get("token") or [None])[0] or self.headers.get("X-Studio-Token")
        return secrets.compare_digest(str(supplied).encode(), str(token).encode())

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

    def _read_body(self, limit: int) -> dict:
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError as exc:
            raise human_actions.ActionError("invalid content length") from exc
        if not 0 < length <= limit:
            raise human_actions.ActionError(f"payload must be 1–{limit} bytes", 413)
        try:
            body = json.loads(self.rfile.read(length))
        except ValueError as exc:
            raise human_actions.ActionError("invalid JSON") from exc
        if not isinstance(body, dict):
            raise human_actions.ActionError("payload must be an object")
        return body

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
        if not self._host_allowed():
            return self._json({"error": "invalid local Host"}, HTTPStatus.BAD_REQUEST)
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if parsed.path == "/api/health":
            return self._json(
                {
                    "ok": True,
                    "read_only": False,
                    "review_only": not bool(self.server.action_token),
                    "setup_write": "POST /api/create",
                }
            )
        if not self._authorised(query):
            if not parsed.path.startswith("/api/"):
                return self._page_error(HTTPStatus.UNAUTHORIZED, "Your Studio link needs a token")
            return self._json({"error": "token required"}, HTTPStatus.UNAUTHORIZED)
        if parsed.path == "/":
            return self._text(PAGE)
        if parsed.path == "/app":
            return self._text(APP)
        if parsed.path == "/api/session":
            from .production import UPSTREAM

            return self._json(
                {"actions_enabled": bool(self.server.action_token), "stages": list(UPSTREAM)}
            )
        if parsed.path == "/api/stream":
            return self._idle_stream()
        if parsed.path in ("/api/runs", "/api/events", "/api/status"):
            # The durable run journal was removed with the agent runtime; the
            # interim Studio keeps these shapes until the Phase 4 frontend.
            return self._json({"retired": True, "runs": [], "events": []})
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
                approval_data = appdata.approvals(root)
                return self._json(
                    {
                        "status": P.status(root),
                        "entry": studio.scan_project(root, verified_stages=approval_data["stages"]),
                        "approvals": approval_data,
                        "checked_at": datetime.now(UTC).isoformat(),
                    }
                )
            if rest == ["stills"]:
                return self._json(appdata.stills(root))
            if rest == ["board"]:
                return self._json(appdata.board(root))
            if rest == ["workflow"]:
                return self._json(appdata.workflow(root))
            if rest == ["story-review"]:
                try:
                    return self._json(human_actions.review_story(root))
                except OSError:
                    return self._json(
                        {"error": "Brief or storyboard unavailable; inspect locally"},
                        HTTPStatus.CONFLICT,
                    )
                except (ValueError, KeyError) as exc:
                    return self._json({"error": str(exc)}, HTTPStatus.CONFLICT)
            if rest == ["feedback"]:
                from . import feedback

                try:
                    return self._json(
                        {
                            "requests": feedback.requests(
                                root,
                                stage=(query.get("stage") or [None])[0],
                                status=(query.get("status") or [None])[0],
                            )
                        }
                    )
                except ValueError as exc:
                    return self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
            if rest == ["approvals"]:
                return self._json(appdata.approvals(root))
            if rest == ["quotes"]:
                return self._json(human_actions.quotes(root))
            if len(rest) == 2 and rest[0] in {"approval", "quote"}:
                try:
                    value = (
                        human_actions.review_stage(root, rest[1])
                        if rest[0] == "approval"
                        else human_actions.review_quote(root, rest[1])
                    )
                    return self._json(value)
                except human_actions.ActionError as exc:
                    return self._json({"error": str(exc)}, exc.status)
                except OSError:
                    return self._json(
                        {"error": "Review artifact or quote unavailable; inspect it locally"},
                        HTTPStatus.CONFLICT,
                    )
                except (ValueError, KeyError) as exc:
                    return self._json({"error": str(exc)}, HTTPStatus.CONFLICT)
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
        if not parsed.path.startswith("/api/"):
            return self._page_error(HTTPStatus.NOT_FOUND, "This Studio page was not found")
        return self._json({"error": "not found"}, HTTPStatus.NOT_FOUND)

    def do_POST(self):  # noqa: N802
        if not self._host_allowed():
            return self._json({"error": "invalid local Host"}, HTTPStatus.BAD_REQUEST)
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        if not self._authorised(query):
            return self._json({"error": "token required"}, HTTPStatus.UNAUTHORIZED)
        if parsed.path == "/api/source":
            try:
                return self._json(self._upload_source(query), HTTPStatus.CREATED)
            except human_actions.ActionError as exc:
                return self._json({"error": str(exc)}, exc.status)
            except (OSError, ValueError) as exc:
                return self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        if parsed.path.startswith("/api/project/"):
            try:
                segments = [unquote(part) for part in parsed.path.strip("/").split("/")]
                supported = (len(segments) == 5 and segments[3] in {"approve", "authorize"}) or (
                    len(segments) == 4
                    and segments[3] in {"feedback", "review", "approve-story", "credits"}
                )
                if not supported:
                    raise human_actions.ActionError("unsupported write route", 405)
                if len(segments) < 3:
                    raise human_actions.ActionError("unknown production", 404)
                self._action_allowed()
                root = self._project_root(segments[2])
                if root is None:
                    raise human_actions.ActionError("unknown production", 404)
                if len(segments) == 5 and segments[3] in {"approve", "authorize"}:
                    body = self._read_body(8192)
                    value = (
                        human_actions.approve_stage(root, segments[4], body)
                        if segments[3] == "approve"
                        else human_actions.authorize_quote(root, segments[4], body)
                    )
                elif len(segments) == 4 and segments[3] == "feedback":
                    from . import feedback
                    from .storage import project_lock

                    body = self._read_body(64000)
                    if set(body) - {"stage", "scope", "target", "message", "style", "confirmed"}:
                        raise human_actions.ActionError("unexpected feedback fields")
                    if body.get("confirmed") is not True:
                        raise human_actions.ActionError(
                            "confirm that this instruction should revise the production"
                        )
                    with project_lock(root):
                        value = {
                            "request": feedback.record(
                                root,
                                stage=body.get("stage"),
                                scope=body.get("scope", "whole"),
                                target=body.get("target"),
                                message=body.get("message"),
                                style=body.get("style"),
                                author="studio",
                            )
                        }
                elif len(segments) == 4 and segments[3] == "review":
                    value = human_actions.record_shot_review(root, self._read_body(8192))
                elif len(segments) == 4 and segments[3] == "approve-story":
                    value = human_actions.approve_story(root, self._read_body(8192))
                elif len(segments) == 4 and segments[3] == "credits":
                    value = human_actions.save_credits(root, self._read_body(64000))
                else:
                    raise human_actions.ActionError("unsupported write route", 405)
                return self._json(value)
            except human_actions.ActionError as exc:
                return self._json({"error": str(exc)}, exc.status)
            except OSError:
                return self._json(
                    {
                        "error": "Local review record unavailable. Refresh current records before retrying."
                    },
                    HTTPStatus.BAD_REQUEST,
                )
            except (ValueError, KeyError) as exc:
                return self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)
        if parsed.path != "/api/create":
            return self._json(
                {"error": "unsupported write: only /api/create"}, HTTPStatus.METHOD_NOT_ALLOWED
            )
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return self._json({"error": "invalid content length"}, HTTPStatus.BAD_REQUEST)
        if length < 0 or length > 20_000:
            return self._json({"error": "payload too large"}, HTTPStatus.BAD_REQUEST)
        try:
            body = json.loads(self.rfile.read(length) or b"{}")
        except ValueError:
            return self._json({"error": "invalid JSON"}, HTTPStatus.BAD_REQUEST)
        if not isinstance(body, dict):
            return self._json({"error": "payload must be an object"}, HTTPStatus.BAD_REQUEST)
        try:
            return self._json(self._create(body), HTTPStatus.CREATED)
        except (OSError, ValueError, KeyError) as exc:
            return self._json({"error": str(exc)}, HTTPStatus.BAD_REQUEST)

    def _upload_source(self, query) -> dict:
        """Copy a browser-selected MP3 into the local upload area.

        The browser cannot expose a filesystem path, so the file bytes are streamed
        to this loopback route. The returned path is a server-owned temporary copy;
        ``/api/create`` copies it into the production and the upload is removed.
        """
        from uuid import uuid4

        from .render import audio_seconds, probe

        raw = (query.get("name") or [""])[0]
        name = Path(raw).name.strip()
        if not name.lower().endswith(".mp3"):
            raise human_actions.ActionError("choose an MP3 file", 400)
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError as exc:
            raise human_actions.ActionError("invalid content length", 400) from exc
        if not 0 < length <= MAX_UPLOAD_BYTES:
            raise human_actions.ActionError(
                f"MP3 must be between 1 byte and {MAX_UPLOAD_BYTES // (1024 * 1024)} MB",
                413,
            )
        uploads = Path(self.server.upload_dir)
        uploads.mkdir(parents=True, exist_ok=True)
        target = uploads / f"{uuid4().hex}.mp3"
        part = uploads / f".{target.name}.part"
        try:
            remaining = length
            with part.open("wb") as handle:
                while remaining:
                    chunk = self.rfile.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise human_actions.ActionError(
                            "upload ended before the file was complete", 400
                        )
                    handle.write(chunk)
                    remaining -= len(chunk)
            part.replace(target)
            try:
                info = probe(target)
                if not any(
                    stream.get("codec_type") == "audio" for stream in info.get("streams", [])
                ):
                    raise human_actions.ActionError("the file has no audio stream", 400)
                seconds = audio_seconds(target)
            except human_actions.ActionError:
                raise
            except (OSError, RuntimeError, ValueError) as exc:
                raise human_actions.ActionError("could not read this MP3", 400) from exc
            if seconds <= 0:
                raise human_actions.ActionError("the file has no decodable audio", 400)
        except Exception:
            part.unlink(missing_ok=True)
            target.unlink(missing_ok=True)
            raise
        title = re.sub(r"[_-]+", " ", Path(name).stem).strip() or "Untitled track"
        return {
            "path": str(target),
            "name": name,
            "title": title[:120],
            "seconds": round(seconds, 3),
            "bytes": length,
        }

    def _create(self, body: dict) -> dict:
        """Create a production through the kernel: init copies the audio, then the cap."""
        from . import budget
        from . import production as P

        title = str(body.get("title") or "").strip()
        audio = Path(str(body.get("audio") or "")).expanduser()
        if not title or not audio.is_file():
            raise ValueError("a title and an existing audio file are required")
        normalized = unicodedata.normalize("NFKD", title).encode("ascii", "ignore").decode()
        derived = re.sub(r"[^a-z0-9]+", "-", normalized.casefold()).strip("-")[:64].rstrip("-")
        slug = str(body.get("slug") or "").strip() or derived
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", slug):
            raise ValueError("slug must be lowercase letters, digits and dashes")
        root = self.server.projects_dir / slug
        if root.exists():
            raise ValueError(f"production {slug!r} already exists")
        cap = body.get("cap")
        if cap is not None and cap != "":
            if budget.money(cap) <= 0:
                raise ValueError("spending cap must be positive")
        note = body.get("note") or "created in studio"
        if not isinstance(note, str) or not note.strip():
            raise ValueError("record a non-empty spending authority note")
        P.init_project(
            root,
            audio,
            slug,
            body.get("aspect") or "16:9",
            int(body.get("fps") or 24),
            body.get("music_mode") or "vocal",
            title=title,
        )
        if audio.resolve().parent == Path(self.server.upload_dir).resolve():
            audio.unlink(missing_ok=True)
        if cap is not None and cap != "":
            from .storage import project_lock

            try:
                with project_lock(root):
                    budget.set_budget(root, str(cap), note)
            except (OSError, ValueError, KeyError) as exc:
                raise ValueError(
                    f"Project {slug!r} was created, but its cap could not be recorded. "
                    "Refresh the library and set its cap with clip budget; do not create it again."
                ) from exc
        return {"created": slug, "title": title, "cap": cap}

    def _unsupported_write(self):
        if not self._host_allowed():
            return self._json({"error": "invalid local Host"}, HTTPStatus.BAD_REQUEST)
        query = parse_qs(urlparse(self.path).query)
        if not self._authorised(query):
            return self._json({"error": "token required"}, HTTPStatus.UNAUTHORIZED)
        return self._json({"error": "method not allowed"}, HTTPStatus.METHOD_NOT_ALLOWED)

    do_PUT = _unsupported_write
    do_DELETE = _unsupported_write
    do_PATCH = _unsupported_write
    do_OPTIONS = _unsupported_write

    # -- interim event stream --------------------------------------------- #
    def _idle_stream(self):
        """Keep the interim Studio's EventSource alive without inventing events.

        The durable journal is gone; real progress events arrive with the Phase 4
        frontend. A heartbeat keeps the browser from reconnecting in a loop.
        """
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "keep-alive")
        self.end_headers()
        try:
            while True:
                self.wfile.write(b": keep-alive\n\n")
                self.wfile.flush()
                time.sleep(HEARTBEAT_SECONDS)
        except (BrokenPipeError, ConnectionResetError):
            return


APP = (
    """<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Studio</title>
<style>
:root{color-scheme:dark;--bg:#0a0f14;--panel:#111a22;--panel2:#16222c;--ink:#f2efe6;--muted:#8fa0ae;--gold:#d4ae6a;
--teal:#688f9d;--line:#1f2c37;--ok:#6fb585;--warn:#d9a441;--bad:#d4655f}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:1380px;margin:0 auto;padding:26px 22px 80px}
.kicker{color:var(--gold);text-transform:uppercase;letter-spacing:.15em;font-size:11px;font-weight:700}
h1{font-size:30px;margin:4px 0 18px;letter-spacing:-.02em}
h2{font-size:20px;color:var(--ink);margin:0 0 12px;overflow-wrap:anywhere}
h3{font-size:15px;margin:18px 0 8px}
.grid{display:grid;grid-template-columns:380px 1fr;gap:18px}@media(max-width:1000px){.grid{grid-template-columns:1fr}}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:16px}
label{display:block;font-size:10px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin:10px 0 4px}
input,select{width:100%;background:#0e161d;color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:8px 10px;font:inherit;font-size:16px}
button{background:var(--gold);color:#0a0f14;border:0;border-radius:8px;padding:9px 14px;font:inherit;font-weight:700;cursor:pointer;margin-top:14px}
button:disabled{background:#2a3540;color:#7b8b98}
.row{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.card{display:block;text-decoration:none;color:var(--ink);border:1px solid var(--line);border-radius:12px;padding:14px;margin-bottom:10px;background:linear-gradient(180deg,#16222c,#111a22);cursor:pointer}
.card:hover,.card.on{border-color:var(--gold)}
.card b{font-size:16px}.meta{color:var(--muted);font-size:12px;margin-top:4px}
.tag{font-size:12px;border:1px solid var(--line);border-radius:999px;padding:3px 7px;color:var(--muted);margin:2px 4px 2px 0;display:inline-block}
.tag.ok{color:var(--ok);border-color:#2c5240}.tag.warn{color:var(--gold);border-color:#4a3d25}.tag.bad{color:var(--bad);border-color:#5b2f2f}
#msg{font-size:12px;margin-top:10px;min-height:18px}#msg.err{color:var(--bad)}#msg.ok{color:var(--ok)}
.mono,.code{font-family:ui-monospace,Menlo,monospace;font-size:11px;color:var(--muted)}
.tabbar{display:flex;gap:6px;flex-wrap:wrap;margin:12px 0 16px;border-bottom:1px solid var(--line);padding-bottom:12px}
button.tab{background:#0f1820;color:var(--muted);border:1px solid var(--line);border-radius:999px;padding:6px 13px;font:inherit;font-size:12px;font-weight:500;margin:0}
button.tab.on{background:var(--gold);border-color:var(--gold);color:#0a0f14;font-weight:700}
.stats{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0 14px}
.stat{background:#0e161d;border:1px solid var(--line);border-radius:10px;padding:7px 11px;min-width:82px}
.stat b{display:block;font-size:20px}.stat span{color:var(--muted);font-size:12px}
.stillgrid{display:grid;grid-template-columns:repeat(auto-fill,minmax(148px,1fr));gap:10px}
.still{background:#0e161d;border:1px solid var(--line);border-radius:10px;padding:0;margin:0;overflow:hidden;text-align:left;cursor:pointer;font-weight:400;color:var(--ink)}
.still:hover,.still.on{border-color:var(--gold)}
.still img{display:block;width:100%;aspect-ratio:16/9;object-fit:contain;background:#0b1218}
.still .noimg{aspect-ratio:16/9;display:flex;align-items:center;justify-content:center;color:var(--muted);font-size:11px;text-align:center;padding:6px}
.still .cap{padding:7px 8px;font-size:11px;line-height:1.35}
.still .cap b{font-size:12px}
.still .cap .p{color:var(--muted);display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.badge{display:inline-block;font-size:12px;padding:3px 6px;border-radius:999px;border:1px solid var(--line);color:var(--muted);margin-left:4px}
.badge.accept{color:var(--ok);border-color:#2c5240}.badge.reject{color:var(--bad);border-color:#5b2f2f}
.badge.uncertain{color:var(--warn);border-color:#5b4a2a}.badge.approved{color:var(--ok);border-color:#2c5240}
.badge.stale,.badge.blocked{color:var(--bad);border-color:#5b2f2f}.badge.missing{color:var(--muted)}
.badge.unavailable{color:#8fa0ae;border-style:dashed}.badge.recorded{color:var(--gold);border-color:#4a3d25}
.filters{display:flex;gap:6px;flex-wrap:wrap;margin:4px 0 12px}
button.chip{background:#0f1820;color:var(--muted);border:1px solid var(--line);border-radius:999px;padding:6px 10px;font:inherit;font-size:12px;font-weight:500;margin:0;min-height:32px}
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
th{color:var(--muted);font-size:12px;position:sticky;top:0;background:var(--panel)}
.scroll{max-height:46vh;overflow:auto;border:1px solid var(--line);border-radius:10px}
.run{display:flex;width:100%;text-align:left;gap:8px;align-items:center;padding:10px;background:none;color:var(--ink);border-bottom:1px solid var(--line);font-size:14px;cursor:pointer;flex-wrap:wrap}
.run:last-child{border:0}.run b{font-weight:600}.run.on{color:var(--gold)}
#log{height:32vh;overflow:auto;background:#0e161d;border:1px solid var(--line);border-radius:9px;padding:9px;font:11px/1.5 ui-monospace,Menlo,monospace}
#log div{padding:1px 0;border-bottom:1px solid #121c24}
.ev{color:var(--teal)}.out{color:var(--muted)}.err{color:var(--bad)}.gold{color:var(--gold)}
button.mini{background:#0f1820;color:var(--ink);border:1px solid var(--line);border-radius:6px;padding:6px 10px;font:inherit;font-size:12px;font-weight:500;margin:0;min-height:32px}
.empty{color:var(--muted);padding:30px;border:1px dashed var(--line);border-radius:12px;text-align:center}
:focus-visible{outline:2px solid var(--gold);outline-offset:3px}
a{color:var(--gold)}button:hover{filter:brightness(1.15)}button:disabled{cursor:wait}
.skip{position:absolute;left:-9999px}.skip:focus{left:20px;top:8px;background:var(--bg);z-index:10}
summary{cursor:pointer;min-height:36px;padding:6px 0;color:var(--gold)}details{margin:12px 0}
.notice{color:var(--muted);max-width:85ch}.decision{border-left:3px solid var(--gold);padding:12px 16px;background:#0e161d;margin:12px 0}
.decision h3{margin:0 0 6px}.decision pre{max-height:none}.blocker,.warn{color:var(--warn)}.note{color:var(--muted)}
.tag.succeeded{color:var(--ok)}.tag.failed,.tag.interrupted{color:var(--bad)}.tag.running{color:var(--teal)}.tag.waiting{color:var(--warn)}
.toolbar{display:flex;align-items:center;gap:12px;flex-wrap:wrap;margin:12px 0}.toolbar button{margin:0}
#detailTitle{font-family:inherit;font-size:22px;color:var(--ink)}#freshness{color:var(--muted);font-size:12px}
.scroll{max-width:100%}.panel{min-width:0}.meta,.code,dd,td{overflow-wrap:anywhere}.card .meta{font-weight:400}
.approval-table{table-layout:fixed}.approval-table th,.approval-table td{width:14%}.approval-table th:nth-child(3),.approval-table td:nth-child(3){width:30%}
@media(max-width:700px){.approval-table thead{display:none}.approval-table,.approval-table tbody,.approval-table tr,.approval-table td{display:block;width:100%!important}.approval-table tr{padding:12px;border-bottom:1px solid var(--line)}.approval-table td{padding:6px 0;border:0}.approval-table td:before{content:attr(data-label);display:block;color:var(--muted);font-weight:600}}
#list{max-height:calc(100dvh - 340px);overflow-y:auto;padding:3px}.grid>section{align-self:start}
@media(max-width:1000px){#list{max-height:300px;overflow:auto}.wrap{padding:20px 16px 40px}}
</style><style>__STUDIO_CSS__</style></head><body><a class="skip" href="#detailTitle">Skip to project</a><main class="wrap">
<header class="app-header"><div class="brand"><span class="brand-mark" aria-hidden="true">S</span><div><div class="kicker">Music to film</div><h1>Production Studio</h1></div></div>
<button id="newProduction" type="button">＋ New production</button></header>
<div class="mobile-projects"><label for="projectSwitch">Your production</label><select id="projectSwitch"><option value="">Choose a production</option></select></div>
<div class="grid">
<aside class="panel" aria-label="Production library">
<div class="library-heading"><h2>Library</h2><span id="projectCount" class="meta"></span></div>
<label class="sr-only" for="projectSearch">Search productions</label><input id="projectSearch" type="search" placeholder="Search productions…">
<nav id="list" aria-label="Productions" aria-live="polite">Loading productions…</nav>
<p class="library-foot">Your workspace, from first listen to final film.<br>Media is verified when you open a project.</p>
</aside>
<section class="panel workspace" aria-labelledby="detailTitle">
<div class="project-heading"><div><div class="kicker" id="projectEyebrow">Your workspace</div><h2 id="detailTitle" tabindex="-1">Choose your next film</h2><p id="projectMeta" class="meta"></p></div>
<div class="toolbar"><button id="refresh" class="mini" type="button">↻ Refresh state</button><span id="freshness" role="status" aria-live="polite">Not checked yet</span></div></div>
<div id="tabs" role="tablist" aria-label="Production workflow" hidden>
<div class="utility-tabs" role="presentation">
<button class="tab" id="tab-project" role="tab" aria-selected="false" aria-controls="view" tabindex="-1" data-tab="project">Project</button>
</div>
<div class="workflow-tabs" role="presentation">
<button class="tab step" id="tab-track" role="tab" aria-selected="false" aria-controls="view" tabindex="-1" data-tab="track"><span class="step-number">01</span><span>Track<span class="step-state"></span></span></button>
<button class="tab step" id="tab-story" role="tab" aria-selected="false" aria-controls="view" tabindex="-1" data-tab="story"><span class="step-number">02</span><span>Story<span class="step-state"></span></span></button>
<button class="tab step" id="tab-style" role="tab" aria-selected="false" aria-controls="view" tabindex="-1" data-tab="style"><span class="step-number">03</span><span>Style check<span class="step-state"></span></span></button>
<button class="tab step" id="tab-images" role="tab" aria-selected="false" aria-controls="view" tabindex="-1" data-tab="images"><span class="step-number">04</span><span>Images<span class="step-state"></span></span></button>
<button class="tab step" id="tab-finish" role="tab" aria-selected="false" aria-controls="view" tabindex="-1" data-tab="finish"><span class="step-number">05</span><span>Finish<span class="step-state"></span></span></button>
</div></div>
<div id="view" role="tabpanel" aria-labelledby="tab-project"><div class="welcome"><span class="welcome-icon" aria-hidden="true">▷</span><div class="kicker">A considered process. A better film.</div><h2>Bring your music into focus.</h2><p>Choose a production from the library, or start with a local track. Analyse the music, agree the story and style, review the images, then finish the film.</p><button type="button" id="welcomeCreate">Start a production</button><p class="meta">Setup is local. Nothing is uploaded, generated or spent.</p></div></div>
</section>
</div>
<dialog id="createDialog" aria-labelledby="createTitle"><div class="dialog-heading"><div><div class="kicker">A new beginning</div><h2 id="createTitle">New production</h2></div><button id="closeCreate" class="mini" type="button" aria-label="Close new production">✕</button></div>
<ol class="wizard-steps" aria-label="Setup progress"><li aria-current="step">1 · Track</li><li>2 · Film settings</li><li>3 · Budget & confirm</li></ol>
<form id="createForm">
<fieldset data-setup-step="0"><legend>Choose your track</legend><p class="notice">Browse for an MP3 on this Mac. The chosen file is copied into this local production; nothing is uploaded to a provider.</p>
<label for="sourceFile">Song file</label><input id="sourceFile" type="file" accept=".mp3,audio/mpeg" required aria-describedby="sourceHelp">
<p id="sourceHelp" class="meta">MP3 only, up to 250 MB. Your original file stays untouched.</p>
<p id="sourceStatus" class="meta" role="status" aria-live="polite"></p>
</fieldset>
<fieldset data-setup-step="1" hidden><legend>Give your film a direction</legend>
<label for="title">Film title</label><input id="title" required maxlength="120" placeholder="Give your film a title">
<div class="row"><div><label for="aspect">Frame format</label><select id="aspect" aria-describedby="aspectHelp"><option value="16:9">Landscape · 16:9</option><option value="9:16">Portrait · 9:16</option></select></div>
<div><label for="fps">Frame rate</label><select id="fps"><option value="24">24 fps · cinematic</option><option value="30">30 fps</option></select></div></div>
<p id="aspectHelp" class="meta">Landscape supports the complete titles and credits package.</p>
<label for="mode">Music approach</label><select id="mode" aria-describedby="modeHelp"><option value="vocal">Vocal · with sung lyrics</option><option value="instrumental">Instrumental · no lyrics</option><option value="music-led">Music-led · mixed or DJ track</option></select>
<p id="modeHelp" class="meta">Vocal includes lyric review. Instrumental skips lyrics, not music review. Music-led keeps supplied intent separate from measured evidence.</p>
</fieldset>
<fieldset data-setup-step="2" hidden><legend>Set your budget. Stay in control.</legend>
<label for="cap">Total production allowance (USD)</label><input id="cap" type="number" required placeholder="Enter your limit" step="0.01" min="0.01" aria-describedby="budgetHelp">
<p id="budgetHelp" class="notice">An overall allowance, not a charge. Every paid batch still needs a separate quote and your authorization.</p>
<dl id="setupSummary" class="setup-summary"></dl>
<div class="callout">Creates a local production and records your allowance. No upload, generation or spending starts here.</div>
</fieldset>
<div id="msg" role="status" aria-live="polite"></div>
<div class="wizard-actions"><button id="setupBack" type="button" class="mini" hidden>Back</button><button id="setupNext" type="button">Continue</button><button id="create" type="submit" hidden>Create production</button></div>
</form></dialog></main>
<script>
const token=new URLSearchParams(location.search).get('token')||'';
const q=token?('?token='+encodeURIComponent(token)):'';
const hdr=token?{'X-Studio-Token':token}:{};
const view=document.getElementById('view');
let current=null, tab='overview', stillsData=null, stillFilter=null, cockpitSource=null, cockpitRun=null, viewGen=0;
let projects=[], currentData=null, sourceGen=0, shotGen=0, pendingShot=null, selectedSource=null, uploading=false, activityVersion=0, cockpitEpoch=0, creating=false;
const verifiedEntries=new Map();
const stageNames={analysis:'Music analysis',lyrics:'Lyrics',listening:'Music listening',brand:'Brand identity',events:'Music events',brief:'Creative brief',storyboard:'Storyboard',proof:'Three-shot proof',preview:'Music preview',stills:'Full still set',graphics:'Titles and credits'};
__JS_HELPERS__
function withToken(path){if(!token)return path;return path+(path.includes('?')?'&':'?')+'token='+encodeURIComponent(token);}
async function api(path){const r=await fetch(withToken(path));const d=await r.json();if(!r.ok)throw new Error(d.error||('HTTP '+r.status));return d;}
function clock(seconds){const n=Math.round(Number(seconds)||0);return Math.floor(n/60)+':'+String(n%60).padStart(2,'0');}
function money(value){return value===null||value===undefined?'not recorded':new Intl.NumberFormat(undefined,{style:'currency',currency:'USD',minimumFractionDigits:2,maximumFractionDigits:6}).format(Number(value));}
function stamp(value){return value?new Date(value).toLocaleString(undefined,{dateStyle:'medium',timeStyle:'short'}):'No decision recorded';}
function errorPanel(node,message,retry){clear(node);node.setAttribute('aria-busy','false');const box=el('div','empty');box.setAttribute('role','alert');box.append(el('p',null,message));if(retry){const b=el('button','mini','Try again');b.onclick=retry;box.append(b);}node.append(box);}
function copyCommand(command){
 const box=el('div');const pre=el('pre',null,command);pre.tabIndex=0;box.append(pre);
 const btn=el('button','mini','Copy command');btn.type='button';const feedback=el('span','meta');feedback.setAttribute('role','status');
 btn.onclick=async function(){try{if(!navigator.clipboard)throw new Error('clipboard unavailable');await navigator.clipboard.writeText(command);feedback.textContent=' Copied';}catch(e){feedback.textContent=' Copy unavailable — select the command above and copy manually.';}};
 box.append(btn,feedback);return box;
}
function badge(v){const t=v||'unreviewed';return el('span','badge '+t,t);}
function stateTag(state){const cls=state==='approved'?'ok':(['stale','blocked'].includes(state)?'bad':(state==='recorded'?'warn':''));const n=el('span','tag '+cls,state==='recorded'?'not checked':state);if(state==='recorded')n.title='Approval on record; current media bytes have not been checked.';return n;}
function clear(node){while(node.firstChild)node.removeChild(node.firstChild);}
function stat(b,label){const n=el('div','stat');n.append(el('b',null,String(b)));n.append(el('span',null,label));return n;}
function stopCockpit(){cockpitEpoch++;if(cockpitSource){cockpitSource.close();cockpitSource=null;}cockpitRun=null;}
function setTab(name){tab=name;document.querySelectorAll('button.tab').forEach(function(b){const on=b.dataset.tab===name;b.classList.toggle('on',on);b.setAttribute('aria-selected',String(on));b.tabIndex=on?0:-1;});view.setAttribute('aria-labelledby','tab-'+name);scrollWorkflow();}
async function loadProjects(){
 const d=await api('/api/studio');
 projects=d.productions;renderProjects();
}
function syncCreate(){
 const submit=document.getElementById('create');
 submit.disabled=creating||uploading||!selectedSource;
 submit.textContent=creating?'Creating production…':'Create production';
 document.getElementById('setupNext').disabled=creating||uploading||!selectedSource;
 document.getElementById('setupBack').disabled=creating;
 document.querySelectorAll('#createForm fieldset').forEach(f=>f.disabled=creating||uploading);
}
function renderProjects(){renderLibrary();}
function openProject(slug,title,name='overview'){
 current={slug:slug,title:title};currentData=null;stillsData=null;stillFilter=null;pendingShot=null;shotGen++;stopCockpit();
  document.getElementById('detailTitle').textContent=title;
  renderProjects();document.getElementById('detailTitle').focus({preventScroll:true});document.getElementById('tabs').hidden=false;showTab(name,true);
}
function navigate(slug,name){const hash='#/'+encodeURIComponent(slug)+'/'+name;if(location.hash===hash)applyRoute();else location.hash=hash;}
function applyRoute(){
  const parts=location.hash.slice(1).split('/');if(parts[0]!==''||!parts[1]){current=null;currentData=null;viewGen++;shotGen++;stopCockpit();setTab('overview');view.setAttribute('aria-busy','false');document.getElementById('tabs').hidden=true;document.getElementById('detailTitle').textContent='Choose your next film';document.getElementById('projectEyebrow').textContent='Your workspace';document.getElementById('projectMeta').textContent='';clear(view);view.append(initialWelcome.cloneNode(true));document.getElementById('welcomeCreate').onclick=openSetup;document.getElementById('freshness').textContent='Not checked yet';renderProjects();return;}
  let slug;try{slug=decodeURIComponent(parts[1]);}catch(e){current=null;currentData=null;viewGen++;shotGen++;stopCockpit();document.getElementById('tabs').hidden=true;document.getElementById('detailTitle').textContent='Invalid project link';document.getElementById('projectMeta').textContent='';renderProjects();errorPanel(view,'Invalid project link. Choose a production from the library.');return;}
 const name=Object.hasOwn(loaders,parts[2])?parts[2]:'overview';
 const p=projects.find(x=>x.slug===slug);
  if(!p){current=null;currentData=null;viewGen++;shotGen++;stopCockpit();document.getElementById('tabs').hidden=true;document.getElementById('detailTitle').textContent='Production not found';document.getElementById('projectMeta').textContent='';renderProjects();errorPanel(view,'This production was not found. Choose one from the library.');return;}
 if(current&&current.slug===slug)showTab(name,true);else openProject(slug,p.title,name);
}
 const loaders={stills:loadStills,board:loadBoard,approvals:loadApprovals,runs:loadRuns};
function showTab(name,fromRoute=false){
 if(!current)return;
 if(!fromRoute){navigate(current.slug,name);return;}
 const gen=++viewGen;
 shotGen++;setTab(name);view.textContent='';view.setAttribute('aria-busy','true');view.append(el('p','meta',currentData?'Loading…':'Checking current project state…'));stopCockpit();
 const snapshot=currentData?Promise.resolve(true):loadSnapshot(gen);
 snapshot.then(function(ok){if(ok)return loaders[name](gen);}).catch(function(e){if(gen!==viewGen)return;errorPanel(view,e.message,()=>showTab(name,true));document.getElementById('freshness').textContent='Check failed — displayed state may be old';}).finally(function(){if(gen===viewGen)view.setAttribute('aria-busy','false');});
}
async function loadSnapshot(gen){
 const version=activityVersion;const d=await api('/api/project/'+encodeURIComponent(current.slug));if(gen!==viewGen)return false;
  currentData=d;verifiedEntries.set(current.slug,{...d.entry,checked_at:d.checked_at});renderProjects();updateWorkflow();
  const freshness=document.getElementById('freshness');freshness.title='Checked '+stamp(d.checked_at)+' · last activity '+(d.entry.last_activity_ago||'unknown');freshness.textContent=version!==activityVersion?'Studio activity detected during this check — refresh again':'Checked '+new Date(d.checked_at).toLocaleTimeString(undefined,{hour:'2-digit',minute:'2-digit'})+' · snapshot';return true;
}
async function loadStills(gen){
 const data=await api('/api/project/'+encodeURIComponent(current.slug)+'/stills');if(gen!==viewGen)return;stillsData=data;renderStills();if(pendingShot){const id=pendingShot;pendingShot=null;showShot(id);}
}
function renderStills(){
  clear(view); const d=stillsData;
  if(!d.available){view.append(el('div','empty',d.warning||'no storyboard'));return;}
  if(tab==='stills')view.append(heading('Review the full visual sequence.','Inspect each selected image against its purpose, music context and neighboring shots. Selecting a tile opens its contract; it does not record a verdict.'));
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
   const selected=stillFilter===pair[0]||(!stillFilter&&pair[0]==='all');const b=el('button','chip'+(selected?' on':''),pair[1]);b.setAttribute('aria-pressed',String(selected));
   b.addEventListener('click',function(){shotGen++;stillFilter=pair[0]==='all'?null:pair[0];renderStills();const target=[...view.querySelectorAll('.chip')].find(x=>x.textContent===pair[1]);if(target)target.focus();});
  filters.append(b);
 }
 view.append(filters);
 const panel=el('div','detailbox'); panel.id='shotPanel';panel.hidden=true;view.append(panel);
 const grid=el('div','stillgrid'); view.append(grid);
 let shown=0;
 for(const s of d.shots){
  const verdict=s.verdict||'unreviewed';
  if(stillFilter&&verdict!==stillFilter)continue;
  shown++;
   const card=el('button','still');card.dataset.shot=s.id;
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
   card.setAttribute('aria-pressed','false');card.addEventListener('click',function(){document.querySelectorAll('.still').forEach(function(x){x.classList.remove('on');x.setAttribute('aria-pressed','false');});card.classList.add('on');card.setAttribute('aria-pressed','true');showShot(s.id);});
  grid.append(card);
 }
 if(!shown)grid.append(el('div','empty','nothing matches this filter'));
}
async function showShot(id){
 const panel=document.getElementById('shotPanel');if(!panel||!current)return;const slug=current.slug;const gen=++shotGen;panel.hidden=false;panel.textContent='Loading '+id+'…';panel.setAttribute('aria-busy','true');
 try{
   const d=await api('/api/project/'+encodeURIComponent(slug)+'/shot/'+encodeURIComponent(id));if(gen!==shotGen||!current||current.slug!==slug||!panel.isConnected)return;
   clear(panel);
   const controls=el('div','detail-actions');controls.append(el('b',null,'Shot inspection'),actionButton('Close inspection',()=>{panel.hidden=true;const selected=[...document.querySelectorAll('.still')].find(c=>c.dataset.shot===id);selected?.focus({preventScroll:true});}));panel.append(controls);
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
   const promptDetails=el('details');promptDetails.append(el('summary',null,'Compiled prompt · technical details'));
   if(d.prompt_error)right.append(el('p','meta','prompt unavailable: '+d.prompt_error));
   const pre=el('pre',null,d.prompt||'no compiled prompt recorded');
   promptDetails.append(pre);right.append(promptDetails);
   cols.append(right); panel.append(cols);panel.setAttribute('aria-busy','false');panel.tabIndex=-1;panel.focus({preventScroll:true});panel.scrollIntoView({block:'nearest'});
 }catch(e){if(gen===shotGen&&panel.isConnected){panel.setAttribute('aria-busy','false');errorPanel(panel,e.message,()=>showShot(id));}}
}
async function loadBoard(gen){
 const d=await api('/api/project/'+current.slug+'/board'); if(gen!==viewGen)return; clear(view);
 if(!d.available){view.append(el('div','empty',d.warning||'no storyboard'));return;}
  view.append(heading('Build the sequence, not just a shot list.','Review timing, musical binding and coverage. Open a shot to inspect its selected still, contract and compiled prompt.'));
  const stats=el('div','stats');
 stats.append(stat(d.shots.length,'shots')); stats.append(stat(d.total_frames,'frames'));
 stats.append(stat(clock(d.duration),'duration')); stats.append(stat(d.fps,'fps'));
 view.append(stats);
 view.append(el('p','meta','bar grid: '+(d.grid.enabled?'enabled':'not claimed — '+(d.grid.reason||'no approved grid'))));
 if(d.bands.length){
   const bands=el('div','section-list');bands.setAttribute('aria-label','Musical sections');
   for(const b of d.bands){
    const seg=el('div','section-item',b.label);seg.append(el('span',null,clock(b.start_seconds)+'–'+clock(b.end_seconds)+' · '+(b.timing_basis||'unknown timing basis')));
    seg.title=b.label+' · '+b.start_seconds+'s–'+b.end_seconds+'s · '+b.confidence;
    bands.append(seg);
  }
  view.append(bands);
 }
 const track=el('div','track');track.setAttribute('aria-hidden','true');
 for(const s of d.shots){
  const bar=el('div','shotbar '+s.framing); bar.title=s.id+' · '+s.start_seconds+'s–'+s.end_seconds+'s · '+s.purpose;
  bar.style.left=(s.start_frame/d.total_frames*100)+'%'; bar.style.width=(s.seconds/d.duration*100)+'%'; track.append(bar);
 }
 view.append(track);
  const scroll=el('div','scroll');scroll.tabIndex=0;scroll.setAttribute('aria-label','Storyboard shots, scroll for more'); const table=el('table','board-table'); const head=el('tr');
  for(const label of ['Shot','Timing','Framing & edit','Purpose & music']){const th=el('th',null,label);th.scope='col';head.append(th);}
  const thead=el('thead');thead.append(head);table.append(thead);const tbody=el('tbody');table.append(tbody);
 for(const s of d.shots){
    const tr=el('tr');const cell=el('td');const inspect=el('button','mini',s.id);inspect.setAttribute('aria-label','Inspect shot '+s.id);inspect.onclick=()=>{pendingShot=s.id;showTab('stills');};cell.append(inspect);tr.append(cell);
   const timing=el('td',null,s.seconds.toFixed(1)+'s');timing.append(el('div','meta',clock(s.start_seconds)+'–'+clock(s.end_seconds)),el('div','mono',s.start_frame+'–'+s.end_frame+'f'));tr.append(timing);
   const edit=el('td',null,(s.framing||'—').replaceAll('_',' '));edit.append(el('div','meta',s.transition+(s.dissolve_frames?' · '+s.dissolve_frames+'f dissolve':'')));tr.append(edit);
   const purpose=el('td','shot-purpose',s.purpose);if(s.event_ids?.length)purpose.append(el('div','meta','Music: '+s.event_ids.join(', ')));tr.append(purpose);tbody.append(tr);
 }
  scroll.append(table); view.append(scroll,stageReview('storyboard'));
}
async function loadApprovals(gen){
 if(gen!==viewGen)return;const d=currentData.approvals;clear(view);
  view.append(heading('Review decisions with the evidence in view.','Approval records stay bound to the exact content you reviewed. Changed artifacts require a fresh decision.'));
  view.append(el('p','meta',d.current+' of '+d.total+' stages would pass now. These checks are not new approvals.'));
 const scroll=el('div','scroll');const table=el('table','approval-table');const head=el('tr');const labels=['Stage','State','Decision note','Recorded at','Would pass','Technical details'];
 for(const label of labels){const th=el('th',null,label);th.scope='col';head.append(th);}const thead=el('thead');thead.append(head);table.append(thead);const tbody=el('tbody');table.append(tbody);
  for(const s of d.stages){
  const tr=el('tr');
   tr.append(el('td',null,stageNames[s.stage]||s.stage));const state=el('td');state.append(badge(s.state));tr.append(state);
    const note=el('td');note.append(el('div','decision-note',s.note||'No decision recorded'));if(s.note?.length>240){const full=el('details','full-note');full.append(el('summary',null,'Read full decision'),el('p',null,s.note));note.append(full);}if(s.problem)note.append(el('p','warn',s.problem));tr.append(note);tr.append(el('td',null,stamp(s.at)+(s.at?' · '+(s.via||'legacy surface'):'')));tr.append(el('td',null,s.would_pass_now?'yes':'no'));
   const cmd=el('td');const technical=el('details');technical.append(el('summary',null,'Hashes and provenance'),el('p','meta','Human decisions use a terminal-enabled Studio session.'),el('p','code','Current hash: '+(s.hash||'unavailable')),el('p','code','Approved hash: '+(s.approved_hash||'none')));if(s.stage==='preview')technical.append(el('p','meta','Continuous playback attestation: '+(s.preview_watched===true?'recorded':'not recorded (legacy/unspecified)')));cmd.append(technical);tr.append(cmd);
   [...tr.children].forEach((td,i)=>td.dataset.label=labels[i]);tbody.append(tr);
 }
  scroll.append(table); view.append(scroll);
  for(const s of d.supporting_stages||[]){const card=el('section','content-card');card.append(el('h3',null,stageNames[s.stage]||s.stage),badge(s.state),el('p','notice',s.note||'No decision recorded'));if(s.problem)card.append(el('p','warn',s.problem));card.append(actionButton('Review '+(stageNames[s.stage]||s.stage),()=>{pendingApprovalStage=s.stage;showTab('approvals');}));view.append(card);}
 humanApprovalPanel(gen);
}
async function loadRuns(gen){
 clear(view); stopCockpit();
 const d=await api('/api/runs?limit=20'); if(gen!==viewGen)return; const list=el('div',''); const panel=el('div','panel'); panel.style.marginTop='12px';
 const head=el('h2',null,'Live events'); const log=el('div'); log.id='log'; panel.append(head,log);
 const runs=d.runs.filter(r=>r.production===current.slug);view.append(el('p','meta','Showing this project’s runs from the latest 20 Studio journal entries.'));
 if(!runs.length){view.append(el('div','empty','No recent runs for this production. Start one with a clip command.'));return;}
 for(const run of runs){
   const row=el('button','run');row.type='button';row.append(el('b',null,run.intent||run.id)); row.append(el('span','tag '+run.status,run.status));
  if(run.production)row.append(el('span','mono',run.production));
  row.addEventListener('click',function(){document.querySelectorAll('.run').forEach(function(x){x.classList.remove('on');});row.classList.add('on');selectRun(run.id);});
  list.append(row);
 }
 view.append(list,panel);
  selectRun(runs[0].id);
}
async function selectRun(id){
 stopCockpit(); cockpitRun=id;const epoch=cockpitEpoch;
 try{
 const d=await api('/api/events?run='+encodeURIComponent(id)+'&after=0&limit=200');
 if(cockpitRun!==id||epoch!==cockpitEpoch)return;
 const log=document.getElementById('log'); if(!log)return; log.textContent='';
 let last=0;
 for(const ev of d.events){last=Math.max(last,ev.seq);appendEvent(ev);}
 function connect(){if(epoch!==cockpitEpoch)return;const url='/api/stream?after='+last+'&run='+encodeURIComponent(id)+(token?'&token='+encodeURIComponent(token):'');
 const es=new EventSource(url);cockpitSource=es;es.onmessage=function(m){if(epoch!==cockpitEpoch)return;try{const ev=JSON.parse(m.data);last=Math.max(last,ev.seq);appendEvent(ev);}catch(e){}};
 es.onerror=function(){es.close();if(cockpitSource===es){cockpitSource=null;setTimeout(connect,3000);}};}
 connect();
 }catch(e){if(epoch===cockpitEpoch){const log=document.getElementById('log');if(log)errorPanel(log,e.message,()=>selectRun(id));}}
}
function appendEvent(ev){
 const log=document.getElementById('log'); if(!log)return;
 const payload=eventPayload(ev);
 const line=el('div',ev.type==='command.output'?'out':((ev.type.includes('failed')||ev.type.includes('interrupted'))?'err':'ev'));
 line.textContent=ev.type==='command.output'&&payload.line!==undefined?payload.line:'['+ev.type+'] '+JSON.stringify(payload);
 log.append(line); while(log.childNodes.length>400)log.removeChild(log.firstChild); log.scrollTop=log.scrollHeight;
}
document.getElementById('tabs').addEventListener('click',function(e){const b=e.target.closest('button.tab');if(b)showTab(b.getAttribute('data-tab'));});
document.getElementById('tabs').addEventListener('keydown',function(e){if(!['ArrowLeft','ArrowRight','Home','End'].includes(e.key))return;const buttons=[...document.querySelectorAll('.tab')];const index=buttons.indexOf(document.activeElement);const next=e.key==='Home'?0:e.key==='End'?buttons.length-1:(index+(e.key==='ArrowRight'?1:-1)+buttons.length)%buttons.length;e.preventDefault();buttons[next].focus();showTab(buttons[next].dataset.tab);});
async function uploadSource(file){
 const gen=++sourceGen;selectedSource=null;uploading=true;
 const status=document.getElementById('sourceStatus');
 status.className='meta';status.textContent='Copying '+file.name+' locally…';syncCreate();
 try{
  const r=await fetch(withToken('/api/source?name='+encodeURIComponent(file.name)),{method:'POST',headers:Object.assign({},hdr,{'Content-Type':'application/octet-stream'}),body:file});
  const d=await r.json();if(!r.ok)throw new Error(d.error||('HTTP '+r.status));
  if(gen!==sourceGen)return;
  selectedSource=d;
  status.className='ok';status.textContent=d.name+' · '+clock(d.seconds)+' · '+((Number(d.bytes)||0)/1048576).toFixed(1)+' MB';
 }catch(e){
  if(gen!==sourceGen)return;selectedSource=null;status.className='warn';status.textContent=e.message;
  const input=document.getElementById('sourceFile');if(input)input.value='';
 }finally{if(gen===sourceGen){uploading=false;syncCreate();}}
}
function chooseSource(file){
 const input=document.getElementById('sourceFile'),status=document.getElementById('sourceStatus');
 if(!file){sourceGen++;selectedSource=null;uploading=false;status.textContent='';syncCreate();return;}
 if(!/\\.mp3$/i.test(file.name)){sourceGen++;selectedSource=null;input.value='';status.className='warn';status.textContent='Choose an MP3 file.';syncCreate();return;}
 if(file.size>250*1024*1024){sourceGen++;selectedSource=null;input.value='';status.className='warn';status.textContent='That MP3 is larger than 250 MB.';syncCreate();return;}
 uploadSource(file);
}
document.getElementById('createForm').addEventListener('submit',async function(event){
 event.preventDefault();if(setupStep!==2){if(validSetupStep())showSetupStep(setupStep+1);return;}const source=selectedSource;if(creating||uploading||!source||!validSetupStep())return;creating=true;syncCreate();
 const body={audio:source.path,title:document.getElementById('title').value.trim(),
  aspect:document.getElementById('aspect').value,fps:Number(document.getElementById('fps').value),
  music_mode:document.getElementById('mode').value,cap:document.getElementById('cap').value};
 const msg=document.getElementById('msg'); msg.className='';msg.textContent='creating…';
 let created=null;
 try{const r=await fetch(withToken('/api/create'),{method:'POST',headers:Object.assign({},hdr,{'Content-Type':'application/json'}),body:JSON.stringify(body)});
 const d=await r.json();if(!r.ok)throw new Error(d.error||('HTTP '+r.status));created=d.created;
 msg.className='ok';msg.textContent='Created '+d.title+'. Opening project…';await loadProjects();navigate(d.created,'overview');document.getElementById('createDialog').close();this.reset();selectedSource=null;uploading=false;sourceGen++;document.getElementById('sourceStatus').textContent='';showSetupStep(0);
 }catch(e){msg.className='err';msg.textContent=created?'Project '+created+' was created, but the library could not refresh. Refresh state before doing anything else.':'Creation could not be confirmed: '+e.message+'. Refresh the library before retrying; do not submit again if the project already exists.';}
 finally{creating=false;syncCreate();}
});
document.getElementById('sourceFile').addEventListener('change',event=>chooseSource(event.target.files[0]));
window.addEventListener('hashchange',applyRoute);
document.getElementById('refresh').onclick=async function(){const b=this;b.disabled=true;try{currentData=null;verifiedEntries.clear();await loadProjects();applyRoute();}catch(e){errorPanel(view,e.message,()=>b.click());}finally{b.disabled=false;}};
let activitySource=null,activityCursor=0,activityReady=false;
async function watchActivity(){
 try{if(!activityReady){const s=await api('/api/status');activityCursor=s.latest_seq||0;activityReady=true;}
 const es=new EventSource(withToken('/api/stream?after='+activityCursor));activitySource=es;
 es.onopen=function(){const f=document.getElementById('freshness');if(f.textContent.startsWith('Live connection'))f.textContent='Live connection restored — refresh to check current state';};
 es.onmessage=function(m){try{const ev=JSON.parse(m.data);activityCursor=Math.max(activityCursor,ev.seq);activityVersion++;document.getElementById('freshness').textContent='Studio activity detected — refresh to check current state';}catch(e){}};
 es.onerror=function(){es.close();if(activitySource===es){activitySource=null;document.getElementById('freshness').textContent='Live connection lost — use Refresh state';setTimeout(watchActivity,3000);}};
 }catch(e){document.getElementById('freshness').textContent='Live connection unavailable — use Refresh state';setTimeout(watchActivity,3000);}
}
window.addEventListener('pagehide',()=>{stopCockpit();if(activitySource)activitySource.close();});
__WORKFLOW_UI__
__HUMAN_UI__
loadProjects().then(applyRoute).catch(e=>errorPanel(document.getElementById('list'),e.message,()=>document.getElementById('refresh').click()));watchActivity();
</script></body></html>""".replace("__JS_HELPERS__", JS_HELPERS)
    .replace("__STUDIO_CSS__", studio_ui.CSS)
    .replace("__WORKFLOW_UI__", studio_ui.SCRIPT)
    .replace("__HUMAN_UI__", human_ui.SCRIPT)
)


def _float(query, key):
    raw = (query.get(key) or [None])[0]
    return float(raw) if raw not in (None, "") else None


def build_server(
    projects_dir: str | Path,
    *,
    port: int = 8765,
    token: str | None = None,
    sources_dir: str | Path | None = None,
    action_token: str | None = None,
):
    """Create a loopback server; internal callers may inject a test action capability.

    The public CLI only enables actions after an interactive terminal confirmation.
    Returns ``(server, read_url)``; no action capability is returned by the read API.
    """
    token = token if token is not None else secrets.token_urlsafe(16)
    httpd = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    httpd.daemon_threads = True
    httpd.projects_dir = Path(projects_dir).resolve()
    httpd.token = token
    httpd.action_token = action_token
    httpd.sources_dir = (
        Path(sources_dir).expanduser()
        if sources_dir
        else Path.home() / "Downloads" / "Suno Downloads"
    )
    httpd.upload_dir = httpd.projects_dir.parent / "studio" / "uploads"
    url = f"http://127.0.0.1:{httpd.server_address[1]}/?token={token}"
    return httpd, url


def serve(
    projects_dir: str | Path,
    *,
    port: int = 8765,
    token: str | None = None,
    ready: queue.Queue | None = None,
    actions: bool = False,
) -> None:
    action_token = None
    if actions:
        if not sys.stdin.isatty():
            raise ValueError("Human actions must be enabled by a person in an interactive terminal")
        if (
            input(
                "Enable human approvals and quote authorizations? Type ENABLE HUMAN ACTIONS: "
            ).strip()
            != "ENABLE HUMAN ACTIONS"
        ):
            raise ValueError("Human actions were not enabled")
        action_token = secrets.token_urlsafe(32)
    httpd, url = build_server(projects_dir, port=port, token=token, action_token=action_token)
    app_url = url.replace("/?token=", "/app?token=")
    if ready is not None:
        ready.put(app_url)
    print(f"Studio live: {app_url}")
    if action_token:
        print(f"Human action session: {app_url}#action={action_token}")
    else:
        print(
            "Review-only session. A person can enable decisions with clip serve --actions in their terminal."
        )
    try:
        httpd.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


def start_in_thread(projects_dir, *, port=0, token="test-token"):
    """Test helper: start the server on an ephemeral port and return (server, url, thread)."""
    httpd, url = build_server(projects_dir, port=port, token=token)
    thread = threading.Thread(
        target=httpd.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True
    )
    thread.start()
    return httpd, url, thread
