"""What the owner has heard: whole seconds that played with the sound on, per film file.

The browser reports the seconds a media element played while it was not muted and its volume
was up; the engine unions them here, append-only, keyed by the file and its bytes. A new final
starts at zero. This is evidence the owner cannot reach by accident, not a proof: a browser
reports playback, nobody checks the speakers.
"""

from __future__ import annotations

from pathlib import Path

from .storage import file_hash, inside, read_optional, state_mutation, write_json

FILE = "work/watched.json"
VERSION = 1
#: The last bucket of a file rarely fires, so a whole film is heard a little short of it.
HEARD_SHARE = 0.98
MAX_BATCH = 20_000


def read(root: Path) -> dict:
    value = read_optional(Path(root) / FILE)
    if not isinstance(value, dict) or not isinstance(value.get("media"), dict):
        return {"version": VERSION, "media": {}}
    return value


def _sha_for(root: Path, media: str) -> str | None:
    """A rendered file's bytes, from its own report when it has one."""
    if not media.startswith(("renders/", "previews/")):
        return None
    path = inside(root, media)
    report = read_optional(path.with_suffix(".json"))
    if isinstance(report, dict):
        expected = report.get("final_output_sha256") or report.get("output_sha256")
        if isinstance(expected, str):
            return expected
    return file_hash(path) if path.is_file() else None


def _total_for(root: Path, media: str) -> int | None:
    if not media.startswith(("renders/", "previews/")):
        return None
    report = read_optional(inside(root, media).with_suffix(".json"))
    if isinstance(report, dict):
        frames = (report.get("video") or {}).get("frames")
        fps = (report.get("video") or {}).get("fps") or 24
        if isinstance(frames, int) and frames > 0:
            return max(1, round(frames / float(fps)))
    return None


@state_mutation
def record(root: Path, media: str, seconds: list, *, sha256: str | None = None, total: int | None = None) -> dict:  # fmt: skip
    """Union these heard seconds into the record. Other bytes under the same name start over."""
    root = Path(root)
    if not isinstance(media, str) or not media.strip() or ".." in media or media.startswith("/"):
        raise ValueError("name the media that played")
    if not isinstance(seconds, list) or len(seconds) > MAX_BATCH:
        raise ValueError("seconds is a short list of whole numbers")
    heard = set()
    for value in seconds:
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise ValueError("seconds is a short list of whole numbers")
        heard.add(value)
    expected = _sha_for(root, media) or sha256
    length = _total_for(root, media) or total
    value = read(root)
    entry = value["media"].get(media)
    if not isinstance(entry, dict) or (expected and entry.get("sha256") not in (None, expected)):
        entry = {"sha256": expected, "seconds": [], "total": length}
    if expected and not entry.get("sha256"):
        entry["sha256"] = expected
    if length:
        entry["total"] = length
    entry["seconds"] = sorted(set(entry.get("seconds", [])) | heard)
    value["media"][media] = entry
    write_json(root / FILE, value)
    return coverage(root, media, total=length)


def coverage(root: Path, media: str, *, total: int | None = None, sha256: str | None = None) -> dict:  # fmt: skip
    """How much of this media was heard: seconds, the total, their share and the verdict."""
    root = Path(root)
    entry = read(root)["media"].get(media) or {}
    expected = sha256 or _sha_for(root, media)
    if expected and entry.get("sha256") not in (None, expected):
        entry = {}
    length = total or entry.get("total") or _total_for(root, media) or 0
    heard = [s for s in entry.get("seconds", []) if length == 0 or s < length]
    share = min(1.0, len(heard) / length) if length else 0.0
    return {
        "media": media,
        "heard": len(heard),
        "total": length,
        "share": round(share, 4),
        "watched": bool(length) and share >= HEARD_SHARE,
    }


def final_heard(root: Path, film: Path) -> dict:
    """Coverage of one rendered final, by its name under ``renders/``."""
    return coverage(root, f"renders/{Path(film).name}")
