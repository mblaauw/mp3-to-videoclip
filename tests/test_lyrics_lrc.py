"""LRC import keeps the user's timestamps and invents nothing."""

from __future__ import annotations

import pytest

from mp3_to_videoclip.domain.lyrics import parse_lrc


def test_lrc_lines_become_bounded_segments():
    lyrics = parse_lrc("[00:10.00] one\n[00:20.50] two", 30.0)
    assert lyrics.provider == "manual"
    assert lyrics.model == "lrc"
    assert [(s.start, s.end, s.text) for s in lyrics.segments] == [
        (10.0, 20.5, "one"),
        (20.5, 30.0, "two"),
    ]


def test_one_line_can_carry_several_timestamps():
    lyrics = parse_lrc("[00:01.00][00:05.00] chorus", 10.0)
    assert [s.start for s in lyrics.segments] == [1.0, 5.0]
    assert all(s.text == "chorus" for s in lyrics.segments)


@pytest.mark.parametrize(
    "text,duration",
    [
        ("plain words", 10.0),
        ("[00:61.00] wrong seconds", 100.0),
        ("[00:20.00] beyond", 10.0),
        ("[00:01.00] one\n[00:01.00] two", 10.0),
        ("", 10.0),
    ],
)
def test_invalid_lrc_is_rejected(text, duration):
    with pytest.raises(ValueError):
        parse_lrc(text, duration)
