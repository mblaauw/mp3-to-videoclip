"""The eval report runner, run bundles, rubric and prompt-version pages."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest
from evals import rubric, runner

from mp3_to_videoclip.models import (
    EditAccent,
    EditDecisionList,
    EditMotion,
    EditSection,
    EditShot,
    EditText,
    EditTransition,
    Grade,
    Shot,
    Storyboard,
)


def _concepts():
    return {
        "concepts": [
            {
                "id": f"c{index}",
                "title": f"Route {index}",
                "structure": structure,
                "logline": "A line",
                "why": "A reason",
                "world": "A world",
                "shape": ["a", "b", "c", "d"],
                "signature_moment": "One image",
                "risk": "One risk",
            }
            for index, structure in enumerate(("narrative", "demonstration", "three reasons"))
        ]
    }


def _board() -> Storyboard:
    return Storyboard(
        aspect="16:9",
        fps=24,
        total_frames=720,
        shots=[
            Shot(
                id="s001",
                start_frame=0,
                duration_frames=240,
                kind="scene",
                purpose="open",
                message="the record",
                text=["THE RECORD"],
                image_prompt="A record on a turntable",
            ),
            Shot(
                id="s002",
                start_frame=240,
                duration_frames=120,
                kind="card",
                purpose="state the silence",
                message="two years",
                text=["Two years of silence."],
            ),
            Shot(
                id="s003",
                start_frame=360,
                duration_frames=360,
                kind="end_card",
                purpose="close",
                message="out now",
                text=["Out 14 Nov", "Pre-save now"],
            ),
        ],
    )


def _edit() -> EditDecisionList:
    return EditDecisionList(
        sections=[
            EditSection(
                id="open",
                start_frame=0,
                end_frame=240,
                feel="arrival",
                density_per_10s=2,
                techniques=["push-in"],
            ),
            EditSection(
                id="close",
                start_frame=240,
                end_frame=720,
                feel="statement and close",
                density_per_10s=2,
                techniques=["pull-back"],
            ),
        ],
        shots=[
            EditShot(
                shot_id="s001",
                start_frame=0,
                duration_frames=240,
                motion=EditMotion(type="hold", reason="let the record land"),
            ),
            EditShot(
                shot_id="s002",
                start_frame=240,
                duration_frames=120,
                motion=EditMotion(
                    type="push_in",
                    **{"from": 1.0, "to": 1.06},
                    reason="approach the statement",
                ),
                transition_in=EditTransition(
                    type="whip_pan", frames=8, direction="left", reason="new thought"
                ),
                text=[
                    EditText(
                        id="t1",
                        style="card",
                        text="TWO YEARS",
                        in_frame=250,
                        out_frame=350,
                        animation="type_on",
                        reason="words land with the line",
                    )
                ],
            ),
            EditShot(
                shot_id="s003",
                start_frame=360,
                duration_frames=360,
                motion=EditMotion(
                    type="pull_back",
                    **{"from": 1.08, "to": 1.0},
                    reason="release to the close",
                ),
                transition_in=EditTransition(type="dip_to_black", frames=8, reason="chapter break"),
                accents=[
                    EditAccent(
                        frame=360,
                        type="punch_in",
                        amount=1.04,
                        reason="the close lands",
                    )
                ],
            ),
        ],
        grade=Grade(preset="warm-night", strength=0.6),
    )


def _meta(hash_value: str, role: str, *, fixture: str = "advert-30s", **extra):
    prompt = {
        "hash": hash_value,
        "files": [{"path": f"{role}/system.md", "version": 2}],
        "role": role,
        "task": "storyboard" if role == "writer" else "edit",
        "kind": "advert",
        "words": 900,
    }
    return {
        "fixture": fixture,
        "role": role,
        "model": "offline-test",
        "created_at": "2026-10-26T12:00:00Z",
        "prompt": prompt,
        **extra,
    }


def _bundle(
    root: Path,
    name: str,
    meta: dict,
    *,
    treatments=None,
    board=None,
    edit=None,
) -> Path:
    directory = root / name
    directory.mkdir(parents=True)
    (directory / "meta.json").write_text(json.dumps(meta))
    if treatments is not None:
        (directory / "treatments.json").write_text(json.dumps(treatments))
    if board is not None:
        (directory / "storyboard.json").write_text(json.dumps(board))
    if edit is not None:
        (directory / "edit.json").write_text(json.dumps(edit))
    return directory


def test_writer_and_editor_runs_produce_passing_prompt_pages(tmp_path):
    runs = tmp_path / "runs"
    reports = tmp_path / "reports"
    board = _board().model_dump()
    _bundle(
        runs,
        "writer",
        _meta(
            "eval-writer-v1",
            "writer",
            cross_review={
                "reviewer_role": "editor",
                "scores": {"routes": 4, "jobs": 4, "rhythm": 3, "truth": 5},
                "notes": "The routes are distinct.",
            },
        ),
        treatments=_concepts(),
        board=board,
    )
    _bundle(
        runs,
        "editor",
        _meta("eval-editor-v1", "editor"),
        board=board,
        edit=_edit().model_dump(by_alias=True),
    )
    paths, summary = runner.run(runs_dir=runs, report_dir=reports)
    assert summary["runs"] == 2
    assert summary["failed"] == 0
    names = {path.name for path in paths}
    assert "prompt-eval-writer-v1.md" in names
    assert "prompt-eval-editor-v1.md" in names
    writer_page = (reports / "prompt-eval-writer-v1.md").read_text()
    editor_page = (reports / "prompt-eval-editor-v1.md").read_text()
    assert "PASS" in writer_page
    assert "3/3" in writer_page
    assert "overall **4.0 / 5**" in writer_page
    assert "PASS" in editor_page
    assert "1 / 1 runs pass" in editor_page
    assert (reports / "index.md").is_file()


def test_failing_writer_run_is_reported_not_hidden(tmp_path):
    runs = tmp_path / "runs"
    reports = tmp_path / "reports"
    duplicate = _concepts()
    duplicate["concepts"][1]["structure"] = "narrative"
    _bundle(
        runs,
        "writer-bad",
        _meta("eval-writer-bad", "writer"),
        treatments=duplicate,
        board=_board().model_dump(),
    )
    _, summary = runner.run(runs_dir=runs, report_dir=reports)
    assert summary["failed"] == 1
    page = (reports / "prompt-eval-writer-bad.md").read_text()
    assert "FAIL" in page
    assert "three different structures" in page


def test_editor_text_claims_must_trace_to_the_fixture(tmp_path):
    runs = tmp_path / "runs"
    reports = tmp_path / "reports"
    edit = _edit()
    edit.shots[1].text[0] = EditText(
        id="t1",
        style="card",
        text="18 DEC",
        in_frame=250,
        out_frame=350,
        animation="type_on",
        reason="wrong date",
    )
    _bundle(
        runs,
        "editor-bad-claim",
        _meta("eval-editor-claim", "editor"),
        board=_board().model_dump(),
        edit=edit.model_dump(by_alias=True),
    )
    _, summary = runner.run(runs_dir=runs, report_dir=reports)
    assert summary["failed"] == 1
    page = (reports / "prompt-eval-editor-claim.md").read_text()
    assert "18 DEC" in page
    assert runner.main(["--runs", str(runs), "--reports", str(reports), "--strict"]) == 1


def test_cross_review_requires_the_other_role_and_aggregates(tmp_path):
    runs = tmp_path / "runs"
    reports = tmp_path / "reports"
    _bundle(
        runs,
        "writer",
        _meta(
            "eval-cross",
            "writer",
            cross_review={
                "reviewer_role": "writer",
                "scores": {"routes": 4, "jobs": 4, "rhythm": 3, "truth": 5},
            },
        ),
        treatments=_concepts(),
        board=_board().model_dump(),
    )
    runner.run(runs_dir=runs, report_dir=reports)
    page = (reports / "prompt-eval-cross.md").read_text()
    assert "other role" in page
    with pytest.raises(ValueError, match="other role"):
        rubric.normalise(
            {
                "reviewer_role": "writer",
                "scores": {"routes": 4, "jobs": 4, "rhythm": 3, "truth": 5},
            },
            "writer",
        )
    with pytest.raises(ValueError, match="integer 1–5"):
        rubric.normalise(
            {
                "reviewer_role": "editor",
                "scores": {"routes": 6, "jobs": 4, "rhythm": 3, "truth": 5},
            },
            "writer",
        )
    with pytest.raises(ValueError, match="missing scores"):
        rubric.normalise(
            {"reviewer_role": "editor", "scores": {"routes": 4}},
            "writer",
        )
    summary = rubric.summarise(
        [
            rubric.normalise(
                {
                    "reviewer_role": "editor",
                    "scores": {"routes": 4, "jobs": 4, "rhythm": 3, "truth": 5},
                    "notes": "solid",
                },
                "writer",
            )
        ]
    )
    assert summary["overall"] == 4
    assert summary["scores"]["truth"] == 5
    review_prompt = rubric.prompt("editor", "writer")
    assert "routes" in review_prompt
    assert "reviewer_role" in review_prompt
    with pytest.raises(ValueError, match="other role"):
        rubric.prompt("writer", "writer")


def test_ratings_in_a_run_and_an_exported_file_are_aggregated(tmp_path):
    runs = tmp_path / "runs"
    reports = tmp_path / "reports"
    _bundle(
        runs,
        "writer",
        _meta(
            "eval-rated",
            "writer",
            ratings=[
                {
                    "artifact": "storyboard",
                    "rating": "up",
                    "note": "clear routes",
                    "prompt_hash": "eval-rated",
                }
            ],
        ),
        treatments=_concepts(),
        board=_board().model_dump(),
    )
    rating_file = tmp_path / "ratings.jsonl"
    rating_file.write_text(
        "\n".join(
            [
                json.dumps(
                    {
                        "artifact": "brief",
                        "rating": "down",
                        "note": "too vague",
                        "prompt_hash": "eval-rated",
                    }
                ),
                json.dumps(
                    {
                        "artifact": "storyboard",
                        "rating": "up",
                        "note": "historical page",
                        "prompt_hash": "eval-history-only",
                        "prompt_role": "writer",
                        "prompt_task": "storyboard",
                    }
                ),
                json.dumps(
                    {
                        "artifact": "edit",
                        "rating": "down",
                        "note": "no prompt history",
                        "prompt_hash": None,
                    }
                ),
            ]
        )
        + "\n"
    )
    paths, _ = runner.run(runs_dir=runs, report_dir=reports, ratings_path=rating_file)
    page = (reports / "prompt-eval-rated.md").read_text()
    assert "Good" in page
    assert "Needs work" in page
    assert "clear routes" in page
    assert "too vague" in page
    names = {path.name for path in paths}
    assert "prompt-eval-history-only.md" in names
    history = (reports / "prompt-eval-history-only.md").read_text()
    assert "historical page" in history
    assert "writer / storyboard" in history
    assert "historical prompt version" in history
    unbound = (reports / "prompt-unbound.md").read_text()
    assert "Unbound ratings" in unbound
    assert "no prompt history" in unbound


def test_a_damaged_ratings_line_does_not_hide_valid_rows(tmp_path):
    runs = tmp_path / "runs"
    reports = tmp_path / "reports"
    run = _bundle(
        runs,
        "writer",
        _meta("eval-damaged-ratings", "writer"),
        treatments=_concepts(),
        board=_board().model_dump(),
    )
    (run / "ratings.jsonl").write_text(
        "{not json}\n"
        + json.dumps(
            {
                "artifact": "storyboard",
                "rating": "up",
                "note": "the valid row",
                "prompt_hash": "eval-damaged-ratings",
            }
        )
        + "\n"
    )
    exported = tmp_path / "ratings.jsonl"
    exported.write_text(
        "[]\n"
        + json.dumps(
            {
                "artifact": "brief",
                "rating": "down",
                "note": "still readable",
                "prompt_hash": "eval-damaged-ratings",
            }
        )
        + "\n"
    )
    # An array followed by a row is not valid JSON; the JSONL fallback keeps the row.
    _, summary = runner.run(runs_dir=runs, report_dir=reports, ratings_path=exported)
    assert summary["failed"] == 0
    page = (reports / "prompt-eval-damaged-ratings.md").read_text()
    assert "the valid row" in page
    assert "still readable" in page


def test_default_command_writes_current_prompt_pages_without_a_model(tmp_path):
    reports = tmp_path / "reports"
    paths, summary = runner.run(runs_dir=tmp_path / "empty", report_dir=reports)
    assert summary["current_prompts"] >= 4
    assert len(paths) == summary["current_prompts"]
    assert all(path.is_file() for path in paths)
    assert (reports / "index.md").is_file()
    assert any("No run recorded" in path.read_text() for path in paths)


def test_module_command_starts_from_a_clean_checkout(tmp_path):
    reports = tmp_path / "reports"
    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "tests.evals",
            "--runs",
            str(tmp_path / "empty"),
            "--reports",
            str(reports),
        ],
        cwd=Path(__file__).resolve().parents[1],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert (reports / "index.md").is_file()
    assert len(list(reports.glob("prompt-*.md"))) >= 4
