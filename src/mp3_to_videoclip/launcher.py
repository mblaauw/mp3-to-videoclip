"""Launcher for the Studio.

Starts the FastAPI app on a free port, opens the browser, and serves until
interrupted. On a fresh clone it installs the pinned local renderer packages
once; the committed frontend build needs no Node packages to serve.
"""

from __future__ import annotations

import argparse
import shutil
import socket
import subprocess
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn

from . import setup
from .app import create_app


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def _ensure_renderer() -> None:
    """Install the pinned renderer once; a failure still leaves the app runnable."""
    if setup.status()["renderer"]:
        return
    print("Studio: installing the pinned local renderer (first run)…", flush=True)
    try:
        result = setup.install_renderer()
    except (OSError, ValueError) as exc:
        print(f"Studio: local renderer setup incomplete: {exc}")
        return
    if not result["already_present"]:
        print("Studio: installed the pinned local renderer (first run).")


def _build_frontend(repo: Path) -> None:
    """Best-effort: rebuild the Vite app when its sources are newer than dist."""
    frontend = repo / "frontend"
    dist = frontend / "dist"
    src = frontend / "src"
    if not src.is_dir():
        return
    npm = shutil.which("npm")
    if not (frontend / "node_modules").is_dir():
        if dist.is_dir() or npm is None:
            # The committed dist is the shipped app; never invoke tsc without deps.
            return
        subprocess.run(
            [npm, "ci", "--prefix", str(frontend), "--ignore-scripts", "--no-audit", "--no-fund"],
            check=False,
        )
        if not (frontend / "node_modules").is_dir():
            return
    if dist.is_dir() and dist.stat().st_mtime >= src.stat().st_mtime:
        return
    if npm is None:
        return
    subprocess.run([npm, "run", "build"], cwd=frontend, check=False)


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the mp3-to-videoclip Studio")
    parser.add_argument("--projects-dir", type=Path, default=Path("projects"))
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()
    repo = Path(__file__).resolve().parents[2]
    _ensure_renderer()
    _build_frontend(repo)

    port = args.port or _free_port()
    app = create_app(projects_dir=args.projects_dir)
    url = f"http://127.0.0.1:{port}/"

    def _serve():
        uvicorn.run(app, host="127.0.0.1", port=port, log_level="warning")

    thread = threading.Thread(target=_serve, daemon=True)
    thread.start()
    time.sleep(0.5)
    try:
        webbrowser.open(url)
    except Exception:  # pragma: no cover
        pass
    print(f"Studio live: {url}")
    try:
        while thread.is_alive():
            thread.join(timeout=0.5)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
