"""Read-only projections for the studio app.

The app is a view over canonical artifacts, never a second state store. These
functions return small JSON-ready dictionaries for the live layer, and one
in-memory thumbnail renderer. Nothing here writes to a production: thumbnails
are encoded in memory and no cache directory is created.
"""

from __future__ import annotations

import io
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageOps

from . import production as P
from . import studio
from .dashboard import _music_grid
from .storage import inside, read_optional

THUMB_WIDTH = 360
THUMB_QUALITY = 78


def _optional(root: Path, relative: str):
    return read_optional(root / relative)


def _verdicts(reviews: list[dict]) -> dict[tuple, dict]:
    """Latest verdict per exact image identity (shot, version and bytes)."""
    latest: dict[tuple, dict] = {}
    for review in reviews:
        key = (review.get("shot_id"), review.get("version"), review.get("sha256"))
        latest[key] = review
    return latest


def _assets(root: Path) -> dict:
    value = _optional(root, "work/assets.json")
    return value if isinstance(value, dict) else {}


def _chosen(entry: dict, version: int | None = None) -> dict | None:
    number = entry.get("selected") if version is None else version
    return next(
        (item for item in entry.get("versions", []) if item.get("version") == number),
        None,
    )


def _readable_image(root: Path, relative: str | None) -> bool:
    if not relative:
        return False
    try:
        return inside(root, relative).is_file()
    except (OSError, ValueError):
        return False


def stills(root: Path) -> dict:
    """Per-shot selected still, verdict and contract summary."""
    root = Path(root)
    project = P.load_project(root)
    base = {
        "slug": project.slug,
        "title": project.title,
        "fps": project.fps,
        "total_frames": project.total_frames,
        "duration": project.duration,
    }
    try:
        board = P.load_board(root)
    except (OSError, ValueError, KeyError) as exc:
        return {**base, "available": False, "warning": str(exc), "shots": []}

    assets = _assets(root)
    reviews = _optional(root, "work/reviews.json")
    verdicts = _verdicts(reviews if isinstance(reviews, list) else [])
    rows = []
    counts = {"accept": 0, "reject": 0, "uncertain": 0, "unreviewed": 0}
    for shot in board.shots:
        owner = shot.asset_shot_id or shot.id
        entry = assets.get(owner) or {}
        version = _chosen(entry)
        number = version.get("version") if version else None
        digest = version.get("sha256") if version else None
        verdict = verdicts.get((owner, number, digest), {}) if version else {}
        label = verdict.get("verdict")
        counts[label if label in counts else "unreviewed"] += 1
        rows.append(
            {
                "id": shot.id,
                "owner": owner,
                "alias_of": shot.asset_shot_id,
                "version": number,
                "verdict": label,
                "verdict_note": verdict.get("note"),
                "sha256": digest,
                "seconds": round(shot.duration_frames / project.fps, 3),
                "start_seconds": round(shot.start_frame / project.fps, 3),
                "framing": shot.framing or "",
                "purpose": shot.purpose,
                "has_image": bool(version) and _readable_image(root, version.get("path")),
                "thumb": f"/api/project/{project.slug}/thumb/{shot.id}",
            }
        )
    return {
        **base,
        "available": True,
        "shots": rows,
        "counts": counts,
        "selected": sum(1 for row in rows if row["version"] is not None),
    }


def shot_detail(root: Path, shot_id: str) -> dict:
    """One shot's contract and compiled prompt, or LookupError when unknown."""
    root = Path(root)
    project = P.load_project(root)
    board = P.load_board(root)
    shot = next((item for item in board.shots if item.id == shot_id), None)
    if shot is None:
        raise LookupError("unknown shot")
    owner = shot.asset_shot_id or shot.id
    entry = _assets(root).get(owner) or {}
    version = _chosen(entry)
    reviews = _optional(root, "work/reviews.json")
    verdict = (
        _verdicts(reviews if isinstance(reviews, list) else []).get(
            (owner, version.get("version"), version.get("sha256"))
        )
        if version
        else {}
    ) or {}
    prompt = shot.image_prompt
    prompt_error = None
    try:
        spec = P.image_spec(root, shot)
        prompt = spec.get("positivePrompt") or prompt
    except (OSError, ValueError, KeyError) as exc:
        prompt_error = str(exc)
        prompt = None
    return {
        "id": shot.id,
        "owner": owner,
        "alias_of": shot.asset_shot_id,
        "version": version.get("version") if version else None,
        "sha256": version.get("sha256") if version else None,
        "verdict": verdict.get("verdict"),
        "verdict_note": verdict.get("note"),
        "seconds": round(shot.duration_frames / project.fps, 3),
        "start_frame": shot.start_frame,
        "end_frame": shot.start_frame + shot.duration_frames,
        "framing": shot.framing or "",
        "contract": {
            "purpose": shot.purpose,
            "framing": shot.framing or "",
            "camera": shot.camera,
            "transition": shot.transition or "cut",
            "dissolve_frames": shot.dissolve_frames,
            "scene": shot.scene_id,
            "characters": list(shot.character_ids),
            "states": dict(shot.character_states),
            "references": list(shot.reference_ids),
            "must_show": list(shot.must_show),
            "music_context": shot.music_context,
            "lyric_context": shot.lyric_context,
        },
        "prompt": prompt,
        "prompt_error": prompt_error,
        "thumb": f"/api/project/{project.slug}/thumb/{shot.id}",
    }


def _bands(events: dict | None, rows: list[dict], total_frames: int, fps: int) -> list[dict]:
    if not events or not events.get("events"):
        return []
    ordered = sorted(events["events"], key=lambda item: item.get("frame", 0))
    bands = []
    for index, event in enumerate(ordered):
        start = event.get("frame", 0)
        end = event.get("end_frame")
        if end is None:
            end = (
                ordered[index + 1].get("frame", start) if index + 1 < len(ordered) else total_frames
            )
        bands.append(
            {
                "id": event.get("id") or f"event-{index + 1}",
                "label": event.get("label") or "Unlabelled",
                "kind": event.get("kind") or "section",
                "start_frame": start,
                "end_frame": end,
                "start_seconds": round(start / fps, 3),
                "end_seconds": round(end / fps, 3),
                "timing_basis": event.get("timing_basis") or "estimated",
                "confidence": event.get("confidence") or "unknown",
                "source": event.get("source") or "unknown",
                "note": event.get("note") or "",
                "shot_ids": [
                    row["id"]
                    for row in rows
                    if row["start_frame"] < end and row["end_frame"] > start
                ],
            }
        )
    return bands


def board(root: Path) -> dict:
    """Shot timeline, section bands and the fail-closed bar-grid state."""
    root = Path(root)
    project = P.load_project(root)
    base = {
        "slug": project.slug,
        "title": project.title,
        "fps": project.fps,
        "duration": project.duration,
        "total_frames": project.total_frames,
        "aspect": project.aspect,
    }
    try:
        storyboard = P.load_board(root)
    except (OSError, ValueError, KeyError) as exc:
        return {**base, "available": False, "warning": str(exc), "shots": [], "bands": []}

    grid = _music_grid(root)
    rows = []
    for index, shot in enumerate(storyboard.shots, 1):
        start = shot.start_frame
        end = start + shot.duration_frames
        row = {
            "index": index,
            "id": shot.id,
            "start_frame": start,
            "end_frame": end,
            "start_seconds": round(start / project.fps, 3),
            "end_seconds": round(end / project.fps, 3),
            "seconds": round(shot.duration_frames / project.fps, 3),
            "framing": shot.framing or "",
            "purpose": shot.purpose,
            "scene": shot.scene_id,
            "camera": shot.camera,
            "transition": shot.transition or "cut",
            "dissolve_frames": shot.dissolve_frames,
            "event_ids": list(shot.event_ids),
            "bar": None,
        }
        if grid.get("enabled"):
            span = grid["frames_per_bar"]
            first = int((start - grid["bar_zero_frame"]) // span) + 1
            last = int((end - grid["bar_zero_frame"] - 1) // span) + 1
            row["bar"] = f"{first}" if first == last else f"{first}–{last}"
        rows.append(row)
    return {
        **base,
        "available": True,
        "shots": rows,
        "bands": _bands(
            _optional(root, "work/events.json"), rows, project.total_frames, project.fps
        ),
        "grid": {
            "enabled": bool(grid.get("enabled")),
            "reason": grid.get("reason", ""),
        },
    }


def approvals(root: Path) -> dict:
    """Live stage hashes beside the recorded human decision, read-only."""
    root = Path(root)
    project = P.load_project(root)
    record = _optional(root, "work/approvals.json")
    record = record if isinstance(record, dict) else {}
    stages = []
    for stage in studio.ORDER:
        try:
            current = P.stage_hash(root, stage)
        except (OSError, ValueError, KeyError):
            current = None
        approval = record.get(stage) or {}
        approved_hash = approval.get("hash")
        if current is None:
            state = "unavailable"
        elif not approval:
            state = "missing"
        elif approved_hash == current:
            state = "approved"
        else:
            state = "stale"
        stages.append(
            {
                "stage": stage,
                "state": state,
                "hash": current,
                "approved_hash": approved_hash,
                "at": approval.get("at"),
                "note": approval.get("note"),
                "would_pass_now": bool(approval)
                and current is not None
                and approved_hash == current,
                "approve_command": (
                    f"uv run clip approve projects/{project.slug} {stage} --note '<your decision>'"
                ),
            }
        )
    return {
        "slug": project.slug,
        "title": project.title,
        "stages": stages,
        "current": sum(1 for stage in stages if stage["would_pass_now"]),
        "total": len(stages),
    }


@lru_cache(maxsize=512)
def _thumb_bytes(path: str, mtime_ns: int, size: int, width: int) -> bytes:
    with Image.open(path) as opened:
        image = ImageOps.exif_transpose(opened).convert("RGB")
        ratio = width / image.width
        thumb = image.resize((width, max(1, round(image.height * ratio))))
        buffer = io.BytesIO()
        thumb.save(buffer, format="JPEG", quality=THUMB_QUALITY, optimize=True)
    return buffer.getvalue()


def thumbnail(root: Path, shot_id: str, version: int | None = None) -> bytes:
    """JPEG bytes for one shot version, only from a path inside the project.

    Raises LookupError for an unknown shot/version, FileNotFoundError for a
    missing file and ValueError for a path outside the project or unreadable image.
    """
    root = Path(root)
    storyboard = P.load_board(root)
    shot = next((item for item in storyboard.shots if item.id == shot_id), None)
    if shot is None:
        raise LookupError("unknown shot")
    owner = shot.asset_shot_id or shot.id
    chosen = _chosen(_assets(root).get(owner) or {}, version)
    if chosen is None:
        raise LookupError("no selected image")
    source = inside(root, chosen.get("path") or "")
    if not source.is_file():
        raise FileNotFoundError("image missing")
    stat = source.stat()
    try:
        return _thumb_bytes(str(source), stat.st_mtime_ns, stat.st_size, THUMB_WIDTH)
    except (OSError, ValueError) as exc:
        raise ValueError("unreadable image") from exc
