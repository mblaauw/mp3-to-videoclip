"""Private local archives; no cloud, keys or Git staging."""

import os
import tarfile
import tempfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from .storage import file_hash


def backup_project(root: Path, directory: Path) -> dict:
    root, directory = root.resolve(), directory.resolve()
    if directory.is_relative_to(root):
        raise ValueError("backup destination must be outside the production folder")
    files = []
    for path in sorted(root.rglob("*")):
        relative = path.relative_to(root)
        if path.is_symlink():
            raise ValueError("backup refuses symlinks; use project-local reference copies")
        if (
            not path.is_file()
            or path.name in (".lock", ".DS_Store")
            or any(part.startswith((".env", ".secrets")) for part in relative.parts)
        ):
            continue
        if relative.parts[:2] in (("work", "plates"), ("work", "preview")):
            continue
        files.append(path)
    directory.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    output = directory / f"{root.name}-{stamp}-{uuid4().hex[:8]}.tar.gz"
    fd, name = tempfile.mkstemp(prefix=".backup-", suffix=".tar.gz", dir=directory)
    os.close(fd)  # mkstemp is mode 0600; publication preserves that private mode.
    temporary = Path(name)
    try:
        with tarfile.open(temporary, "w:gz") as archive:
            for path in files:
                archive.add(
                    path, arcname=str(Path(root.name) / path.relative_to(root)), recursive=False
                )
        os.link(temporary, output)
    finally:
        temporary.unlink(missing_ok=True)
    return {
        "backup": str(output),
        "sha256": file_hash(output),
        "files": len(files),
        "warning": "Private archive includes audio, images, provider URLs and results. Keep local/secure; never commit it.",
    }
