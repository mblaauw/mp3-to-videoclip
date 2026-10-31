"""A chunk's key changes with anything it shows, and not when its shot merely moves."""

import copy

import pytest

from mp3_to_videoclip.chunks import film_chunks


def _edit(start, length, frames_in=0, **extra):
    return {
        "shot_id": "x",
        "start_frame": start,
        "duration_frames": length,
        "motion": {"type": "push_in", "from": 1.0, "to": 1.1, "reason": "lean in"},
        "transition_in": {"type": "fade" if frames_in else "cut", "frames": frames_in},
        "accents": [],
        "text": [],
        "crops": [],
        **extra,
    }


def _shot(name, start, length, frames_in=0, **edit):
    return {
        "id": name,
        "start_frame": start,
        "duration_frames": length,
        "purpose": "p",
        "camera": "zoom_in",
        "dissolve_frames": 0,
        "image": f"{name}.png",
        "image_sha256": name * 8,
        "edit": _edit(start, length, frames_in, **edit),
        "grade": {"preset": "neutral", "look": {"grain": 0.3}},
    }


def _film():
    return {
        "shots": [
            _shot("a", 0, 48),
            _shot(
                "b",
                48,
                96,
                accents=[{"frame": 60, "type": "flash", "duration_frames": 6, "reason": "hit"}],
                crops=[{"frame": 80, "zoom": 1.3, "x": 0.5, "y": 0.5, "reason": "hands"}],
                text=[
                    {
                        "id": "t",
                        "style": "lyric",
                        "text": "words",
                        "in_frame": 50,
                        "out_frame": 90,
                        "animation": "fade",
                        "reason": "line",
                    }
                ],
            ),
            _shot("c", 144, 48, frames_in=12),
            _shot("d", 192, 48),
        ],
        "preview_banner": False,
        "preview_placeholders": [],
    }


def _keys(film, revision="r"):
    return {c.shot_id: c.key for c in film_chunks(film, (1920, 1080), 24, revision)}


def test_chunks_cover_every_frame_in_order():
    chunks = film_chunks(_film(), (1920, 1080), 24, "r")
    assert [(c.shot_id, c.start, c.last) for c in chunks] == [
        ("a", 0, 47),
        ("b", 48, 143),
        ("c", 144, 191),
        ("d", 192, 239),
    ]


def _shift_after(film, shot_id, by):
    moved = copy.deepcopy(film)
    shots = moved["shots"]
    at = [s["id"] for s in shots].index(shot_id)
    shots[at]["duration_frames"] += by
    shots[at]["edit"]["duration_frames"] += by
    for shot in shots[at + 1 :]:
        shot["start_frame"] += by
        edit = shot["edit"]
        edit["start_frame"] += by
        for item in edit["accents"] + edit["crops"]:
            item["frame"] += by
        for item in edit["text"]:
            item["in_frame"] += by
            item["out_frame"] += by
    return moved


def test_a_shot_that_only_moves_keeps_its_key():
    before = _keys(_film())
    after = _keys(_shift_after(_film(), "a", 24))
    assert after["a"] != before["a"]
    assert all(after[name] == before[name] for name in "bcd")


def test_lengthening_a_shot_before_a_transition_also_renews_the_one_after():
    before = _keys(_film())
    after = _keys(_shift_after(_film(), "b", 24))
    assert after["b"] != before["b"]
    # c fades in over b's tail, so c shows b's new length; d shows neither.
    assert after["c"] != before["c"]
    assert after["d"] == before["d"]


def test_a_hard_cut_hides_the_previous_shot():
    before = _keys(_film())
    film = _film()
    film["shots"][0]["image_sha256"] = "changed"
    after = _keys(film)
    assert after["a"] != before["a"]
    assert after["b"] == before["b"]


def test_a_transition_shows_the_previous_shot():
    before = _keys(_film())
    film = _film()
    film["shots"][1]["image_sha256"] = "changed"
    after = _keys(film)
    assert after["b"] != before["b"]
    assert after["c"] != before["c"]
    assert after["d"] == before["d"]


def test_a_new_transition_renews_the_outgoing_shot_because_its_move_runs_longer():
    before = _keys(_film())
    film = _film()
    film["shots"][3]["edit"]["transition_in"] = {"type": "fade", "frames": 12}
    after = _keys(film)
    assert after["c"] != before["c"]
    assert after["d"] != before["d"]
    assert after["a"] == before["a"]


def test_a_legacy_dissolve_shows_the_previous_shot():
    film = _film()
    for shot in film["shots"]:
        shot.pop("edit")
    film["shots"][0]["dissolve_frames"] = 12
    before = _keys(film)
    film["shots"][0]["image_sha256"] = "changed"
    after = _keys(film)
    assert after["a"] != before["a"]
    assert after["b"] != before["b"]
    assert after["c"] == before["c"]


@pytest.mark.parametrize(
    "field",
    sorted(set(_film()["shots"][1]) - {"id", "start_frame", "dissolve_frames", "edit"}),
)
def test_every_field_of_a_shot_reaches_its_key(field):
    before = _keys(_film())
    film = _film()
    film["shots"][1][field] = "anything else"
    assert _keys(film)["b"] != before["b"]


def test_an_unknown_future_field_invalidates_by_default():
    before = _keys(_film())
    film = _film()
    film["shots"][1]["future_setting"] = 1
    film["shots"][2]["edit"]["future_setting"] = 1
    after = _keys(film)
    assert after["b"] != before["b"]
    assert after["c"] != before["c"]


@pytest.mark.parametrize(
    "change",
    [
        lambda edit: edit["motion"].update(to=1.2),
        lambda edit: edit["accents"][0].update(frame=61),
        lambda edit: edit["crops"][0].update(frame=81),
        lambda edit: edit["crops"][0].update(zoom=1.4),
        lambda edit: edit["text"][0].update(text="other"),
        lambda edit: edit["text"][0].update(out_frame=91),
    ],
)
def test_everything_in_an_edit_that_draws_reaches_its_key(change):
    before = _keys(_film())
    film = _film()
    change(film["shots"][1]["edit"])
    assert _keys(film)["b"] != before["b"]


def test_written_reasons_draw_nothing():
    before = _keys(_film())
    film = _film()
    edit = film["shots"][1]["edit"]
    edit["motion"]["reason"] = "another thought"
    edit["crops"][0]["reason"] = "another thought"
    assert _keys(film) == before


@pytest.mark.parametrize(
    "change",
    [
        lambda film: film.update(capture={"format": "jpeg", "quality": 95}),
        lambda film: film.update(preview_banner=True),
    ],
)
def test_film_wide_settings_renew_every_chunk(change):
    before = _keys(_film())
    film = _film()
    change(film)
    assert all(after != before[name] for name, after in _keys(film).items())


def test_renderer_size_and_rate_renew_every_chunk():
    base = film_chunks(_film(), (1920, 1080), 24, "r")
    for other in (
        film_chunks(_film(), (1920, 1080), 24, "s"),
        film_chunks(_film(), (1280, 720), 24, "r"),
        film_chunks(_film(), (1920, 1080), 25, "r"),
    ):
        assert all(a.key != b.key for a, b in zip(base, other, strict=True))


def test_a_placeholder_only_renews_its_own_shot():
    before = _keys(_film())
    film = _film()
    film["preview_placeholders"] = ["b"]
    after = _keys(film)
    assert after["b"] != before["b"]
    assert after["a"] == before["a"]


def _titles(start=60, frames=48, spec="one"):
    return {
        "spec": spec,
        "logo": "data",
        "windows": [{"id": "w", "kind": "caption", "start_frame": start, "frames": frames}],
    }


def test_a_title_renews_only_the_chunks_it_touches():
    before = _keys(_film())
    film = _film()
    film["titles"] = _titles()
    after = _keys(film)
    assert after["a"] == before["a"]
    assert after["b"] != before["b"]
    assert after["c"] == before["c"]
    # Titled frames depend on the title's look as well as its place.
    film["titles"] = _titles(spec="two")
    assert _keys(film)["b"] != after["b"]
    film["titles"] = _titles(start=61)
    assert _keys(film)["b"] != after["b"]


def test_a_title_crossing_a_join_renews_both_chunks():
    film = _film()
    before = _keys(film)
    film["titles"] = _titles(start=130, frames=30)
    after = _keys(film)
    assert after["b"] != before["b"]
    assert after["c"] != before["c"]
    assert after["d"] == before["d"]


def test_a_title_moving_with_its_shot_keeps_the_key():
    film = _film()
    film["titles"] = _titles()
    before = _keys(film)
    moved = _shift_after(_film(), "a", 24)
    moved["titles"] = _titles(start=84)
    after = _keys(moved)
    assert after["b"] == before["b"]


def test_a_brand_plate_renews_the_chunks_under_it():
    before = _keys(_film())
    film = _film()
    film["brand_plate"] = "data:image/png;base64,AA"
    film["brand_duration_frames"] = 60
    after = _keys(film)
    assert after["a"] != before["a"]
    assert after["b"] != before["b"]
    assert after["c"] == before["c"]
    film["brand_plate"] = "data:image/png;base64,BB"
    assert _keys(film)["a"] != after["a"]
