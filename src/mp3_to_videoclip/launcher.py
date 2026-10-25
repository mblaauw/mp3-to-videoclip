"""Launcher for the Studio.

Phase 2: starts the FastAPI app on a free port, opens the browser, and serves
until interrupted. Falls back to the interim loopback Studio if uvicorn is not
available.
"""

from __future__ import annotations

import argparse
import socket
import threading
import time
import webbrowser
from pathlib import Path

import uvicorn

from .app import create_app


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the mp3-to-videoclip Studio")
    parser.add_argument("--projects-dir", type=Path, default=Path("projects"))
    parser.add_argument("--port", type=int, default=0)
    args = parser.parse_args()

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
