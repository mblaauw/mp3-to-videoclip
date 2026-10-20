"""Studio index: one static page for every production on disk.

The studio is the shell of the production app, kept honest: it is generated from
the same canonical artifacts the CLI uses, it holds no state, and it never edits a
production. It reads small JSON files only — never ``assets/`` — so a catalogue of
many-gigabyte projects stays fast.

Every card answers three questions: what is this, what stage is it at, and what
needs a human decision. Actions point at existing commands; nothing is approved
from the page.
"""

from __future__ import annotations

import html
import json
import os
import re
from datetime import UTC, datetime
from pathlib import Path

from . import budget as budget_module
from . import operations
from . import production as P
from .storage import file_hash, read_json, write_json

FOLDER = "studio"
ORDER = ("analysis", "events", "brief", "storyboard", "proof", "preview", "stills", "graphics")
MAX_BLOCKERS = 4
#: Stages whose current hash requires reading image/movie bytes. An index stays
#: cheap and honest by reporting the recorded approval without claiming freshness;
#: the per-project dashboard recomputes those hashes exactly.
RECORDED_ONLY = frozenset({"proof", "preview", "stills", "graphics"})
APPROVE_STAGES = frozenset(ORDER)


def _optional(path: Path):
    try:
        return read_json(path)
    except (OSError, ValueError):
        return None


def _short(value: str | None, length: int = 10) -> str:
    return (value or "")[:length]


def _ago(timestamp: float | None, now: float) -> str:
    if not timestamp:
        return "never"
    seconds = max(0, now - timestamp)
    if seconds < 90:
        return f"{int(seconds)}s ago"
    if seconds < 5400:
        return f"{int(seconds / 60)}min ago"
    if seconds < 172800:
        return f"{int(seconds / 3600)}h ago"
    return f"{int(seconds / 86400)}d ago"


def _stamp(timestamp: float | None) -> str:
    if not timestamp:
        return "—"
    return datetime.fromtimestamp(timestamp, UTC).strftime("%Y-%m-%d %H:%M")


def scan_project(root: Path, now: float | None = None) -> dict | None:
    """Summarise one production from small artifacts only."""
    now = now or datetime.now(UTC).timestamp()
    config = _optional(root / "project.json")
    if not isinstance(config, dict):
        return None
    approvals = _optional(root / "work/approvals.json") or {}
    stage_state: dict[str, str] = {}
    for stage in ORDER:
        record = approvals.get(stage)
        if stage in RECORDED_ONLY:
            # No byte hashing here: a catalogue over gigabytes of media must stay
            # instant, so these tiers report the recorded approval without claiming
            # freshness. The per-project dashboard recomputes them exactly.
            stage_state[stage] = "recorded" if record else "missing"
            continue
        try:
            current = P.stage_hash(root, stage)
        except (OSError, ValueError, KeyError):
            stage_state[stage] = "unavailable"
            continue
        stage_state[stage] = (
            "approved"
            if record and record.get("hash") == current
            else ("stale" if record else "missing")
        )

    spend = {"cap_usd": None, "accounted_usd": None, "remaining_usd": None, "over_cap": None}
    try:
        summary = budget_module.summary(root)
        spend = {
            "cap_usd": summary.get("cap_usd"),
            "accounted_usd": summary.get("total_accounted_usd"),
            "remaining_usd": summary.get("cap_remaining_usd"),
            "over_cap": summary.get("over_cap"),
        }
    except (OSError, ValueError, KeyError):
        pass

    reviews = _optional(root / "work/reviews.json") or []
    # Latest verdict per (shot, version): a superseded rejection is history, not a blocker.
    latest: dict[tuple, str] = {}
    for review in reviews:
        latest[(review.get("shot_id"), review.get("version"))] = review.get("verdict")
    verdicts = {"accept": 0, "reject": 0, "uncertain": 0}
    for verdict in latest.values():
        if verdict in verdicts:
            verdicts[verdict] += 1

    board = _optional(root / "work/storyboard.json")
    shots = len(board.get("shots", [])) if isinstance(board, dict) else 0

    renders = []
    folder = root / "renders"
    if folder.is_dir():
        for report_path in folder.glob("*.json"):
            report = _optional(report_path)
            if not isinstance(report, dict) or not report.get("output"):
                continue
            movie = root / "renders" / report_path.name.replace(".json", ".mp4")
            renders.append(
                {
                    "name": report_path.name.replace(".json", ".mp4"),
                    "exists": movie.is_file(),
                    "delivery_ready": bool(report.get("delivery_ready")),
                    "verified": bool(report.get("verified")),
                    "frames": (report.get("video") or {}).get("frames"),
                    "mtime": report_path.stat().st_mtime,
                    "bytes": movie.stat().st_size if movie.is_file() else 0,
                }
            )
    renders.sort(key=lambda item: item["mtime"], reverse=True)

    previews = []
    preview_dir = root / "previews"
    if preview_dir.is_dir():
        for movie in preview_dir.glob("*.mp4"):
            previews.append({"name": movie.name, "mtime": movie.stat().st_mtime})
    previews.sort(key=lambda item: item["mtime"], reverse=True)

    dashboards = []
    dash_dir = root / "work/dashboard"
    if dash_dir.is_dir():
        for page in dash_dir.glob("*.html"):
            dashboards.append({"name": page.name, "mtime": page.stat().st_mtime})
    dashboards.sort(key=lambda item: item["mtime"], reverse=True)

    ops = operations.summary(root)
    open_tasks = 0
    tasks = _optional(root / "work/tasks.json") or {}
    for task in tasks.values():
        if task.get("status") in ("submitted", "result") or task.get("cost_usd") is None:
            open_tasks += 1

    activity = []
    for name in (
        "project.json",
        "brief.json",
        "work/storyboard.json",
        "work/approvals.json",
        "work/events.json",
    ):
        path = root / name
        if path.is_file():
            activity.append(path.stat().st_mtime)
    for render in renders[:1]:
        activity.append(render["mtime"])
    last = max(activity) if activity else None

    blockers = []
    if spend["cap_usd"] is None:
        blockers.append(("blocker", "no spending cap recorded"))
    if spend["over_cap"]:
        blockers.append(("blocker", "over the recorded cap"))
    if open_tasks:
        blockers.append(("blocker", f"{open_tasks} unresolved paid task(s)"))
    stale = [stage for stage, state in stage_state.items() if state == "stale"]
    missing = [stage for stage, state in stage_state.items() if state == "missing"]
    if stale:
        blockers.append(("warn", "stale approval: " + ", ".join(stale)))
    if any(item.get("status") == "interrupted" for item in ops.get("needs_attention", [])):
        blockers.append(("warn", "interrupted operation receipt"))
    elif ops.get("newest_running"):
        running = ops["newest_running"]
        blockers.append(("note", f"running: {running['command']} · {running['phase']}"))
    rejected = verdicts["reject"] + verdicts["uncertain"]
    if rejected:
        blockers.append(("warn", f"{rejected} rejected/uncertain still verdict(s)"))

    next_stage = next(
        (stage for stage in ORDER if stage_state.get(stage) not in ("approved", "recorded")), None
    )
    if next_stage is None:
        latest = renders[0] if renders else None
        next_step = (
            "delivered"
            if latest and latest["exists"] and latest["delivery_ready"]
            else ("final export" if latest else "render")
        )
    else:
        next_step = f"{next_stage} approval"

    entry = {
        "slug": root.name,
        "title": config.get("title") or root.name,
        "duration": config.get("duration"),
        "fps": config.get("fps"),
        "aspect": config.get("aspect"),
        "width": config.get("width"),
        "height": config.get("height"),
        "renderer": config.get("renderer_backend"),
        "music_mode": config.get("music_mode"),
        "total_frames": config.get("total_frames"),
        "shots": shots,
        "stages": stage_state,
        "approved_count": sum(
            1 for state in stage_state.values() if state in ("approved", "recorded")
        ),
        "missing_stages": missing,
        "spend": spend,
        "verdicts": verdicts,
        "renders": renders[:3],
        "preview": previews[0] if previews else None,
        "dashboard": dashboards[0] if dashboards else None,
        "operations": ops,
        "blockers": blockers[:MAX_BLOCKERS],
        "next_step": next_step,
        "actions": [],
        "last_activity": last,
        "last_activity_ago": _ago(last, now),
        "last_activity_stamp": _stamp(last),
        "path": str(root),
    }
    entry["actions"] = _actions(entry)
    return entry


def scan(projects_dir: Path, now: float | None = None) -> list[dict]:
    projects_dir = Path(projects_dir)
    now = now or datetime.now(UTC).timestamp()
    entries = []
    if not projects_dir.is_dir():
        return entries
    for folder in sorted(projects_dir.iterdir()):
        if not folder.is_dir() or folder.name.startswith("."):
            continue
        entry = scan_project(folder, now)
        if entry is not None:
            entries.append(entry)
    entries.sort(key=lambda item: item["last_activity"] or 0, reverse=True)
    return entries


CSS = """
:root{--bg:#0a0f14;--panel:#111a22;--panel2:#16222c;--ink:#f2efe6;--muted:#8fa0ae;
--gold:#d4ae6a;--teal:#688f9d;--line:#1f2c37;--ok:#6fb585;--warn:#d9a441;--bad:#d4655f}
*{box-sizing:border-box}
body{margin:0;background:radial-gradient(1200px 600px at 12% -10%,#14212b 0%,var(--bg) 55%);
color:var(--ink);font:15px/1.5 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
.wrap{max-width:1320px;margin:0 auto;padding:34px 24px 90px}
.kicker{color:var(--gold);text-transform:uppercase;letter-spacing:.16em;font-size:11px;font-weight:700}
h1{font-size:38px;letter-spacing:-.025em;margin:6px 0 6px;line-height:1.05}
.sub{color:var(--muted);max-width:70ch;margin:0}
.strip{display:flex;gap:12px;flex-wrap:wrap;margin:26px 0 8px}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:12px 16px;min-width:118px}
.stat b{display:block;font-size:24px;letter-spacing:-.02em}
.stat span{color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.1em}
.bar{display:flex;gap:8px;flex-wrap:wrap;align-items:center;margin:22px 0 18px}
button{background:var(--panel2);color:var(--ink);border:1px solid var(--line);border-radius:999px;
padding:6px 13px;font:inherit;font-size:12px;cursor:pointer;color:var(--muted)}
button.on{background:var(--gold);border-color:var(--gold);color:#0a0f14;font-weight:700}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(400px,1fr));gap:16px}
.card{position:relative;background:linear-gradient(180deg,var(--panel2),var(--panel));
border:1px solid var(--line);border-radius:16px;padding:18px 18px 14px;overflow:hidden}
.card:before{content:"";position:absolute;left:0;top:0;bottom:0;width:4px;background:var(--accent,var(--line))}
.card h2{font-size:19px;margin:0 0 2px;letter-spacing:-.01em}
.meta{color:var(--muted);font-size:12px;display:flex;gap:8px;flex-wrap:wrap;margin:4px 0 12px}
.dot{width:4px;height:4px;border-radius:50%;background:var(--muted);display:inline-block;margin:7px 2px}
.stages{display:flex;gap:5px;flex-wrap:wrap;margin:10px 0 12px}
.pill{font-size:10px;letter-spacing:.05em;text-transform:uppercase;padding:3px 8px;border-radius:999px;
border:1px solid var(--line);color:var(--muted)}
.pill.approved{color:var(--ok);border-color:#2c5240;background:#12211a}
.pill.stale{color:var(--bad);border-color:#5b2f2f;background:#221314}
.pill.recorded{color:var(--gold);border-color:#4a3d25;background:#1d1912}
.pill.missing{color:var(--muted)}
.pill.unavailable{color:#5d6b77;border-style:dashed}
.spend{margin:12px 0 4px}
.track{height:6px;border-radius:3px;background:#0c141a;border:1px solid var(--line);overflow:hidden}
.track i{display:block;height:100%;background:linear-gradient(90deg,var(--teal),var(--gold))}
.spendline{display:flex;justify-content:space-between;color:var(--muted);font-size:11px;margin-top:5px}
.blockers{list-style:none;margin:12px 0 0;padding:0;display:flex;flex-direction:column;gap:5px}
.blockers li{font-size:12px;color:var(--muted)}
.blockers .sev{font-size:9px;text-transform:uppercase;letter-spacing:.09em;margin-right:6px}
.sev.blocker{color:var(--bad)}.sev.warn{color:var(--warn)}.sev.note{color:var(--teal)}
.actions{display:flex;gap:8px;flex-wrap:wrap;margin-top:14px;align-items:center}
a.btn,button.btn{display:inline-block;text-decoration:none;color:var(--ink);border:1px solid var(--line);
border-radius:8px;padding:6px 11px;font-size:12px;background:#0f1820}
a.btn:hover{border-color:var(--gold);color:var(--gold)}
.next{color:var(--gold);font-size:12px;font-weight:600}
footer{margin-top:44px;border-top:1px solid var(--line);padding-top:14px;color:var(--muted);font-size:12px}
.empty{color:var(--muted);padding:40px;border:1px dashed var(--line);border-radius:14px;text-align:center}
"""

SCRIPT = """
(function(){
 var chips=document.querySelectorAll('button.chip');
 chips.forEach(function(chip){
  chip.addEventListener('click',function(){
   var on=chip.classList.toggle('on');
   chips.forEach(function(c){if(c!==chip)c.classList.remove('on');});
   var filter=on?chip.getAttribute('data-filter'):null;
   document.querySelectorAll('.card').forEach(function(card){
    var state=card.getAttribute('data-state');
    card.style.display=(!filter||state===filter)?'':'none';
   });
  });
 });
 document.querySelectorAll('[data-copy]').forEach(function(btn){
  btn.addEventListener('click',function(){
   var el=document.getElementById(btn.getAttribute('data-copy'));
   if(!el)return;
   if(navigator.clipboard)navigator.clipboard.writeText(el.textContent);
   btn.textContent='Copied';
  });
 });
})();
"""


def _actions(entry: dict) -> list[dict]:
    """What this production needs, as inspectable commands — never as hidden writes."""
    slug = entry["slug"]
    project = f"projects/{slug}"
    stage = entry["next_step"].split(" ")[0]
    actions: list[dict] = []

    if entry["spend"].get("cap_usd") is None:
        actions.append(
            {
                "id": "budget",
                "label": "Set spending cap",
                "command": f"uv run clip budget {project} --cap 5.00 --note '<your cap>'",
                "reason": "no cap recorded, so paid work cannot be authorised",
                "needs_input": True,
                "severity": "blocker",
            }
        )
    if stage not in {"delivered", "render", "final"} and stage in APPROVE_STAGES:
        actions.append(
            {
                "id": f"approve-{stage}",
                "label": f"Approve {stage}",
                "command": f"uv run clip approve {project} {stage} --note '<your decision>'",
                "reason": f"{stage} is not current; inspect the dashboard before deciding",
                "needs_input": True,
                "severity": "blocker" if entry["stages"].get(stage) == "stale" else "warn",
            }
        )
    if entry["verdicts"]["reject"] or entry["verdicts"]["uncertain"]:
        actions.append(
            {
                "id": "review-stills",
                "label": "Review rejected stills",
                "command": f"uv run clip dashboard {project} --stage stills",
                "reason": (
                    f"{entry['verdicts']['reject']} rejected, "
                    f"{entry['verdicts']['uncertain']} uncertain verdict(s)"
                ),
                "needs_input": False,
                "severity": "warn",
            }
        )
    for item in entry["operations"].get("needs_attention", []):
        if item.get("status") == "interrupted":
            actions.append(
                {
                    "id": "reconcile",
                    "label": "Inspect interrupted run",
                    "command": f"uv run clip progress {project} --reconcile",
                    "reason": "owning process is gone; outputs may be partial",
                    "needs_input": False,
                    "severity": "warn",
                }
            )
            break
    if entry["renders"] and entry["renders"][0]["exists"]:
        latest = entry["renders"][0]
        actions.append(
            {
                "id": "export",
                "label": "Open export" if not latest["delivery_ready"] else "Open final",
                "href": f"projects/{slug}/renders/{latest['name']}",
                "reason": "verified" if latest["verified"] else "unverified export",
                "needs_input": False,
                "severity": "note",
            }
        )
    actions.append(
        {
            "id": "plan",
            "label": "Propose a plan",
            "command": f"uv run clip plan build {project}",
            "reason": "inspect the open steps before anything runs",
            "needs_input": False,
            "severity": "note",
        }
    )
    actions.append(
        {
            "id": "status",
            "label": "Copy status command",
            "command": f"uv run clip status {project}",
            "reason": "full stage and shot state",
            "needs_input": False,
            "severity": "note",
        }
    )
    return actions


def _esc(value) -> str:
    return html.escape("" if value is None else str(value))


def _accent(entry: dict) -> str:
    if any(sev == "blocker" for sev, _ in entry["blockers"]):
        return "#d4655f"
    if entry["next_step"] == "delivered":
        return "#6fb585"
    if any(sev == "warn" for sev, _ in entry["blockers"]):
        return "#d9a441"
    return "#688f9d"


def _card(entry: dict, studio_dir: Path, projects_dir: Path) -> str:
    spend = entry["spend"]
    cap = spend.get("cap_usd")
    used = spend.get("accounted_usd")
    fraction = 0.0
    if cap and used is not None:
        try:
            fraction = min(1.0, float(used) / float(cap))
        except (TypeError, ValueError, ZeroDivisionError):
            fraction = 0.0
    pills = "".join(
        f'<span class="pill {_esc(state)}">{_esc(stage)}</span>'
        for stage, state in entry["stages"].items()
    )
    blockers = (
        "".join(
            f'<li><span class="sev {_esc(sev)}">{_esc(sev)}</span>{_esc(text)}</li>'
            for sev, text in entry["blockers"]
        )
        or '<li><span class="sev note">note</span>no open blocker recorded</li>'
    )

    actions = []
    project_dir = projects_dir / entry["slug"]
    if entry["dashboard"]:
        target = project_dir / "work/dashboard" / entry["dashboard"]["name"]
        actions.append(
            f'<a class="btn" href="{_esc(os.path.relpath(target, studio_dir))}">Open dashboard</a>'
        )
    if entry["preview"]:
        target = project_dir / "previews" / entry["preview"]["name"]
        actions.append(
            f'<a class="btn" href="{_esc(os.path.relpath(target, studio_dir))}">Open preview</a>'
        )
    for index, action in enumerate(entry["actions"]):
        if action.get("href"):
            target = projects_dir.parent / action["href"]
            actions.append(
                f'<a class="btn" href="{_esc(os.path.relpath(target, studio_dir))}">{_esc(action["label"])}</a>'
            )
            continue
        command_id = f"cmd-{entry['slug']}-{index}"
        marker = " *" if action.get("needs_input") else ""
        actions.append(
            f'<button class="btn" data-copy="{_esc(command_id)}" title="{_esc(action["reason"])}">'
            f"{_esc(action['label'])}{marker}</button>"
            f'<span id="{_esc(command_id)}" style="display:none">{_esc(action["command"])}</span>'
        )

    duration = entry["duration"] or 0
    return f"""<article class="card" data-state="{_esc(entry["next_step"].split(" ")[0])}"
 style="--accent:{_accent(entry)}">
<h2>{_esc(entry["title"])}</h2>
<div class="meta"><span class="mono">{_esc(entry["slug"])}</span><span class="dot"></span>
<span>{duration:.0f}s</span><span class="dot"></span><span>{entry["shots"]} shots</span>
<span class="dot"></span><span>{_esc(entry["aspect"])} · {_esc(entry["fps"])}fps · {_esc(entry["renderer"])}</span></div>
<div class="stages">{pills}</div>
<div class="spend"><div class="track"><i style="width:{fraction * 100:.1f}%"></i></div>
<div class="spendline"><span>{_esc(used if used is not None else "—")} / {_esc(cap if cap is not None else "no cap")} USD</span>
<span>{entry["approved_count"]}/{len(entry["stages"])} stages approved · <span title="image/movie stages record their approval here; freshness is verified in the project dashboard">recorded tiers</span></span></div></div>
<ul class="blockers">{blockers}</ul>
<div class="actions"><span class="next">next: {_esc(entry["next_step"])}</span>{"".join(actions)}</div>
<div class="meta" style="margin-top:10px">activity {_esc(entry["last_activity_ago"])} · {_esc(entry["last_activity_stamp"])}</div>
</article>"""


def render_page(entries: list[dict], projects_dir: Path, studio_dir: Path) -> str:
    total_renders = sum(1 for entry in entries for render in entry["renders"] if render["exists"])
    delivered = sum(1 for entry in entries if entry["next_step"] == "delivered")
    attention = sum(1 for entry in entries if any(sev == "blocker" for sev, _ in entry["blockers"]))
    cards = "".join(_card(entry, studio_dir, projects_dir) for entry in entries)
    generated = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Studio — {len(entries)} productions</title>
<style>{CSS}</style></head>
<body><div class="wrap">
<div class="kicker">Production studio</div>
<h1>What exists, what is next</h1>
<p class="sub">Generated from canonical artifacts. Every card is a production folder on this machine;
this page holds no state, edits nothing and uploads nothing. Decisions stay in the CLI, against
the hash each stage shows in its own dashboard.</p>

<div class="strip">
<div class="stat"><b>{len(entries)}</b><span>productions</span></div>
<div class="stat"><b>{total_renders}</b><span>exports on disk</span></div>
<div class="stat"><b>{delivered}</b><span>delivered</span></div>
<div class="stat"><b>{attention}</b><span>need attention</span></div>
</div>

<div class="bar">
<button class="chip on" data-filter="all">All</button>
<button class="chip" data-filter="storyboard">At board</button>
<button class="chip" data-filter="stills">At stills</button>
<button class="chip" data-filter="graphics">At graphics</button>
<button class="chip" data-filter="render">At export</button>
<button class="chip" data-filter="delivered">Delivered</button>
</div>

<div class="grid">{cards or '<div class="empty">No productions found in projects/.</div>'}</div>

<footer>
<p>Scanned <span class="mono">{_esc(projects_dir)}</span> · generated {generated} ·
<span class="mono">clip studio</span> reads small JSON artifacts only, never image bytes.</p>
<p>Agentic loop underneath: music map → treatment → board → proofs → stills → graphics → delivery,
with content-bound approvals and durable operation receipts.</p>
</footer>
</div>
<script>{SCRIPT}</script>
</body></html>
"""


def build_studio(
    projects_dir: Path,
    *,
    output_dir: Path | None = None,
    name: str | None = None,
) -> dict:
    projects_dir = Path(projects_dir).resolve()
    studio_dir = (Path(output_dir) if output_dir else projects_dir.parent / FOLDER).resolve()
    entries = scan(projects_dir)
    document = render_page(entries, projects_dir, studio_dir)

    studio_dir.mkdir(parents=True, exist_ok=True)
    if name:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*\.html", name):
            raise ValueError("studio name must be a safe lowercase .html basename")
        target = studio_dir / name
        if target.exists():
            raise ValueError(f"{target.name} already exists; studio pages are never overwritten")
    else:
        version = 1
        while (studio_dir / f"studio-v{version:03d}.html").exists():
            version += 1
        target = studio_dir / f"studio-v{version:03d}.html"
    target.write_text(document, encoding="utf-8")

    sidecar = {
        "page": str(target),
        "html_sha256": file_hash(target),
        "bytes": target.stat().st_size,
        "productions": len(entries),
        "projects_dir": str(projects_dir),
        "slugs": [entry["slug"] for entry in entries],
        "needs_attention": [entry["slug"] for entry in entries if entry["blockers"]],
        "next_steps": {entry["slug"]: entry["next_step"] for entry in entries},
        "inputs": {
            "project_configs": {
                entry["slug"]: file_hash(projects_dir / entry["slug"] / "project.json")
                for entry in entries
            },
        },
        "warning": (
            "Read-only index: no approval, no selection, no upload. Actions link to artifacts or "
            "print commands; the CLI remains the only writer."
        ),
    }
    write_json(target.with_suffix(".json"), sidecar)
    return sidecar


def scan_json(entries: list[dict]) -> str:
    """Small machine-readable view used by tests and future app clients."""
    return json.dumps({"productions": entries}, indent=2, default=str)
