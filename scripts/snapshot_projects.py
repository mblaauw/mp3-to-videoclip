#!/usr/bin/env python3
"""Snapshot production metadata into backups/ before a migration.

The live productions under ``projects/`` are gitignored, so the repository tag
protects code only. This script is the rollback for real work: it copies the
JSON/Markdown metadata (briefs, storyboards, asset manifests, approvals, budget,
chat logs) into one timestamped zip and records a sha256 per captured file, so a
later snapshot can be diffed byte for byte.

It never writes inside a production, never copies the song, stills, previews or
renders, and never touches a paid task journal's meaning — ``work/tasks.json`` is
captured as text like any other metadata.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

# Metadata only. Media, stills, previews and renders are excluded by suffix and
# by directory, so an accidental ``assets/notes.json`` still cannot pull binaries in.
METADATA_SUFFIXES = frozenset({".json", ".md", ".txt", ".toml", ".yaml", ".yml"})
BINARY_DIRS = frozenset({"assets", "media", "previews", "renders", "psd", "layers"})


def digest(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            sha.update(block)
    return sha.hexdigest()


def collect(root: Path) -> dict[str, str]:
    """Relative path -> sha256 for every metadata file in one production."""
    files: dict[str, str] = {}
    for path in sorted(root.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in METADATA_SUFFIXES:
            continue
        relative = path.relative_to(root)
        if BINARY_DIRS & set(relative.parts[:-1]):
            continue
        files[relative.as_posix()] = digest(path)
    return files


def snapshot(projects: Path, out: Path, *, now: datetime | None = None) -> dict:
    """Write one metadata zip plus an embedded manifest; return a summary.

    A second snapshot inside the same second keeps both archives: the collision
    suffix changes the filename, never the manifest's ``created_at``.
    """
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%dT%H%M%SZ")
    out.mkdir(parents=True, exist_ok=True)
    target = out / f"projects-metadata-{stamp}.zip"
    suffix = 1
    while target.exists():
        target = out / f"projects-metadata-{stamp}-{suffix:02d}.zip"
        suffix += 1
    manifest: dict = {"created_at": stamp, "projects": {}}
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
        for project in sorted(p for p in projects.iterdir() if p.is_dir()):
            files = collect(project)
            manifest["projects"][project.name] = files
            for relative in files:
                archive.write(project / relative, f"{project.name}/{relative}")
        archive.writestr("manifest.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")
    return {
        "zip": str(target),
        "projects": len(manifest["projects"]),
        "files": sum(len(files) for files in manifest["projects"].values()),
        "bytes": target.stat().st_size,
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
        counts = {
            project.name: len(collect(project))
            for project in sorted(p for p in args.projects.iterdir() if p.is_dir())
        }
        print(json.dumps({"projects": counts, "files": sum(counts.values())}, indent=2))
        return 0
    result = snapshot(args.projects, args.out)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
