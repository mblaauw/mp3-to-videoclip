"""The song map merges what was measured and moves no approval."""

from __future__ import annotations

import json
from pathlib import Path

from api_support import api_client, make_api_project

from mp3_to_videoclip import pacing, song_map
from mp3_to_videoclip import production as P
from mp3_to_videoclip.director.context import build_context
from mp3_to_videoclip.domain import music_notes, section_map
from mp3_to_videoclip.production.project import STAGE_FILES
from mp3_to_videoclip.storage import read_json, write_json


def _deep(root: Path, boundaries=(10.0, 20.0, 30.0), score=1.4) -> None:
    write_json(
        root / "work/music-deep.json",
        {
            "refined_tempo": {"primary_bpm": 120.0, "half_bpm": 60.0, "double_bpm": 240.0},
            "downbeats": [{"time": t * 2.0, "strength": 1.0} for t in range(20)],
            "bar_length_candidates": [
                {"beats_per_bar": 3, "score": 1.0},
                {"beats_per_bar": 4, "score": score},
            ],
            "key": {"tonic": "A", "mode": "minor", "runner_up": {"tonic": "C", "mode": "major"}},
            "sections": [{"time": time, "strength": 0.5} for time in boundaries],
            "warnings": ["unverified"],
        },
    )


def _music(root: Path, duration: float = 40.0) -> dict:
    """A measurement with the fields a real pass writes, and a quiet opening."""
    music = {
        "duration": duration,
        "estimated_tempo_bpm": 118.0,
        "beats": [t * 0.5 for t in range(int(duration * 2))],
        "sections": [
            {"start": 0.0, "end": 25.0, "energy": 0.3, "label": "unreviewed"},
            {"start": 25.0, "end": duration, "energy": 0.7, "label": "unreviewed"},
        ],
        "energy_curve": [
            {"time": float(t), "energy": 0.1 if t < 10 else 0.9} for t in range(int(duration))
        ],
        "candidate_changes": [{"time": 10.2, "spectral_change": 0.9}],
        "warnings": [],
    }
    write_json(root / "work/music.json", music)
    return music


def _film(tmp_path: Path, **deep) -> Path:
    root = make_api_project(tmp_path)
    _music(root)
    if deep.pop("with_deep", True):
        _deep(root, **deep)
    return root


def test_a_film_with_a_deep_pass_gets_sections_from_the_music(tmp_path):
    root = _film(tmp_path)
    song = song_map.song_map(root)
    assert song["sections_source"] == "music-deep.json"
    assert [item["start"] for item in song["sections"]] == [0.0, 10.0, 20.0, 30.0]
    assert song["sections"][-1]["end"] == 40.0
    assert song["sections"][0]["energy_word"] == "quiet"
    assert song["sections"][1]["energy_word"] == "full"
    assert song["tempo"]["bpm"] == 120.0
    assert song["key"]["runner_up"] == "C major"
    assert song["beats_per_bar"] == 4
    assert song["grid_trusted"] is True
    assert song["bar_frames"] == 48
    assert all(isinstance(frame, int) for frame in song["downbeats"])
    assert len(song["sparkline"]) <= song_map.SPARK_POINTS


def test_with_no_deep_file_it_falls_back_and_says_so(tmp_path):
    root = _film(tmp_path, with_deep=False)
    measured = read_json(root / "work/music.json")["sections"]
    song = song_map.song_map(root)
    assert song["deep"] is False
    assert song["sections_source"] == "music.json"
    assert [item["start"] for item in song["sections"]] == [item["start"] for item in measured]
    assert song["grid_trusted"] is False
    assert song["downbeats"] == []


def test_too_few_boundaries_fall_back(tmp_path):
    root = _film(tmp_path, boundaries=(10.0,))
    assert song_map.song_map(root)["sections_source"] == "music.json"


def test_a_low_bar_score_is_not_a_trusted_grid(tmp_path):
    root = _film(tmp_path, score=1.05)
    assert song_map.song_map(root)["grid_trusted"] is False


def test_the_owners_sections_stay_on_top(tmp_path):
    root = _film(tmp_path)
    section_map.save(root, {"sections": [{"start": 0, "name": "Mine"}]}, 40.0)
    song = song_map.song_map(root)
    assert [item["name"] for item in song["sections"]] == ["Mine"]
    assert song["sections_source"] == "section-map.json"
    section_map.reset(root)
    assert song_map.song_map(root)["sections_source"] == "music-deep.json"


def test_names_already_given_keep_their_sections(tmp_path):
    root = _film(tmp_path, with_deep=False)
    measured = read_json(root / "work/music.json")["sections"]
    music_notes.save(
        root,
        {
            "sections": [
                {"start": item["start"], "name": f"Named {index}"}
                for index, item in enumerate(measured)
            ]
        },
    )
    _deep(root)
    song = song_map.song_map(root)
    assert song["sections_source"] == "music.json"
    assert song["sections"][0]["name"] == "Named 0"


def test_it_is_cached_until_an_input_changes(tmp_path):
    root = _film(tmp_path, with_deep=False)
    first = song_map.song_map(root)
    stamp = (root / song_map.FILE).stat().st_mtime_ns
    assert song_map.song_map(root) == first
    assert (root / song_map.FILE).stat().st_mtime_ns == stamp
    _deep(root)
    assert song_map.song_map(root)["deep"] is True


def test_music_json_and_every_stage_hash_hold(tmp_path):
    root = _film(tmp_path, with_deep=False)

    def state():
        hashes = {}
        for stage in STAGE_FILES:
            try:
                hashes[stage] = P.stage_hash(root, stage)
            except (FileNotFoundError, ValueError):
                hashes[stage] = None
        return hashes, (root / "work/music.json").read_bytes()

    before = state()
    assert any(before[0].values())
    _deep(root)
    song_map.song_map(root)
    section_map.apply(root, read_json(root / "work/music.json"))
    assert state() == before


def test_density_follows_energy_and_the_bar_and_respects_the_shortest_shot():
    assert pacing.density_plan(["quiet", "middle", "full"], 4, 60.0) == [1.25, 2.5, 6.25]
    assert pacing.density_plan(["full"], 4, 120.0) == [6.67]
    assert pacing.density_plan(["quiet", "full"], None, None) == [1.5, 5.0]


def test_the_route_and_the_snapshot_carry_it(tmp_path):
    root = _film(tmp_path)
    with api_client(tmp_path) as client:
        body = client.get(f"/api/projects/{root.name}/song-map").json()
    assert body["sections"][0]["name"]
    snapshot = build_context(root.name, tmp_path, task="concepts")
    assert "## The song (measured estimates)" in snapshot
    assert "key A minor, or C major" in snapshot
    assert "about" in snapshot and "cuts per 10 s" in snapshot


def test_writer_tasks_see_the_sung_lines_and_the_whole_treatment(tmp_path):
    root = _film(tmp_path, with_deep=False)
    write_json(root / "work/lyrics.json", {"lines": ["[Verse]", "First line", "Second line"]})
    write_json(
        root / "work/lyric-timing.json",
        {"lines": [{"text": "First line", "start": 65.0, "end": None, "source": "tapped"}]},
    )
    brief = read_json(root / "brief.json")
    brief["treatment"] = "word " * 300
    write_json(root / "brief.json", brief)
    concepts = build_context(root.name, tmp_path, task="concepts")
    assert "## Sung lines (1 of 2 timed)" in concepts
    assert "- 1:05 (tapped) First line" in concepts
    assert "- Second line" in concepts
    assert ("word " * 299).strip() in concepts
    other = build_context(root.name, tmp_path, task="profile")
    assert "## Sung lines" not in other
    assert ("word " * 299).strip() not in other
    assert json.dumps(concepts)


def test_a_failed_deep_pass_keeps_the_measurement(tmp_path, monkeypatch):
    from mp3_to_videoclip import services

    root = make_api_project(tmp_path)
    monkeypatch.setattr(
        "mp3_to_videoclip.analysis.analyze", lambda audio, duration: {"sections": [], "duration": 1}
    )
    monkeypatch.setattr(P, "render_audio", lambda root, project: root / "x")

    def fail(_root):
        raise RuntimeError("deep pass broke")

    monkeypatch.setattr(services.analysis, "deep_analyze_project", fail)
    assert services.analysis.analyze_project(root, force=True)["reused"] is False
    assert read_json(root / "work/music.json")["duration"] == 1
