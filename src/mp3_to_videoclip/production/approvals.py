"""The content-bound approval chain and the status built on it."""

from pathlib import Path

from .. import flow, shotkinds
from ..branding import brand_hash, load_brand
from ..models import (
    Brief,
    Lyrics,
    Project,
    Storyboard,
)
from ..storage import (
    digest,
    file_hash,
    inside,
    read_json,
    snapshot_read,
    state_mutation,
    write_json,
)
from .assets import _current_proof_ids, _local_plate, has_placeholders, proof_ids, resolved_assets
from .board import load_board, load_events
from .brief import is_creative, load_brief
from .image_specs import (
    _character_refusal,
    _permission_refusal,
    _require_default_style_core,
    brief_references,
    image_spec,
)
from .project import (
    STAGE_FILES,
    UPSTREAM,
    creative_workflow,
    load_project,
    now,
    project_payload,
    requires_signature,
)


def effective_upstream(root: Path, stage: str) -> str | None:
    """Return the real parent artifact for a stage's current production kind.

    Promo and advert briefs are built from the measured song and the intent, not
    from a lyrics map: only music videos have a lyrics stage. Instrumental and
    music-led music videos likewise depend on analysis. Creative stills depend on
    the watched preview when that gate applies.
    """
    if stage == "brief":
        project = load_project(root)
        if project.kind not in (None, "music_video"):
            return "analysis"
        if project.music_mode in ("instrumental", "music-led"):
            return "analysis"
    if stage == "stills" and is_creative(root) and flow.settings(root)["preview_gate"]:
        return "preview"
    return UPSTREAM[stage]


def _required_parents(root: Path, stage: str) -> list[str]:
    # Guided productions treat music analysis, events and the brand package as
    # agent-owned evidence: their bytes still bind into the brief hash, but the
    # user is not asked to certify tempo, meter or section estimates before
    # agreeing the story. Recorded v2 productions keep every upstream gate.
    if stage == "brief" and flow.settings(root)["guided"]:
        return []
    upstream = effective_upstream(root, stage)
    parents = [upstream] if upstream else []
    if stage == "brief" and (root / STAGE_FILES["events"]).exists() and is_creative(root):
        parents.append("events")
    if stage == "brief" and (root / STAGE_FILES["brand"]).exists():
        parents.append("brand")
    if (
        stage == "brief"
        and load_project(root).music_mode == "music-led"
        and (root / STAGE_FILES["listening"]).exists()
    ):
        parents.append("listening")
    return parents


def preview_board_hash(root: Path):
    """Only inputs visible in a proof-only animatic, for new workflows.

    Changing a placeholder's generation prompt still requires storyboard review,
    but cannot change a movie which never displayed that future image.
    """
    value = read_json(root / STAGE_FILES["storyboard"])
    from .. import edits

    board = Storyboard.model_validate(value)
    edit = edits.load_edit(root, board=board)
    if not creative_workflow(load_project(root)):
        if edit is not None:
            return digest({"storyboard": value, "edit": edit.model_dump(by_alias=True)})
        return digest(value)
    keys = (
        "id",
        "start_frame",
        "duration_frames",
        "purpose",
        "framing",
        "camera",
        "camera_path",
        "dissolve_frames",
        "asset_shot_id",
    )
    payload = {
        "fps": value["fps"],
        "aspect": value["aspect"],
        "total_frames": value["total_frames"],
        "shots": [
            {
                **{k: s.get(k) for k in keys},
                **{k: s[k] for k in ("camera_keyframes", "post_effects", "transition") if k in s},
            }
            for s in value["shots"]
        ],
    }
    if edit is not None:
        payload["edit"] = edit.model_dump(by_alias=True)
    return digest(payload)


def check_preview_binding(root: Path, report: dict):
    """Bind a reviewed preview to the current storyboard, proof set and movie bytes."""
    for key in ("movie", "movie_sha256", "storyboard_hash", "proof_hash"):
        if not report.get(key):
            raise ValueError(f"preview review report is missing {key}")
    if report["storyboard_hash"] != preview_board_hash(root):
        raise ValueError("preview was generated from a different storyboard; re-render and review")
    if report["proof_hash"] != stage_hash(root, "proof"):
        raise ValueError("preview was generated from a different proof set; re-render and review")
    if report.get("brand_hash") != brand_hash(root):
        raise ValueError("brand changed since preview; re-render and review")
    if load_project(root).uses_remotion:
        from ..remotion import implementation_hash

        if report.get("renderer_revision") != implementation_hash():
            raise ValueError("Remotion changed since preview; re-render and review")
    movie = inside(root, report["movie"])
    if not movie.is_file():
        raise ValueError("reviewed preview movie is missing")
    if file_hash(movie) != report["movie_sha256"]:
        raise ValueError("reviewed preview movie changed; re-render and review")


def _local_proof_entries(root: Path, board: Storyboard, project: Project) -> list[dict]:
    """Bind local plate bytes where they can render, otherwise their definition.

    A split whose pane stills do not exist yet cannot be photographed; the proof
    gate still binds the shot definition, and the later stills gate binds the
    actual plate bytes.
    """
    entries = []
    for shot in board.shots:
        if shot.asset_shot_id is not None or shotkinds.is_paid(shot):
            continue
        try:
            path = _local_plate(root, project, shot)
        except (OSError, ValueError):
            entries.append({"id": shot.id, "definition": digest(shot.model_dump())})
        else:
            entries.append({"id": shot.id, "image": file_hash(path)})
    return entries


@snapshot_read
def stage_hash(root: Path, stage: str) -> str:
    project = load_project(root)
    upstream = effective_upstream(root, stage)
    # The current storyboard must still be explicitly approved (parents are
    # checked by require_approval). Proof identity depends only on proof inputs,
    # not on a generation-only correction to an unseen placeholder.
    parent = (
        None
        if stage == "proof" and creative_workflow(project)
        else (stage_hash(root, upstream) if upstream else None)
    )
    if stage == "preview":
        value = read_json(root / STAGE_FILES["preview"])
        check_preview_binding(root, value)
    elif stage == "brand":
        value = {"package": read_json(root / STAGE_FILES[stage]), "render_hash": brand_hash(root)}
    elif stage in STAGE_FILES:
        value = read_json(root / STAGE_FILES[stage])
        if stage == "brief":
            brief = Brief.model_validate(value)
            value = {"brief": value, "references": brief_references(root, brief)}
            if requires_signature(root, project) and not flow.settings(root)["late_credits"]:
                value["signature"] = digest(read_json(root / "work/graphics-spec.json"))
            if (root / STAGE_FILES["events"]).exists():
                value["events"] = digest(read_json(root / STAGE_FILES["events"]))
            if (root / STAGE_FILES["brand"]).exists():
                value["brand_hash"] = brand_hash(root)
            if project.music_mode == "music-led" and (root / STAGE_FILES["listening"]).exists():
                value["listening"] = stage_hash(root, "listening")
    else:
        board = load_board(root)
        if stage == "proof":
            shots = resolved_assets(root, _current_proof_ids(root, board))
            value = [{"id": s.shot.id, "image": file_hash(Path(s.image))} for s in shots]
            if creative_workflow(project):
                value = [
                    {**item, "input_hash": digest(image_spec(root, rs.shot))}
                    for item, rs in zip(value, shots, strict=True)
                ]
            value += _local_proof_entries(root, board, project)
        else:
            shots = resolved_assets(root)
            value = [{"id": s.shot.id, "image": file_hash(Path(s.image))} for s in shots]
            from .. import edits

            if stage == "stills":
                edit = edits.load_edit(root, board=board)
                if edit is not None:
                    value = {"assets": value, "edit": edit.model_dump(by_alias=True)}
    return digest({"project": project_payload(project), "upstream": parent, "content": value})


@snapshot_read
def require_approval(root: Path, stage: str):
    """Check gates; Studio attestations are consistency claims, not proof of human acts."""
    if stage == "lyrics" and load_project(root).music_mode == "instrumental":
        raise ValueError("instrumental projects have no lyrics stage to approve")
    for parent in _required_parents(root, stage):
        require_approval(root, parent)
    record = read_json(root / "work/approvals.json").get(stage)
    if not record:
        raise ValueError(f"{stage} needs current user approval")
    try:
        current_hash = stage_hash(root, stage)
    except FileNotFoundError as exc:
        raise ValueError(
            f"{stage} review artifact is missing; recreate and obtain current user approval"
        ) from exc
    if record["hash"] != current_hash:
        raise ValueError(f"{stage} needs current user approval")
    if record.get("via") == "studio":
        complete = record.get("review_confirmed") is True
        if stage == "preview":
            complete = complete and record.get("preview_watched") is True
        if stage == "graphics":
            complete = complete and record.get("inspected") is True
        if stage == "lyrics":
            lyrics = Lyrics.model_validate(read_json(root / STAGE_FILES[stage]))
            if any(segment.flags for segment in lyrics.segments):
                complete = complete and record.get("acknowledge_uncertain") is True
        if not complete:
            raise ValueError(
                f"{stage} Studio approval is incomplete; review and decide again in Studio"
            )
    if stage == "graphics":
        from ..signature import validate_review

        validate_review(root, load_project(root))
    if stage in ("proof", "stills") and creative_workflow(load_project(root)):
        from ..reviews import require_accepted

        board = load_board(root)
        ids = (
            proof_ids(board, load_brief(root))
            if stage == "proof"
            else [s.id for s in board.shots if shotkinds.is_paid(s)]
        )
        require_accepted(root, ids)


def _require_reference_permissions(brief: Brief):
    for character in brief.characters:
        if not character.permission_confirmed:
            raise _character_refusal(character.id)
    for reference in brief.creative.references if brief.creative else []:
        if not reference.permission_confirmed:
            raise _permission_refusal(reference.id)


@state_mutation
def approve(
    root: Path,
    stage: str,
    note: str,
    acknowledge_uncertain=False,
    *,
    inspected=False,
    expected_hash: str | None = None,
    via: str | None = None,
    preview_watched: bool = False,
    review_confirmed: bool | None = None,
):
    if via != "studio" and not note.strip():
        raise ValueError("record the user's approval decision in --note")
    note = note.strip() or None
    if via == "studio" and review_confirmed is not True:
        raise ValueError("Studio decisions require explicit review confirmation")
    if via == "studio" and stage == "preview" and preview_watched is not True:
        raise ValueError("confirm continuous preview playback with the actual music")
    if stage == "lyrics" and load_project(root).music_mode == "instrumental":
        raise ValueError(
            "instrumental projects have no lyrics stage; approve the analysis and events instead"
        )
    for parent in _required_parents(root, stage):
        require_approval(root, parent)
    if stage == "lyrics":
        lyrics = Lyrics.model_validate(read_json(root / STAGE_FILES[stage]))
        project = load_project(root)
        if not lyrics.segments and not lyrics.lines:
            raise ValueError("empty lyrics cannot be approved for this vocal project")
        for segment in lyrics.segments:
            if segment.end > project.duration + 0.1:
                raise ValueError("lyric timestamps extend beyond the source")
        if any(s.flags for s in lyrics.segments) and not acknowledge_uncertain:
            raise ValueError("review/correct flagged lyrics, then explicitly --ack-uncertain")
    elif stage == "brief":
        brief = load_brief(root)
        project = load_project(root)
        _require_default_style_core(project, brief)
        if requires_signature(root) and not flow.settings(root)["late_credits"]:
            from ..signature import validate_spec

            validate_spec(root, load_project(root))
        _require_reference_permissions(brief)
        if creative_workflow(project) and brief.creative is None:
            raise ValueError("the creative workflow requires a creative profile")
        if project.prompt_version == 2:
            if not brief.treatment.strip():
                raise ValueError("write the treatment before approving the story")
            if not brief.creative.look.strip():
                raise ValueError("define creative.look (global appearance only) before approval")
            if brief.creative.profile_version < 1:
                raise ValueError(
                    "create the creative profile (cast, places, rules and a compact look) "
                    "before approving the story"
                )
        elif not all(x.strip() for x in [brief.direction, brief.style, brief.treatment]):
            raise ValueError("choose a treatment, direction and style before approval")
        if brief.creative is not None and not brief.creative.look.strip():
            raise ValueError("define creative.look (global appearance only) before approval")
        if creative_workflow(project):
            from ..references import validate_import

            for character in brief.characters:
                if not character.identity:
                    raise ValueError("workflow 2 characters need identity separate from shot state")
            for ref in brief_references(root, brief):
                validate_import(root, ref["path"])
    elif stage == "storyboard":
        board = load_board(root)
        if any(has_placeholders(s) for s in board.shots):
            raise ValueError("finish storyboard placeholders before approval")
        # A creative profile must name its own explicit proof selection.
        proof_ids(board, load_brief(root))
        if creative_workflow(load_project(root)):
            from ..preflight import validate_before_spend

            validate_before_spend(root, [s.id for s in board.shots])
    elif stage == "analysis":
        data = read_json(root / STAGE_FILES[stage])
        if abs(data["duration"] - load_project(root).duration) > 0.05:
            raise ValueError("analysis does not match the source duration")
    elif stage == "events":
        load_events(root)  # Source identity, frame bounds and ordering.
    elif stage == "brand":
        brand = load_brand(root)
        if brand is None or brand.duration_seconds > load_project(root).duration:
            raise ValueError("brand intro is missing or longer than the music")
    elif stage == "listening":
        from ..music_analysis import load_listening

        load_listening(root)
    elif stage == "graphics":
        from ..signature import validate_review

        if not inspected:
            raise ValueError(
                "inspect the actual composited graphics samples, then approve graphics with --inspected"
            )
        validate_review(root, load_project(root))
    if stage in ("proof", "stills") and creative_workflow(load_project(root)):
        from ..reviews import require_accepted

        board = load_board(root)
        ids = (
            proof_ids(board, load_brief(root))
            if stage == "proof"
            else [s.id for s in board.shots if shotkinds.is_paid(s)]
        )
        require_accepted(root, ids)
    approvals = read_json(root / "work/approvals.json")
    current = stage_hash(root, stage)
    if expected_hash is not None and current != expected_hash:
        raise ValueError("stage changed during review; inspect its current artifacts again")
    if stage in ("brief", "storyboard"):
        # The decision binds the hash; this copy only lets Studio explain what
        # changed afterwards. It is never read by the gate itself.
        write_json(
            root / "work/approval-snapshots" / f"{stage}-{current}.json",
            {
                "stage": stage,
                "hash": current,
                "artifact": read_json(root / STAGE_FILES[stage]),
            },
        )
    approvals[stage] = {"hash": current, "at": now(), "note": note}
    if via is not None:
        approvals[stage].update(
            via=via, inspected=bool(inspected), acknowledge_uncertain=bool(acknowledge_uncertain)
        )
        if via == "studio":
            approvals[stage]["review_confirmed"] = True
            if stage == "preview":
                approvals[stage]["preview_watched"] = bool(preview_watched)
    write_json(root / "work/approvals.json", approvals)


def status(root: Path) -> dict:
    project = load_project(root)
    approvals = {}
    for stage in UPSTREAM:
        try:
            require_approval(root, stage)
            approvals[stage] = "approved"
        except (OSError, ValueError, KeyError):
            approvals[stage] = "missing/stale/unapproved"
    from .. import edits

    edit = None
    try:
        board = load_board(root)
        edit = edits.load_edit(root, board=board)
        if edit is not None:
            board = edit.effective_board(board)
        shots = []
        for shot in board.shots:
            try:
                resolved_assets(root, [shot.id])
                image = "current"
            except (OSError, ValueError, KeyError):
                image = "missing/stale"
            shots.append(
                {
                    "id": shot.id,
                    "start": shot.start_frame / project.fps,
                    "duration": shot.duration_frames / project.fps,
                    "still": image,
                }
            )
    except (OSError, ValueError):
        shots = []
    return {
        "project": project.slug,
        "duration": project.duration,
        "total_frames": project.total_frames,
        "aspect": project.aspect,
        "approvals": approvals,
        "edit": edit is not None,
        "shots": shots,
    }
