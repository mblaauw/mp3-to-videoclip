"""The director context is a cheap snapshot, never a full gate pass."""

from __future__ import annotations

from pathlib import Path

from api_support import add_assets, api_client, make_api_project

from mp3_to_videoclip import production as P
from mp3_to_videoclip import story_beats
from mp3_to_videoclip.director.context import build_context
from mp3_to_videoclip.storage import write_json


def test_context_contains_the_brief_shots_and_stage_without_source_hashes(
    tmp_path: Path, monkeypatch
):
    root = make_api_project(tmp_path)
    add_assets(root)
    seen: list[bool] = []
    original = P.load_project

    def tracked(project_root, verify_source=True):
        seen.append(verify_source)
        return original(project_root, verify_source=False)

    monkeypatch.setattr(P, "load_project", tracked)

    def fail(_root):
        raise AssertionError("context must not run P.status")

    monkeypatch.setattr(P, "status", fail)

    text = build_context("production", tmp_path, stage="story")

    assert "Project snapshot" in text
    assert "Current stage: story" in text
    assert "Direction: DIRECTION-SECRET" in text
    assert "Shots (4:" in text
    assert "current v1" in text
    assert "Recorded approvals" in text
    assert seen and not any(seen), "the snapshot must never re-hash the source"


def test_context_reports_stale_stills_after_a_brief_change(tmp_path: Path):
    root = make_api_project(tmp_path)
    add_assets(root)
    P.update_brief(root, {"creative": {"look": "A different look"}})
    text = build_context("production", tmp_path)
    assert "stale (inputs changed)" in text
    assert "0 current" in text


def test_context_carries_the_playhead_and_selected_shots(tmp_path: Path):
    make_api_project(tmp_path)
    text = build_context(
        "production",
        tmp_path,
        stage="storyboard",
        context={"stage": "storyboard", "time": 12.5, "selected_shots": ["s001", "s004"]},
    )
    assert "## Session context" in text
    assert "Stage when asked: storyboard" in text
    assert "Playhead: 12.50s" in text
    assert "Selected shots: s001, s004" in text


STORY = "One walks.\n\nTwo runs.\n\nThree stops."


def _placed(root: Path, *spans) -> None:
    story_beats.place_story(
        root, {"passages": [{"start": a, "end": b, "text": text} for a, b, text in spans]}
    )


def _story_section(text: str) -> list[str]:
    lines = text.splitlines()
    start = next(i for i, line in enumerate(lines) if line.startswith("## Story on the song"))
    return lines[start : lines.index("", start)]


def test_the_storyboard_task_sees_placed_and_unplaced_passages(tmp_path: Path):
    root = make_api_project(tmp_path)
    P.update_brief(root, {"treatment": STORY})
    _placed(root, (0, 0.5, "One walks."), (0.5, 1, "Two runs."), (1, 2, "Three stops."))
    P.update_brief(root, {"treatment": "One walks.\n\nTwo flies.\n\nThree stops."})
    fps = P.load_project(root, verify_source=False).fps

    section = _story_section(build_context("production", tmp_path, task="storyboard"))

    assert section == [
        "## Story on the song (evidence, not an approval): 2 of 3 placed",
        f"- 0.00-0.50s (frames 0-{fps // 2}): One walks.",
        "- not on the song: Two flies.",
        f"- 1.00-2.00s (frames {fps}-{2 * fps}): Three stops.",
    ]


def test_a_story_never_placed_reads_as_unplaced_on_a_film_with_no_board(tmp_path: Path):
    root = make_api_project(tmp_path)
    P.update_brief(root, {"treatment": STORY})
    (root / "work/storyboard.json").unlink()

    text = build_context("production", tmp_path, task="storyboard")

    assert _story_section(text) == [
        "## Story on the song (evidence, not an approval): 0 of 3 placed",
        "- not on the song: One walks.",
        "- not on the song: Two runs.",
        "- not on the song: Three stops.",
    ]
    assert "No storyboard yet." in text


def test_a_time_left_past_the_end_of_the_film_reads_as_unplaced(tmp_path: Path):
    root = make_api_project(tmp_path)
    P.update_brief(root, {"treatment": STORY})
    duration = P.load_project(root, verify_source=False).duration
    write_json(
        root / story_beats.PATH,
        {
            "schema_version": 1,
            "passages": [
                {"start": 0, "end": 1, "text": "One walks."},
                {"start": duration, "end": duration + 9, "text": "Two runs. Three stops."},
            ],
        },
    )

    section = _story_section(build_context("production", tmp_path, task="storyboard"))

    assert section[0].endswith("1 of 2 placed")
    assert section[2].startswith("- not on the song: Two runs.")


def test_a_passage_ending_at_the_film_end_stays_inside_the_last_frame(tmp_path: Path):
    root = make_api_project(tmp_path)
    P.update_brief(root, {"treatment": "One walks."})
    project = P.load_project(root, verify_source=False)
    _placed(root, (0, project.duration + 0.4, "One walks."))

    section = _story_section(build_context("production", tmp_path, task="storyboard"))

    assert f"(frames 0-{project.total_frames})" in section[1]


def test_unreadable_timings_keep_the_snapshot_and_guess_nothing(tmp_path: Path):
    root = make_api_project(tmp_path)
    P.update_brief(root, {"treatment": STORY})
    (root / story_beats.PATH).parent.mkdir(exist_ok=True)
    (root / story_beats.PATH).write_text("{not json")

    text = build_context("production", tmp_path, task="storyboard")

    assert "Project snapshot" in text
    assert "treat every passage as not on the song" in text
    assert "Shots (4:" in text


def test_only_the_storyboard_task_gets_the_timings(tmp_path: Path):
    root = make_api_project(tmp_path)
    P.update_brief(root, {"treatment": STORY})
    for task in (None, "revise", "notes"):
        text = build_context("production", tmp_path, stage="storyboard", task=task)
        assert "Story on the song" not in text


def test_timings_stay_out_of_every_approval_hash(tmp_path: Path):
    root = make_api_project(tmp_path)
    P.update_brief(root, {"treatment": STORY})
    client = api_client(tmp_path)
    url = "/api/projects/production/approvals"

    def hashes():
        return {item["stage"]: item["expected_hash"] for item in client.get(url).json()["stages"]}

    before = hashes()
    assert before["brief"] and before["storyboard"]
    _placed(root, (0, 0.5, "One walks."), (0.5, 1, "Two runs."), (1, 2, "Three stops."))
    assert hashes() == before
    build_context("production", tmp_path, task="storyboard")
    _placed(root, (0, 1, "One walks."), (1, 1.5, "Two runs."), (1.5, 2, "Three stops."))
    assert hashes() == before
