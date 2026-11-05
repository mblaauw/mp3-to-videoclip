"""The files that travel with a verified final. A final is only ever read here.

Every file is a new sidecar beside the film. A poster is named by its frame, so choosing another
frame adds a file and never replaces one. Pure FFmpeg and the cut: no renderer, no provider.
"""

from __future__ import annotations

import re
import shutil
import statistics
import subprocess
from pathlib import Path

from . import captions, edits
from .production.project import load_project, requires_signature
from .storage import file_hash, read_optional, write_json

CONTACT_FRAMES = 20
#: Platforms ignore chapters shorter than this, and may ignore all of them.
MIN_CHAPTER_SECONDS = 10.0
POSTER_SAMPLE_SECONDS = 2.0
SIDECAR = re.compile(
    r"[a-z0-9][a-z0-9-]*\.(?:poster-f\d+\.(?:png|jpg)|contact\.png|chapters\.txt|ffmetadata|srt|vtt|package-f\d+\.json|thumb-f\d+-\d\.jpg|publish\.json)"
)
MEDIA = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".txt": "text/plain",
    ".ffmetadata": "text/plain",
    ".srt": "application/x-subrip",
    ".vtt": "text/vtt",
    ".json": "application/json",
}


def _ffmpeg() -> str:
    binary = shutil.which("ffmpeg")
    if binary is None:
        raise ValueError("ffmpeg is required to make the package")
    return binary


def _run(*args: str) -> bytes:
    completed = subprocess.run([_ffmpeg(), "-nostdin", "-v", "error", *args], capture_output=True)
    if completed.returncode != 0:
        raise ValueError(completed.stderr.decode("utf-8", "replace")[-400:] or "ffmpeg failed")
    return completed.stdout


def _verified_final(root: Path, film: Path) -> dict:
    report = read_optional(film.with_suffix(".json"))
    if not isinstance(report, dict) or report.get("render_kind") != "final":
        raise ValueError("only a final has a package")
    if report.get("verified") is not True or file_hash(film) != report.get("output_sha256"):
        raise ValueError("this file is not the final its report verified")
    return report


def _section_name(section, names: dict[int, str], number: int, fps: int) -> str:
    # A cut retimed by its takes drifts from the map, so a name within a second still counts.
    near = [at for at in names if abs(at - section.start_frame) <= fps]
    if near:
        return names[min(near, key=lambda at: abs(at - section.start_frame))]
    feel = re.split(r"[.;:—]", section.feel, maxsplit=1)[0].strip()
    return feel[:60].rstrip() or f"Section {number}"


def chapter_list(root: Path) -> list[dict]:
    """The cut's sections as chapters: the first at zero, none too short for a platform."""
    from .song_map import song_map

    project = load_project(root, verify_source=False)
    edit = edits.load_edit(root)
    if edit is None or not edit.sections:
        return []
    try:
        names = {row["start_frame"]: row["name"] for row in song_map(root).get("sections", [])}
    except (OSError, ValueError, KeyError):
        names = {}
    rows: list[dict] = []
    ordered = sorted(edit.sections, key=lambda section: section.start_frame)
    for number, section in enumerate(ordered, start=1):
        at = 0 if not rows else section.start_frame
        if rows and (at - rows[-1]["start_frame"]) / project.fps < MIN_CHAPTER_SECONDS:
            continue
        rows.append(
            {"start_frame": at, "title": _section_name(section, names, number, project.fps)}
        )
    return rows


def _clock(frame: int, fps: int) -> str:
    seconds = frame // fps
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}" if hours else f"{minutes:02d}:{seconds:02d}"


def chapters_text(rows: list[dict], fps: int) -> str:
    return "".join(f"{_clock(row['start_frame'], fps)} {row['title']}\n" for row in rows)


def _escape(value: str) -> str:
    return re.sub(r"([=;#\\\n])", r"\\\1", value)


def ffmetadata(rows: list[dict], fps: int, total_frames: int) -> str:
    blocks = [";FFMETADATA1\n"]
    for index, row in enumerate(rows):
        end = rows[index + 1]["start_frame"] if index + 1 < len(rows) else total_frames
        blocks.append(
            "[CHAPTER]\nTIMEBASE=1/1000\n"
            f"START={row['start_frame'] * 1000 // fps}\nEND={end * 1000 // fps}\n"
            f"title={_escape(row['title'])}\n"
        )
    return "".join(blocks)


def _opening_frames(root: Path, project) -> int:
    if not requires_signature(root, project):
        return 0
    spec = read_optional(root / "work/graphics-spec.json")
    seconds = spec.get("intro_seconds", 0) if isinstance(spec, dict) else 0
    return round(float(seconds) * project.fps)


def poster_frame(root: Path, film: Path, project, total: int) -> int:
    """After the opening, the earliest sampled frame nearest the film's median brightness."""
    first = min(_opening_frames(root, project), max(0, total - 1))
    step = max(1, round(POSTER_SAMPLE_SECONDS * project.fps))
    raw = _run(
        "-i", str(film),
        "-vf", f"select='gte(n\\,{first})*not(mod(n-{first}\\,{step}))',scale=16:9,format=gray",
        "-fps_mode", "vfr",
        "-f", "rawvideo", "-",
    )  # fmt: skip
    levels = [sum(raw[at : at + 144]) / 144 for at in range(0, len(raw) - 143, 144)]
    if not levels:
        return first
    middle = statistics.median(levels)
    nearest = min(range(len(levels)), key=lambda at: (abs(levels[at] - middle), at))
    return first + nearest * step


def _write_new(path: Path, text: str) -> None:
    if not path.exists():
        path.write_text(text, encoding="utf-8")


def _poster(film: Path, frame: int) -> list[Path]:
    png = film.with_suffix(f".poster-f{frame:06d}.png")
    jpg = film.with_suffix(f".poster-f{frame:06d}.jpg")
    for path in (png, jpg):
        if not path.exists():
            _run(
                "-n", "-i", str(film),
                "-vf", f"select='eq(n\\,{frame})'",
                "-frames:v", "1",
                *(["-q:v", "2"] if path.suffix == ".jpg" else []),
                str(path),
            )  # fmt: skip
    return [png, jpg]


def _contact(film: Path, total: int) -> Path:
    path = film.with_suffix(".contact.png")
    if not path.exists():
        count = min(CONTACT_FRAMES, total)
        picks = "+".join(
            f"eq(n\\,{(2 * index + 1) * total // (2 * count)})" for index in range(count)
        )
        rows = max(1, (count + 4) // 5)
        _run(
            "-n", "-i", str(film),
            "-vf", f"select='{picks}',scale=384:-2,tile=5x{rows}:padding=4",
            "-fps_mode", "vfr",
            "-frames:v", "1",
            str(path),
        )  # fmt: skip
    return path


def make_package(root: Path, film: Path, *, frame: int | None = None) -> dict:
    """Write what is missing beside this final and list what is there, with hashes."""
    root, film = Path(root), Path(film)
    report = _verified_final(root, film)
    project = load_project(root, verify_source=False)
    total = int(report.get("video", {}).get("frames") or project.total_frames)
    if frame is not None and not 0 <= frame < total:
        raise ValueError("that frame is not in this film")
    chosen = poster_frame(root, film, project, total) if frame is None else frame
    files = [*_poster(film, chosen), _contact(film, total)]
    rows = chapter_list(root)
    if rows:
        for suffix, text in (
            (".chapters.txt", chapters_text(rows, project.fps)),
            (".ffmetadata", ffmetadata(rows, project.fps, total)),
        ):
            path = film.with_suffix(suffix)
            _write_new(path, text)
            files.append(path)
    captions.sidecars_for(root, film, project)
    files += [
        path for path in (film.with_suffix(".srt"), film.with_suffix(".vtt")) if path.exists()
    ]
    value = {
        "final": film.name,
        "final_sha256": report["output_sha256"],
        "poster_frame": chosen,
        "files": {path.name: file_hash(path) for path in files},
    }
    listing = film.with_suffix(f".package-f{chosen:06d}.json")
    if not listing.exists():
        write_json(listing, value)
    return value


def listing(film: Path) -> list[str]:
    """The package files already beside a film, for the exports list. Reads no bytes."""
    stem = film.stem
    return sorted(
        path.name
        for path in film.parent.glob(f"{stem}.*")
        if path.is_file() and SIDECAR.fullmatch(path.name)
    )


def newest_poster(root: Path) -> str | None:
    """The film's own frame for the Library, from the latest packaged final."""
    posters = sorted(
        (root / "renders").glob("*.poster-f*.jpg"), key=lambda path: path.stat().st_mtime
    )
    return posters[-1].name if posters else None
