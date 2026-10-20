"""Cumulative production budget, correction cycles and accounting reports.

No provider is contacted: journal/quote/budget artifacts are written directly and
the only generation entry points exercised are ``authorize``/``begin_task``, which
perform no network calls.
"""

from decimal import Decimal

import pytest

from mp3_to_videoclip import budget as B
from mp3_to_videoclip import generation as G
from mp3_to_videoclip.storage import read_json, write_json


def make_root(tmp_path, *, workflow_version=None):
    root = tmp_path / "production"
    (root / "work").mkdir(parents=True)
    project = {
        "schema_version": 1,
        "slug": "test",
        "title": "Test",
        "source_sha256": "0" * 64,
        "duration": 1,
        "width": 192,
        "height": 108,
    }
    if workflow_version is not None:
        project["workflow_version"] = workflow_version
    write_json(root / "project.json", project)
    write_json(root / "work/tasks.json", {})
    return root


def image_task(uuid, shot_id, *, status="ready", cost="0.001", version=1):
    value = {
        "uuid": uuid,
        "kind": "images",
        "status": status,
        "quote_id": "q",
        "shot_id": shot_id,
        "version": version,
        "reserve_usd": "0.01",
    }
    if cost is not None:
        value["cost_usd"] = cost
    return value


def journal_task(uuid, *, kind="images", status="ready", cost=None, reserve="0.01", **extra):
    value = {"uuid": uuid, "kind": kind, "status": status, "quote_id": "q"}
    if cost is not None:
        value["cost_usd"] = cost
    if reserve is not None:
        value["reserve_usd"] = reserve
    value.update(extra)
    return value


def write_quote(root, reserve_total, quote_id="00000000-0000-4000-8000-000000000000"):
    write_json(
        root / f"work/quotes/{quote_id}.json",
        {"id": quote_id, "kind": "images", "reserve_total_usd": reserve_total},
    )
    return quote_id


# --------------------------------------------------------------------------- #
# set_budget
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("cap", ["nan", "Infinity", "-1", "0", True, "invalid"])
def test_set_budget_rejects_invalid_caps(tmp_path, cap):
    root = make_root(tmp_path)
    with pytest.raises(ValueError):
        B.set_budget(root, cap, "user authority note")


def test_set_budget_requires_note_and_bounded_corrections(tmp_path):
    root = make_root(tmp_path)
    with pytest.raises(ValueError, match="note"):
        B.set_budget(root, "1", "   ")
    for value in (-1, 11, True, "2"):
        with pytest.raises(ValueError, match="max_corrections"):
            B.set_budget(root, "1", "user authority note", value)
    record = B.set_budget(root, "1.50", "user set a hard ceiling", 3)
    assert record["version"] == 1
    assert record["cap_usd"] == "1.50" and record["max_corrections"] == 3 and record["at"]
    assert read_json(root / "work/production-budget.json") == record
    assert B.read_budget(root)["cap_usd"] == "1.50"


def test_set_budget_refuses_to_hide_committed_and_reserved_spend(tmp_path):
    root = make_root(tmp_path)
    write_json(
        root / "work/tasks.json",
        {
            "a": journal_task("a", cost="0.50"),
            "b": journal_task("b", kind="audio-upload", cost=None, reserve="0.20"),
        },
    )
    assert B.commitment(root) == Decimal("0.70")
    with pytest.raises(ValueError, match="below"):
        B.set_budget(root, "0.60", "too low to be honest")
    assert B.set_budget(root, "0.70", "covers committed spend")["cap_usd"] == "0.70"


def test_corrupt_budget_artifact_is_rejected(tmp_path):
    root = make_root(tmp_path)
    write_json(
        root / "work/production-budget.json",
        {"version": 2, "cap_usd": "1", "max_corrections": 2, "note": "x"},
    )
    with pytest.raises(ValueError, match="invalid"):
        B.read_budget(root)


def test_restaging_keeps_unrelated_cycles(tmp_path):
    root = make_root(tmp_path)
    B.set_budget(root, "1", "test authority")
    B.authorize_restaging(root, ["s001"], "diagnose first shot")
    first = B.correction_cycle(root, "s001")
    B.authorize_restaging(root, ["s002"], "diagnose second shot")
    assert B.correction_cycle(root, "s001") == first


# --------------------------------------------------------------------------- #
# summary
# --------------------------------------------------------------------------- #
def test_summary_keeps_unknown_reservations_and_never_invents_zero(tmp_path):
    root = make_root(tmp_path)
    B.set_budget(root, "1.00", "user set the production ceiling", 2)
    write_json(
        root / "work/tasks.json",
        {
            "i1": journal_task(
                "i1",
                cost="0.001",
                shot_id="s001",
                submitted_at="2026-01-01T00:00:00+00:00",
                completed_at="2026-01-01T00:00:02.500000+00:00",
            ),
            "i2": image_task("i2", "s001", cost="0.002"),
            "i3": image_task("i3", "s002", status="submitted", cost=None),
            "up": journal_task("up", kind="audio-upload", cost=None, reserve="0.01"),
            "t1": journal_task("t1", kind="transcription", status="resolved", cost="0.06"),
            "m1": journal_task("m1", kind="music-analysis", status="invalid", cost="0.004"),
            "x": {"uuid": "x", "kind": "images", "status": "submitted", "quote_id": "q"},
        },
    )
    report = B.summary(root)
    with pytest.raises(ValueError, match="unpriced journal"):
        B.check_capacity(root, "0.001")
    assert report["reported_usd"] == "0.067"
    assert report["reserved_unknown_usd"] == "0.02"  # unresolved image 0.01 + ready upload 0.01
    assert report["total_accounted_usd"] == "0.087"
    assert report["cap_usd"] == "1.00" and report["cap_remaining_usd"] == "0.913"
    assert report["over_cap"] is False and report["unresolved_tasks"] == 2
    assert report["unpriced_tasks"] == ["x"]  # no fabricated $0, listed as unpriced
    assert report["task_count"] == 7
    assert report["successful_image_generations_by_shot"] == {"s001": 2}
    assert report["successful_calls_by_kind"]["audio-upload"] == 1
    assert report["statuses"]["submitted"] == 2
    assert report["kinds"]["music-analysis"] == 1
    assert report["task_latency_seconds"]["count"] == 1
    assert report["task_latency_seconds"]["max_seconds"] == 2.5
    assert "not inference-only" in report["task_latency_seconds"]["coverage"]


def test_summary_without_budget_is_legacy_and_check_capacity_is_a_noop(tmp_path):
    root = make_root(tmp_path)
    report = B.summary(root)
    assert report["budget_configured"] is False
    assert report["cap_usd"] is None and report["cap_remaining_usd"] is None
    assert report["over_cap"] is False and report["admission_note"]
    assert B.check_capacity(root, "100") is None  # historical behaviour preserved


def test_summary_flags_over_cap_after_new_spend(tmp_path):
    root = make_root(tmp_path)
    B.set_budget(root, "0.01", "tiny explicit cap")
    write_json(
        root / "work/tasks.json", {"a": journal_task("a", status="submitted", reserve="0.05")}
    )
    report = B.summary(root)
    assert report["over_cap"] is True and report["cap_remaining_usd"] == "-0.04"


# --------------------------------------------------------------------------- #
# admission
# --------------------------------------------------------------------------- #
def test_workflow_two_requires_budget_before_admission(tmp_path):
    root = make_root(tmp_path, workflow_version=2)
    with pytest.raises(ValueError, match="workflow version 2"):
        B.require_budget(root)
    with pytest.raises(ValueError, match="workflow version 2"):
        B.check_capacity(root, "0.01")
    B.set_budget(root, "0.02", "user authorized v2 budget")
    assert B.check_capacity(root, "0.01")["cap_usd"] == "0.02"
    with pytest.raises(ValueError, match="exhausted"):
        B.check_capacity(root, "0.03")


def test_authorize_and_begin_task_enforce_cumulative_production_cap(tmp_path):
    root = make_root(tmp_path, workflow_version=2)
    quote_id = write_quote(root, "0.02")
    with pytest.raises(ValueError, match="workflow version 2"):
        G.authorize(root, quote_id, "0.10", "user authorized this scope")
    B.set_budget(root, "0.03", "user set a production ceiling")
    G.authorize(root, quote_id, "0.10", "user authorized this scope")
    # An independent, already-committed task of another kind consumes the cap.
    write_json(
        root / "work/tasks.json",
        {"other": journal_task("other", kind="music-analysis", status="submitted", reserve="0.02")},
    )
    task = {"uuid": "11111111-1111-4111-8111-111111111111", "reserve_usd": "0.02"}
    with pytest.raises(ValueError, match="production budget"):
        G.begin_task(root, read_json(root / f"work/quotes/{quote_id}.json"), task)
    assert list(read_json(root / "work/tasks.json")) == ["other"]


# --------------------------------------------------------------------------- #
# correction cycles
# --------------------------------------------------------------------------- #
def test_correction_limit_requires_explicit_restaging(tmp_path):
    root = make_root(tmp_path)
    B.set_budget(root, "1.00", "user enabled correction limits", 2)
    write_json(
        root / "work/tasks.json", {"a": image_task("a", "s001"), "b": image_task("b", "s001")}
    )
    B.check_correction_cycle(root, "s001")  # one original + one correction used: still allowed
    write_json(
        root / "work/tasks.json",
        {
            "a": image_task("a", "s001"),
            "b": image_task("b", "s001"),
            "c": image_task("c", "s001"),
        },
    )
    with pytest.raises(ValueError, match="restaging"):
        B.check_correction_cycle(root, "s001")
    record = B.authorize_restaging(
        root, ["s001"], "hands and logo malformed; restage after diagnosis"
    )
    assert record["shots"]["s001"]["baseline"] == 3
    B.check_correction_cycle(root, "s001")  # a deliberate new cycle is allowed
    new_cycle = B.correction_cycle(root, "s001")
    assert new_cycle["baseline"] == 3 and new_cycle["restage_hash"]
    B.check_correction_cycle(root, "s001", new_cycle)
    # A quote recorded before the restaging can no longer be generated.
    with pytest.raises(ValueError, match="changed"):
        B.check_correction_cycle(root, "s001", {"baseline": 0, "restage_hash": None})
    # After three more successes the fresh cycle is used up again.
    write_json(
        root / "work/tasks.json",
        {u: image_task(u, "s001") for u in "abcdef"},
    )
    with pytest.raises(ValueError, match="restaging"):
        B.check_correction_cycle(root, "s001")


def test_correction_policy_is_inactive_for_legacy_projects(tmp_path):
    root = make_root(tmp_path)
    write_json(root / "work/tasks.json", {f"t{i}": image_task(f"t{i}", "s001") for i in range(6)})
    assert B.correction_policy(root) == (False, 2)
    B.check_correction_cycle(root, "s001")
    B.require_correction_cycles(root, ["s001"])  # uncontrolled legacy behaviour preserved


@pytest.mark.parametrize(
    "ids,note",
    [([], "ok"), (["s001", "s001"], "ok"), (["  "], "ok"), ("s001", "ok"), (["s001"], "   ")],
)
def test_restaging_requires_real_ids_and_note(tmp_path, ids, note):
    root = make_root(tmp_path)
    with pytest.raises(ValueError):
        B.authorize_restaging(root, ids, note)


def test_costs_reports_budget_summary(tmp_path):
    root = make_root(tmp_path)
    B.set_budget(root, "0.50", "user set the production ceiling")
    report = G.costs(root)
    assert report["budget"]["cap_usd"] == "0.50"
    assert report["reported_or_calculated_usd"] == "0"
