"""Local derivative registration: a new immutable version plus its provenance.

A crop, mirror or tone adjustment made outside the paid generator produces a new
artifact. It must be recorded like any other version, must keep its original, and
must still be inspected before acceptance.

``adopt_derivative`` records the version and a provenance receipt. It
deliberately does **not** select, review, approve or normalise anything: the new
bytes need their own verdict, and selection is a separate decision.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

from . import production as P
from .storage import digest, file_hash, inside, read_json, write_json

RECEIPTS = "work/derivations"


def adopt_derivative(
    root: Path,
    shot_id: str,
    source: Path,
    *,
    operation: str,
    note: str,
    permission_confirmed: bool = False,
    from_version: int | None = None,
) -> dict:
    """Register ``source`` as the next immutable version of ``shot_id``.

    ``permission_confirmed`` attests that the source bytes are owned or
    authorized for this production; it is required because adopting an arbitrary
    downloaded image would bypass the reference/provider provenance rules.
    """
    root = Path(root)
    if permission_confirmed is not True:
        raise ValueError("adopt needs --permission-confirmed for the source bytes")
    if not str(operation).strip():
        raise ValueError("adopt needs --operation describing what was changed")
    if not str(note).strip():
        raise ValueError("adopt needs --note recording why this derivative exists")
    source = Path(source).resolve(strict=True)
    if not source.is_file():
        raise ValueError("adopt source is not a file")

    board = P.load_board(root)
    shot = next((s for s in board.shots if s.id == shot_id), None)
    if shot is None:
        raise ValueError(f"unknown shot ID {shot_id!r}")
    if shot.asset_shot_id is not None:
        raise ValueError(
            f"{shot.id} is an editorial reprise of {shot.asset_shot_id}; "
            f"adopt the version on {shot.asset_shot_id} instead"
        )

    with Image.open(source) as image:
        image.load()
        size = [image.width, image.height]

    sha = file_hash(source)
    assets = read_json(root / "work/assets.json")
    versions = [v["version"] for v in assets.get(shot.id, {}).get("versions", [])]
    version = 1 + max(versions, default=0)
    if from_version is not None and from_version not in versions:
        raise ValueError(f"shot {shot.id} has no version {from_version} to derive from")
    recorded = next(
        (
            v
            for v in assets.get(shot.id, {}).get("versions", [])
            if v.get("task_id") == f"local:{sha}"
        ),
        None,
    )
    if recorded is not None:
        raise ValueError(
            f"these exact bytes are already recorded as {shot.id} v{recorded['version']:03d}; "
            "inspect or review that version instead of registering a duplicate"
        )

    suffix = source.suffix.lower() if source.suffix.lower() in (".png", ".jpg", ".jpeg") else ".png"
    relative = f"assets/{shot.id}/v{version:03d}-local-{sha[:8]}{suffix}"
    target = inside(root, relative)
    if target.exists():
        raise ValueError(f"that derivative is already recorded at {relative}")

    input_hash = digest(P.image_spec(root, shot))

    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(source.read_bytes())
    if file_hash(target) != sha:
        raise ValueError("adopted bytes changed during the copy; inspect the source")

    P.record_asset(root, shot.id, version, target, input_hash, f"local:{sha}")
    receipt = {
        "schema_version": 1,
        "shot_id": shot.id,
        "version": version,
        "path": relative,
        "sha256": sha,
        "bytes": target.stat().st_size,
        "dimensions": size,
        "source": {"path": str(source), "sha256": sha},
        "from_version": from_version,
        "operation": str(operation),
        "note": str(note),
        "permission_confirmed": True,
        "image_input_hash": input_hash,
        "created_at": P.now(),
        "selected": False,
        "reviewed": False,
        "next_steps": [
            f"clip review PROJECT --shot {shot.id} --version {version} --verdict "
            "accept|reject|uncertain --reviewer ... --inspected --note 'actual inspection'",
            f"clip select PROJECT --shot {shot.id} --version {version}",
        ],
        "warning": (
            "Recording a version is not inspection. These bytes need their own verdict, and "
            "selection is a separate decision; the earlier version and the original stay intact."
        ),
    }
    write_json(root / RECEIPTS / f"{shot.id}-v{version:03d}.json", receipt)
    return receipt
