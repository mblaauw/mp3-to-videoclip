"""The Studio Player's input: resolved shot payloads plus local API URLs.

This is read-only and never a render gate: a shot without a selected still keeps
its allocated span and is marked as a placeholder, exactly like a marked preview
render. The browser runs the renderer's own BaseFilm and timing module over this
payload, so the live picture follows the same frame functions as the MP4.
"""

from __future__ import annotations

from pathlib import Path

from mp3_to_videoclip import production as P
from mp3_to_videoclip import shotkinds
from mp3_to_videoclip.branding import pack_hash, render_brand_plate
from mp3_to_videoclip.remotion import data_url
from mp3_to_videoclip.storage import digest, inside, read_json

MISSING_IMAGE = "missing-still.jpg"


def _selected(root: Path, assets: dict, shot) -> dict | None:
    owner = shot.asset_shot_id or shot.id
    entry = assets.get(owner, {})
    return next(
        (v for v in entry.get("versions", []) if v["version"] == entry.get("selected")),
        None,
    )


def _pane_payload(root: Path, slug: str, assets: dict, pane, source) -> dict:
    owner = source.asset_shot_id or source.id
    if source.asset_shot_id is None and shotkinds.is_local(source):
        try:
            path = Path(P.resolved_assets(root, [source.id])[0].image)
        except (OSError, ValueError):
            return {"shot_id": pane.shot_id, "crop": pane.crop.model_dump(), "src": None}
        return {
            "shot_id": pane.shot_id,
            "crop": pane.crop.model_dump(),
            "src": f"/api/projects/{slug}/plates/{source.id}",
            "image": path.name,
        }
    chosen = _selected(root, assets, source)
    if chosen is None:
        return {"shot_id": pane.shot_id, "crop": pane.crop.model_dump(), "src": None}
    path = inside(root, chosen["path"])
    return {
        "shot_id": pane.shot_id,
        "crop": pane.crop.model_dump(),
        "src": f"/api/projects/{slug}/images/{owner}/{chosen['version']}",
        "image": path.name,
    }


def player_input(root: Path, slug: str) -> dict:
    from mp3_to_videoclip import edits

    project = P.load_project(root)
    board = P.load_board(root)
    edit = edits.load_edit(root, board=board)
    effective = edit.effective_board(board) if edit is not None else board
    decisions = {shot.shot_id: shot for shot in edit.shots} if edit is not None else {}
    grade = edit.grade.model_dump(by_alias=True) if edit is not None else None
    assets = read_json(root / "work/assets.json")
    content = {shot.id: shot for shot in board.shots}
    shots: list[dict] = []
    placeholders: list[str] = []
    stale: list[str] = []
    for shot in effective.shots:
        owner = shot.asset_shot_id or shot.id
        chosen = _selected(root, assets, shot)
        dumped = shot.model_dump()
        value = {
            # Only the renderer's own fields: prompt text stays out of the Player.
            **{
                key: dumped[key]
                for key in (
                    "id",
                    "start_frame",
                    "duration_frames",
                    "dissolve_frames",
                    "camera",
                    "camera_path",
                    "camera_keyframes",
                    "post_effects",
                    "transition",
                )
                if key in dumped
            },
            "kind": shot.kind,
            "image": MISSING_IMAGE,
            "src": None,
            "still_current": False,
        }
        if shot.id in decisions:
            value["edit"] = decisions[shot.id].model_dump(by_alias=True)
            value["grade"] = grade
        if shot.kind == "split":
            panes = [
                _pane_payload(root, slug, assets, pane, content[pane.shot_id])
                for pane in shot.panes
                if pane.shot_id in content
            ]
            if panes and all(pane.get("src") for pane in panes):
                value["split_panes"] = panes
            if any(not pane.get("src") for pane in panes):
                stale.append(shot.id)
        if shot.asset_shot_id is None and shotkinds.is_local(shot):
            try:
                resolved = P.resolved_assets(root, [shot.id])[0]
                value["image"] = Path(resolved.image).name
                value["src"] = f"/api/projects/{slug}/plates/{shot.id}"
                value["still_current"] = True
            except (OSError, ValueError):
                placeholders.append(shot.id)
            shots.append(value)
            continue
        if chosen is not None:
            path = inside(root, chosen["path"])
            value["image"] = path.name
            value["src"] = f"/api/projects/{slug}/images/{owner}/{chosen['version']}"
            value["still_current"] = chosen.get("input_hash") == digest(P.image_spec(root, shot))
            if not value["still_current"]:
                stale.append(shot.id)
        else:
            placeholders.append(shot.id)
        shots.append(value)

    payload = {
        "available": True,
        "fps": board.fps,
        "width": project.width,
        "height": project.height,
        "durationInFrames": board.total_frames,
        "shots": shots,
        "grade": grade,
        "audio": (
            f"/api/projects/{slug}/audio-excerpt"
            if project.audio_window is not None
            else f"/api/projects/{slug}/audio"
        ),
        # A live preview is unmarked; the rendered preview carries its own banner.
        "preview_banner": False,
        "preview_placeholders": placeholders,
        "stale_shots": stale,
    }
    brand = P.load_brand(root)
    if brand is not None and brand.plate and brand.mark != "filmstrip":
        plate = (
            root
            / "work"
            / "remotion-assets"
            / f"brand-{pack_hash(brand)}-{project.width}x{project.height}.png"
        )
        if not plate.is_file():
            render_brand_plate(brand, project, plate)
        payload["brand_plate"] = data_url(plate, "image/png")
        payload["brand_duration_frames"] = round(brand.duration_seconds * project.fps)
    return payload
