"""The Critic's notes on a cut, and the frames it looks at to write them.

Notes are advice. They live in their own append-only file, outside every approval
hash, so a review can never open or close a gate. Each is bound to the render it
judged and the cut it came from, so a note on an older cut says so.
"""

from __future__ import annotations

import io
import json
import shutil
import subprocess
from datetime import UTC, datetime
from pathlib import Path

from PIL import Image

from .storage import digest, file_hash, read_optional

CRITIQUES_PATH = "work/critiques.jsonl"
SEVERITIES = ("must_fix", "should_fix", "consider")
MAX_NOTES = 12
MAX_FRAMES = 8
FRAME_PIXELS = 768


def _edit_hash(root: Path) -> str | None:
    value = read_optional(root / "work/edit.json")
    return digest(value) if value is not None else None


def newest_render(root: Path) -> Path | None:
    """The film as it stands: the newest final, else the newest base or preview."""
    finals = sorted((root / "renders").glob("*-final-v*.mp4"))
    if finals:
        return max(finals, key=lambda path: path.stat().st_mtime)
    others = [*(root / "renders").glob("*.mp4"), *(root / "previews").glob("*.mp4")]
    return max(others, key=lambda path: path.stat().st_mtime) if others else None


def film_frames(root: Path, frames: list[int], fps: int) -> dict:
    """JPEG bytes of the newest render at the given frames, with what they show."""
    if not isinstance(frames, list) or not frames:
        raise ValueError("name at least one frame")
    if len(frames) > MAX_FRAMES:
        raise ValueError(f"ask for at most {MAX_FRAMES} frames per call")
    if any(isinstance(item, bool) or not isinstance(item, int) or item < 0 for item in frames):
        raise ValueError("frames must be whole film frames")
    render = newest_render(root)
    if render is None:
        raise ValueError("there is no render to look at yet; render the film first")
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("ffmpeg was not found on PATH")
    pictures = []
    for frame in frames:
        completed = subprocess.run(
            [
                ffmpeg,
                "-nostdin",
                "-v",
                "error",
                "-ss",
                f"{frame / fps:.6f}",
                "-i",
                str(render),
                "-frames:v",
                "1",
                "-f",
                "image2pipe",
                "-c:v",
                "mjpeg",
                "pipe:1",
            ],
            capture_output=True,
        )
        if completed.returncode != 0 or not completed.stdout:
            raise ValueError(f"frame {frame} is outside {render.name}")
        with Image.open(io.BytesIO(completed.stdout)) as source:
            image = source.convert("RGB")
            image.thumbnail((FRAME_PIXELS, FRAME_PIXELS))
            data = io.BytesIO()
            image.save(data, format="JPEG", quality=85)
        pictures.append({"frame": frame, "seconds": round(frame / fps, 3), "jpeg": data.getvalue()})
    return {
        "render": render.name,
        "cut_is_current": _render_matches_cut(root, render),
        "frames": pictures,
    }


def _render_matches_cut(root: Path, render: Path) -> bool:
    report = read_optional(render.with_suffix(".json"))
    current = _edit_hash(root)
    return (
        bool(isinstance(report, dict) and report.get("current"))
        and current is not None
        and (render.stat().st_mtime >= (root / "work/edit.json").stat().st_mtime)
    )


def _clean_note(raw: object, fps: int) -> dict:
    if not isinstance(raw, dict):
        raise ValueError("each note must be an object")
    severity = raw.get("severity")
    if severity not in SEVERITIES:
        raise ValueError(f"severity must be one of {', '.join(SEVERITIES)}")
    note = raw.get("note")
    if not isinstance(note, str) or not note.strip():
        raise ValueError("each note must say what is wrong")
    value = {"severity": severity, "note": note.strip()}
    suggestion = raw.get("suggestion")
    if isinstance(suggestion, str) and suggestion.strip():
        value["suggestion"] = suggestion.strip()
    if isinstance(raw.get("shot_id"), str) and raw["shot_id"].strip():
        value["shot_id"] = raw["shot_id"].strip()
    frame = raw.get("frame")
    if isinstance(frame, int) and not isinstance(frame, bool) and frame >= 0:
        value["frame"] = frame
    return value


def save(root: Path, verdict: str, notes: list, fps: int) -> dict:
    if not isinstance(verdict, str) or not verdict.strip():
        raise ValueError("give a verdict of one or two sentences")
    if not isinstance(notes, list) or len(notes) > MAX_NOTES:
        raise ValueError(f"give at most {MAX_NOTES} notes")
    render = newest_render(root)
    if render is None:
        raise ValueError("there is no render to review yet")
    entry = {
        "at": datetime.now(UTC).isoformat(),
        "render": render.name,
        "render_sha256": file_hash(render),
        "edit_hash": _edit_hash(root),
        "verdict": verdict.strip(),
        "notes": [_clean_note(item, fps) for item in notes],
    }
    path = root / CRITIQUES_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(entry) + "\n")
    return entry


def latest(root: Path) -> dict | None:
    path = root / CRITIQUES_PATH
    if not path.is_file():
        return None
    rows = [line for line in path.read_text().splitlines() if line.strip()]
    if not rows:
        return None
    entry = json.loads(rows[-1])
    entry["current"] = entry.get("edit_hash") == _edit_hash(root)
    return entry
