"""Atomic artifacts, content-bound approvals and single-writer project locks."""

import contextlib
import fcntl
import hashlib
import json
import os
import tempfile
from pathlib import Path


def read_json(path: Path):
    return json.loads(path.read_text())


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
