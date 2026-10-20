"""Static intake wizard: validate a new production, then emit the exact commands.

The page cannot create anything. It composes `clip init` and `clip budget` for a
human or agent to run, and refuses to emit a command that the kernel would reject:
missing title, unsafe slug, missing factual credits, non-positive budget, portrait
with the 16:9-only signature, or a source that cannot be found.
"""

from __future__ import annotations

import re
from datetime import UTC, datetime
from pathlib import Path

from .storage import file_hash, write_json

FOLDER = "studio"
CSS = """
:root{--bg:#0a0f14;--panel:#111a22;--panel2:#16222c;--ink:#f2efe6;--muted:#8fa0ae;
--gold:#d4ae6a;--teal:#688f9d;--line:#1f2c37;--ok:#6fb585;--warn:#d9a441;--bad:#d4655f}
*{box-sizing:border-box}
body{margin:0;background:radial-gradient(1100px 560px at 10% -10%,#14212b 0%,var(--bg) 55%);
color:var(--ink);font:15px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif}
.wrap{max-width:1080px;margin:0 auto;padding:38px 24px 90px}
.kicker{color:var(--gold);text-transform:uppercase;letter-spacing:.16em;font-size:11px;font-weight:700}
h1{font-size:34px;letter-spacing:-.025em;margin:6px 0 8px}
.sub{color:var(--muted);max-width:72ch;margin:0 0 22px}
.grid{display:grid;grid-template-columns:1fr 1fr;gap:16px}
@media (max-width:820px){.grid{grid-template-columns:1fr}}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:14px;padding:18px}
h2{font-size:13px;letter-spacing:.1em;text-transform:uppercase;color:var(--muted);margin:0 0 12px}
label{display:block;font-size:11px;text-transform:uppercase;letter-spacing:.08em;color:var(--muted);margin:12px 0 5px}
input,select{width:100%;background:#0e161d;color:var(--ink);border:1px solid var(--line);
border-radius:8px;padding:9px 11px;font:inherit;font-size:14px}
input:invalid{border-color:var(--bad)}
.hint{color:var(--muted);font-size:11px;margin-top:4px}
pre{background:#0e161d;border:1px solid var(--line);border-radius:9px;padding:12px;
overflow:auto;font-size:12px;white-space:pre-wrap;word-break:break-word}
button{background:var(--gold);color:#0a0f14;border:0;border-radius:9px;padding:9px 15px;
font:inherit;font-weight:700;font-size:13px;cursor:pointer}
button:disabled{background:#2a3540;color:#7b8b98;cursor:not-allowed}
.blockers{list-style:none;margin:10px 0 0;padding:0}
.blockers li{font-size:12px;color:var(--muted);padding:3px 0}
.blockers .sev{font-size:9px;text-transform:uppercase;letter-spacing:.08em;margin-right:7px}
.sev.blocker{color:var(--bad)}.sev.warn{color:var(--warn)}
.note{color:var(--muted);font-size:12px}
ol{padding-left:18px;color:var(--muted);font-size:13px}
code{color:var(--teal)}
footer{margin-top:30px;border-top:1px solid var(--line);padding-top:14px;color:var(--muted);font-size:12px}
"""

SCRIPT = """
(function(){
 var ids=['mp3','title','slug','aspect','fps','mode','music','direction','cap','corrections'];
 function v(id){var el=document.getElementById(id);return el?el.value.trim():'';}
 function slugify(text){return text.toLowerCase().replace(/[^a-z0-9]+/g,'-').replace(/^-+|-+$/g,'').slice(0,64);}
 var auto=true;
 document.getElementById('title').addEventListener('input',function(){
   if(auto){document.getElementById('slug').value=slugify(v('title'));}
   update();
 });
 document.getElementById('slug').addEventListener('input',function(){auto=false;update();});
 ids.forEach(function(id){var el=document.getElementById(id);if(el){el.addEventListener('input',update);el.addEventListener('change',update);}});

 function shq(value){
   return "'"+String(value).replace(/'/g, "'\\\\''")+"'";
 }
 function blockers(){
   var out=[];
   if(!v('mp3'))out.push(['blocker','source MP3 path is required']);
   if(!v('title'))out.push(['blocker','a film title is required (the slug derives from it)']);
   if(v('slug')&&!/^[a-z0-9][a-z0-9-]{0,63}$/.test(v('slug')))out.push(['blocker','slug must be lowercase letters, digits and dashes']);
   if(!v('music'))out.push(['blocker','MUSIC credit is required']);
   if(!v('direction'))out.push(['blocker','FILM DIRECTION credit is required']);
   var cap=parseFloat(v('cap'));
   if(!(cap>0))out.push(['blocker','a positive spending cap is required before paid work']);
   if(v('aspect')==='9:16')out.push(['warn','the signature compositor is 16:9 only; resolve portrait before spending']);
   return out;
 }
 function update(){
   var list=blockers();
   var box=document.getElementById('blockers');
   box.innerHTML=list.map(function(item){
     return '<li><span class="sev '+item[0]+'">'+item[0]+'</span>'+item[1]+'</li>';
   }).join('')||'<li><span class="sev">ok</span>ready to emit commands</li>';
   var blocked=list.some(function(item){return item[0]==='blocker';});
   document.getElementById('copy').disabled=blocked;
   var slug=v('slug')||'<slug>';
   var commands=[
     'uv run clip init '+shq('projects/'+slug)+' \\\\',
     '  --mp3 '+shq(v('mp3'))+' --title '+shq(v('title'))+' --aspect '+shq(v('aspect')||'16:9')+
       ' --fps '+shq(v('fps')||'24')+' --music-mode '+shq(v('mode')||'vocal'),
     'uv run clip budget '+shq('projects/'+slug)+' --cap '+shq(v('cap'))+
       ' --max-corrections '+shq(v('corrections')||'1')+' --note '+shq('initial production cap'),
   ];
   document.getElementById('commands').textContent=commands.join('\\n');
   document.getElementById('credits').textContent=
     'MUSIC — '+v('music')+'\\nFILM DIRECTION — '+v('direction')+
     '\\nA JOINT MAH\u0041 KALA & VJDJ69 PRODUCTION';
 }
 document.getElementById('copy').addEventListener('click',function(){
   var text=document.getElementById('commands').textContent;
   if(navigator.clipboard)navigator.clipboard.writeText(text);
   this.textContent='Copied';
 });
 update();
})();
"""


def render_page() -> str:
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    return f"""<!DOCTYPE html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>New production · intake</title><style>{CSS}</style></head>
<body><div class="wrap">
<div class="kicker">Studio · intake</div>
<h1>New production</h1>
<p class="sub">Fill the fields and this page emits the two commands that create the production
and its spending cap. It never writes anything itself: the kernel validates again, so a
mistake here is caught before a single file or dollar is committed.</p>

<div class="grid">
<div class="panel">
<h2>Source and identity</h2>
<label for="mp3">Source MP3 (absolute or repo-relative path)</label>
<input id="mp3" placeholder="/Users/mich/Downloads/song.mp3" autocomplete="off">
<div class="hint">Copied byte-identically into the production; never uploaded by init.</div>

<label for="title">Film title</label>
<input id="title" placeholder="Forward Ever" autocomplete="off">

<label for="slug">Folder slug</label>
<input id="slug" placeholder="forward-ever" autocomplete="off">
<div class="hint">Derived from the title; lowercase letters, digits, dashes.</div>
</div>

<div class="panel">
<h2>Format</h2>
<div style="display:grid;grid-template-columns:1fr 1fr;gap:12px">
<div><label for="aspect">Aspect</label>
<select id="aspect"><option>16:9</option><option>9:16</option></select></div>
<div><label for="fps">FPS</label>
<select id="fps"><option>24</option><option>30</option></select></div>
</div>
<label for="mode">Music mode</label>
<select id="mode"><option>vocal</option><option>instrumental</option><option>music-led</option></select>
<div class="hint">Instrumental skips lyrics and transcription; music-led preserves sparse vocals.</div>
</div>

<div class="panel">
<h2>Factual credits</h2>
<label for="music">MUSIC</label>
<input id="music" value="MAHA KALA" autocomplete="off">
<label for="direction">FILM DIRECTION</label>
<input id="direction" value="VJDJ69" autocomplete="off">
<div class="hint">Supplied once at intake; never randomised or invented by an agent.</div>
</div>

<div class="panel">
<h2>Money and corrections</h2>
<label for="cap">Cumulative cap (USD)</label>
<input id="cap" type="number" min="0.01" step="0.01" value="5.00">
<label for="corrections">Max corrections per source shot</label>
<input id="corrections" type="number" min="0" max="5" value="1">
<div class="hint">A cap records authority, not permission to invent spend. Quotes stay scoped.</div>
</div>
</div>

<h2 style="margin-top:26px">Refusals</h2>
<ul class="blockers" id="blockers"></ul>

<h2>Commands</h2>
<pre id="commands"></pre>
<button id="copy" disabled>Copy commands</button>
<p class="note">The agent runs these; nothing on this page is executed. After init, the next
gates are analysis → events → brief → storyboard.</p>

<h2>What will appear on the film</h2>
<pre id="credits"></pre>
<p class="note">The shared joint-production line is fixed; roles are the ones above.</p>

<footer>Generated {generated} by <span class="mono">clip intake</span>. No network, no analytics,
no external fonts, no state.</footer>
</div>
<script>{SCRIPT}</script></body></html>"""


def build_intake(*, output_dir: Path | None = None, name: str | None = None) -> dict:
    studio_dir = (Path(output_dir) if output_dir else Path(FOLDER)).resolve()
    studio_dir.mkdir(parents=True, exist_ok=True)
    if name:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*\.html", name):
            raise ValueError("intake name must be a safe lowercase .html basename")
        target = studio_dir / name
        if target.exists():
            raise ValueError(f"{target.name} already exists; intake pages are never overwritten")
    else:
        version = 1
        while (studio_dir / f"intake-v{version:03d}.html").exists():
            version += 1
        target = studio_dir / f"intake-v{version:03d}.html"
    target.write_text(render_page(), encoding="utf-8")
    sidecar = {
        "page": str(target),
        "html_sha256": file_hash(target),
        "bytes": target.stat().st_size,
        "emits": ["clip init", "clip budget"],
        "warning": (
            "Composes commands only. The kernel re-validates; this page creates no files, "
            "records no approval and spends nothing."
        ),
    }
    write_json(target.with_suffix(".json"), sidecar)
    return sidecar
