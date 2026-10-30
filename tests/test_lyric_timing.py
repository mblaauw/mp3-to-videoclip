import pytest

from mp3_to_videoclip.domain import lyric_timing
from mp3_to_videoclip.storage import read_json, write_json


def _song(tmp_path, lines):
    (tmp_path / "work").mkdir(exist_ok=True)
    write_json(
        tmp_path / "work/lyrics.json",
        {"provider": "manual", "model": "text", "segments": [], "lines": lines},
    )
    return tmp_path


LINES = ["[Hook]", "one", "two", "[Break]", "three"]


def _timed(root, *starts):
    view = lyric_timing.view(root)["lines"]
    sung = [row["index"] for row in view if not row["tag"]]
    return [
        {"index": index, "start": start, "end": None, "source": "tapped"}
        for index, start in zip(sung, starts, strict=False)
    ]


def test_tags_are_headings_with_no_time(tmp_path):
    root = _song(tmp_path, LINES)
    rows = lyric_timing.view(root)["lines"]
    assert [row["tag"] for row in rows] == ["Hook", None, None, "Break", None]
    assert all(row["start"] is None for row in rows)
    with pytest.raises(ValueError, match="not sung"):
        lyric_timing.save(
            root, {"lines": [{"index": 0, "start": 1, "source": "tapped"}]}, duration=60
        )


def test_times_survive_a_reload_and_leave_the_words_alone(tmp_path):
    root = _song(tmp_path, LINES)
    before = read_json(root / "work/lyrics.json")
    lyric_timing.save(root, {"lines": _timed(root, 1.5, 3.0)}, duration=60)
    assert read_json(root / "work/lyrics.json") == before
    rows = lyric_timing.view(root)["lines"]
    assert [(row["text"], row["start"]) for row in rows if not row["tag"]] == [
        ("one", 1.5),
        ("two", 3.0),
        ("three", None),
    ]


def test_editing_the_words_clears_only_the_changed_lines(tmp_path):
    root = _song(tmp_path, LINES)
    lyric_timing.save(root, {"lines": _timed(root, 1.0, 2.0, 3.0)}, duration=60)
    _song(root, ["[Hook]", "one", "a new line", "[Break]", "three"])
    rows = [row for row in lyric_timing.view(root)["lines"] if not row["tag"]]
    assert [(row["text"], row["start"]) for row in rows] == [
        ("one", 1.0),
        ("a new line", None),
        ("three", 3.0),
    ]


def test_repeated_lines_keep_their_own_times(tmp_path):
    root = _song(tmp_path, ["hook", "verse", "hook"])
    lyric_timing.save(root, {"lines": _timed(root, 1.0, 2.0, 3.0)}, duration=60)
    assert [row["start"] for row in lyric_timing.view(root)["lines"]] == [1.0, 2.0, 3.0]


@pytest.mark.parametrize(
    "lines, message",
    [
        ([{"index": 1, "start": 99, "source": "tapped"}], "inside the song"),
        ([{"index": 1, "start": "1", "source": "tapped"}], "number"),
        ([{"index": 9, "start": 1, "source": "tapped"}], "not in the lyrics"),
        ([{"index": 1, "start": 1, "source": "guess"}], "tapped or auto"),
        ([{"index": 1, "start": 5, "end": 4, "source": "auto"}], "follow its start"),
        (
            [
                {"index": 1, "start": 5, "source": "tapped"},
                {"index": 2, "start": 4, "source": "tapped"},
            ],
            "in order",
        ),
    ],
)
def test_bad_times_are_refused(tmp_path, lines, message):
    root = _song(tmp_path, LINES)
    with pytest.raises(ValueError, match=message):
        lyric_timing.save(root, {"lines": lines}, duration=60)
    assert not (root / lyric_timing.FILE).exists()


def test_an_lrc_lines_own_time_shows_but_is_not_stored(tmp_path):
    (tmp_path / "work").mkdir()
    write_json(
        tmp_path / "work/lyrics.json",
        {
            "provider": "manual",
            "model": "lrc",
            "segments": [{"start": 4.0, "end": 8.0, "text": "one"}],
        },
    )
    rows = lyric_timing.view(tmp_path)["lines"]
    assert rows[0]["start"] == 4.0 and rows[0]["source"] == "lrc"


def test_a_multi_line_segment_gives_no_line_a_time(tmp_path):
    (tmp_path / "work").mkdir()
    write_json(
        tmp_path / "work/lyrics.json",
        {
            "provider": "manual",
            "model": "sections",
            "segments": [{"start": 4.0, "end": 8.0, "text": "one\ntwo"}],
        },
    )
    assert [row["start"] for row in lyric_timing.view(tmp_path)["lines"]] == [None, None]
