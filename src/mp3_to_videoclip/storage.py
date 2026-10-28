"""Atomic artifacts, content-bound approvals and single-writer project locks."""

import contextlib
import copy
import errno
import fcntl
import functools
import hashlib
import json
import os
import tempfile
import threading
import time
from contextvars import ContextVar
from pathlib import Path

_READ_SNAPSHOT: ContextVar[dict | None] = ContextVar("read_snapshot", default=None)


def _read_cache():
    snapshot = _READ_SNAPSHOT.get()
    if snapshot and snapshot["thread"] == threading.get_ident() and snapshot["enabled"]:
        return snapshot["values"]
    return None


def _retire_read_snapshot():
    snapshot = _READ_SNAPSHOT.get()
    while snapshot and snapshot["thread"] == threading.get_ident():
        snapshot["enabled"] = False
        snapshot["values"].clear()
        snapshot = snapshot.get("parent")


@contextlib.contextmanager
def read_snapshot(root: Path):
    """One coherent, synchronous read calculation; never wrap IO/network jobs.

    Values are private to this operation and thread, not a cross-request cache.
    A writer boundary permanently retires them, even if the write fails.
    Nested distinct roots must be acquired in sorted resolved-path order.
    """
    root = Path(root).resolve()
    current = _READ_SNAPSHOT.get()
    if _read_cache() is not None and current["root"] == root:
        yield
        return
    # Cross-root nesting is supported in a deterministic order, preventing two
    # readers from taking A/B and B/A locks. Reentrant ancestor roots are safe.
    ancestors = []
    parent = current
    while parent and parent["thread"] == threading.get_ident():
        if parent["active"]:
            ancestors.append(parent["root"])
        parent = parent.get("parent")
    if ancestors and root not in ancestors and str(root) < max(map(str, ancestors)):
        raise RuntimeError("nested read snapshots must acquire roots in sorted path order")
    with state_lock(root):
        snapshot = {
            "root": root,
            "thread": threading.get_ident(),
            "enabled": True,
            "active": True,
            "values": {},
            "parent": current,
        }
        token = _READ_SNAPSHOT.set(snapshot)
        try:
            yield
        finally:
            snapshot["active"] = False
            snapshot["enabled"] = False
            snapshot["values"].clear()
            _READ_SNAPSHOT.reset(token)


def snapshot_read(function=None, *, private=False):
    """Memoize reads in scope; only private, read-only indexes may borrow values.

    Public readers always return defensive copies. ``private=True`` is reserved
    for internal indexes whose contents must never be mutated or returned.
    """
    import inspect

    if function is None:
        return functools.partial(snapshot_read, private=private)
    signature = inspect.signature(function)

    @functools.wraps(function)
    def cached(*args, **kwargs):
        cache = _read_cache()
        if cache is None:
            return function(*args, **kwargs)
        bound = signature.bind(*args, **kwargs)
        bound.apply_defaults()

        def key_value(value):
            if isinstance(value, Path):
                return str(value.resolve())
            if hasattr(value, "model_dump"):
                return value.model_dump()
            return value

        key = (function, digest({k: key_value(v) for k, v in bound.arguments.items()}))
        if key not in cache:
            try:
                cache[key] = (True, function(*args, **kwargs))
            except (OSError, ValueError) as exc:
                cache[key] = (False, copy.copy(exc))
                raise
        succeeded, value = cache[key]
        if not succeeded:
            raise copy.copy(value)
        return value if private else copy.deepcopy(value)

    return cached


@snapshot_read
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


@snapshot_read
def file_hash(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def sync_directory(directory: Path) -> None:
    """Persist a published directory entry, not just its temporary file's bytes.

    Some POSIX filesystems do not support directory fsync. Only those explicit
    unsupported errors are tolerated; IO errors must fail before paid submission.
    """
    fd = os.open(directory, os.O_RDONLY | os.O_DIRECTORY)
    try:
        try:
            os.fsync(fd)
        except OSError as exc:
            if exc.errno not in (errno.EINVAL, errno.ENOTSUP):
                raise
    finally:
        os.close(fd)


def write_json(path: Path, value):
    _retire_read_snapshot()
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, indent=2, allow_nan=False) + "\n"
    fd, name = tempfile.mkstemp(prefix=".write-", dir=path.parent)
    try:
        with os.fdopen(fd, "w") as f:
            f.write(data)
            f.flush()
            os.fsync(f.fileno())
        os.replace(name, path)
        sync_directory(path.parent)
    finally:
        Path(name).unlink(missing_ok=True)


def inside(root: Path, relative: str) -> Path:
    p = (root / relative).resolve()
    if Path(relative).is_absolute() or not p.is_relative_to(root.resolve()):
        raise ValueError("artifact path must remain inside the project")
    return p


class ProjectBusy(ValueError):
    """Another writer (a paid batch, a render, the CLI) holds the project lock.

    A ``ValueError`` so every existing caller keeps its behaviour; the Studio
    maps it to a 409 ``project_busy`` so the browser can say "try again when the
    job finishes" instead of reporting a broken request.
    """


class RevisionConflict(ValueError):
    """The caller's version is no longer the document being edited."""


_STATE_LOCKS: dict[tuple[int, str], threading.RLock] = {}
_STATE_GUARD = threading.Lock()
_STATE_LOCAL = threading.local()


@contextlib.contextmanager
def state_lock(root: Path, *, timeout: float = 5):
    """Short, reentrant thread/process transaction; never surround network work.

    Lock order is operation ``.lock`` first, then ``.state.lock``. State-only
    editors can run between paid submissions/downloads. Never acquire an
    operation lock from inside a state transaction. Nesting is local to a thread
    and process, not a ContextVar copied into another worker.
    """
    key = (os.getpid(), str(Path(root).resolve()))
    with _STATE_GUARD:
        lock = _STATE_LOCKS.setdefault(key, threading.RLock())
    if not lock.acquire(timeout=timeout):
        raise ProjectBusy("another writer is updating this project's state")
    held = getattr(_STATE_LOCAL, "held", set())
    _STATE_LOCAL.held = held
    try:
        if key in held:
            yield
            return
        with (Path(root) / ".state.lock").open("a") as handle:
            deadline = time.monotonic() + timeout
            while True:
                try:
                    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError as exc:
                    if time.monotonic() >= deadline:
                        raise ProjectBusy(
                            "another writer is updating this project's state"
                        ) from exc
                    time.sleep(0.01)
            held.add(key)
            try:
                yield
            finally:
                held.remove(key)
                fcntl.flock(handle, fcntl.LOCK_UN)
    finally:
        lock.release()


def state_mutation(function):
    """Coordinate an engine mutation whose first argument is its project root."""

    @functools.wraps(function)
    def locked(root, *args, **kwargs):
        _retire_read_snapshot()
        with state_lock(root):
            return function(root, *args, **kwargs)

    return locked


def require_revision(path: Path, expected: str | None, *, value=None) -> None:
    """Call within state_lock; optional for legacy CLI/tool compatibility."""
    if expected is not None and digest(
        read_json(path) if value is None else value
    ) != expected.strip('"'):
        raise RevisionConflict("This document changed. Reload it before saving your edits.")


@contextlib.contextmanager
def project_lock(root: Path):
    key = (os.getpid(), str(Path(root).resolve()))
    if key in getattr(_STATE_LOCAL, "held", set()):
        raise RuntimeError("operation locks must be acquired before state locks")
    with (root / ".lock").open("a") as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as e:
            raise ProjectBusy("another command is writing this project") from e
        try:
            yield
        finally:
            fcntl.flock(f, fcntl.LOCK_UN)
