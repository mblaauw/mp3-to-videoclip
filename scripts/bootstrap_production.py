"""Validate the production bundle and install the pinned external recipes.

The bundle is this project's own source: seven inline production agents in
``opencode.json``, the ten original ``clip-*`` skills and the root contract files.
Nothing about it is generated here — it ships in the repository and this command
only verifies that it is intact and consistent.

``--check`` is strictly read-only: it never clones, checks out, installs,
archives or touches the network. A normal run reuses the cached vendor checkout
(no network when it is already present), copies only the five selected recipes,
refuses to overwrite a locally adapted copy, and moves the two deselected motion
recipes out of active skill discovery byte for byte into
``backups/unused-motion-skills/`` (never edited, never deleted). A second normal
run changes nothing.
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ".opencode/vendor/runware-skills"
REVISION = "9dc1bfdbb6535393b8a60ac168642ffbd6278f73"
REPOSITORY = "https://github.com/runware/runware-skills.git"
SELECTED = (
    "runware-run",
    "runware-models",
    "runware-prompting",
    "photoreal-stills",
    "character-consistency",
)
# Deselected for this still-film project: motion recipes. They are archived out
# of active discovery, not installed and not deleted.
ARCHIVED = ("animate-image", "cinematic-video")
ARCHIVE = "backups/unused-motion-skills"
# The whole crew, in config order: the director plus six non-nesting specialists.
AGENTS = (
    "film-director",
    "music-editor",
    "short-film-writer",
    "visual-director",
    "visual-critic",
    "post-editor",
    "film-finisher",
)
STAGES = (
    "clip-music-analysis",
    "clip-story",
    "clip-storyboard",
    "clip-art-direction",
    "clip-image-prompts",
    "clip-image-production",
    "clip-visual-review",
    "clip-edit-graphics",
    "clip-delivery",
)
ORIGINAL_SKILLS = ("clip-music-director", *STAGES)
ROOT_FILES = ("LOOP.md", "AGENTS.md", "opencode.json")


def _bytes(directory: Path) -> dict[Path, bytes]:
    return {p.relative_to(directory): p.read_bytes() for p in directory.rglob("*") if p.is_file()}


def cached_revision(root: Path = ROOT) -> str | None:
    """Read the cached checkout revision without running git or touching the network."""
    head = root / VENDOR / ".git/HEAD"
    if not head.is_file():
        return None
    text = head.read_text().strip()
    if not text:
        return None
    if text.startswith("ref: "):
        ref = root / VENDOR / ".git" / text[5:]
        return ref.read_text().strip() if ref.is_file() else None
    return text


def _bundle_problems(root: Path = ROOT) -> list[str]:
    problems: list[str] = []
    for name in ROOT_FILES:
        if not (root / name).is_file():
            problems.append(f"missing root file {name}")
    config: dict = {}
    path = root / "opencode.json"
    if path.is_file():
        try:
            config = json.loads(path.read_text())
        except json.JSONDecodeError as error:
            problems.append(f"opencode.json is not valid JSON: {error}")
    instructions = config.get("instructions", [])
    if not isinstance(instructions, list) or "LOOP.md" not in instructions:
        problems.append('opencode.json must load "LOOP.md" via instructions')
    if config.get("default_agent") != "film-director":
        problems.append("opencode.json default_agent must be film-director")
    agents = config.get("agents")
    if not isinstance(agents, dict):
        problems.append("opencode.json needs an inline agents map")
        agents = {}
    for name in sorted(set(agents) - set(AGENTS)):
        problems.append(f"unknown inline agent {name}; the crew is exactly these seven roles")
    for name in AGENTS:
        entry = agents.get(name)
        if not isinstance(entry, dict):
            problems.append(f"missing inline agent {name}")
            continue
        for field in ("description", "mode", "system", "permissions"):
            if not entry.get(field):
                problems.append(f"inline agent {name} lacks {field}")
        expected = "primary" if name == "film-director" else "subagent"
        if entry.get("mode") != expected:
            problems.append(f"inline agent {name} mode must be {expected}")
    if (root / "agent").exists():
        problems.append("keep agents inline in opencode.json; .md agent overrides win silently")
    for name in ORIGINAL_SKILLS:
        skill = root / ".opencode/skills" / name / "SKILL.md"
        if not skill.is_file():
            problems.append(f"missing original skill {name}")
        elif f"name: {name}" not in skill.read_text():
            problems.append(f"skill {name} frontmatter does not declare its name")
    vendor = root / VENDOR / "skills"
    if vendor.is_dir():
        revision = cached_revision(root)
        if revision is None:
            problems.append("cached recipe checkout has no readable revision")
        elif revision != REVISION:
            problems.append(f"cached recipes are at {revision[:12]}, expected {REVISION[:12]}")
        for name in SELECTED:
            source = vendor / name
            if not source.is_dir():
                problems.append(f"cached recipe checkout lacks {name}")
                continue
            installed = root / ".opencode/skills" / name
            if installed.is_dir() and _bytes(source) != _bytes(installed):
                problems.append(f"installed recipe {name} is adapted; refusing to overwrite it")
    return problems


def report(root: Path = ROOT) -> dict:
    """Describe the local bundle without writing anything."""
    skills = root / ".opencode/skills"
    problems = _bundle_problems(root)
    revision = cached_revision(root)
    return {
        "agents": list(AGENTS),
        "original_skills": list(ORIGINAL_SKILLS),
        "cached_revision": revision,
        "recipes_available": (root / VENDOR / "skills").is_dir(),
        "recipes_missing": [n for n in SELECTED if not (skills / n).is_dir()],
        "pending_archive": [n for n in ARCHIVED if (skills / n).is_dir()],
        "problems": problems,
        "ok": not problems,
    }


def ensure_cached_recipes(root: Path = ROOT) -> None:
    """Clone or detach the pinned checkout. Only reached from a normal run."""
    target = root / VENDOR
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "clone", "--no-checkout", REPOSITORY, str(target)], check=True)
    current = subprocess.run(
        ["git", "-C", str(target), "status", "--porcelain"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    # A fresh --no-checkout clone has no HEAD worktree yet; reset only in that case.
    if current and (target / "skills").exists():
        raise SystemExit("External skills checkout has local changes; refusing to overwrite")
    subprocess.run(["git", "-C", str(target), "checkout", "--detach", REVISION], check=True)


def install_recipes(root: Path = ROOT) -> list[str]:
    """Copy the five selected pinned recipes that are not installed yet."""
    vendor = root / VENDOR / "skills"
    installed: list[str] = []
    for name in SELECTED:
        source, destination = vendor / name, root / ".opencode/skills" / name
        if not source.is_dir():
            raise SystemExit(f"Cached recipe {name} is missing; cached checkout is incomplete")
        if destination.exists():
            # Do not overwrite locally adapted recipes.
            if _bytes(source) != _bytes(destination):
                raise SystemExit(f"Installed recipe {name} differs; refusing to overwrite")
            continue
        shutil.copytree(source, destination)
        installed.append(name)
    return installed


def archive_motion_skills(root: Path = ROOT) -> list[str]:
    """Move deselected motion recipes out of active discovery, byte for byte.

    An existing archive directory is never merged or overwritten: a partial earlier
    archive must be inspected by hand.
    """
    moved: list[str] = []
    for name in ARCHIVED:
        source = root / ".opencode/skills" / name
        if not source.is_dir():
            continue
        destination = root / ARCHIVE / name
        if destination.exists():
            raise SystemExit(f"Archive {destination} already exists; refusing to overwrite")
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(source), str(destination))
        moved.append(str(destination.relative_to(root)))
    return moved


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check",
        action="store_true",
        help="Validate the local bundle only; no clone, checkout, install, archive or network",
    )
    args = parser.parse_args(argv)
    if args.check:
        result = report()
        print(json.dumps(result, indent=2))
        return 0 if result["ok"] else 1
    before = report()
    if not before["ok"]:
        print(json.dumps(before, indent=2))
        return 1
    ensure_cached_recipes()
    installed = install_recipes()
    archived = archive_motion_skills()
    result = report() | {"installed": installed, "archived": archived}
    print(json.dumps(result, indent=2))
    print(
        "Pinned recipes only. No upstream scripts were executed and no global "
        "configuration was changed."
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
