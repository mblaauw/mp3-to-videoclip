"""Only the CLI may reach the old compositor. The Studio's layers never import it."""

from __future__ import annotations

import ast
from pathlib import Path

import mp3_to_videoclip

PACKAGE = Path(mp3_to_videoclip.__file__).parent
STUDIO = ("api", "services", "director", "jobs")


def _imports_legacy(path: Path) -> bool:
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.ImportFrom) and "legacy" in (node.module or ""):
            return True
        if isinstance(node, ast.Import) and any("legacy" in item.name for item in node.names):
            return True
    return False


def test_no_studio_layer_imports_the_compositor():
    offenders = [
        str(path.relative_to(PACKAGE))
        for layer in STUDIO
        for path in (PACKAGE / layer).rglob("*.py")
        if _imports_legacy(path)
    ]
    assert offenders == []


def test_the_renderer_and_the_old_renderer_stay_gone():
    assert not (PACKAGE / "render.py").exists()
    assert not (PACKAGE / "preview.py").exists()
