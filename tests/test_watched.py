"""Heard seconds: unioned, append-only, keyed by the file's bytes. Evidence, not proof."""

from __future__ import annotations

import pytest
from test_publish import _stamped_final, film  # noqa: F401

from mp3_to_videoclip import watched
from mp3_to_videoclip.storage import read_json, write_json

# ------------------------------------------------------------------ heard


def test_heard_seconds_are_unioned_and_a_new_final_starts_over(film):  # noqa: F811
    root = film
    final = _stamped_final(root)
    media = f"renders/{final.name}"
    first = watched.record(root, media, [0, 1, 1, 2])
    assert first == {"media": media, "heard": 3, "total": 4, "share": 0.75, "watched": False}
    assert watched.record(root, media, [3])["watched"] is True
    assert watched.record(root, media, [])["heard"] == 4  # nothing is ever forgotten
    assert watched.coverage(root, media)["share"] == 1.0
    with pytest.raises(ValueError, match="whole numbers"):
        watched.record(root, media, [1.5])
    with pytest.raises(ValueError, match="name the media"):
        watched.record(root, "../x", [1])
    # Other bytes under the same name are another film: the count starts again.
    stored = read_json(root / watched.FILE)
    stored["media"][media]["sha256"] = "0" * 64
    write_json(root / watched.FILE, stored)
    assert watched.coverage(root, media)["heard"] == 0
    assert watched.record(root, media, [0])["heard"] == 1
    # The live Player's mix is its own media, with the total the browser knows.
    live = watched.record(root, "live:abc", [0, 1, 2, 3, 4], total=5)
    assert live["watched"] is True and live["total"] == 5
    assert watched.coverage(root, "live:abc", total=5)["share"] == 1.0


def test_the_last_second_may_be_missed_and_the_film_still_counts_as_heard(film):  # noqa: F811
    root = film
    final = _stamped_final(root, seconds=100)
    media = f"renders/{final.name}"
    assert watched.record(root, media, list(range(97)))["watched"] is False
    assert watched.record(root, media, [97])["watched"] is True
