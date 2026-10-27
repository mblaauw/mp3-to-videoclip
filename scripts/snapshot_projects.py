#!/usr/bin/env python3
"""Snapshot production metadata into backups/ before a migration.

The live productions under ``projects/`` are gitignored, so the repository tag
protects code only. This script is the rollback for real work: it copies the
JSON/JSONL/Markdown metadata (briefs, storyboards, asset manifests, approvals, budget,
chat logs) into one timestamped zip and records a sha256 per captured file, so a
later snapshot can be diffed byte for byte.

It never writes inside a production, never copies the song, stills, previews or
renders, and never touches a paid task journal's meaning — ``work/tasks.json`` is
captured as text like any other metadata.
"""

from __future__ import annotations

import argparse
import errno
import hashlib
import json
import os
import stat
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

# Metadata only. Media, stills, previews and renders are excluded by suffix and
# by directory, so an accidental ``assets/notes.json`` still cannot pull binaries in.
METADATA_SUFFIXES = frozenset({".json", ".jsonl", ".md", ".txt", ".toml", ".yaml", ".yml"})
BINARY_DIRS = frozenset({"assets", "media", "previews", "renders", "psd", "layers"})
SECRET_NAMES = frozenset({"secrets", "credentials"})
DIRECTORY_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW


def _identity(info: os.stat_result) -> tuple[int, ...]:
    # atime is deliberately absent: our reads may change it.
    return (
        info.st_dev,
        info.st_ino,
        info.st_mode,
        info.st_size,
        info.st_mtime_ns,
        info.st_ctime_ns,
    )


def _inventory(root: Path) -> dict[str, tuple[int, ...]]:
    """Inspect the entire tree without following links or reading binary payloads."""
    entries: dict[str, tuple[int, ...]] = {}

    def visit(fd: int, relative: str) -> None:
        before = _identity(os.fstat(fd))
        entries[relative] = before
        for name in sorted(os.listdir(fd)):
            child = f"{relative}/{name}" if relative else name
            info = os.stat(name, dir_fd=fd, follow_symlinks=False)
            if stat.S_ISDIR(info.st_mode):
                child_fd = os.open(name, DIRECTORY_FLAGS, dir_fd=fd)
                try:
                    if _identity(os.fstat(child_fd)) != _identity(info):
                        raise RuntimeError(f"snapshot source changed: {child}")
                    visit(child_fd, child)
                finally:
                    os.close(child_fd)
            elif stat.S_ISREG(info.st_mode):
                entries[child] = _identity(info)
            else:
                raise ValueError(f"snapshot refuses symlinks and special files: {child}")
        if _identity(os.fstat(fd)) != before:
            raise RuntimeError(f"snapshot directory changed: {relative or root}")

    fd = os.open(root, DIRECTORY_FLAGS)
    try:
        visit(fd, "")
    finally:
        os.close(fd)
    return entries


def _secret(relative: str) -> bool:
    parts = tuple(part.lower() for part in Path(relative).parts)
    return any(part.startswith((".env", ".secrets", ".credentials")) for part in parts) or any(
        part.split(".", 1)[0] in SECRET_NAMES for part in parts
    )


def _metadata(relative: str) -> bool:
    path = Path(relative)
    return (
        path.suffix.lower() in METADATA_SUFFIXES
        and not BINARY_DIRS.intersection(part.lower() for part in path.parts[:-1])
        and not _secret(relative)
    )


def _read_file(root: Path, relative: str, expected: tuple[int, ...]) -> bytes:
    """Open every path component without following a concurrently substituted link."""
    fd = os.open(root, DIRECTORY_FLAGS)
    try:
        parts = Path(relative).parts
        for part in parts[:-1]:
            child_fd = os.open(part, DIRECTORY_FLAGS, dir_fd=fd)
            os.close(fd)
            fd = child_fd
        file_fd = os.open(parts[-1], os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK, dir_fd=fd)
        with os.fdopen(file_fd, "rb") as handle:
            if _identity(os.fstat(handle.fileno())) != expected:
                raise RuntimeError(f"snapshot source changed: {relative}")
            payload = handle.read()
            if _identity(os.fstat(handle.fileno())) != expected:
                raise RuntimeError(f"snapshot source changed: {relative}")
            return payload
    finally:
        os.close(fd)


def _verify(root: Path, expected: dict[str, tuple[int, ...]]) -> None:
    if _inventory(root) != expected:
        raise RuntimeError("snapshot source changed during capture; retry when idle")


def _capture(root: Path, *, projects: bool = False) -> tuple[dict, dict[str, bytes], dict]:
    """Capture once, then validate identities, timestamps and directory membership.

    This is optimistic validation, not a filesystem transaction. Writers should
    be idle: any detected activity aborts rather than silently retrying a capture.
    """
    before = _inventory(root)
    productions = {
        name: {}
        for name, info in before.items()
        if name and "/" not in name and stat.S_ISDIR(info[2]) and not _secret(name)
    }
    payloads = {}
    hashes = {}
    for relative, info in before.items():
        if not stat.S_ISREG(info[2]):
            continue
        parts = Path(relative).parts
        metadata_path = "/".join(parts[1:]) if projects else relative
        if projects and (len(parts) < 2 or parts[0] not in productions):
            continue
        if not _metadata(metadata_path):
            continue
        payload = _read_file(root, relative, info)
        payloads[relative] = payload
        sha = hashlib.sha256(payload).hexdigest()
        if projects:
            productions[parts[0]][metadata_path] = sha
        else:
            hashes[relative] = sha
    _verify(root, before)
    return productions if projects else hashes, payloads, before


def digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            sha.update(block)
    return sha.hexdigest()


def collect(root: Path) -> dict[str, str]:
    """Relative path -> sha256 for every metadata file in one production."""
    files, _, _ = _capture(root)
    return files


def _fsync_directory(fd: int) -> None:
    """Persist publication where directory fsync is supported; surface real IO errors."""
    try:
        os.fsync(fd)
    except OSError as exc:
        if exc.errno not in {errno.EINVAL, errno.ENOTSUP, errno.EOPNOTSUPP}:
            raise


def snapshot(projects: Path, out: Path, *, now: datetime | None = None) -> dict:
    """Write one metadata zip plus an embedded manifest; return a summary.

    A second snapshot inside the same second keeps both archives: the collision
    suffix changes the filename, never the manifest's ``created_at``.
    """
    # Resolve once: callers may have passed a symlink that changes during capture.
    out = out.resolve()
    if out.is_relative_to(projects.resolve()):
        raise ValueError("snapshot destination must be outside the projects directory")
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    files, payloads, inventory = _capture(projects, projects=True)
    manifest: dict = {"created_at": stamp, "projects": files}
    out.mkdir(parents=True, exist_ok=True)
    directory_fd = os.open(out, DIRECTORY_FLAGS)
    directory_identity = os.fstat(directory_fd)
    temporary = None
    try:
        name = f".snapshot-{uuid4().hex}.tmp"
        fd = os.open(
            name,
            os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW,
            0o600,
            dir_fd=directory_fd,
        )
        temporary = name
        with os.fdopen(fd, "w+b") as handle:
            with zipfile.ZipFile(handle, "w", zipfile.ZIP_DEFLATED) as archive:
                for relative, payload in payloads.items():
                    archive.writestr(relative, payload)
                archive.writestr(
                    "manifest.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n"
                )
            handle.flush()
            os.fsync(handle.fileno())
            size = os.fstat(handle.fileno()).st_size
        suffix = 0
        while True:
            collision = f"-{suffix:02d}" if suffix else ""
            target = out / f"projects-metadata-{stamp}{collision}.zip"
            _verify(projects, inventory)
            current = out.stat(follow_symlinks=False)
            if (current.st_dev, current.st_ino) != (
                directory_identity.st_dev,
                directory_identity.st_ino,
            ):
                raise RuntimeError("snapshot output directory changed during capture")
            try:
                # A hard link publishes the complete, private (0600) file atomically.
                # Unlike rename/replace, it cannot overwrite an existing backup.
                os.link(
                    temporary,
                    target.name,
                    src_dir_fd=directory_fd,
                    dst_dir_fd=directory_fd,
                    follow_symlinks=False,
                )
                break
            except FileExistsError:
                suffix += 1
    finally:
        try:
            if temporary is not None:
                os.unlink(temporary, dir_fd=directory_fd)
            _fsync_directory(directory_fd)
        finally:
            os.close(directory_fd)
    return {
        "zip": str(target),
        "projects": len(manifest["projects"]),
        "files": sum(len(files) for files in manifest["projects"].values()),
        "bytes": size,
    }


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--projects", type=Path, default=root / "projects")
    parser.add_argument("--out", type=Path, default=root / "backups")
    parser.add_argument("--dry-run", action="store_true", help="report counts, write nothing")
    args = parser.parse_args(argv)
    if not args.projects.is_dir():
        parser.error(f"no projects directory at {args.projects}")
    if args.dry_run:
        files, _, _ = _capture(args.projects, projects=True)
        counts = {project: len(entries) for project, entries in files.items()}
        print(json.dumps({"projects": counts, "files": sum(counts.values())}, indent=2))
        return 0
    result = snapshot(args.projects, args.out)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
