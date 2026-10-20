"""Combine evidence and listening interpretations without pretending either is approval."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .models import EventMap, MusicEvent
from .music_analysis import load_listening
from .production import load_project
from .storage import digest, read_json, write_json


def build_music_map(root: Path) -> dict:
    project = load_project(root)
    local = read_json(root / "work/music.json")
    listening = load_listening(root)
    passages = []
    events = []
    review_flags = []
    for index, passage in enumerate(listening["draft"]["passages"], 1):
        start, end = passage["start"], passage["end"]
        if end - start > 20:
            review_flags.append(
                f"Passage {index} spans {end - start:.1f}s; too coarse for detailed DJ editing without further review."
            )
        if passage["label"].strip().lower() in ("verse", "chorus", "pre-chorus", "bridge"):
            review_flags.append(
                f"Passage {index} uses an unverified conventional song label; do not treat it as established DJ structure."
            )
        measured = {}
        rows = [
            (w, max(0, min(end, w["end"]) - max(start, w["time"])))
            for w in local.get("fine_windows", [])
        ]
        weight = sum(n for _, n in rows)
        if weight:
            for key in (
                "rms_db",
                "level_db",
                "low_bass_share",
                "high_share",
                "spectral_centroid_hz",
                "onset_density_per_s",
            ):
                measured[key + "_window_mean"] = round(sum(w[key] * n for w, n in rows) / weight, 4)
        nearby = [c for c in local.get("candidate_changes", []) if abs(c["time"] - start) <= 4]
        row = {
            "id": f"passage-{index:02d}",
            "interpretation": passage,
            "measured": measured,
            "start_frame": round(start * project.fps),
            "end_frame": min(project.total_frames, round(end * project.fps)),
            "nearby_measured_change": min(nearby, key=lambda c: abs(c["time"] - start))
            if nearby
            else None,
            "reviewed": False,
        }
        passages.append(row)
        if row["start_frame"] < project.total_frames and row["end_frame"] > row["start_frame"]:
            events.append(
                MusicEvent(
                    id=row["id"],
                    frame=row["start_frame"],
                    end_frame=row["end_frame"],
                    kind="section",
                    label=passage["label"],
                    timing_basis="estimated",
                    level="section",
                    confidence=passage["confidence"],
                    source="audio-model",
                    evidence=passage["evidence"],
                    note="Unreviewed listening candidate; groove/texture: "
                    + passage["groove"]
                    + "; "
                    + ", ".join(passage["texture"]),
                )
            )
    return {
        "source_sha256": project.source_sha256,
        "duration": project.duration,
        "analysis_hash": digest(local),
        "listening_hash": digest(listening),
        "passages": passages,
        "review_flags": review_flags,
        "overall_observations": listening["draft"]["overall_observations"],
        "limitations": listening["draft"]["limitations"],
        "candidate_changes": local.get("candidate_changes", []),
        "pulse_candidates": local.get("pulse_candidates", []),
        "draft_event_map": EventMap(
            source_sha256=project.source_sha256,
            fps=project.fps,
            total_frames=project.total_frames,
            events=events,
        ).model_dump(),
        "warning": "DRAFT: model interpretation and local measurements are separate evidence. No genre, exact cut, instrument, key, hook or narrative has been approved. Event times are estimates, not a beat grid.",
    }


def _time(seconds: float) -> str:
    return f"{int(seconds // 60)}:{seconds % 60:05.2f}"


def measured_chart(root: Path, output: Path):
    """Local evidence chart, not an artistic energy judgment or a beat grid."""
    local = read_json(root / "work/music.json")
    rows = local.get("fine_windows", [])
    duration = load_project(root).duration
    image = Image.new("RGB", (1600, 970), (18, 21, 26))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default(size=20)
    small = ImageFont.load_default(size=15)
    draw.text((90, 20), "MEASURED SOUND MAP — UNREVIEWED", font=font, fill="white")
    draw.text(
        (90, 52),
        "Level is not emotion. Yellow lines are change candidates, not verified edits or genre boundaries.",
        font=small,
        fill=(220, 220, 220),
    )
    panels = [
        ("rms_db", "RMS level / dBFS", -80, 0, (100, 190, 255)),
        ("low_bass_share", "35–150 Hz power share / fraction", 0, 1, (130, 240, 170)),
        ("high_share", ">4 kHz power share / fraction", 0, 1, (230, 160, 245)),
        (
            "onset_density_per_s",
            "Detected onset density / per second",
            0,
            max(1, max((r["onset_density_per_s"] for r in rows), default=1)),
            (250, 190, 100),
        ),
    ]
    left, right = 90, 1540
    for number, (key, label, lo, hi, colour) in enumerate(panels):
        top, bottom = 125 + number * 205, 285 + number * 205
        draw.text((left, top - 30), label, font=small, fill=colour)
        for step in range(5):
            y = top + (bottom - top) * step / 4
            draw.line((left, y, right, y), fill=(55, 58, 65))
            draw.text(
                (10, y - 6), f"{hi - (hi - lo) * step / 4:.2g}", font=small, fill=(190, 190, 190)
            )
        for candidate in local.get("candidate_changes", []):
            x = left + (right - left) * candidate["time"] / duration
            draw.line((x, top, x, bottom), fill=(100, 95, 35))
        points = []
        for row in rows:
            x = left + (right - left) * row["time"] / duration
            value = max(lo, min(hi, row[key]))
            y = bottom - (bottom - top) * (value - lo) / (hi - lo)
            points.append((x, y))
        if len(points) > 1:
            draw.line(points, fill=colour, width=2)
        for index in range(9):
            t = duration * index / 8
            x = left + (right - left) * index / 8
            draw.text((min(right - 45, x), bottom + 10), _time(t), font=small, fill=(205, 205, 205))
    image.save(output)


def write_music_map(root: Path) -> dict:
    value = build_music_map(root)
    path = root / "work/music-map.json"
    if path.exists():
        previous = read_json(path)
        if previous != value:
            write_json(root / f"work/music-map-history/{digest(previous)}.json", previous)
    write_json(path, value)
    lines = [
        "# Music map — unreviewed",
        "",
        value["warning"],
        "",
        "Measurements below are window averages, not semantic energy judgments or exact edit points.",
        "",
    ]
    if value["review_flags"]:
        lines += [
            "## Review blockers / limitations",
            "",
            *["- " + flag for flag in value["review_flags"]],
            "",
        ]
    for row in value["passages"]:
        p = row["interpretation"]
        lines += [
            f"## {_time(p['start'])}–{_time(p['end'])}: {p['label']}",
            "",
            f"- Groove: {p['groove']}",
            f"- Texture: {', '.join(p['texture'])}",
            f"- Model energy / tension: {p['energy']} / {p['tension']}",
            f"- Transition: {p['transition']}",
            f"- Hook draft: {p['vocal_hook'] or 'not established'}",
            f"- Model confidence: {p['confidence']}; uncertainty: {p['uncertainty'] or 'not stated'}",
            f"- Evidence: {p['evidence']}",
            f"- Measured means: {row['measured']}",
            "",
        ]
    lines += [
        "## Limitations",
        "",
        *["- " + item for item in value["limitations"]],
        "",
        "Candidate event map is embedded in music-map.json, not promoted to work/events.json or approved.",
    ]
    markdown = root / "work/music-map.md"
    chart = root / "work/music-measured.png"
    measured_chart(root, chart)
    lines += [
        "",
        "## Local measured sound map",
        "",
        "![Measured level, bass, brightness and onset density](music-measured.png)",
    ]
    markdown.write_text("\n".join(lines) + "\n")
    return {
        "map": str(path),
        "review": str(markdown),
        "passages": len(value["passages"]),
        "chart": str(chart),
        "approved": False,
    }
