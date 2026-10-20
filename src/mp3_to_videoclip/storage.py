"""Atomic artifacts, content-bound approvals and single-writer project locks."""

import contextlib
import fcntl
import hashlib
import json
import os
import re
import tempfile
from pathlib import Path


def read_json(path: Path):
    return json.loads(path.read_text())


def read_optional(path: Path, default=None):
    """Read a JSON file if it exists; a missing, unreadable or corrupt file yields ``default``.

    Views use this so one damaged artifact degrades a panel instead of killing the
    page. Writers keep using ``read_json`` so corruption during a mutation fails
    loudly rather than silently overwriting a file that could not be parsed.
    """
    path = Path(path)
    if not path.is_file():
        return default
    try:
        return read_json(path)
    except (OSError, ValueError):
        return default


def digest(value) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def write_json(path: Path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, indent=2, allow_nan=False) + "\n"
    fd, name = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
    finally:
        Path(name).unlink(missing_ok=True)


def inside(root: Path, relative: str) -> Path:
    p = (root / relative).resolve()
    if Path(relative).is_absolute() or not p.is_relative_to(root.resolve()):
        raise ValueError("artifact path must remain inside the project")
    return p


@contextlib.contextmanager
def project_lock(root: Path):
    with (root / ".lock").open("a") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as e:
            raise ValueError("another command is writing this project") from e
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)


def write_versioned_page(
    directory: Path, prefix: str, name: str | None, text: str, label: str
) -> Path:
    """Write one generated page under a safe basename; never overwrite a page.

    ``label`` names the page kind in error messages (intake, studio). Without an
    explicit ``name`` the next ``prefix-vNNN.html`` is used.
    """
    directory = Path(directory).resolve()
    directory.mkdir(parents=True, exist_ok=True)
    if name:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]*\.html", name):
            raise ValueError(f"{label} name must be a safe lowercase .html basename")
        target = directory / name
        if target.exists():
            raise ValueError(f"{target.name} already exists; {label} pages are never overwritten")
    else:
        version = 1
        while (directory / f"{prefix}-v{version:03d}.html").exists():
            version += 1
        target = directory / f"{prefix}-v{version:03d}.html"
    target.write_text(text, encoding="utf-8")
    return target
