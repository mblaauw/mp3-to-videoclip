"""Read-only beatmap/storyboard dashboard: one self-contained review artifact.

The dashboard is a *view* of canonical artifacts, never a state store. It renders
what the project actually recorded and marks what it does not know:

* no meter, bar grid or downbeat is claimed unless an explicitly approved
  ``work/music-grid.json`` exists (fail-closed: an unapproved grid shows nothing);
* measured values keep their provenance and stay labelled as measurements;
* approvals use complete kernel gate checks beside their live content hash;
  human decisions use terminal-enabled Studio. The page never writes anything.

Output is deterministic for fixed inputs (no timestamps, no random ids), versioned
and never overwritten, with a sidecar recording every input hash.
"""

from __future__ import annotations

import base64
import io
import os
import re
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image

from . import production as P
from .markup import esc as _esc
from .markup import script_json
from .storage import file_hash, inside, read_json, read_optional, write_json
from .studio import approval_state

STAGES = ("board", "stills", "delivery")
FOLDER = "work/dashboard"
THUMB_WIDTH = 420
THUMB_QUALITY = 72
AUDIO_LIMIT_BYTES = 12 * 1024 * 1024
APPROVAL_ORDER = (
    "analysis",
    "lyrics",
    "events",
    "brief",
    "storyboard",
    "proof",
    "preview",
    "stills",
    "graphics",
)


# --------------------------------------------------------------------------- #
# loading
# --------------------------------------------------------------------------- #
def _optional(path: Path):
    return read_optional(path)


def _music_grid(root: Path) -> dict:
    """Optional reviewed bar grid. Absent or unapproved means no bar claims at all."""
    path = root / "work/music-grid.json"
    if not path.is_file():
        return {
            "enabled": False,
            "reason": "no reviewed grid file; no meter or bar numbers claimed",
        }
    raw = read_json(path)
    problems = []
    if raw.get("approved") is not True:
        problems.append("grid is not marked approved")
    bpm = raw.get("bpm")
    beats_per_bar = raw.get("beats_per_bar")
    zero = raw.get("bar_zero_frame")
    if not isinstance(bpm, (int, float)) or not 30 <= bpm <= 300:
        problems.append("bpm must be a number between 30 and 300")
    if not isinstance(beats_per_bar, int) or not 2 <= beats_per_bar <= 12:
        problems.append("beats_per_bar must be an integer between 2 and 12")
    if not isinstance(zero, int) or zero < 0:
        problems.append("bar_zero_frame must be a non-negative integer")
    frames_per_bar = raw.get("frames_per_bar")
    if frames_per_bar is None and not problems:
        frames_per_bar = (60.0 / float(bpm)) * beats_per_bar * raw.get("fps", 24)
    if not isinstance(frames_per_bar, (int, float)) or frames_per_bar <= 0:
        problems.append("frames_per_bar must be positive")
    if problems:
        return {
            "enabled": False,
            "reason": "; ".join(problems),
            "file": str(path.relative_to(root)),
        }
    return {
        "enabled": True,
        "bpm": float(bpm),
        "beats_per_bar": int(beats_per_bar),
        "frames_per_bar": float(frames_per_bar),
        "bar_zero_frame": int(zero),
        "note": raw.get("note", ""),
        "approved_by": raw.get("approved_by", ""),
    }


def _approval_states(root: Path) -> list[dict]:
    record = _optional(root / "work/approvals.json") or {}
    states = []
    for stage in APPROVAL_ORDER:
        entry = {"stage": stage, "state": "unavailable", "hash": None, "approved_at": None}
        try:
            current = P.stage_hash(root, stage)
        except (OSError, ValueError, KeyError):
            states.append(entry)
            continue
        entry["hash"] = current[:16]
        approval = record.get(stage)
        entry["state"], entry["problem"] = approval_state(root, stage, current, approval)
        if approval:
            entry["approved_at"] = approval.get("at")
        states.append(entry)
    return states


def _short_label(label: str) -> str:
    """The supplied label minus its provenance prefix; the tooltip keeps the full one."""
    text = re.sub(r"(?i)^supplied\s+candidate:\s*", "", (label or "").strip())
    return text or (label or "")


def _duration_class(seconds: float) -> str:
    if seconds < 3:
        return "short"
    if seconds < 7:
        return "medium"
    return "long"


def _sections(events: dict | None, rows: list[dict], fps: int) -> list[dict]:
    if not events or not events.get("events"):
        return []
    entries = sorted(events["events"], key=lambda e: e.get("frame", 0))
    result = []
    for index, event in enumerate(entries):
        start = event.get("frame", 0)
        end = event.get("end_frame")
        if end is None:
            end = entries[index + 1].get("frame", start) if index + 1 < len(entries) else start
        ids = {event["id"]} if event.get("id") else set()
        members = [
            row
            for row in rows
            if (set(row.get("event_ids") or []) & ids)
            or (row["start_frame"] < end and row["end_frame"] > start)
        ]
        result.append(
            {
                "id": event.get("id") or f"section-{index + 1}",
                "label": event.get("label") or "Unlabelled",
                "start_seconds": start / fps,
                "end_seconds": end / fps,
                "start_frame": start,
                "end_frame": end,
                "confidence": event.get("confidence") or "unknown",
                "basis": event.get("timing_basis") or "unknown",
                "source": event.get("source") or "unknown",
                "note": event.get("note") or "",
                "evidence": event.get("evidence") or "",
                "shots": members,
            }
        )
    return result


def _shot_rows(
    board: dict,
    project,
    assets: dict,
    reviews: list[dict],
    grid: dict,
    stage: str,
) -> list[dict]:
    fps = project.fps
    rows = []
    for index, shot in enumerate(board["shots"], 1):
        start = shot["start_frame"]
        seconds = shot["duration_frames"] / fps
        owner = shot.get("asset_shot_id") or shot["id"]
        entry = assets.get(owner, {})
        selected = entry.get("selected")
        version = next((v for v in entry.get("versions", []) if v["version"] == selected), None)
        verdict = next(
            (
                review
                for review in reversed(reviews)
                if review.get("shot_id") == owner
                and version is not None
                and review.get("version") == version.get("version")
                and review.get("sha256") == version.get("sha256")
            ),
            None,
        )
        row = {
            "index": index,
            "id": shot["id"],
            "start_frame": start,
            "end_frame": start + shot["duration_frames"],
            "start_seconds": start / fps,
            "seconds": seconds,
            "duration_class": _duration_class(seconds),
            "framing": shot.get("framing") or "",
            "camera": shot.get("camera") or "",
            "camera_path": shot.get("camera_path"),
            "transition": shot.get("transition") or "",
            "dissolve_frames": shot.get("dissolve_frames") or 0,
            "purpose": shot.get("purpose") or "",
            "must_show": shot.get("must_show") or [],
            "image_prompt": shot.get("image_prompt") or "",
            "music_context": shot.get("music_context") or "",
            "scene_id": shot.get("scene_id"),
            "characters": shot.get("character_ids") or [],
            "states": shot.get("character_states") or {},
            "references": shot.get("reference_ids") or [],
            "event_ids": shot.get("event_ids") or [],
            "alias_of": shot.get("asset_shot_id"),
            "owner": owner,
            "version": version["version"] if version else None,
            "sha256": version["sha256"] if version else None,
            "image": None,
            "verdict": verdict.get("verdict") if verdict else None,
            "verdict_note": verdict.get("note") if verdict else None,
            "bar": None,
        }
        if grid.get("enabled"):
            span = grid["frames_per_bar"]
            first = int((start - grid["bar_zero_frame"]) // span) + 1
            last = int((row["end_frame"] - grid["bar_zero_frame"] - 1) // span) + 1
            row["bar"] = f"{first}" if first == last else f"{first}–{last}"
        if stage in ("stills", "delivery") and version is not None:
            row["image"] = version["path"]
        rows.append(row)
    return rows


def _diagnostics(rows: list[dict], project, stage: str, grid: dict) -> list[dict]:
    findings = []
    expected = 0
    for row in rows:
        if row["start_frame"] != expected:
            kind = "gap" if row["start_frame"] > expected else "overlap"
            findings.append(
                {
                    "severity": "blocker",
                    "kind": kind,
                    "detail": (
                        f"{row['id']} starts at frame {row['start_frame']}, "
                        f"expected {expected} ({kind} of {abs(row['start_frame'] - expected)} frames)"
                    ),
                }
            )
        expected = row["end_frame"]
    if expected != project.total_frames:
        findings.append(
            {
                "severity": "blocker",
                "kind": "coverage",
                "detail": f"shots cover {expected} frames, project has {project.total_frames}",
            }
        )
    for row in rows:
        if stage in ("stills", "delivery") and row["image"] is None:
            findings.append(
                {
                    "severity": "blocker",
                    "kind": "missing-still",
                    "detail": f"{row['id']} has no selected image for this stage",
                }
            )
        elif stage in ("stills", "delivery") and row["verdict"] not in ("accept",):
            findings.append(
                {
                    "severity": "blocker",
                    "kind": "unreviewed",
                    "detail": f"{row['id']} selected v{row['version']} has verdict "
                    f"{row['verdict'] or 'none'}",
                }
            )
        if row["alias_of"] and row["duration_class"] == "long" and row["seconds"] > 6:
            findings.append(
                {
                    "severity": "note",
                    "kind": "alias-hold",
                    "detail": f"{row['id']} reuses {row['alias_of']} for {row['seconds']:.1f}s",
                }
            )
    if not grid.get("enabled"):
        findings.append(
            {
                "severity": "note",
                "kind": "no-grid",
                "detail": "no approved meter/bar grid: the timeline is seconds and frames only",
            }
        )
    return findings


def _stats(rows: list[dict], project, music: dict | None) -> dict:
    classes = {"short": 0, "medium": 0, "long": 0}
    for row in rows:
        classes[row["duration_class"]] += 1
    return {
        "duration": project.duration,
        "frames": project.total_frames,
        "fps": project.fps,
        "shots": len(rows),
        "classes": classes,
        "tempo": (music or {}).get("estimated_tempo_bpm"),
        "beats": len((music or {}).get("beats") or []),
    }


# --------------------------------------------------------------------------- #
# thumbnails
# --------------------------------------------------------------------------- #
def _thumbnail(root: Path, cache: Path, relative: str) -> str | None:
    source = inside(root, relative)
    if not source.is_file():
        return None
    digest = file_hash(source)
    target = cache / f"{digest[:24]}-{THUMB_WIDTH}.jpg"
    if not target.is_file():
        try:
            with Image.open(source) as opened:
                image = opened.convert("RGB")
                ratio = THUMB_WIDTH / image.width
                image = image.resize((THUMB_WIDTH, max(1, round(image.height * ratio))))
                buffer = io.BytesIO()
                image.save(buffer, format="JPEG", quality=THUMB_QUALITY, optimize=True)
            cache.mkdir(parents=True, exist_ok=True)
            temporary = target.with_name(f".{target.name}.tmp")
            temporary.write_bytes(buffer.getvalue())
            os.replace(temporary, target)
        except (OSError, ValueError):
            return None
    return base64.b64encode(target.read_bytes()).decode("ascii")


def _data_uri(root: Path, relative: str, mime: str, limit: int | None = None) -> str | None:
    path = inside(root, relative)
    if not path.is_file():
        return None
    if limit is not None and path.stat().st_size > limit:
        return None
    return f"data:{mime};base64," + base64.b64encode(path.read_bytes()).decode("ascii")


# --------------------------------------------------------------------------- #
# HTML
# --------------------------------------------------------------------------- #
CSS = """
:root{--bg:#0b1015;--panel:#131b23;--panel2:#18222c;--ink:#f4f1e8;--muted:#93a3b1;
--gold:#d4ae6a;--teal:#688f9d;--line:#22303b;--ok:#68b07d;--warn:#d9a441;--bad:#d4655f;
--short:#5f8fae;--medium:#7fae8a;--long:#c9a37a}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif}
a{color:var(--gold)}
.wrap{max-width:1280px;margin:0 auto;padding:28px 22px 80px}
header.top{display:flex;gap:26px;align-items:flex-start;justify-content:space-between;flex-wrap:wrap;border-bottom:1px solid var(--line);padding-bottom:18px}
h1{font-size:34px;line-height:1.05;margin:0 0 8px;letter-spacing:-.02em}
h2{font-size:20px;margin:38px 0 12px;letter-spacing:.01em}
h3{font-size:15px;margin:0 0 6px}
.kicker{color:var(--gold);text-transform:uppercase;letter-spacing:.14em;font-size:11px;font-weight:700}
.sub{color:var(--muted);max-width:62ch;margin:6px 0 0;display:-webkit-box;-webkit-line-clamp:3;-webkit-box-orient:vertical;overflow:hidden}
.stats{display:flex;gap:10px;flex-wrap:wrap}
.stat{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:10px 14px;min-width:92px}
.stat b{display:block;font-size:21px;letter-spacing:-.01em}
.stat span{color:var(--muted);font-size:11px;text-transform:uppercase;letter-spacing:.08em}
.panel{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px}
.note{color:var(--muted);font-size:13px}
.badge{display:inline-block;font-size:10px;text-transform:uppercase;letter-spacing:.08em;padding:2px 7px;border-radius:999px;border:1px solid var(--line);color:var(--muted)}
.badge.estimated{border-color:#5b4a2a;color:var(--warn)}
.badge.manual{border-color:#2f5b42;color:var(--ok)}
.badge.high{color:var(--ok);border-color:#2f5b42}
.badge.medium{color:var(--warn);border-color:#5b4a2a}
.badge.low{color:var(--bad);border-color:#5b2f2f}
.badge.approved{color:var(--ok);border-color:#2f5b42}
.badge.stale,.badge.blocked{color:var(--bad);border-color:#5b2f2f}
.badge.missing,.badge.unavailable{color:var(--muted)}
.badge.short,.badge.mediumd{border-color:#2b3d4a}
.toolbar{display:flex;gap:10px;align-items:center;flex-wrap:wrap;margin:10px 0 14px}
button{background:var(--panel2);color:var(--ink);border:1px solid var(--line);border-radius:8px;padding:6px 12px;font:inherit;cursor:pointer}
button:hover{border-color:var(--gold)}
button.chip{border-radius:999px;font-size:12px;padding:4px 10px;color:var(--muted)}
button.chip.on{color:var(--bg);background:var(--gold);border-color:var(--gold);font-weight:700}
.tl{position:relative;background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px 14px 10px}
.tlrow{position:relative;margin:6px 0}
.tlrow .label{font-size:10px;text-transform:uppercase;letter-spacing:.09em;color:var(--muted);margin-bottom:4px}
.track{position:relative;height:26px;background:#0e161d;border-radius:6px;overflow:hidden}
.track.tall{height:34px}
.seg{position:absolute;top:0;bottom:0;border-right:1px solid #0b1015;display:flex;align-items:center;justify-content:center;font-size:10px;color:#06121a;font-weight:700;overflow:hidden;white-space:nowrap;cursor:pointer}
.seg.short{background:var(--short)}.seg.medium{background:var(--medium)}.seg.long{background:var(--long)}
.seg.dim{opacity:.22}
.seg.section{background:#111a22;border:1px dashed #4a5d6b;color:var(--muted);font-weight:600;justify-content:flex-start;padding-left:6px;font-size:11px}
.seg.section.manual{border-style:solid;border-color:var(--teal);color:var(--ink)}
.seg.gfx{background:#243543;color:var(--ink);font-weight:600}
.seg.gfx.caption{background:#2a2c22;border:1px solid var(--gold)}
.ruler{display:flex;justify-content:space-between;color:var(--muted);font-size:11px;margin:2px 0 8px}
.act{display:flex;align-items:flex-end;gap:1px;height:56px;background:#0e161d;border-radius:6px;padding:4px}
.act i{flex:1;display:block;position:relative;height:100%}
.act i u{position:absolute;bottom:0;left:0;right:0;background:var(--teal);opacity:.75;border-radius:1px 1px 0 0}
.act i s{position:absolute;bottom:0;left:0;right:0;background:var(--gold);opacity:.85;border-radius:1px 1px 0 0}
.act i s{width:45%}
.beats{height:14px;background:#0e161d;border-radius:6px;overflow:hidden}
.playhead{position:absolute;top:34px;bottom:10px;width:2px;background:var(--gold);pointer-events:none;box-shadow:0 0 8px #d4ae6a88}
.legend{display:flex;gap:14px;flex-wrap:wrap;color:var(--muted);font-size:12px;margin-top:10px}
.legend i{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:5px;vertical-align:middle}
.grid2{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:14px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:14px}
.card.estimated{border-style:dashed;border-color:#5b4a2a}
.card .meta{color:var(--muted);font-size:12px;margin:4px 0 8px}
.card ul{margin:6px 0 0;padding-left:18px;color:var(--muted);font-size:13px}
table{width:100%;border-collapse:collapse;font-size:13px}
th,td{text-align:left;vertical-align:top;padding:8px 9px;border-bottom:1px solid var(--line)}
th{color:var(--muted);font-size:10px;text-transform:uppercase;letter-spacing:.09em;position:sticky;top:0;background:var(--bg)}
td.num{font-variant-numeric:tabular-nums;white-space:nowrap;color:var(--muted)}
td.img{width:150px}
td.img img{width:150px;border-radius:6px;display:block;border:1px solid var(--line)}
.missing-thumb{width:150px;height:84px;border:1px dashed #4a5d6b;border-radius:6px;display:flex;align-items:center;justify-content:center;color:var(--muted);font-size:11px;text-align:center;padding:6px}
.prompt{color:var(--muted);font-size:12px;margin-top:4px;display:-webkit-box;-webkit-line-clamp:2;-webkit-box-orient:vertical;overflow:hidden}
.must{color:var(--teal);font-size:12px}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,monospace;font-size:12px}
pre{background:#0e161d;border:1px solid var(--line);border-radius:8px;padding:10px;overflow:auto;font-size:12px}
.findings{list-style:none;margin:0;padding:0}
.findings li{padding:6px 0;border-bottom:1px solid var(--line);font-size:13px}
.findings .sev{font-size:10px;text-transform:uppercase;letter-spacing:.08em;margin-right:8px}
.sev.blocker{color:var(--bad)}.sev.note{color:var(--muted)}
footer{margin-top:46px;border-top:1px solid var(--line);padding-top:14px;color:var(--muted);font-size:12px}
.limits{color:var(--muted);font-size:12px;margin-top:8px}
"""

SCRIPT = """
(function(){
 var data=window.__DASH__||{duration:0,shots:[],sections:[]};
 var audio=document.getElementById('audio'),ph=document.getElementById('playhead'),
     clock=document.getElementById('clock'),play=document.getElementById('play'),
     tl=document.getElementById('tl');
 function fmt(t){var m=Math.floor(t/60),s=t-m*60;return m+':'+(s<10?'0':'')+s.toFixed(1);}
 function draw(){var d=data.duration||1;ph.style.left=((audio.currentTime/d)*100)+'%';clock.textContent=fmt(audio.currentTime)+' / '+fmt(d);}
 if(audio){audio.addEventListener('timeupdate',draw);draw();}
 if(play&&audio){play.addEventListener('click',function(){if(audio.paused){audio.play();play.textContent='Pause';}else{audio.pause();play.textContent='Play';}});}
 document.querySelectorAll('[data-start]').forEach(function(el){
   el.addEventListener('click',function(){
     var t=parseFloat(el.getAttribute('data-start'));
     if(audio){audio.currentTime=t;draw();}
     var target=document.getElementById('shot-'+el.getAttribute('data-shot'));
     if(target)target.scrollIntoView({behavior:'smooth',block:'center'});
   });
 });
 var chips=document.querySelectorAll('button.chip');
 chips.forEach(function(chip){
   chip.addEventListener('click',function(){
     var on=chip.classList.toggle('on');
     chips.forEach(function(c){if(c!==chip)c.classList.remove('on');});
     var id=on?chip.getAttribute('data-section'):null;
     document.querySelectorAll('tr[data-section]').forEach(function(row){
       row.style.display=(!id||row.getAttribute('data-section')===id)?'':'none';
     });
     document.querySelectorAll('.seg[data-section]').forEach(function(seg){
       seg.classList.toggle('dim',!!id&&seg.getAttribute('data-section')!==id);
     });
   });
 });
 document.querySelectorAll('[data-copy]').forEach(function(btn){
    btn.addEventListener('click',async function(){
     var text=document.getElementById(btn.getAttribute('data-copy')).textContent;
      btn.setAttribute('aria-live','polite');
      try{if(!navigator.clipboard)throw new Error('clipboard unavailable');await navigator.clipboard.writeText(text);btn.textContent='Copied';}
      catch(e){btn.textContent='Copy unavailable — select command manually';}
   });
 });
})();
"""


def _pct(value: float, total: float) -> str:
    return f"{(100.0 * value / total) if total else 0:.4f}%"


def _timeline(rows, sections, music, grid, graphics, project) -> str:
    total = project.duration or 1
    parts = ['<div class="tl" id="tl">']
    parts.append(
        '<div class="tlrow"><div class="label">Sections — dashed means estimated, not verified</div>'
        '<div class="track">'
    )
    for section in sections:
        span = max(0.0, section["end_seconds"] - section["start_seconds"])
        cls = "manual" if section["basis"] == "manual" else ""
        share = 100.0 * span / total if total else 0
        label = _short_label(section["label"]) if share >= 3.2 else ""
        parts.append(
            f'<div class="seg section {cls}" data-section="{_esc(section["id"])}" data-start="{section["start_seconds"]:.3f}" '
            f'style="left:{_pct(section["start_seconds"], total)};width:{_pct(span, total)}" '
            f'title="{_esc(section["label"])} · {section["start_seconds"]:.1f}s–{section["end_seconds"]:.1f}s · '
            f'{_esc(section["basis"])} · confidence {_esc(section["confidence"])}">{_esc(label)}</div>'
        )
    parts.append("</div></div>")

    parts.append(
        '<div class="tlrow"><div class="label">Shots — width is duration; click to seek</div>'
        '<div class="track tall">'
    )
    for row in rows:
        share = 100.0 * row["seconds"] / total if total else 0
        label = str(row["index"]) if share >= 2.2 else ""
        parts.append(
            f'<div class="seg {row["duration_class"]}" data-shot="{_esc(row["id"])}" '
            f'data-section="{_esc((row["event_ids"] or ["unassigned"])[0])}" '
            f'data-start="{row["start_seconds"]:.3f}" '
            f'style="left:{_pct(row["start_seconds"], total)};width:{_pct(row["seconds"], total)}" '
            f'title="#{row["index"]} {_esc(row["id"])} · {row["seconds"]:.2f}s · {_esc(row["framing"])}">'
            f"{label}</div>"
        )
    parts.append("</div></div>")

    gfx = []
    intro = graphics.get("intro_seconds") if graphics else None
    if isinstance(intro, (int, float)) and intro > 0:
        gfx.append(("Opening title package", 0.0, float(intro), "intro"))
    if graphics:
        for caption in graphics.get("captions") or []:
            shot = next((r for r in rows if r["id"] == caption.get("shot_id")), None)
            if shot is None:
                continue
            start = shot["start_seconds"] + (caption.get("offset_frames") or 0) / project.fps
            length = (caption.get("duration_frames") or 0) / project.fps
            gfx.append((f"Caption: {caption.get('text', '')}", start, length, "caption"))
        tail = graphics.get("credits_tail_seconds")
        if isinstance(tail, (int, float)) and tail > 0:
            gfx.append(
                (
                    "Identity + credit package",
                    max(0.0, project.duration - float(tail)),
                    float(tail),
                    "credits",
                )
            )
    if gfx:
        parts.append(
            '<div class="tlrow"><div class="label">Local graphics windows</div><div class="track">'
        )
        for label, start, length, kind in gfx:
            share = 100.0 * length / total if total else 0
            text = label if share >= 6 else ""
            parts.append(
                f'<div class="seg gfx {_esc(kind)}" style="left:{_pct(start, total)};width:{_pct(length, total)}" '
                f'title="{_esc(label)} · {start:.1f}s–{start + length:.1f}s">{_esc(text)}</div>'
            )
        parts.append("</div></div>")

    windows = (music or {}).get("summary_windows") or []
    if windows:
        levels = [
            w.get("level_db_mean")
            for w in windows
            if isinstance(w.get("level_db_mean"), (int, float))
        ]
        low, high = (min(levels), max(levels)) if levels else (-60.0, 0.0)
        span = max(1e-6, high - low)
        bars = []
        for window in windows:
            level = window.get("level_db_mean")
            bass = window.get("low_bass_share_mean") or 0
            height = 6 + 94 * ((level - low) / span) if isinstance(level, (int, float)) else 0
            bars.append(
                f'<i title="{window.get("start", 0):.0f}s level {level if level is not None else "?"} dB · '
                f'bass share {bass:.2f}"><u style="height:{min(100, max(0, height)):.1f}%"></u>'
                f'<s style="height:{min(100, max(0, bass * 100)):.1f}%"></s></i>'
            )
        parts.append(
            '<div class="tlrow"><div class="label">Measured activity — 8 s windows (level and low-bass share), '
            'not musical meaning</div><div class="act">' + "".join(bars) + "</div></div>"
        )

    beats = (music or {}).get("beats") or []
    if beats:
        marks = "".join(
            f'<div style="position:absolute;left:{_pct(float(beat), total)};top:0;bottom:0;width:1px;'
            f'background:#688f9d66"></div>'
            for beat in beats[:1200]
            if isinstance(beat, (int, float))
        )
        parts.append(
            '<div class="tlrow"><div class="label">Measured beat estimate — tick positions only; '
            'no meter, bar or downbeat claimed</div><div class="beats" style="position:relative">'
            + marks
            + "</div></div>"
        )

    parts.append('<div class="ruler">')
    steps = 6
    for index in range(steps + 1):
        seconds = total * index / steps
        label = f"{int(seconds // 60)}:{int(seconds % 60):02d}"
        if grid.get("enabled") and index > 0:
            bar = (
                int((seconds * project.fps - grid["bar_zero_frame"]) // grid["frames_per_bar"]) + 1
            )
            label += f" · bar {bar}"
        parts.append(f"<span>{label}</span>")
    parts.append("</div>")
    parts.append('<div class="playhead" id="playhead"></div>')
    parts.append("</div>")
    return "".join(parts)


def _section_cards(sections: list[dict]) -> str:
    cards = []
    for section in sections:
        members = section["shots"]
        cls = "card estimated" if section["basis"] != "manual" else "card"
        cards.append(
            f'<article class="{cls}" data-section="{_esc(section["id"])}">'
            f"<h3>{_esc(section['label'])}</h3>"
            f'<div class="meta">{section["start_seconds"]:.1f}s–{section["end_seconds"]:.1f}s · '
            f'{len(members)} shot(s) · <span class="badge {_esc(section["basis"])}">{_esc(section["basis"])}</span> '
            f'<span class="badge {_esc(section["confidence"])}">{_esc(section["confidence"])}</span> '
            f'<span class="badge">source: {_esc(section["source"])}</span></div>'
            f'<div class="note">{_esc(section["note"])}</div>'
            + (
                f'<div class="limits">Evidence: {_esc(section["evidence"])}</div>'
                if section["evidence"]
                else ""
            )
            + (
                "<ul>"
                + "".join(
                    f"<li>#{row['index']} {_esc(row['id'])} · {row['seconds']:.1f}s · {_esc(row['framing'])}</li>"
                    for row in members
                )
                + "</ul>"
                if members
                else ""
            )
            + "</article>"
        )
    return '<div class="grid2">' + "".join(cards) + "</div>"


def _shot_table(rows: list[dict], stage: str, thumbs: dict) -> str:
    head = (
        "<tr><th>#</th><th>Shot</th><th>Time</th><th>Frame</th><th>Length</th>"
        + ("<th>Bars</th>" if any(row["bar"] for row in rows) else "")
        + ("<th>Still</th>" if stage in ("stills", "delivery") else "")
        + "<th>Framing</th><th>Camera</th><th>Transition</th><th>Content</th></tr>"
    )
    body = []
    for row in rows:
        if row["alias_of"]:
            transition = f"reuses {row['alias_of']}"
        elif row["dissolve_frames"]:
            transition = f"{row['transition'] or 'cut'}; {row['dissolve_frames']}f dissolve"
        elif row["transition"]:
            transition = row["transition"]
        elif row["index"] == 1:
            transition = "opening"
        else:
            transition = "cut"
        still = ""
        if stage in ("stills", "delivery"):
            thumb = thumbs.get(row["id"])
            badge = row["verdict"] or "no verdict"
            if thumb:
                still = (
                    f'<td class="img"><img alt="{_esc(row["id"])}" src="{thumb}">'
                    f'<div class="badge {_esc(row["verdict"] or "missing")}">{_esc(badge)} v{row["version"]}</div></td>'
                )
            else:
                still = (
                    '<td class="img"><div class="missing-thumb">no selected image<br>for this stage</div>'
                    f'<div class="badge {_esc(badge)}">{_esc(badge)}</div></td>'
                )
        content = (
            f"<div>{_esc(row['purpose'][:220])}</div>"
            f'<div class="must">must show: {_esc("; ".join(row["must_show"]))}</div>'
            f'<div class="prompt">{_esc(row["image_prompt"][:260])}</div>'
        )
        bars = f'<td class="num">{_esc(row["bar"])}</td>' if any(r["bar"] for r in rows) else ""
        body.append(
            f'<tr id="shot-{_esc(row["id"])}" data-section="{_esc((row["event_ids"] or ["unassigned"])[0])}">'
            f'<td class="num">{row["index"]}</td>'
            f'<td class="mono">{_esc(row["id"])}<div class="badge {_esc(row["duration_class"])}">{_esc(row["duration_class"])}</div></td>'
            f'<td class="num">{_esc(f"{int(row['start_seconds'] // 60)}:{row['start_seconds'] % 60:04.1f}")}</td>'
            f'<td class="num">{row["start_frame"]}–{row["end_frame"]}</td>'
            f'<td class="num">{row["seconds"]:.2f}s</td>'
            f"{bars}{still}"
            f"<td>{_esc(row['framing'])}</td>"
            f"<td>{_esc(row['camera'])}</td>"
            f'<td class="note">{_esc(transition)}</td>'
            f"<td>{content}</td></tr>"
        )
    return f"<table><thead>{head}</thead><tbody>{''.join(body)}</tbody></table>"


def _approval_panel(states: list[dict], project, stage: str) -> str:
    rows = []
    for entry in states:
        badge = entry["state"]
        details = entry["hash"] or "no current artifact"
        if entry.get("problem"):
            details += " · " + entry["problem"]
        rows.append(
            f'<tr><td class="mono">{_esc(entry["stage"])}</td>'
            f'<td><span class="badge {_esc(badge)}">{_esc(badge)}</span></td>'
            f'<td class="mono">{_esc(details)}</td>'
            f'<td class="note">{_esc(entry["approved_at"] or "")}</td></tr>'
        )
    command = "uv run clip serve --actions"
    return (
        '<div class="panel"><table><thead><tr><th>Stage</th><th>State</th><th>Current hash (short)</th>'
        "<th>Approved at</th></tr></thead><tbody>" + "".join(rows) + "</tbody></table>"
        '<p class="note">A person records decisions in a terminal-enabled Studio session, not on this page. '
        "This generated snapshot must be refreshed after edits; Studio rechecks the reviewed hash.</p>"
        f'<pre id="approve-command">{_esc(command)}</pre>'
        '<button data-copy="approve-command">Copy command</button>'
        "</div>"
    )


def render_html(data: dict) -> str:
    project = data["project"]
    stats = data["stats"]
    grid = data["grid"]
    music = data["music"] or {}
    rows = data["rows"]
    sections = data["sections"]
    findings = data["findings"]
    stage = data["stage"]

    tempo = stats["tempo"]
    if grid["enabled"]:
        tempo_line = (
            f"<b>{grid['bpm']:.2f}</b> BPM · {grid['beats_per_bar']}/4 reviewed grid "
            f'<span class="badge manual">approved</span>'
        )
    else:
        pulses = music.get("pulse_candidates") or []
        candidates = sorted(
            {
                round(float(candidate["primary_bpm"]), 1)
                for candidate in pulses
                if isinstance(candidate.get("primary_bpm"), (int, float))
            }
        )
        detail = (
            f"measured {tempo:.2f} BPM"
            if isinstance(tempo, (int, float))
            else "no tempo measurement"
        )
        if candidates:
            detail += " · window candidates " + ", ".join(f"{value:g}" for value in candidates[:6])
        tempo_line = f"<b>unresolved</b> · {_esc(detail)}"

    audio_tag = ""
    if data.get("audio_uri"):
        audio_tag = f'<audio id="audio" preload="metadata" src="{data["audio_uri"]}"></audio>'
    elif data.get("audio_path"):
        audio_tag = (
            f'<audio id="audio" preload="metadata" src="{_esc(data["audio_path"])}"></audio>'
        )

    findings_html = (
        '<ul class="findings">'
        + "".join(
            f'<li><span class="sev {_esc(item["severity"])}">{_esc(item["severity"])}</span>'
            f"{_esc(item['detail'])}</li>"
            for item in findings
        )
        + "</ul>"
        if findings
        else '<p class="note">No structural findings.</p>'
    )

    chips = "".join(
        f'<button class="chip" data-section="{_esc(section["id"])}">{_esc(section["label"])}</button>'
        for section in sections
    )

    return f"""<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{_esc(project.title)} — {_esc(stage)} dashboard</title>
<style>{CSS}</style></head>
<body><div class="wrap">
<header class="top">
<div>
<div class="kicker">Storyboard map · {_esc(stage)} review</div>
<h1>{_esc(project.title)}</h1>
<p class="sub">{_esc(data["direction"])}</p>
</div>
<div class="stats">
<div class="stat"><b>{stats["duration"]:.0f}s</b><span>length</span></div>
<div class="stat"><b>{stats["shots"]}</b><span>shots</span></div>
<div class="stat"><b>{stats["classes"]["short"]}/{stats["classes"]["medium"]}/{stats["classes"]["long"]}</b><span>short/med/long</span></div>
<div class="stat"><b>{stats["frames"]}</b><span>frames</span></div>
<div class="stat" style="min-width:220px"><b style="font-size:15px">{tempo_line}</b><span>tempo</span></div>
</div>
</header>

<h2>The timeline</h2>
<div class="toolbar">
{audio_tag}
<button id="play">Play</button>
<span class="mono" id="clock">0:00.0</span>
{chips}
</div>
{_timeline(rows, sections, music, grid, data["graphics"], project)}
<div class="legend">
<span><i style="background:var(--short)"></i>short &lt;3s</span>
<span><i style="background:var(--medium)"></i>medium 3–7s</span>
<span><i style="background:var(--long)"></i>long ≥7s</span>
<span><i style="background:#243543"></i>local graphics</span>
<span><i style="background:var(--teal)"></i>measured level</span>
<span><i style="background:var(--gold)"></i>low-bass share</span>
</div>
<p class="limits">{_esc(data["grid_note"])}</p>

<h2>Sections: supplied tags vs. measurement</h2>
<p class="note">A dashed card means the boundary is estimated rather than verified in this project.
Confidence is the recorded source value, not an independent confirmation.</p>
{_section_cards(sections) if sections else '<p class="note">No event map recorded yet.</p>'}

<h2>Shot list</h2>
<p class="note">One row per still: stable id, exact frames and seconds, framing, camera, transition and required content.
Generated lettering stays out of image pixels; all words are composited locally.</p>
{_shot_table(rows, stage, data["thumbs"])}

<h2>Findings</h2>
<div class="panel">{findings_html}</div>

<h2>Approval state</h2>
{_approval_panel(data["approvals"], project, data["approve_stage"])}

<footer>
<p>Generated from canonical artifacts by <span class="mono">clip dashboard</span>; this page is a review aid and never an approval.
No network requests, no analytics, no external fonts.</p>
<p class="mono">board {data["input_summary"]}</p>
<p class="limits">{_esc(data["limits"])}</p>
</footer>
</div>
<script>window.__DASH__={data["payload"]};</script>
<script>{SCRIPT}</script>
</body></html>
"""


# --------------------------------------------------------------------------- #
# build
# --------------------------------------------------------------------------- #
def build_dashboard(
    root: Path,
    stage: str = "board",
    *,
    embed_images: bool = True,
    embed_audio: bool = False,
    name: str | None = None,
) -> dict:
    root = Path(root)
    if stage not in STAGES:
        raise ValueError(f"stage must be one of {', '.join(STAGES)}")
    project = P.load_project(root)
    brief = P.load_brief(root)
    board = P.load_board(root)
    music = _optional(root / "work/music.json")
    events = _optional(root / "work/events.json")
    graphics = _optional(root / "work/graphics-spec.json") or {}
    assets = _optional(root / "work/assets.json") or {}
    reviews = _optional(root / "work/reviews.json") or []
    grid = _music_grid(root)

    rows = _shot_rows(board.model_dump(), project, assets, reviews, grid, stage)
    sections = _sections(events, rows, project.fps)
    findings = _diagnostics(rows, project, stage, grid)
    stats = _stats(rows, project, music)

    cache = root / FOLDER / "thumbs"
    thumbs: dict[str, str] = {}
    if stage in ("stills", "delivery"):
        for row in rows:
            if not row["image"]:
                continue
            if embed_images:
                thumb = _thumbnail(root, cache, row["image"])
                if thumb:
                    thumbs[row["id"]] = f"data:image/jpeg;base64,{thumb}"
            else:
                thumbs[row["id"]] = os.path.relpath(
                    inside(root, row["image"]), (root / FOLDER).resolve()
                )

    audio_uri = None
    audio_path = None
    audio_note = "audio not embedded"
    if embed_audio:
        audio_uri = _data_uri(root, project.source, "audio/mpeg", AUDIO_LIMIT_BYTES)
        if audio_uri:
            audio_note = "audio embedded from the private original (no upload)"
    if audio_uri is None:
        relative = os.path.relpath(inside(root, project.source), (root / FOLDER).resolve())
        audio_path = relative

    grid_note = (
        f"Bar numbers come from the reviewed grid file: {grid.get('note') or grid.get('approved_by') or 'approved grid'}."
        if grid["enabled"]
        else f"No bar grid: {grid['reason']}. The timeline is seconds and frames only."
    )

    payload = script_json(
        {
            "duration": project.duration,
            "shots": [
                {
                    "id": row["id"],
                    "start": row["start_seconds"],
                    "section": (row["event_ids"] or ["unassigned"])[0],
                }
                for row in rows
            ],
            "sections": [
                {"id": s["id"], "label": s["label"], "start": s["start_seconds"]} for s in sections
            ],
        }
    )

    data = {
        "project": project,
        "stage": stage,
        "approve_stage": "storyboard"
        if stage == "board"
        else ("stills" if stage == "stills" else "graphics"),
        "direction": (brief.direction or "").replace("REOPENED by user: ", ""),
        "music": music,
        "events": events,
        "graphics": graphics,
        "grid": grid,
        "grid_note": grid_note,
        "rows": rows,
        "sections": sections,
        "findings": findings,
        "stats": stats,
        "thumbs": thumbs,
        "approvals": _approval_states(root),
        "audio_uri": audio_uri,
        "audio_path": audio_path,
        "audio_note": audio_note,
        "payload": payload,
        "input_summary": " · ".join(
            f"{label} {hash_value[:12]}"
            for label, hash_value in (
                ("brief", file_hash(root / "brief.json")),
                ("board", file_hash(root / "work/storyboard.json")),
                (
                    "events",
                    file_hash(root / "work/events.json")
                    if (root / "work/events.json").is_file()
                    else "-",
                ),
                (
                    "music",
                    file_hash(root / "work/music.json")
                    if (root / "work/music.json").is_file()
                    else "-",
                ),
            )
        ),
        "limits": (
            "Measured values are local estimates. No meter, downbeat, lyric timestamp, genre or emotional "
            "meaning is inferred from a filename or a tempo estimate. Sampled review here is not continuous "
            "playback; approval remains a separate CLI decision bound to artifact hashes."
        ),
    }
    document = render_html(data)

    folder = root / FOLDER
    folder.mkdir(parents=True, exist_ok=True)
    if name:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*\.html", name):
            raise ValueError("dashboard name must be a safe lowercase .html basename")
        target = folder / name
        if target.exists():
            raise ValueError(f"{target.name} already exists; dashboards are never overwritten")
    else:
        version = 1
        while (folder / f"{stage}-v{version:03d}.html").exists():
            version += 1
        target = folder / f"{stage}-v{version:03d}.html"
    target.write_text(document, encoding="utf-8")

    sidecar = {
        "stage": stage,
        "html": str(target.relative_to(root)),
        "html_sha256": file_hash(target),
        "bytes": target.stat().st_size,
        "shots": len(rows),
        "sections": len(sections),
        "grid_enabled": grid["enabled"],
        "embedded_images": len(thumbs),
        "embedded_audio": audio_uri is not None,
        "findings": findings,
        "inputs": {
            "project": file_hash(root / "project.json"),
            "brief": file_hash(root / "brief.json"),
            "storyboard": file_hash(root / "work/storyboard.json"),
            **(
                {"events": file_hash(root / "work/events.json")}
                if (root / "work/events.json").is_file()
                else {}
            ),
            **(
                {"music": file_hash(root / "work/music.json")}
                if (root / "work/music.json").is_file()
                else {}
            ),
            **(
                {"graphics_spec": file_hash(root / "work/graphics-spec.json")}
                if (root / "work/graphics-spec.json").is_file()
                else {}
            ),
            **(
                {"assets": file_hash(root / "work/assets.json")}
                if (root / "work/assets.json").is_file()
                else {}
            ),
            **(
                {"reviews": file_hash(root / "work/reviews.json")}
                if (root / "work/reviews.json").is_file()
                else {}
            ),
        },
        "limits": data["limits"],
        "warning": (
            "Review aid only: this page records no approval, uploads nothing and cannot replace continuous "
            "playback. Decide in the human Studio against the current artifact hash."
        ),
    }
    write_json(target.with_suffix(".json"), sidecar)
    return {**sidecar, "created_at": datetime.now(UTC).isoformat()}
