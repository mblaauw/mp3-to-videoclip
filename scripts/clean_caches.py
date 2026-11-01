#!/usr/bin/env python3
"""Show, and only with --yes remove, render caches the app can rebuild.

Dry by default, and only the owner runs it for real. It removes nothing but the folders on
the one list in ``caches.py``, which the Settings panel uses too. Stills, source audio,
renders, voice takes, approvals and the journal are never touched.

    uv run python scripts/clean_caches.py
    uv run python scripts/clean_caches.py --yes
"""

from __future__ import annotations

import argparse
import shutil
from pathlib import Path

from mp3_to_videoclip import caches


def find_caches(projects: Path) -> list[tuple[Path, int]]:
    return sorted(
        found for cache in caches.PRODUCTION_CACHES for found in caches.find(projects, cache)
    )


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
