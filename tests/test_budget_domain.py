"""The schema 3 budget must admit inside the cap and pause outside it.

The cap lives in project.json, the journal supplies commitments, and an over-cap
request returns a needs_budget decision with a suggested top-up instead of
raising a bare error.
"""

from __future__ import annotations

import json
from pathlib import Path

from mp3_to_videoclip.domain import budget


def _root(tmp_path: Path, cap_value: str = "5.00") -> Path:
    root = tmp_path / "projects" / "demo"
    (root / "work").mkdir(parents=True)
    (root / "project.json").write_text(
        json.dumps(
            {
                "schema_version": 3,
                "slug": "demo",
                "title": "Demo",
                "source": "media/song.mp3",
                "source_sha256": "a" * 64,
                "duration": 60.0,
                "aspect": "16:9",
                "fps": 24,
                "width": 1920,
                "height": 1080,
                "budget": [{"at": "2026-10-25T00:00:00+00:00", "cap_usd": cap_value}],
            }
        )
    )
    (root / "work" / "tasks.json").write_text("{}")
    return root


def test_cap_and_committed_come_from_project_and_journal(tmp_path):
    root = _root(tmp_path)
    assert budget.cap(root) == budget.money("5.00")
    assert budget.committed(root) == budget.money("0")
    (root / "work" / "tasks.json").write_text(
        json.dumps(
            {
                "t1": {"status": "ready", "cost_usd": "1.25"},
                "t2": {"status": "submitted", "reserve_usd": "0.50"},
            }
        )
    )
    assert budget.committed(root) == budget.money("1.75")
    assert budget.remaining(root) == budget.money("3.25")


def test_admission_inside_and_pause_outside(tmp_path):
    root = _root(tmp_path)
    inside = budget.check(root, "1.00")
    assert inside["ok"] is True and inside["needs_budget"] is False
    outside = budget.check(root, "6.00")
    assert outside["ok"] is False and outside["needs_budget"] is True
    assert float(outside["suggested_usd"]) >= 1.0


def test_adding_budget_appends_history(tmp_path):
    root = _root(tmp_path)
    entry = budget.add_budget(root, "3.00", "user approved more")
    assert entry["cap_usd"] == "3.00"
    assert len(budget.history(root)) == 2
    assert budget.cap(root) == budget.money("3.00")


def test_engine_reads_the_schema_three_cap(tmp_path):
    """The engine admission path must see the cap in project.json, not only the UI."""
    import pytest

    from mp3_to_videoclip import budget as engine

    root = _root(tmp_path)
    record = engine.read_budget(root)
    assert record["cap_usd"] == "5.00"
    assert record["max_corrections"] == 1
    assert engine.check_capacity(root, "1.00")
    with pytest.raises(ValueError):
        engine.check_capacity(root, "6.00")


def test_schema_three_without_a_cap_refuses_paid_admission(tmp_path):
    import json

    import pytest

    from mp3_to_videoclip import budget as engine

    root = _root(tmp_path)
    data = json.loads((root / "project.json").read_text())
    data["budget"] = []
    (root / "project.json").write_text(json.dumps(data))
    with pytest.raises(ValueError):
        engine.check_capacity(root, "1.00")
