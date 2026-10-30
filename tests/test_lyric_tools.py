import json
import subprocess

import pytest

from mp3_to_videoclip import lyric_tools
from mp3_to_videoclip.domain import lyric_timing
from mp3_to_videoclip.storage import read_json, write_json


def _tokens(*words):
    """(word, start) pairs as the recogniser reports them: a space opens each word."""
    return [{"text": f" {word}", "start": at, "end": at + 0.4} for word, at in words]


def _rows(*lines):
    return [
        {"index": index, "text": text, "tag": lyric_timing.tag_of(text)}
        for index, text in enumerate(lines)
    ]


def test_pieces_join_into_words():
    tokens = [
        {"text": " Hel", "start": 1.0, "end": 1.2},
        {"text": "lo,", "start": 1.2, "end": 1.5},
        {"text": " you", "start": 2.0, "end": 2.2},
    ]
    assert lyric_tools.heard_words(tokens) == [
        {"text": "hello", "start": 1.0, "end": 1.5},
        {"text": "you", "start": 2.0, "end": 2.2},
    ]


def test_lines_get_the_time_of_their_heard_words_and_tags_get_none():
    rows = _rows("[Hook]", "hey you stay", "come back through")
    tokens = _tokens(("hey", 1), ("you", 2), ("stay", 3), ("come", 5), ("back", 6), ("through", 7))
    times = lyric_tools.match_lines(rows, tokens)
    assert times == {1: (1.0, 3.4), 2: (5.0, 7.4)}


def test_a_line_that_was_not_heard_gets_no_time():
    rows = _rows("one two three", "never sung at all", "four five six")
    tokens = _tokens(("one", 1), ("two", 2), ("three", 3), ("four", 8), ("five", 9), ("six", 10))
    times = lyric_tools.match_lines(rows, tokens)
    assert set(times) == {0, 2}
    assert times[2][0] == 8.0


def test_a_repeated_hook_lands_on_its_own_repeat_in_order():
    rows = _rows("stay a little", "a verse between them", "stay a little")
    tokens = _tokens(
        ("stay", 1),
        ("a", 2),
        ("little", 3),
        ("a", 5),
        ("verse", 6),
        ("between", 7),
        ("them", 8),
        ("stay", 20),
        ("a", 21),
        ("little", 22),
    )
    times = lyric_tools.match_lines(rows, tokens)
    assert [times[0][0], times[1][0], times[2][0]] == [1.0, 5.0, 20.0]


def test_close_spellings_still_count():
    times = lyric_tools.match_lines(
        _rows("korrekt ouderwets"), _tokens(("correct", 1), ("oude", 2), ("wets", 3))
    )
    assert times and times[0][0] == 1.0


@pytest.fixture
def film(tmp_path, monkeypatch):
    """A song with heard words already cached, so no tool can run."""
    monkeypatch.setenv("STUDIO_LYRIC_TOOLS", str(tmp_path / "tools"))
    root = tmp_path / "film"
    (root / "work").mkdir(parents=True)
    audio = root / "song.wav"
    audio.write_bytes(b"not really audio")
    write_json(
        root / "work/lyrics.json",
        {
            "provider": "manual",
            "model": "text",
            "segments": [],
            "lines": ["[Hook]", "one two", "three four", "five six"],
        },
    )

    class Project:
        duration = 60.0

    from mp3_to_videoclip import production as P

    monkeypatch.setattr(P, "load_project", lambda _root: Project())
    monkeypatch.setattr(P, "render_audio", lambda _root, _project=None: audio)
    write_json(
        lyric_tools._heard_path(root, audio),
        {
            "tokens": _tokens(
                ("one", 1), ("two", 2), ("three", 4), ("four", 5), ("five", 7), ("six", 8)
            )
        },
    )
    return root


def test_timing_writes_only_its_own_file(film):
    before = read_json(film / "work/lyrics.json")
    assert lyric_tools.time_lyrics(film) == {"timed": 3, "sung": 3}
    assert read_json(film / "work/lyrics.json") == before
    rows = lyric_timing.view(film)["lines"]
    assert [row["source"] for row in rows] == [None, "auto", "auto", "auto"]


def test_tapped_lines_are_never_overwritten(film):
    lyric_timing.save(film, {"lines": [{"index": 2, "start": 4.5, "source": "tapped"}]}, 60.0)
    lyric_tools.time_lyrics(film)
    rows = lyric_timing.view(film)["lines"]
    assert (rows[2]["start"], rows[2]["source"]) == (4.5, "tapped")
    assert rows[1]["source"] == "auto" and rows[3]["source"] == "auto"


def test_a_line_that_would_land_before_a_tapped_one_stays_untimed(film):
    lyric_timing.save(film, {"lines": [{"index": 1, "start": 6.0, "source": "tapped"}]}, 60.0)
    lyric_tools.time_lyrics(film)
    rows = lyric_timing.view(film)["lines"]
    assert rows[2]["start"] is None
    assert rows[3]["start"] == 7.0


def test_timing_without_tools_or_a_cache_asks_for_setup(film):
    next(iter((film / lyric_tools.HEARD_DIR).glob("*.json"))).unlink()
    with pytest.raises(ValueError, match="set up"):
        lyric_tools.time_lyrics(film)
    assert not (film / lyric_timing.FILE).exists()


def test_status_needs_a_marker_matching_this_lock(tmp_path, monkeypatch):
    monkeypatch.setenv("STUDIO_LYRIC_TOOLS", str(tmp_path))
    monkeypatch.setattr(lyric_tools.sys, "platform", "darwin")
    monkeypatch.setattr(lyric_tools.platform, "machine", lambda: "arm64")
    monkeypatch.setattr(lyric_tools.shutil, "which", lambda _name: "/usr/bin/uv")
    assert lyric_tools.status()["ready"] is False
    (tmp_path / "env/bin").mkdir(parents=True)
    (tmp_path / "env/bin/python").write_text("")
    (tmp_path / "ready.json").write_text(json.dumps({"lock": "old"}))
    assert lyric_tools.status()["ready"] is False
    (tmp_path / "ready.json").write_text(json.dumps({"lock": lyric_tools._lock_hash()}))
    assert lyric_tools.status()["ready"] is True


def test_other_machines_are_told_why_and_keep_tapping(tmp_path, monkeypatch):
    monkeypatch.setenv("STUDIO_LYRIC_TOOLS", str(tmp_path))
    monkeypatch.setattr(lyric_tools.sys, "platform", "linux")
    state = lyric_tools.status()
    assert state["supported"] is False and "tap" in state["reason"]
    with pytest.raises(ValueError, match="Apple Silicon"):
        lyric_tools.install()


def test_stop_ends_the_process(monkeypatch):
    monkeypatch.setattr(lyric_tools.operations, "stop_requested", lambda: True)
    with pytest.raises(ValueError, match="stopped"):
        lyric_tools._run(["/bin/sleep", "30"])


def test_a_failed_tool_says_so():
    with pytest.raises(ValueError, match="lyric tools failed"):
        lyric_tools._run(["/bin/sh", "-c", "echo broken >&2; exit 3"])


def test_the_worker_imports_nothing_from_the_project():
    source = lyric_tools.WORKER.read_text()
    assert "mp3_to_videoclip" not in source
    result = subprocess.run(
        ["python3", "-I", "-c", f"import ast;ast.parse(open({str(lyric_tools.WORKER)!r}).read())"],
        check=False,
    )
    assert result.returncode == 0
