"""Static shot inspector: versions, verdicts, contract and pre-filled edit commands.

One page per shot. It never writes: the controls compose `clip shot-edit` / `clip
adopt` / `clip review` commands for a human (or an agent) to run, and it states
exactly which approvals a change would invalidate.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from . import production as P
from .dashboard import _thumbnail
from .markup import esc as _esc
from .markup import script_json
from .storage import file_hash, read_json, write_json

FOLDER = "work/inspector"
CSS = """
:root{--bg:#0a0f14;--panel:#111a22;--panel2:#16222c;--ink:#f2efe6;--muted:#8fa0ae;
--gold:#d4ae6a;--teal:#688f9d;--line:#1f2c37;--ok:#6fb585;--warn:#d9a441;--bad:#d4655f}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:1280px;margin:0 auto;padding:28px 22px 90px}
a{color:var(--gold)}
.kicker{color:var(--gold);text-transform:uppercase;letter-spacing:.15em;font-size:11px;font-weight:700}
h1{font-size:30px;margin:4px 0 6px;letter-spacing:-.02em}
h2{font-size:16px;margin:26px 0 10px}
.sub{color:var(--muted);max-width:75ch;margin:0 0 18px}
.cols{display:grid;grid-template-columns:1.25fr .95fr;gap:18px}
@media (max-width:1000px){.cols{grid-template-columns:1fr}}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px}
.versions{display:flex;gap:10px;flex-wrap:wrap}
.version{width:190px}
.version img{width:100%;border-radius:8px;border:1px solid var(--line);display:block}
.version .meta{font-size:11px;color:var(--muted);margin-top:4px;word-break:break-all}
.badge{display:inline-block;font-size:10px;text-transform:uppercase;letter-spacing:.08em;
padding:2px 7px;border-radius:999px;border:1px solid var(--line);color:var(--muted)}
.badge.accept{color:var(--ok);border-color:#2c5240}
.badge.reject{color:var(--bad);border-color:#5b2f2f}
.badge.uncertain{color:var(--warn);border-color:#5b4a2a}
.badge.selected{color:var(--gold);border-color:#4a3d25}
dl{display:grid;grid-template-columns:130px 1fr;gap:6px 12px;margin:0;font-size:13px}
dt{color:var(--muted)}
dd{margin:0}
pre{background:#0e161d;border:1px solid var(--line);border-radius:8px;padding:10px;
overflow:auto;font-size:12px;white-space:pre-wrap;word-break:break-word}
label{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin:10px 0 4px}
input,select{width:100%;background:#0e161d;color:var(--ink);border:1px solid var(--line);
border-radius:7px;padding:7px 9px;font:inherit;font-size:13px}
button{background:var(--panel2);color:var(--ink);border:1px solid var(--line);border-radius:8px;
padding:7px 12px;font:inherit;font-size:13px;cursor:pointer;margin-top:10px}
button:hover{border-color:var(--gold)}
.row{display:grid;grid-template-columns:1fr 1fr;gap:10px}
.must{color:var(--teal);font-size:13px}
.note{color:var(--muted);font-size:12px}
.warn{border-left:3px solid var(--warn);padding-left:10px;color:var(--muted);font-size:12px}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;padding:7px 8px;border-bottom:1px solid var(--line)}
th{color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.08em}
"""

SCRIPT = """
(function(){
 var s=window.__SHOT__;
 function val(id){var el=document.getElementById(id);return el?el.value:'';}
 function set(id,text){var el=document.getElementById(id);if(el)el.textContent=text;}
 function edit(){
   var parts=['uv run clip shot-edit '+'projects/'+s.slug,'--shot '+s.id];
   var tr=val('transition'); if(tr&&tr!=='keep'){parts.push('--transition '+tr);}
   var dv=val('dissolve'); if(dv!==''){parts.push('--dissolve '+dv);}
   var cam=val('camera'); if(cam&&cam!=='keep'){parts.push('--camera '+cam);}
   if(document.getElementById('clear-effects').checked){parts.push('--clear-effects');}
   [['contrast','contrast'],['saturation','saturation'],['brightness','brightness'],['vignette','vignette']]
     .forEach(function(pair){var v=val(pair[0]); if(v!==''){parts.push("--effect "+pair[1]+"="+v);}});
   parts.push("--note '<why this change>'");
   set('edit-command',parts.join(' '));
 }
 document.querySelectorAll('input,select').forEach(function(el){
   el.addEventListener('input',edit); el.addEventListener('change',edit);
 });
 edit();
 var adopt=document.getElementById('adopt-source');
 if(adopt){adopt.addEventListener('input',function(){
   set('adopt-command',"uv run clip adopt projects/"+s.slug+" --shot "+s.id+
     " --source '"+adopt.value+"' --operation '<crop|mirror|grade>' --note '<why>' --permission-confirmed");
 });}
 document.querySelectorAll('[data-copy]').forEach(function(btn){
   btn.addEventListener('click',function(){
     var el=document.getElementById(btn.getAttribute('data-copy'));
     if(el&&navigator.clipboard)navigator.clipboard.writeText(el.textContent);
     btn.textContent='Copied';
   });
 });
})();
"""


def _thumbnail_uri(root: Path, cache: Path, relative: str) -> str | None:
    thumb = _thumbnail(root, cache, relative)
    return f"data:image/jpeg;base64,{thumb}" if thumb else None


def _latest_verdicts(reviews: list[dict]) -> dict[tuple, dict]:
    latest: dict[tuple, dict] = {}
    for review in reviews:
        latest[(review.get("shot_id"), review.get("version"))] = review
    return latest


def _version_block(root: Path, cache: Path, shot, versions, verdicts, selected) -> str:
    cards = []
    for version in versions:
        uri = _thumbnail_uri(root, cache, version["path"])
        verdict = verdicts.get((shot.id, version["version"]), {})
        label = verdict.get("verdict") or "unreviewed"
        chosen = version["version"] == selected
        selected_badge = ' <span class="badge selected">selected</span>' if chosen else ""
        image = (
            f'<img alt="v{version["version"]}" src="{uri}">'
            if uri
            else '<div class="note">image unreadable</div>'
        )
        cards.append(
            f'<div class="version">{image}'
            f'<div class="meta">v{version["version"]:03d} · {_esc(version["sha256"][:12])} · '
            f'<span class="badge {_esc(label)}">{_esc(label)}</span>{selected_badge}</div>'
            f'<div class="meta">{_esc((verdict.get("note") or "")[:120])}</div></div>'
        )
    return (
        '<div class="versions">'
        + ("".join(cards) or '<div class="note">No versions.</div>')
        + "</div>"
    )


def render_shot(root: Path, shot, entry: dict, versions, verdicts, selected) -> str:
    compiled = P.image_spec(root, shot)
    project = P.load_project(root)
    cache = root / FOLDER / "thumbs"
    current = next((v for v in versions if v["version"] == selected), None)
    effects = (shot.post_effects.model_dump() if shot.post_effects else {}) or {}
    contract_rows = [
        ("purpose", shot.purpose),
        ("framing", shot.framing or "—"),
        ("camera", shot.camera),
        ("transition", shot.transition or "cut"),
        ("dissolve", f"{shot.dissolve_frames} frames"),
        ("scene", shot.scene_id or "—"),
        ("characters", ", ".join(shot.character_ids) or "—"),
        ("states", json.dumps(shot.character_states) if shot.character_states else "—"),
        ("references", ", ".join(shot.reference_ids) or "—"),
    ]
    contract = "".join(
        f"<dt>{_esc(key)}</dt><dd>{_esc(value)}</dd>" for key, value in contract_rows
    )
    must = "".join(f"<li>{_esc(item)}</li>" for item in shot.must_show)
    payload = script_json({"id": shot.id, "slug": project.slug})
    alias_note = (
        f'<p class="warn">This shot reuses <code>{_esc(shot.asset_shot_id)}</code>; edit the source '
        "shot so both stay identical.</p>"
        if shot.asset_shot_id
        else ""
    )
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(project.title)} · {_esc(shot.id)}</title><style>{CSS}</style></head>
<body><div class="wrap">
<div class="kicker">Shot inspector · {_esc(project.title)}</div>
<h1>{_esc(shot.id)}</h1>
<p class="sub">Frame {shot.start_frame}–{shot.start_frame + shot.duration_frames} ·
{shot.duration_frames / project.fps:.2f}s · {_esc(entry["mode"])} review.
This page records nothing: every control composes a validated command for you (or an agent) to run.</p>
{alias_note}
<div class="cols">
<div>
<h2>Versions</h2>
{_version_block(root, cache, shot, versions, verdicts, selected)}
<h2>Contract</h2>
<div class="panel"><dl>{contract}</dl>
<p class="must">must show: {_esc("; ".join(shot.must_show))}</p>
<ul class="note">{must}</ul></div>
<h2>Compiled prompt</h2>
<pre>{_esc(compiled["positivePrompt"])}</pre>
<p class="note">References: {_esc(json.dumps(compiled["references"]))}</p>
</div>
<div>
<h2>Propose a presentation edit</h2>
<div class="panel">
<div class="row">
<div><label for="transition">Transition</label>
<select id="transition"><option value="keep">keep</option><option>fade</option>
<option>wipe_left</option><option>wipe_right</option><option value="none">none</option></select></div>
<div><label for="dissolve">Dissolve frames</label>
<input id="dissolve" type="number" min="0" max="48" placeholder="0"></div>
</div>
<div class="row">
<div><label for="camera">Camera</label>
<select id="camera"><option value="keep">keep</option><option>hold</option>
<option>zoom_in</option><option>zoom_out</option><option>pan_left</option><option>pan_right</option></select></div>
<div><label>Effects</label>
<label style="text-transform:none;letter-spacing:0;margin:0"><input type="checkbox" id="clear-effects"> clear all</label></div>
</div>
<div class="row"><div><label for="contrast">contrast</label>
<input id="contrast" type="number" step="0.01" min="1" max="1.2" value="{_esc(effects.get("contrast", ""))}"></div>
<div><label for="saturation">saturation</label>
<input id="saturation" type="number" step="0.01" min="0.7" max="1.3" value="{_esc(effects.get("saturation", ""))}"></div></div>
<div class="row"><div><label for="brightness">brightness</label>
<input id="brightness" type="number" step="0.01" min="0.9" max="1.1" value="{_esc(effects.get("brightness", ""))}"></div>
<div><label for="vignette">vignette</label>
<input id="vignette" type="number" step="0.01" min="0" max="0.3" value="{_esc(effects.get("vignette", ""))}"></div></div>
<pre id="edit-command"></pre>
<button data-copy="edit-command">Copy edit command</button>
<p class="note">Timing, other shots and the recording cannot change here. An edit marks
storyboard, proof, preview, stills and graphics approvals stale.</p>
</div>

<h2>Register a derivative</h2>
<div class="panel">
<label for="adopt-source">Path to a crop / mirror / grade candidate</label>
<input id="adopt-source" placeholder="/path/to/candidate.png">
<pre id="adopt-command"></pre>
<button data-copy="adopt-command">Copy adopt command</button>
<p class="note">Adopting records a new immutable version with provenance. It does not
select or approve it; the new bytes need their own review.</p>
</div>

<h2>Record a verdict</h2>
<div class="panel">
<pre id="review-command">uv run clip review projects/{_esc(project.slug)} --shot {_esc(shot.id)} --version {selected or 1} --verdict accept|reject|uncertain --reviewer '&lt;you&gt;' --inspected --note '&lt;what you actually saw&gt;'</pre>
<button data-copy="review-command">Copy review command</button>
<p class="note">Selected bytes: {_esc(current["sha256"] if current else "none")}</p>
</div>
</div>
</div>
<p class="note" style="margin-top:26px">Generated by <span class="mono">clip inspect</span>. No network,
no analytics, no external fonts, no state.</p>
</div>
<script>window.__SHOT__={payload};</script><script>{SCRIPT}</script></body></html>"""


def render_index(root: Path, rows: list[dict]) -> str:
    project = P.load_project(root)
    body = "".join(
        f'<tr><td><a href="{_esc(row["page"])}">{_esc(row["id"])}</a></td>'
        f"<td>{row['start_frame']}</td><td>{row['seconds']:.2f}s</td>"
        f"<td>{_esc(row['framing'])}</td><td>{_esc(row['camera'])}</td>"
        f'<td><span class="badge {_esc(row["verdict"])}">{_esc(row["verdict"])}</span></td>'
        f'<td class="note">{_esc(row["command"])}</td></tr>'
        for row in rows
    )
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(project.title)} · shot inspector index</title><style>{CSS}</style></head>
<body><div class="wrap"><div class="kicker">Shot inspector</div>
<h1>{_esc(project.title)}</h1>
<p class="sub">One page per shot: versions, verdicts, the shot contract and pre-filled edit commands.
Pages are built on demand; the command column shows what to run for a shot that has none yet.</p>
<table><thead><tr><th>Shot</th><th>Frame</th><th>Length</th><th>Framing</th><th>Camera</th>
<th>Verdict</th><th>Build</th></tr></thead><tbody>{body}</tbody></table>
<p class="note" style="margin-top:20px">No approval, selection or upload happens here.</p>
</div></body></html>"""


def build_inspector(root: Path, shot_id: str | None = None) -> dict:
    root = Path(root)
    project = P.load_project(root)
    board = P.load_board(root)
    assets = read_json(root / "work/assets.json") if (root / "work/assets.json").is_file() else {}
    reviews = (
        read_json(root / "work/reviews.json") if (root / "work/reviews.json").is_file() else []
    )
    verdicts = _latest_verdicts(reviews)
    folder = root / FOLDER
    folder.mkdir(parents=True, exist_ok=True)

    if shot_id:
        shot = next((candidate for candidate in board.shots if candidate.id == shot_id), None)
        if shot is None:
            raise ValueError(f"unknown shot ID {shot_id!r}")
        entry = assets.get(shot.asset_shot_id or shot.id, {})
        versions = entry.get("versions", [])
        document = render_shot(
            root,
            shot,
            {"mode": "static"},
            versions,
            verdicts,
            entry.get("selected"),
        )
        version = 1
        target = folder / f"{shot.id}-v{version:03d}.html"
        while target.exists():
            version += 1
            target = folder / f"{shot.id}-v{version:03d}.html"
        target.write_text(document, encoding="utf-8")
        sidecar = {
            "page": str(target.relative_to(root)),
            "html_sha256": file_hash(target),
            "shot": shot.id,
            "versions": len(versions),
            "selected": entry.get("selected"),
            "warning": "Review aid: composes commands, records nothing, approves nothing.",
        }
        write_json(target.with_suffix(".json"), sidecar)
        return {**sidecar, "created": True}

    rows = []
    for shot in board.shots:
        entry = assets.get(shot.asset_shot_id or shot.id, {})
        selected = entry.get("selected")
        verdict = verdicts.get((shot.asset_shot_id or shot.id, selected), {}).get("verdict", "none")
        page = folder / f"{shot.id}-v001.html"
        rows.append(
            {
                "id": shot.id,
                "start_frame": shot.start_frame,
                "seconds": shot.duration_frames / project.fps,
                "framing": shot.framing or "—",
                "camera": shot.camera,
                "verdict": verdict,
                "page": os.path.relpath(page, folder),
                "command": f"uv run clip inspect projects/{project.slug} --shot {shot.id}",
            }
        )
    document = render_index(root, rows)
    version = 1
    target = folder / f"index-v{version:03d}.html"
    while target.exists():
        version += 1
        target = folder / f"index-v{version:03d}.html"
    target.write_text(document, encoding="utf-8")
    sidecar = {
        "page": str(target.relative_to(root)),
        "html_sha256": file_hash(target),
        "shots": len(rows),
        "built_pages": sum(1 for row in rows if (folder / row["page"]).is_file()),
        "warning": "Index only: open a shot page for controls; nothing is approved here.",
    }
    write_json(target.with_suffix(".json"), sidecar)
    return sidecar
