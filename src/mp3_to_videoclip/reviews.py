"""Human/agent visual judgements bound to exact generated versions and bytes."""

from pathlib import Path

from .storage import digest, file_hash, inside, read_json, snapshot_read, state_mutation, write_json

REVIEWS = "work/reviews.json"


@snapshot_read(private=True)
def _shot_assets(root):
    """Borrowed operation-private index; callers must not mutate its contents."""
    from . import production as P

    return {shot.id: shot for shot in P.load_board(root).shots}, read_json(
        root / "work/assets.json"
    )


@snapshot_read(private=True)
def _review_index(root):
    path = root / REVIEWS
    history = read_json(path) if path.exists() else []
    return {
        tuple(record.get(key) for key in ("shot_id", "version", "sha256", "input_hash")): record
        for record in history
    }


def _version(root, shot_id, version):
    from . import shotkinds

    by_id, assets = _shot_assets(root)
    shot = by_id.get(shot_id)
    if shot is None:
        raise ValueError("unknown review shot")
    if shotkinds.is_local(shot) and shot.asset_shot_id is None:
        raise ValueError(
            f"{shot.kind} shot {shot.id} is rendered locally; there is no image to review"
        )
    owner = shot.asset_shot_id or shot.id
    entry = assets.get(owner, {})
    number = entry.get("selected") if version is None else version
    chosen = next((v for v in entry.get("versions", []) if v["version"] == number), None)
    if not chosen or file_hash(inside(root, chosen["path"])) != chosen["sha256"]:
        raise ValueError("review needs an intact image version")
    return shot, owner, chosen


@state_mutation
def record_review(
    root: Path,
    shot_id: str,
    version: int,
    verdict: str,
    *,
    note: str | None = None,
    reviewer: str,
    inspected=False,
):
    from . import production as P

    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise ValueError("review version must be a positive integer")

    if verdict not in ("accept", "reject", "uncertain"):
        raise ValueError("review verdict must be accept, reject or uncertain")
    note = (note or "").strip() or None
    if (note is not None and len(note) > 2000) or not reviewer.strip() or inspected is not True:
        raise ValueError("review needs an inspection acknowledgement, reviewer and a valid note")
    shot, owner, chosen = _version(root, shot_id, version)
    if verdict == "accept" and chosen["input_hash"] != digest(P.image_spec(root, shot)):
        raise ValueError("cannot accept an image generated from stale inputs")
    record = {
        "shot_id": owner,
        "version": chosen["version"],
        "sha256": chosen["sha256"],
        "input_hash": chosen["input_hash"],
        "verdict": verdict,
        "note": note,
        "reviewer": reviewer,
        "inspected": True,
        "at": P.now(),
    }
    path = root / REVIEWS
    history = read_json(path) if path.exists() else []
    history.append(record)
    write_json(path, history)
    return record


@snapshot_read
def verdict_for(root: Path, shot_id: str, version=None):
    shot, owner, chosen = _version(root, shot_id, version)
    return _review_index(root).get(
        (owner, chosen.get("version"), chosen.get("sha256"), chosen.get("input_hash"))
    )


def require_accepted(root: Path, shot_ids):
    from . import production as P
    from . import shotkinds

    board = P.load_board(root)
    by_id = {shot.id: shot for shot in board.shots}
    for sid in shot_ids:
        shot = by_id.get(sid)
        if shot is None:
            raise ValueError(f"unknown review shot {sid}")
        if shotkinds.is_local(shot):
            continue
        _, _, chosen = _version(root, sid, None)
        verdict = verdict_for(root, sid)
        if (
            chosen["input_hash"] != digest(P.image_spec(root, shot))
            or not verdict
            or verdict.get("verdict") != "accept"
            or verdict.get("inspected") is not True
        ):
            raise ValueError(
                f"shot {sid} needs an accepted review of the selected current image bytes"
            )
