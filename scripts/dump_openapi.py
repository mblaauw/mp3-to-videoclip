"""Dump the Studio OpenAPI document for frontend type generation.

This is the same document served at ``GET /openapi.json``. Writing it from the
app keeps ``npm run api:types`` reproducible without starting a server.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from mp3_to_videoclip.app import create_app  # noqa: E402


def main() -> None:
    destination = Path(sys.argv[1] if len(sys.argv) > 1 else "frontend/openapi.json")
    destination.parent.mkdir(parents=True, exist_ok=True)
    schema = create_app().openapi()
    destination.write_text(
        json.dumps(schema, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
