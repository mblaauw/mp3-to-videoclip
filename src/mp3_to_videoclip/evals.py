"""Repository invariants as a repeatable report — the start of the eval harness.

These are the rules that have actually been broken or nearly broken in this project:
an unclassified command, a write/spend tool leaking onto the agent surface, a page
that phones home, a loop document that sprawls, or a generated page whose sidecar no
longer matches its bytes. Each check is cheap, deterministic and reads only files.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from . import mcp, tools
from .storage import file_hash

# Headroom is deliberate: the loop document is edited as the crew evolves, and a
# limit pinned to its current length turns every legitimate addition into a trim.
MAX_LOOP_LINES = 140
EXTERNAL = ("http://", "https://", "<script src", "fetch(")


def _pages(root: Path) -> list[Path]:
    found = sorted((root / "studio").glob("*.html"))
    found += sorted((root / "projects").glob("*/work/dashboard/*.html"))
    found += sorted((root / "projects").glob("*/work/inspector/*.html"))
    return found


def check_command_registry() -> dict:
    missing = tools.unclassified()
    return {
        "name": "command-registry",
        "ok": not missing,
        "detail": f"unclassified: {missing}" if missing else "every parser command has a scope",
    }


def check_mcp_surface() -> dict:
    leaked = []
    aliases = {"plan_build": "plan"}
    for tool in mcp.TOOLS:
        command = aliases.get(tool["name"], tool["name"])
        kind = tools.scope_for(command)["kind"]
        if kind in {"spend", "human"}:
            leaked.append(f"{tool['name']}:{kind}")
    return {
        "name": "mcp-surface",
        "ok": not leaked,
        "detail": f"leaked: {leaked}" if leaked else "no spend or human tool is exposed over MCP",
    }


def check_pages_offline(pages=None, root: Path | None = None) -> dict:
    pages = _pages(root) if pages is None and root is not None else (pages or [])
    offending = []
    for page in pages:
        text = page.read_text(errors="ignore")
        hits = [token for token in EXTERNAL if token in text]
        if hits:
            offending.append(f"{page}: {hits}")
    return {
        "name": "pages-offline",
        "ok": not offending,
        "detail": "; ".join(offending)
        if offending
        else f"{len(pages)} page(s) have no external calls",
    }


def check_sidecars(pages=None) -> dict:
    pages = pages or []
    broken = []
    for page in pages:
        sidecar = page.with_suffix(".json")
        if not sidecar.is_file():
            broken.append(f"{page.name}: no sidecar")
            continue
        try:
            recorded = json.loads(sidecar.read_text())
        except ValueError:
            broken.append(f"{page.name}: unreadable sidecar")
            continue
        if recorded.get("html_sha256") != file_hash(page):
            broken.append(f"{page.name}: hash mismatch")
    return {
        "name": "page-sidecars",
        "ok": not broken,
        "detail": "; ".join(broken) if broken else f"{len(pages)} page(s) match their sidecars",
    }


def check_loop_length(root: Path) -> dict:
    loop = root / "LOOP.md"
    if not loop.is_file():
        return {"name": "loop-length", "ok": False, "detail": "LOOP.md missing"}
    lines = len(loop.read_text().splitlines())
    return {
        "name": "loop-length",
        "ok": lines <= MAX_LOOP_LINES,
        "detail": f"{lines} lines (max {MAX_LOOP_LINES})",
    }


def check_no_bar_claims_without_grid(root: Path) -> dict:
    """A dashboard must not show bars/meter for a production without an approved grid."""
    offending = []
    for project in sorted((root / "projects").iterdir()) if (root / "projects").is_dir() else []:
        grid = project / "work/music-grid.json"
        approved = False
        if grid.is_file():
            try:
                approved = json.loads(grid.read_text()).get("approved") is True
            except ValueError:
                approved = False
        if approved:
            continue
        for page in (project / "work/dashboard").glob("*.html"):
            text = page.read_text(errors="ignore")
            if "<th>Bars</th>" in text or re.search(r"\bbar \d+\b", text):
                offending.append(page.name)
    return {
        "name": "no-grid-no-bars",
        "ok": not offending,
        "detail": f"bar claims without an approved grid: {offending}"
        if offending
        else "no bar numbers appear without an approved grid",
    }


def run(root: Path | None = None) -> dict:
    root = Path(root or ".")
    pages = _pages(root)
    checks = [
        check_command_registry(),
        check_mcp_surface(),
        check_pages_offline(pages),
        check_sidecars(pages),
        check_loop_length(root),
        check_no_bar_claims_without_grid(root),
    ]
    return {
        "ok": all(check["ok"] for check in checks),
        "checks": checks,
        "pages": len(pages),
        "note": (
            "Invariant report, not a creative review. It proves structural rules only: "
            "no image, audio or approval is inspected here."
        ),
    }
