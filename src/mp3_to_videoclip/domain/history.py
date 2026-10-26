"""Artifact history: one previous value per write, restorable by the Studio.

Snapshots are content-addressed JSON files beside the live artifact. Restoring
walks backwards: the live value is excluded, so repeated Undo reaches older
snapshots instead of toggling. Validation happens before anything is written; a
snapshot can never put an invalid artifact or an edit that disagrees with the
storyboard back on disk.
"""

from __future__ import annotations

from pathlib import Path

from mp3_to_videoclip.storage import digest, read_json, write_json

ARTIFACTS: dict[str, tuple[str, str]] = {
    "brief": ("brief.json", "work/brief-history"),
    "storyboard": ("work/storyboard.json", "work/storyboard-history"),
    "edit": ("work/edit.json", "work/edit-history"),
    "lyrics": ("work/lyrics.json", "work/lyrics-history"),
    "treatments": ("work/treatments.json", "work/treatments-history"),
}


def _paths(root: Path, artifact: str) -> tuple[Path, Path]:
    try:
        relative, directory = ARTIFACTS[artifact]
    except KeyError as exc:
        raise ValueError("history is kept for " + ", ".join(sorted(ARTIFACTS))) from exc
    return root / relative, root / directory


def snapshot(root: Path, artifact: str, value=None) -> str | None:
    """Record the current (or supplied) artifact without touching it."""
    live, directory = _paths(root, artifact)
    if value is None:
        if not live.is_file():
            return None
        value = read_json(live)
    directory.mkdir(parents=True, exist_ok=True)
    token = digest(value)
    target = directory / f"{token}.json"
    if not target.exists():
        write_json(target, value)
    return token


def snapshots(root: Path, artifact: str) -> list[dict]:
    """Newest first; timestamps come from the snapshot file's mtime."""
    _, directory = _paths(root, artifact)
    if not directory.is_dir():
        return []
    rows = []
    for path in directory.glob("*.json"):
        try:
            rows.append(
                {
                    "hash": path.stem,
                    "at": path.stat().st_mtime,
                    "bytes": path.stat().st_size,
                }
            )
        except OSError:
            continue
    rows.sort(key=lambda row: row["at"], reverse=True)
    return rows


def _validate(root: Path, artifact: str, value) -> None:
    from mp3_to_videoclip import edits
    from mp3_to_videoclip import production as P
    from mp3_to_videoclip.models import (
        Brief,
        EditDecisionList,
        Lyrics,
        Storyboard,
        Treatments,
    )

    if artifact == "brief":
        Brief.model_validate(value)
        return
    if artifact == "storyboard":
        board = Storyboard.model_validate(value)
        P.validate_board(root, board, verify_source=False)
        edit = edits.load_edit(root, board=board)
        if edit is not None:
            edit.check_board(board)
        return
    if artifact == "edit":
        edit = EditDecisionList.model_validate(value)
        edit.check_board(P.load_board(root))
        return
    if artifact == "lyrics":
        Lyrics.model_validate(value)
        return
    if artifact == "treatments":
        Treatments.model_validate(value)
        return
    raise ValueError("unknown history artifact")


def restore(root: Path, artifact: str) -> dict:
    """Restore the newest snapshot that differs from the live value."""
    live, _ = _paths(root, artifact)
    if not live.is_file():
        raise ValueError(f"there is no {artifact} to restore")
    current = read_json(live)
    current_hash = digest(current)
    candidates = [row for row in snapshots(root, artifact) if row["hash"] != current_hash]
    for row in candidates:
        target = root / ARTIFACTS[artifact][1] / f"{row['hash']}.json"
        try:
            value = read_json(target)
            _validate(root, artifact, value)
        except (OSError, ValueError):
            continue
        write_json(live, value)
        from mp3_to_videoclip import promptlog

        promptlog.record(root, artifact)
        return {
            "artifact": artifact,
            "restored": row["hash"],
            "previous": current_hash,
        }
    raise ValueError(f"there is no older {artifact} version to restore")
