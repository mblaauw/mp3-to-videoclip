"""Engineering headroom must not add an eighth creative crew member."""

import json
from pathlib import Path


def test_build_budget_is_an_isolated_native_override():
    root = Path(__file__).resolve().parents[1]
    crew = json.loads((root / "opencode.json").read_text())
    override = json.loads((root / ".opencode/opencode.json").read_text())
    assert "build" not in crew["agents"]
    assert crew["default_agent"] == "film-director"
    assert override == {
        "$schema": "https://opencode.ai/config.json",
        "agents": {"build": {"steps": 160}},
    }
