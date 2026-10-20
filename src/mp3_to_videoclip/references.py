"""Permission-gated, immutable local reference imports. Never edits a brief."""

import hashlib
import io
import os
import tempfile
from pathlib import Path

from PIL import Image

from .storage import digest, file_hash, inside, read_json, write_json

LIBRARY = "work/reference-library.json"


def import_reference(root: Path, source: Path, *, note: str, permission_confirmed=False, box=None):
    if permission_confirmed is not True or not note.strip():
        raise ValueError("reference import needs explicit permission and a provenance note")
    source = source.resolve(strict=True)
    original = source.read_bytes()
    original_hash = hashlib.sha256(original).hexdigest()
    with Image.open(io.BytesIO(original)) as image:
        image.load()
        if box is not None:
            if (
                len(box) != 4
                or any(isinstance(v, bool) or not isinstance(v, int) for v in box)
                or not 0 <= box[0] < box[2] <= image.width
                or not 0 <= box[1] < box[3] <= image.height
            ):
                raise ValueError("crop must be four integer pixel bounds inside the source")
            image = image.crop(tuple(box))
        data = io.BytesIO()
        image.convert("RGB").save(data, format="PNG")
        size = list(image.size)
    payload = data.getvalue()
    sha = hashlib.sha256(payload).hexdigest()
    relative = f"media/references/{sha}.png"
    target = inside(root, relative)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if file_hash(target) != sha:
            raise ValueError(
                "immutable reference bytes changed; restore the original, do not overwrite"
            )
    else:
        fd, name = tempfile.mkstemp(prefix=".reference-", dir=target.parent)
        try:
            with os.fdopen(fd, "wb") as handle:
                handle.write(payload)
                handle.flush()
                os.fsync(handle.fileno())
            os.link(name, target)
        finally:
            Path(name).unlink(missing_ok=True)
    path = root / LIBRARY
    library = read_json(path) if path.exists() else {}
    provenance = {
        "source": str(source),
        "source_sha256": original_hash,
        "crop_box_px": list(box) if box is not None else None,
        "note": note,
    }
    entry = library.setdefault(
        sha,
        {
            "path": relative,
            "sha256": sha,
            "size": size,
            "permission_confirmed": True,
            "origins": [],
        },
    )
    if digest(provenance) not in {digest(item) for item in entry["origins"]}:
        entry["origins"].append(provenance)
    write_json(path, library)
    return entry


def validate_import(root: Path, relative: str):
    path = root / LIBRARY
    library = read_json(path) if path.exists() else {}
    actual = file_hash(inside(root, relative))
    entry = library.get(actual)
    if not entry or entry.get("path") != relative or not entry.get("permission_confirmed"):
        raise ValueError(
            f"reference {relative} needs a permission-confirmed immutable reference import"
        )
    return entry
