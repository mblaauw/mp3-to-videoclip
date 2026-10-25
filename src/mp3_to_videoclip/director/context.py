"""Build the per-turn project context for the director."""

from __future__ import annotations

from pathlib import Path


def build_context(slug: str, projects_dir: Path | None = None) -> str:
    """Compact project snapshot for the director's system prompt."""
    root = (projects_dir or Path("projects")) / slug
    if not root.is_dir():
        return f"Project {slug} not found."
    try:
        from mp3_to_videoclip import production as P

        project = P.load_project(root)
        status = P.status(root)
        lines = [
            f"Project: {project.title} ({project.slug})",
            f"Duration: {project.duration:.1f}s, {project.total_frames} frames at {project.fps}fps",
            f"Music mode: {project.music_mode}",
            f"Status: {status}",
        ]
        return "\n".join(lines)
    except Exception as exc:  # noqa: BLE001
        return f"Project {slug}: {exc}"
