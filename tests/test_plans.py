"""Plan objects: proposal-only build, honest stops, idempotent replay."""

import pytest
from test_creative_production import make_root

from mp3_to_videoclip import budget, plans
from mp3_to_videoclip.cli import execute, parser
from mp3_to_videoclip.storage import read_json


def plan_with(monkeypatch, root, steps):
    """Save a hand-built plan so tests do not depend on command templates."""
    built = plans.build(root)
    built["steps"] = [
        plans._step(command, label, reason, invalidates=()) for label, reason, command in steps
    ]
    built["blocked_by"] = [s["label"] for s in built["steps"] if s["human"] or s["needs_input"]]
    built["executable"] = [
        s["label"] for s in built["steps"] if not s["human"] and not s["needs_input"]
    ]
    plans.save(root, built)
    return built


def test_build_is_a_proposal_and_records_nothing(tmp_path):
    root = make_root(tmp_path)
    before = sorted(path.name for path in (root / "work").iterdir())
    built = plans.build(root, intent="advance")
    assert built["steps"]
    assert built["warning"].startswith("A plan changes nothing")
    assert sorted(path.name for path in (root / "work").iterdir()) == before
    assert "Set spending cap" in built["blocked_by"]
    assert "Approve analysis" in built["blocked_by"]


def test_save_is_immutable_and_history_lists_plans(tmp_path):
    root = make_root(tmp_path)
    built = plans.save(root, plans.build(root))
    with pytest.raises(ValueError, match="immutable"):
        plans.save(root, read_json(built))
    listed = plans.history(root)
    assert listed and listed[0]["id"] == read_json(built)["id"]


def test_run_executes_concrete_steps_then_waits_for_a_human(tmp_path):
    root = make_root(tmp_path)
    built = plan_with(
        None,
        root,
        [
            ("say hello", "harmless", f"uv run clip status {root}"),
            (
                "Approve storyboard",
                "human gate",
                "uv run clip approve projects/x storyboard --note 'ok'",
            ),
        ],
    )
    result = plans.run(root, built["id"], db=tmp_path / "spine.sqlite3", cwd=tmp_path)
    assert result["status"] == "waiting"
    assert [step["label"] for step in result["executed"]] == ["say hello"]
    assert result["stopped_at"]["why"] == "human decision"
    assert result["stopped_at"]["interrupt"].startswith("int_")
    # A second run is a new deliberate execution, not a replay of the first.
    again = plans.run(root, built["id"], db=tmp_path / "spine.sqlite3", cwd=tmp_path)
    assert again["executed"][0]["replayed"] is False
    assert again["executed"][0]["run_id"] != result["executed"][0]["run_id"]


def test_placeholder_commands_stop_for_input(tmp_path):
    root = make_root(tmp_path)
    built = plan_with(
        None,
        root,
        [("Approve", "template", "uv run clip approve projects/x brief --note '<decision>'")],
    )
    result = plans.run(root, built["id"], db=tmp_path / "spine.sqlite3", cwd=tmp_path)
    assert result["status"] == "waiting" and result["stopped_at"]["why"] == "needs input"


def test_edit_steps_need_explicit_delegation(tmp_path):
    root = make_root(tmp_path)
    budget.set_budget(root, "5.00", "test")
    built = plan_with(
        None,
        root,
        [
            (
                "Edit",
                "canonical",
                "uv run clip shot-edit projects/x --shot s001 --camera hold --note y",
            )
        ],
    )
    refused = plans.run(root, built["id"], db=tmp_path / "spine.sqlite3", cwd=tmp_path)
    assert refused["status"] == "waiting" and "capability" in refused["stopped_at"]["why"]
    allowed = plans.run(
        root, built["id"], db=tmp_path / "spine.sqlite3", cwd=tmp_path, allow_edit=True
    )
    # With delegation the capability gate opens: the command really runs, and its own
    # failure in this fixture is reported as a failed step rather than a blocked plan.
    assert "capability" not in ((allowed.get("stopped_at") or {}).get("why") or "")
    assert allowed["status"] in {"failed", "succeeded"}


def test_failure_stops_the_plan(tmp_path):
    root = make_root(tmp_path)
    built = plan_with(
        None, root, [("Fail", "nonzero", f"uv run clip status {tmp_path / 'missing'}")]
    )
    result = plans.run(root, built["id"], db=tmp_path / "spine.sqlite3", cwd=tmp_path)
    assert result["status"] == "failed" and result["failed_step"] == "Fail"


def test_cli_build_and_run(tmp_path):
    root = make_root(tmp_path)
    built = execute(parser().parse_args(["plan", "build", str(root), "--intent", "test"]))
    assert built["id"].startswith("plan-") and built["path"].startswith("work/plans")
    listed = execute(parser().parse_args(["plan", "list", str(root)]))
    assert listed["plans"][0]["id"] == built["id"]
    shown = execute(parser().parse_args(["plan", "show", str(root), "--id", built["id"]]))
    assert shown["intent"] == "test"


def test_unclassified_commands_are_refused(tmp_path):
    root = make_root(tmp_path)
    built = plans.build(root)
    built["steps"] = [
        {
            "label": "shell",
            "reason": "not a clip command",
            "command": "rm -rf /tmp/whatever",
            "tool": None,
            "kind": "edit",
            "human": False,
            "needs_input": False,
            "invalidates": [],
            "status": "pending",
        }
    ]
    plans.save(root, built)
    result = plans.run(root, built["id"], db=tmp_path / "spine.sqlite3", cwd=tmp_path)
    assert result["status"] == "waiting"
    assert "uv run clip" in result["stopped_at"]["why"]


def test_a_stored_tool_label_cannot_smuggle_a_command(tmp_path):
    """The saved capability label is a proposal artefact, never an authority."""
    root = make_root(tmp_path)
    built = plans.build(root)
    marker = tmp_path / "ARBITRARY-COMMAND-RAN"
    built["steps"] = [
        {
            "label": "status",
            "reason": "claims read capability",
            "command": f"touch {marker} clip",
            "tool": "status",
            "kind": "read",
            "human": False,
            "needs_input": False,
            "invalidates": [],
            "status": "pending",
        }
    ]
    plans.save(root, built)
    result = plans.run(root, built["id"], db=tmp_path / "spine.sqlite3", cwd=tmp_path)
    assert result["status"] == "waiting"
    assert "uv run clip" in result["stopped_at"]["why"]
    assert not marker.exists()


def test_malformed_plans_are_refused_at_save(tmp_path):
    root = make_root(tmp_path)
    base = plans.build(root)
    for mutate, message in (
        (lambda plan: plan.pop("intent"), "needs an intent"),
        (lambda plan: plan.__setitem__("steps", []), "at least one step"),
        (
            lambda plan: plan["steps"][0].__setitem__("command", "uv run clip nonsense"),
            "unknown clip command",
        ),
        (
            lambda plan: plan["steps"][0].__setitem__("invalidates", ["not-a-stage"]),
            "known stages",
        ),
        (lambda plan: plan["steps"][0].pop("label"), "missing label"),
    ):
        import copy

        candidate = copy.deepcopy(base)
        mutate(candidate)
        with pytest.raises(ValueError, match=message):
            plans.save(root, candidate)


def test_a_built_plan_is_valid(tmp_path):
    root = make_root(tmp_path)
    built = plans.build(root)
    assert plans.problems(built) == []
    plans.save(root, built)


def test_cli_plan_run_actually_reaches_the_runner(tmp_path):
    """The CLI dispatch, not just plans.run(), must resolve the journal import."""
    root = make_root(tmp_path)
    built = execute(parser().parse_args(["plan", "build", str(root), "--intent", "run me"]))
    result = execute(
        parser().parse_args(
            [
                "plan",
                "run",
                str(root),
                "--id",
                built["id"],
                "--db",
                str(tmp_path / "spine.sqlite3"),
            ]
        )
    )
    assert result["plan"] == built["id"]
    assert result["status"] in {"succeeded", "waiting", "failed"}


def test_cli_spine_status_uses_the_top_level_import(tmp_path):
    result = execute(parser().parse_args(["spine", "status", "--db", str(tmp_path / "s.db")]))
    assert result["runs"] == {}
