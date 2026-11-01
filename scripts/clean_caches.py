#!/usr/bin/env python3
"""Show, and only with --yes remove, render caches the app can rebuild.

Dry by default, and only the owner runs it for real. It removes nothing but two kinds of
folder: the old compositor's frame cache and finished render chunks. Stills, source audio,
renders, voice takes, approvals and the journal are never touched.

    uv run python scripts/clean_caches.py
    uv run python scripts/clean_caches.py --yes
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

CACHES = ("work/graphics/cache", "work/remotion-chunks")


def size_of(path: Path) -> int:
    return sum(item.stat().st_size for item in path.rglob("*") if item.is_file())


def find_caches(projects: Path) -> list[tuple[Path, int]]:
    found = []
    for root in sorted(item for item in projects.iterdir() if item.is_dir()):
        for relative in CACHES:
            path = root / relative
            if path.is_dir() and not path.is_symlink():
                found.append((path, size_of(path)))
    return found


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--projects", type=Path, default=Path("projects"))
    parser.add_argument("--yes", action="store_true", help="really remove them")
    args = parser.parse_args(argv)
    found = find_caches(args.projects)
    total = 0
    for path, size in found:
        total += size
        print(f"{size / 1e9:7.2f} GB  {path}")
        if args.yes:
            shutil.rmtree(path)
    print(f"{total / 1e9:7.2f} GB  {'removed' if args.yes else 'would be removed; pass --yes'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
