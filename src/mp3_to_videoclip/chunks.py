"""Split a film into one chunk per shot and name each chunk by what it shows.

A chunk's key is the whole render reuse decision, so a wrong key would show a stale
picture. The rule is therefore subtractive: a shot's compiled entry goes into the key
as it is, except for the named position fields, which are made relative to the chunk's
start, and for written reasons, which draw nothing. A new field invalidates by default.

Frames of shot N show shot N and, during a transition, shot N-1, so every join falls on
a shot's first frame and never inside a transition. Shot N's move also runs through its
handle, which shot N+1's transition sets, so that length is part of N's key.
"""

from dataclasses import dataclass

from .storage import digest

KEY_VERSION = 1
# Written explanations of a choice; they never reach a pixel.
NOT_DRAWN = {"reason"}


@dataclass(frozen=True)
class Chunk:
    shot_id: str
    start: int
    frames: int
    key: str

    @property
    def last(self) -> int:
        return self.start + self.frames - 1


def _handle(shots: list[dict], index: int) -> int:
    """Frames shot ``index`` runs past its end; ``allocateSpans`` in the renderer's terms."""
    following = shots[index + 1] if index + 1 < len(shots) else None
    if following is not None and following.get("edit"):
        return following["edit"]["transition_in"]["frames"]
    return shots[index].get("dissolve_frames", 0)


def _without_notes(value):
    if isinstance(value, dict):
        return {k: _without_notes(v) for k, v in value.items() if k not in NOT_DRAWN}
    if isinstance(value, list):
        return [_without_notes(item) for item in value]
    return value


def _relative_edit(edit: dict, origin: int) -> dict:
    moved = {**edit, "start_frame": edit["start_frame"] - origin}
    for name, fields in (
        ("accents", ("frame",)),
        ("crops", ("frame",)),
        ("text", ("in_frame", "out_frame")),
    ):
        if name in edit:
            moved[name] = [
                {**item, **{field: item[field] - origin for field in fields}} for item in edit[name]
            ]
    return moved


def _relative_shot(shots: list[dict], index: int, origin: int) -> dict:
    shot = shots[index]
    moved = {
        **shot,
        "start_frame": shot["start_frame"] - origin,
        "resolved_handle": _handle(shots, index),
    }
    # The renderer takes a legacy dissolve from the incoming shot's edit when it has one,
    # so the declared value only counts through the resolved handle above.
    moved.pop("dissolve_frames", None)
    if shot.get("edit"):
        moved["edit"] = _relative_edit(shot["edit"], origin)
    return _without_notes(moved)


def _titles_in(titles: dict | None, start: int, frames: int) -> dict | None:
    if not titles:
        return None
    windows = [
        {**window, "start_frame": window["start_frame"] - start}
        for window in titles["windows"]
        if window["start_frame"] < start + frames
        and start < window["start_frame"] + window["frames"]
    ]
    if not windows:
        return None
    return {**{k: v for k, v in titles.items() if k != "windows"}, "windows": windows}


def _brand_in(inputs: dict, start: int, fps: int) -> dict | None:
    plate = inputs.get("brand_plate")
    if not plate:
        return None
    # The renderer's own default length is longer than any plate we pass without one,
    # so a plate without a stated length always counts as overlapping.
    length = inputs.get("brand_duration_frames")
    if length is not None and start >= length:
        return None
    return {"plate": plate, "frames": length, "start": start, "fps": fps}


def film_chunks(inputs: dict, canvas: tuple[int, int], fps: int, revision: str) -> list[Chunk]:
    """One chunk per shot of a compiled film, in order, covering every frame."""
    shots = inputs["shots"]
    placeholders = set(inputs.get("preview_placeholders") or ())
    chunks = []
    for index, shot in enumerate(shots):
        start, frames = shot["start_frame"], shot["duration_frames"]
        previous = None
        if index > 0 and _handle(shots, index - 1) > 0:
            previous = _relative_shot(shots, index - 1, start)
        key = digest(
            {
                "version": KEY_VERSION,
                "implementation_revision": revision,
                "canvas": list(canvas),
                "fps": fps,
                "capture": inputs.get("capture"),
                "preview_banner": inputs.get("preview_banner", False),
                "placeholder": shot["id"] in placeholders,
                "shot": _relative_shot(shots, index, start),
                "previous": previous,
                "first": index == 0,
                "titles": _titles_in(inputs.get("titles"), start, frames),
                "brand": _brand_in(inputs, start, fps),
            }
        )
        chunks.append(Chunk(shot["id"], start, frames, key))
    return chunks
