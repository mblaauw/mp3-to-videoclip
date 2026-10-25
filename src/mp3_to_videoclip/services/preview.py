"""The Studio Player's input: resolved shot payloads plus local API URLs.

This is read-only and never a render gate: a shot without a selected still keeps
its allocated span and is marked as a placeholder, exactly like a marked preview
render. The browser runs the renderer's own BaseFilm and timing module over this
payload, so the live picture follows the same frame functions as the MP4.
"""

from __future__ import annotations

from pathlib import Path

from mp3_to_videoclip import production as P
from mp3_to_videoclip.branding import pack_hash, render_brand_plate
from mp3_to_videoclip.remotion import data_url
from mp3_to_videoclip.storage import digest, inside, read_json

MISSING_IMAGE = "missing-still.jpg"


def player_input(root: Path, slug: str) -> dict:
    project = P.load_project(root)
    board = P.load_board(root)
    assets = read_json(root / "work/assets.json")
    shots: list[dict] = []
    placeholders: list[str] = []
    stale: list[str] = []
    for shot in board.shots:
        owner = shot.asset_shot_id or shot.id
        entry = assets.get(owner, {})
        chosen = next(
            (v for v in entry.get("versions", []) if v["version"] == entry.get("selected")),
            None,
        )
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
            "image": MISSING_IMAGE,
            "src": None,
            "still_current": False,
        }
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
