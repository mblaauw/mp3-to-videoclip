"""Embedded faces come from the repository's bytes, and only when a film asks for one."""

from __future__ import annotations

import base64
from pathlib import Path

from mp3_to_videoclip import remotion, signature
from mp3_to_videoclip.models import Grade


def test_every_face_is_a_real_woff2_with_its_licence():
    for family, file in remotion.TYPEFACES.values():
        path = remotion.FONTS / file
        assert path.read_bytes()[:4] == b"wOF2", family
        assert (remotion.FONTS / f"OFL-{Path(file).stem}.txt").is_file()


def test_a_face_is_embedded_as_data_and_named():
    faces = remotion.typefaces_input(["fraunces", None, "fraunces"])
    assert list(faces) == ["fraunces"]
    assert faces["fraunces"]["family"] == "Fraunces"
    head, data = faces["fraunces"]["src"].split(",", 1)
    assert head == "data:font/woff2;base64"
    assert base64.b64decode(data)[:4] == b"wOF2"


def test_a_spec_with_no_typeface_keeps_the_system_stack(monkeypatch):
    spec = {"intro": {"mark": {"kind": "filmstrip"}}}
    palette = {"accent": (1, 2, 3)}
    assert remotion.title_assets(spec, palette)["font"] is None
    named = remotion.title_assets({**spec, "typeface": "bebas"}, palette)
    assert named["font"].startswith("data:font/woff2")


def test_a_grade_without_a_face_serialises_as_before():
    assert "typeface" not in Grade().model_dump()
    assert Grade(typeface="inter").model_dump()["typeface"] == "inter"


def test_a_new_film_takes_its_looks_face_and_no_face_changes_nothing():
    plain = signature.draft_spec("Song")
    assert "typeface" not in plain
    assert signature.draft_spec("Song", None, "fraunces")["typeface"] == "fraunces"


def test_the_renderer_revision_no_longer_reads_this_computers_font(monkeypatch):
    before = remotion.implementation_hash()
    monkeypatch.setattr("mp3_to_videoclip.graphics.resolve_font", lambda: 1 / 0)
    assert remotion.implementation_hash() == before
