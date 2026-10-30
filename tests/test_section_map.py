import pytest

from mp3_to_videoclip.domain import lyric_timing, music_notes, section_map
from mp3_to_videoclip.storage import read_json, write_json

MUSIC = {
    "duration": 100.0,
    "sections": [
        {"start": 0.0, "end": 30.0, "energy": 0.2, "label": "unreviewed"},
        {"start": 30.0, "end": 60.0, "energy": 0.5, "label": "unreviewed"},
        {"start": 60.0, "end": 100.0, "energy": 0.4, "label": "unreviewed"},
    ],
    "energy_curve": [{"time": float(t), "energy": 0.5} for t in range(100)],
}


@pytest.fixture
def root(tmp_path):
    (tmp_path / "work").mkdir()
    write_json(tmp_path / "work/music.json", MUSIC)
    return tmp_path


def _sections(*pairs):
    return {"sections": [{"start": start, "name": name} for start, name in pairs]}


def test_without_a_map_the_measured_sections_and_names_show(root):
    music_notes.save(root, _sections((0.0, "Intro"), (30.0, "Section 2"), (60.0, "Section 3")))
    shown = section_map.apply(root, read_json(root / "work/music.json"))
    assert [s["start"] for s in shown["sections"]] == [0.0, 30.0, 60.0]
    assert shown["sections"][0]["name"] == "Intro"
    assert section_map.read(root) is None


def test_a_map_replaces_what_shows_and_leaves_the_measurement_alone(root):
    before = read_json(root / "work/music.json")
    section_map.save(root, _sections((0, "Intro"), (40, "Hook")), duration=100)
    assert read_json(root / "work/music.json") == before
    shown = section_map.apply(root, before)
    assert [(s["start"], s["end"], s["name"]) for s in shown["sections"]] == [
        (0.0, 40.0, "Intro"),
        (40.0, 100.0, "Hook"),
    ]
    assert shown["sections"][1]["energy"] == pytest.approx(0.5)


def test_reset_returns_to_detected_sections_and_keeps_surviving_names(root):
    section_map.save(root, _sections((0, "Intro"), (40, "Moved"), (60, "Verse")), duration=100)
    section_map.reset(root)
    assert section_map.read(root) is None
    shown = section_map.apply(root, read_json(root / "work/music.json"))
    assert [s["start"] for s in shown["sections"]] == [0.0, 30.0, 60.0]
    assert [s["name"] for s in shown["sections"]] == ["Intro", "Section 2", "Verse"]


def test_reset_with_no_map_changes_nothing(root):
    section_map.reset(root)
    assert section_map.read(root) is None


@pytest.mark.parametrize(
    "payload, message",
    [
        (_sections((5, "Late")), "beginning"),
        (_sections((0, "A"), (1, "B")), "at least"),
        (_sections((0, "A"), (50, "B"), (40, "C")), "at least"),
        (_sections((0, "A"), (99, "B")), "at least"),
        (_sections((0, "")), "name"),
        ({"sections": []}, "sections list"),
        ({"sections": [{"start": True, "name": "A"}]}, "seconds"),
    ],
)
def test_bad_maps_are_refused(root, payload, message):
    with pytest.raises(ValueError, match=message):
        section_map.save(root, payload, duration=100)
    assert section_map.read(root) is None


def test_a_map_needs_a_measured_song(tmp_path):
    (tmp_path / "work").mkdir()
    with pytest.raises(ValueError, match="measure"):
        section_map.save(tmp_path, _sections((0, "A")), duration=100)


def _lyrics(root, lines):
    write_json(
        root / "work/lyrics.json",
        {"provider": "manual", "model": "text", "segments": [], "lines": lines},
    )


def test_a_proposal_needs_tags_and_times(root):
    _lyrics(root, ["one", "two"])
    with pytest.raises(ValueError, match="no \\[Verse\\]"):
        section_map.propose(root, 100)
    _lyrics(root, ["[Hook]", "one"])
    with pytest.raises(ValueError, match="on the song first"):
        section_map.propose(root, 100)


def test_a_proposal_uses_first_words_last_words_and_nearby_edges(root):
    _lyrics(root, ["intro line", "[Hook]", "one", "[Break]", "[Verse]", "two", "[Outro]", "three"])
    lyric_timing.save(
        root,
        {
            "lines": [
                {"index": 0, "start": 5.0, "end": 8.0, "source": "auto"},
                # 33 s is just after the detected edge at 30 s, so it moves there.
                {"index": 2, "start": 33.0, "end": 45.0, "source": "auto"},
                {"index": 5, "start": 50.0, "end": 55.0, "source": "auto"},
                {"index": 7, "start": 80.0, "end": 85.0, "source": "auto"},
            ]
        },
        duration=100,
    )
    proposed = section_map.propose(root, 100)
    assert [(item["start"], item["name"]) for item in proposed] == [
        (0.0, "Section 1"),
        (30.0, "Hook"),
        (45.0, "Break"),
        (50.0, "Verse"),
        (80.0, "Outro"),
    ]
    # Nothing is saved until it's accepted, and a proposal is a valid map.
    assert section_map.read(root) is None
    section_map.save(root, {"sections": proposed}, duration=100)


def test_a_finer_detected_edge_can_be_used(root):
    write_json(root / "work/music-deep.json", {"sections": [{"time": 48.0}, 49.5]})
    _lyrics(root, ["first", "[Hook]", "one"])
    lyric_timing.save(
        root,
        {
            "lines": [
                {"index": 0, "start": 5.0, "end": 8.0, "source": "auto"},
                {"index": 2, "start": 52.0, "source": "auto"},
            ]
        },
        duration=100,
    )
    assert section_map.propose(root, 100)[1] == {"start": 49.5, "name": "Hook"}


def test_a_tag_before_any_sung_line_opens_the_song(root):
    _lyrics(root, ["[Intro]", "one", "[Verse]", "two"])
    lyric_timing.save(
        root,
        {
            "lines": [
                {"index": 1, "start": 6.0, "end": 8.0, "source": "auto"},
                {"index": 3, "start": 20.0, "source": "auto"},
            ]
        },
        duration=100,
    )
    assert [(item["start"], item["name"]) for item in section_map.propose(root, 100)] == [
        (0.0, "Intro"),
        (20.0, "Verse"),
    ]


def test_an_edge_never_pulls_a_section_back_across_a_sung_word(root):
    write_json(root / "work/music-deep.json", {"sections": [{"time": 43.0}, {"time": 74.0}]})
    _lyrics(root, ["first", "[Hook]", "one", "[Break]", "[Verse]", "two"])
    lyric_timing.save(
        root,
        {
            "lines": [
                {"index": 0, "start": 5.0, "end": 8.0, "source": "auto"},
                {"index": 2, "start": 40.0, "end": 46.0, "source": "auto"},
                {"index": 5, "start": 76.0, "end": 80.0, "source": "auto"},
            ]
        },
        duration=100,
    )
    proposed = section_map.propose(root, 100)
    # The edge at 43 s is inside the sung line, so the break waits for its last word.
    assert [(item["start"], item["name"]) for item in proposed] == [
        (0.0, "Section 1"),
        (40.0, "Hook"),
        (46.0, "Break"),
        (74.0, "Verse"),
    ]
