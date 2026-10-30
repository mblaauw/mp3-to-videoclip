"""Integer-frame title windows, and their parity with the float-second compositor."""

from __future__ import annotations

import math

import pytest
from test_edits import _energetic_edit, _energetic_root

from mp3_to_videoclip import edits, titles


def _spec(cards: int = 5, *, design: str | None = "joint-v1", captions=None) -> dict:
    spec = {
        "intro_seconds": 25.0,
        "credits_tail_seconds": 40.0,
        "lockup_seconds": 4.0,
        "captions": captions or [],
        "credits": {"cards": [[f"ROLE {i}", f"NAME {i}"] for i in range(cards)]},
    }
    if design:
        spec["design"] = design
    return spec


def _float_plan(spec: dict, duration: float, fps: int, captions=None):
    """The compositor's float-second planner before the frame plan, verbatim in effect."""
    intro_frames = max(1, round(float(spec["intro_seconds"]) * fps))
    total = math.ceil(duration * fps)
    credits_start = duration - float(spec["credits_tail_seconds"])
    lockup_seconds = float(spec["lockup_seconds"])
    credits_tail = float(spec["credits_tail_seconds"])
    parts = [{"kind": "intro", "id": "intro", "start": 0.0, "frames": intro_frames}]
    for cap in sorted(captions or spec["captions"], key=lambda c: float(c["start"])):
        start, end = float(cap["start"]), float(cap["end"])
        parts.append(
            {
                "kind": "caption",
                "id": cap["id"],
                "start": start,
                "frames": max(1, round((end - start) * fps)),
            }
        )
    cursor = credits_start
    cards = spec["credits"]["cards"]
    identity_span = 0.0
    if spec.get("design") == "joint-v1":
        identity_span = max(0.0, min(6.0, (credits_tail - lockup_seconds) / (len(cards) + 1)))
        if identity_span > 0:
            frames = max(1, round(identity_span * fps))
            parts.append({"kind": "identity", "id": "identity", "start": cursor, "frames": frames})
            cursor += frames / fps
    card_span = (credits_tail - lockup_seconds - identity_span) / len(cards)
    for index in range(len(cards)):
        frames = max(1, round(card_span * fps))
        parts.append(
            {"kind": "card", "id": f"card-{index + 1:02d}", "start": cursor, "frames": frames}
        )
        cursor += frames / fps
    lock_frames = max(1, total - round(cursor * fps))
    parts.append({"kind": "lockup", "id": "lockup", "start": cursor, "frames": lock_frames})
    parts.sort(key=lambda p: p["start"])
    return parts, total


@pytest.mark.parametrize("fps", [24, 25, 30])
@pytest.mark.parametrize("duration", [65.0, 199.96, 222.8, 239.8, 239.9583, 240.0, 251.37])
@pytest.mark.parametrize("cards", [1, 2, 5, 9])
@pytest.mark.parametrize("design", [None, "joint-v1"])
def test_every_window_lands_on_the_frame_the_compositor_drew(fps, duration, cards, design):
    spec = _spec(cards, design=design)
    windows, total = titles.plan_titles(spec, fps=fps, duration=duration)
    old, old_total = _float_plan(spec, duration, fps)
    assert total == old_total
    assert [(w["kind"], w["id"], w["frames"]) for w in windows] == [
        (p["kind"], p["id"], p["frames"]) for p in old
    ]
    # The compositor placed every element at round(start * fps).
    assert [w["start_frame"] for w in windows] == [round(p["start"] * fps) for p in old]
    assert all(isinstance(w["start_frame"], int) for w in windows)
    last = windows[-1]
    assert last["kind"] == "lockup"
    assert last["start_frame"] + last["frames"] == total


def test_windows_are_contiguous_through_the_credits_and_never_overlap():
    windows, total = titles.plan_titles(_spec(5), fps=24, duration=239.8)
    package = [w for w in windows if w["kind"] in ("identity", "card", "lockup")]
    for earlier, later in zip(package, package[1:], strict=False):
        assert earlier["start_frame"] + earlier["frames"] == later["start_frame"]
    assert [w["kind"] for w in package] == ["identity", *["card"] * 5, "lockup"]
    assert package[1]["card"] == ["ROLE 0", "NAME 0"] and package[1]["index"] == 0
    assert package[-1]["start_frame"] + package[-1]["frames"] == total


def test_captions_keep_clear_of_the_opening_and_the_credits():
    near_intro = [{"id": "early", "style": "caption", "text": "x", "start": 25.1, "end": 27.0}]
    with pytest.raises(titles.TitleError, match="inside the intro"):
        titles.plan_titles(_spec(captions=near_intro), fps=24, duration=240.0)
    near_credits = [{"id": "late", "style": "caption", "text": "x", "start": 190.0, "end": 199.9}]
    with pytest.raises(titles.TitleError, match="overlaps the credits"):
        titles.plan_titles(_spec(captions=near_credits), fps=24, duration=240.0)
    fine = [{"id": "mid", "style": "caption", "text": "x", "start": 60.0, "end": 63.5}]
    windows, _ = titles.plan_titles(_spec(captions=fine), fps=24, duration=240.0)
    caption = next(w for w in windows if w["kind"] == "caption")
    assert (caption["start_frame"], caption["frames"]) == (1440, 84)


def test_credits_need_a_card():
    with pytest.raises(titles.TitleError, match="at least one card"):
        titles.plan_titles(_spec(0), fps=24, duration=240.0)


def test_a_shot_bound_caption_follows_the_edit_not_the_storyboard(tmp_path):
    root = _energetic_root(tmp_path)
    edit = _energetic_edit()
    # The cut plays s002 first and s001 second.
    first, second = edit.shots[0], edit.shots[1]
    edit.shots[0] = second.model_copy(
        update={"start_frame": 0, "transition_in": first.transition_in}
    )
    edit.shots[1] = first.model_copy(update={"start_frame": 24})
    edits.save_edit(root, edit)
    caption = {"id": "c", "shot_id": "s001", "offset_frames": 2, "duration_frames": 6}
    spec = {"captions": [caption]}

    from mp3_to_videoclip import production as P

    storyboard = P.load_board(root)
    assert titles.resolve_titles(spec, storyboard, 24)[0]["start_frame"] == 2
    board = titles.timing_board(root, storyboard)
    resolved = titles.resolve_titles(spec, board, 24)[0]
    assert (resolved["start_frame"], resolved["end_frame"]) == (26, 32)
    assert titles.needs_board(spec)


def test_the_player_gets_the_planned_titles_or_says_why_not(tmp_path):
    from test_signature_iteration import signature_root

    from mp3_to_videoclip import production as P
    from mp3_to_videoclip import signature
    from mp3_to_videoclip.services.preview import player_input
    from mp3_to_videoclip.storage import read_json, write_json

    root = signature_root(tmp_path)
    spec = read_json(root / signature.SPEC)
    spec["renderer"] = "remotion"
    spec["intro"]["mark"] = {"kind": "filmstrip"}
    write_json(root / signature.SPEC, spec)

    payload = player_input(root, "production")
    assert payload["titles_note"] is None
    windows = payload["titles"]["windows"]
    assert windows[0]["id"] == "intro" and windows[0]["start_frame"] == 0
    total = P.load_project(root).total_frames
    assert windows[-1]["id"] == "lockup"
    assert windows[-1]["start_frame"] + windows[-1]["frames"] == total
    assert payload["titles"]["logo"].startswith("data:image/svg+xml;base64,")

    spec["captions"] = [
        {"id": "late", "style": "caption", "text": "x", "start": 160.0, "end": 170.0}
    ]
    write_json(root / signature.SPEC, spec)
    payload = player_input(root, "production")
    assert payload["titles"] is None
    assert "overlaps the credits" in payload["titles_note"]


def _review_root(tmp_path, monkeypatch):
    from test_signature_iteration import signature_root

    from mp3_to_videoclip import remotion, signature
    from mp3_to_videoclip.storage import file_hash

    draft = signature.draft_spec

    def remotion_draft(title):
        spec = draft(title)
        spec["renderer"] = "remotion"
        spec["intro"]["mark"] = {"kind": "filmstrip"}
        spec["intro"]["names"] = signature.FILMSTRIP_NAMES
        return spec

    # Shape the spec before the fixture approves anything that binds it.
    monkeypatch.setattr(signature, "draft_spec", remotion_draft)
    root = signature_root(tmp_path)
    renders = []

    def fake_stills(project, shots, frames, output, workdir, *, brand=None, titles=None):
        renders.append((list(frames), titles))
        output.mkdir(parents=True)
        stills = []
        for frame in sorted(set(frames)):
            name = f"f{frame:05d}.png"
            (output / name).write_bytes(f"frame {frame}".encode())
            stills.append({"frame": frame, "file": name, "sha256": file_hash(output / name)})
        return {"stills": stills}

    monkeypatch.setattr(remotion, "render_stills", fake_stills)
    monkeypatch.setattr(remotion, "implementation_hash", lambda: "renderer-r1")
    return root, renders


def test_a_titles_review_is_drawn_from_the_film_and_needs_no_base(tmp_path, monkeypatch):
    from mp3_to_videoclip import production as P
    from mp3_to_videoclip import signature
    from mp3_to_videoclip.services import render
    from mp3_to_videoclip.storage import read_json

    root, renders = _review_root(tmp_path, monkeypatch)
    assert not list((root / "renders").glob("*base*")) if (root / "renders").exists() else True

    review = render.check_titles(root)
    assert review["method"] == "composition-v1"
    assert "base" not in review
    frames, titles = renders[0]
    windows = {w["id"]: w for w in titles["windows"]}
    # Every non-intro window is sampled at its middle frame.
    for window in windows.values():
        if window["kind"] != "intro":
            assert window["start_frame"] + window["frames"] // 2 in frames
    recorded = read_json(root / review["preflight"])
    assert len(recorded["frames"]) == len(review["samples"]) == len(frames)
    assert {f["window"] for f in recorded["frames"]} >= set(windows) - {"intro"}

    assert signature.validate_review(root, P.load_project(root)) == review
    P.approve(root, "graphics", "test inspected samples", inspected=True)
    P.require_approval(root, "graphics")

    # A second check with unchanged inputs reuses the same stills.
    assert render.check_titles(root)["samples"] == review["samples"]
    assert len(renders) == 1


@pytest.mark.parametrize("change", ["spec", "sample", "renderer", "edit"])
def test_any_bound_input_makes_the_titles_review_stale(tmp_path, monkeypatch, change):
    from mp3_to_videoclip import edits, remotion, signature
    from mp3_to_videoclip import production as P
    from mp3_to_videoclip.services import render
    from mp3_to_videoclip.storage import read_json, write_json

    root, _renders = _review_root(tmp_path, monkeypatch)
    review = render.check_titles(root)
    if change == "spec":
        spec = read_json(root / signature.SPEC)
        spec["credits"]["cards"] = [["MUSIC", "Someone else"]]
        write_json(root / signature.SPEC, spec)
    elif change == "sample":
        (root / next(iter(review["samples"]))).write_bytes(b"edited")
    elif change == "renderer":
        monkeypatch.setattr(remotion, "implementation_hash", lambda: "renderer-r2")
    else:
        # The review binds the cut file through input_metadata_hash; this
        # fixture is not a Remotion production, so seed_edit would refuse it.
        write_json(root / edits.EDIT, {"marker": "a new cut"})
    with pytest.raises(ValueError):
        signature.validate_review(root, P.load_project(root))
