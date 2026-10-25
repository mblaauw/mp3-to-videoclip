"""Launcher for the Studio.

Phase 1 stub: starts the interim loopback Studio (``serve``) and opens it in the
browser. Phase 2 replaces this with the FastAPI app, the job runner and the
Vite frontend, but the entry point and its contract stay the same.
"""

from __future__ import annotations

import argparse
import threading
import time
import webbrowser
from pathlib import Path

from . import serve


def main() -> None:
    parser = argparse.ArgumentParser(description="Start the mp3-to-videoclip Studio")
    parser.add_argument("--projects-dir", type=Path, default=Path("projects"))
    parser.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()

    httpd, url = serve.build_server(args.projects_dir, port=args.port, token=None)
    app_url = url.replace("/?token=", "/app?token=")
    thread = threading.Thread(target=httpd.serve_forever, kwargs={"poll_interval": 0.2}, daemon=True)
    thread.start()
    # Give the server a moment to bind before opening the browser.
    time.sleep(0.2)
    try:
        webbrowser.open(app_url)
    except Exception:  # pragma: no cover - best effort
        pass
    print(f"Studio live: {app_url}")
    try:
        while thread.is_alive():
            thread.join(timeout=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
