"""First-run capability checks and the one local renderer install.

The Studio serves a committed frontend build, so a fresh clone needs only
``uv sync`` and ``uv run studio``. The pinned Remotion packages are not committed;
the launcher installs them once when they are missing, and the Film screen can
retry from the GUI if that first attempt failed. Nothing here downloads a browser,
runs a paid provider or touches a production.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from .remotion import ENGINE

REPO = Path(__file__).resolve().parents[2]
INSTALL_TIMEOUT_SECONDS = 900

CHROME_CANDIDATES = (
    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
    "/Applications/Chromium.app/Contents/MacOS/Chromium",
    "/usr/bin/google-chrome",
    "/usr/bin/chromium-browser",
    "/usr/bin/chromium",
)


def _chrome() -> bool:
    explicit = os.environ.get("REMOTION_CHROME") or os.environ.get("CHROME_PATH")
    if explicit:
        return Path(explicit).is_file()
    return any(Path(candidate).is_file() for candidate in CHROME_CANDIDATES)


def status() -> dict:
    """Capabilities the local app needs; booleans only, no paths or secrets."""
    return {
        "node": shutil.which("node") is not None,
        "npm": shutil.which("npm") is not None,
        "chrome": _chrome(),
        "ffmpeg": shutil.which("ffmpeg") is not None,
        "ffprobe": shutil.which("ffprobe") is not None,
        "renderer": (ENGINE / "node_modules/@remotion/renderer").is_dir(),
        "frontend": (REPO / "frontend/dist/index.html").is_file(),
    }


def install_renderer() -> dict:
    """Install the pinned renderer packages; safe to call when already present."""
    if status()["renderer"]:
        return {"installed": True, "already_present": True, "output": ""}
    npm = shutil.which("npm")
    if npm is None:
        raise ValueError("npm is not available; install Node.js (which includes npm) first")
    result = subprocess.run(
        [
            npm,
            "ci",
            "--prefix",
            str(ENGINE),
            "--ignore-scripts",
            "--no-audit",
            "--no-fund",
        ],
        cwd=REPO,
        capture_output=True,
        text=True,
        timeout=INSTALL_TIMEOUT_SECONDS,
        check=False,
    )
    output = (result.stdout + result.stderr)[-4000:]
    if result.returncode != 0:
        raise ValueError("the local renderer install failed: " + (output or "npm exited non-zero"))
    if not (ENGINE / "node_modules/@remotion/renderer").is_dir():
        raise ValueError("the local renderer install finished but @remotion/renderer is missing")
    return {"installed": True, "already_present": False, "output": output}
