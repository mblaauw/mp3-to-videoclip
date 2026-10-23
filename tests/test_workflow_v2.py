"""Local workflow regression cases derived from the Cool Cat audit. No paid calls."""

import copy

import pytest
from test_creative_production import approve_prerequisites, jpeg, make_root, record_stills
from test_production import FakeRunware

from mp3_to_videoclip import budget, preflight
from mp3_to_videoclip import generation as G
from mp3_to_videoclip import production as P
from mp3_to_videoclip.cli import execute, parser
from mp3_to_videoclip.models import Character, CharacterState, Project, Shot
from mp3_to_videoclip.references import import_reference
from mp3_to_videoclip.reviews import record_review, require_accepted, verdict_for
from mp3_to_videoclip.storage import digest, file_hash, read_json, write_json


def strict_root(tmp_path):
    root = make_root(tmp_path)
    project = read_json(root / "project.json")
    project["workflow_version"] = 2
    write_json(root / "project.json", project)
    brief = read_json(root / "brief.json")
    for ref in brief["creative"]["references"]:
        imported = import_reference(
            root, root / ref["path"], note="test-owned image", permission_confirmed=True
        )
        ref["path"] = imported["path"]
    path = jpeg(root / "identity.jpg", (80, 40, 20))
    ref = import_reference(root, path, note="identity only", permission_confirmed=True)
    brief["characters"] = [
        Character(
            id="juno",
            identity="Adult woman, short dark hair with one bleached streak",
            references=[ref["path"]],
            permission_confirmed=True,
            states={
                "coat": CharacterState(
                    description="An olive parka over a black dress", attributes={"wardrobe": "coat"}
                ),
                "dance": CharacterState(
                    description="Plain black dress, bare arms, no parka",
                    attributes={"wardrobe": "dress"},
                ),
            },
            default_state="coat",
        ).model_dump()
    ]
    write_json(root / "brief.json", brief)
    board = read_json(root / "work/storyboard.json")
    for shot in board["shots"]:
        shot.update(
            character_ids=["juno"],
            character_states={"juno": "dance"},
            state_requirements={"juno": {"wardrobe": "dress"}},
        )
    write_json(root / "work/storyboard.json", board)
    return root


def test_legacy_model_serialization_stays_exact():
    assert (
        "workflow_version"
        not in Project(
            slug="test", title="Test", source_sha256="x", duration=2, width=192, height=108
        ).model_dump()
    )
    c = Character(id="person", description="legacy", references=["photo.jpg"])
    assert c.model_dump() == {
        "id": "person",
        "description": "legacy",
        "references": ["photo.jpg"],
        "permission_confirmed": False,
    }
    shot = Shot(id="s1", start_frame=0, duration_frames=24, purpose="test", image_prompt="test")
    assert "character_states" not in shot.model_dump()
    assert "state_requirements" not in shot.model_dump()


def test_resolved_state_excludes_other_costumes_and_names_reference_roles(tmp_path):
    root = strict_root(tmp_path)
    report = preflight.manifest(root)
    assert report["ok"], report["issues"]
    prompt = report["shots"][0]["spec"]["positivePrompt"]
    assert "olive parka" not in prompt
    assert "Plain black dress" in prompt
    assert "Image 1: juno identity reference" in prompt
    assert report["shots"][0]["characters"]["juno"]["attributes"] == {"wardrobe": "dress"}


def test_state_requirements_block_before_spending(tmp_path):
    root = strict_root(tmp_path)
    board = read_json(root / "work/storyboard.json")
    board["shots"][0]["character_states"]["juno"] = "coat"
    write_json(root / "work/storyboard.json", board)
    with pytest.raises(ValueError, match="required 'dress', resolved 'coat'"):
        preflight.validate_before_spend(root, ["s001"])


@pytest.mark.parametrize(
    ("prompt", "required", "code"),
    [
        ("The hands apart, gap of air", ["hands clasped"], "must-show-conflict"),
        ("Five clean fingers and one thumb", [], "digit-count"),
        ("Juno without parka", [], "state-conflict"),
    ],
)
def test_known_contradictions_block(tmp_path, prompt, required, code):
    root = strict_root(tmp_path)
    board = read_json(root / "work/storyboard.json")
    shot = board["shots"][0]
    shot.update(
        image_prompt=prompt,
        must_show=required,
        character_states={"juno": "coat"},
        state_requirements={},
    )
    write_json(root / "work/storyboard.json", board)
    report = preflight.manifest(root, ["s001"])
    assert code in {i["code"] for i in report["issues"]}
    with pytest.raises(ValueError, match="preflight blocked"):
        preflight.validate_before_spend(root, ["s001"])


def test_import_is_immutable_crop_with_provenance_not_canon_writer(tmp_path):
    root = make_root(tmp_path)
    before = (root / "brief.json").read_bytes()
    source = jpeg(root / "source.jpg")
    with pytest.raises(ValueError, match="explicit permission"):
        import_reference(root, source, note="owned")
    result = import_reference(
        root, source, note="owned crop", permission_confirmed=True, box=[0, 0, 8, 8]
    )
    assert result["size"] == [8, 8]
    assert result["origins"][0]["source_sha256"] == file_hash(source)
    assert result["origins"][0]["crop_box_px"] == [0, 0, 8, 8]
    assert (root / "brief.json").read_bytes() == before
    target = root / result["path"]
    assert target.name == result["sha256"] + ".png"
    target.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="immutable reference"):
        import_reference(
            root, source, note="owned crop", permission_confirmed=True, box=[0, 0, 8, 8]
        )


def test_unimported_reference_blocks_strict_workflow(tmp_path):
    root = strict_root(tmp_path)
    brief = read_json(root / "brief.json")
    brief["characters"][0]["references"] = [str(jpeg(root / "loose.jpg").relative_to(root))]
    write_json(root / "brief.json", brief)
    with pytest.raises(ValueError, match="immutable reference import"):
        preflight.validate_before_spend(root, ["s001"])


def accept(root, ids):
    for sid in ids:
        record_review(
            root,
            sid,
            1,
            "accept",
            note="inspected locally; fits beat",
            reviewer="test",
            inspected=True,
        )


def test_review_bound_to_bytes_and_input_and_latest_verdict(tmp_path):
    root = strict_root(tmp_path)
    record_stills(root, ["s001"])
    with pytest.raises(ValueError, match="inspection acknowledgement"):
        record_review(root, "s001", 1, "accept", note="looks good", reviewer="test")
    accept(root, ["s001"])
    require_accepted(root, ["s001"])
    record_review(
        root, "s001", 1, "uncertain", note="needs closer look", reviewer="test", inspected=True
    )
    with pytest.raises(ValueError, match="accepted review"):
        require_accepted(root, ["s001"])
    accept(root, ["s001"])
    board = read_json(root / "work/storyboard.json")
    board["shots"][0]["image_prompt"] += " New image detail"
    write_json(root / "work/storyboard.json", board)
    with pytest.raises(ValueError, match="accepted review"):
        require_accepted(root, ["s001"])
    with pytest.raises(ValueError, match="stale inputs"):
        accept(root, ["s001"])


def test_proof_requires_inspected_selection_and_unrelated_edit_keeps_preview(tmp_path):
    root = strict_root(tmp_path)
    approve_prerequisites(root)
    P.approve(root, "storyboard", "test approval")
    ids = P.proof_ids(P.load_board(root), P.load_brief(root))
    record_stills(root, ids)
    with pytest.raises(ValueError, match="accepted review"):
        P.approve(root, "proof", "not yet inspected")
    accept(root, ids)
    P.approve(root, "proof", "inspected proof")
    movie = root / "previews/test.mp4"
    movie.parent.mkdir(exist_ok=True)
    movie.write_bytes(b"local test preview")
    write_json(
        root / "work/preview-review.json",
        {
            "movie": "previews/test.mp4",
            "movie_sha256": file_hash(movie),
            "storyboard_hash": P.preview_board_hash(root),
            "proof_hash": P.stage_hash(root, "proof"),
        },
    )
    P.approve(root, "preview", "test reviewed preview")
    old = P.stage_hash(root, "proof")
    board = read_json(root / "work/storyboard.json")
    # s003 is a placeholder, not one of s001,s002,s004 proof images.
    board["shots"][2]["image_prompt"] += " corrected future image"
    write_json(root / "work/storyboard.json", board)
    with pytest.raises(ValueError, match="storyboard needs current"):
        P.require_approval(root, "preview")
    P.approve(root, "storyboard", "reviewed revised prompt")
    assert P.stage_hash(root, "proof") == old
    P.require_approval(root, "preview")
    board["shots"][2]["purpose"] += " new beat"
    write_json(root / "work/storyboard.json", board)
    P.approve(root, "storyboard", "reviewed new beat")
    with pytest.raises(ValueError, match="different storyboard"):
        P.require_approval(root, "preview")


def test_selected_new_version_does_not_change_imported_identity(tmp_path):
    root = strict_root(tmp_path)
    record_stills(root, ["s001"])
    ref = copy.deepcopy(P.load_brief(root).characters[0].references)
    spec_before = digest(P.image_spec(root, P.load_board(root).shots[0]))
    path = jpeg(root / "assets/s001/new.jpg", (10, 20, 30))
    P.record_asset(root, "s001", 2, path, spec_before, "new")
    P.select_asset(root, "s001", 2)
    assert P.load_brief(root).characters[0].references == ref
    assert digest(P.image_spec(root, P.load_board(root).shots[0])) == spec_before
    assert verdict_for(root, "s001") is None


def test_cli_commands_and_new_default(tmp_path):
    args = parser().parse_args(
        ["init", str(tmp_path / "new"), "--slug", "new", "--mp3", "song.mp3"]
    )
    assert args.command == "init"
    root = strict_root(tmp_path)
    result = execute(parser().parse_args(["locate", str(root), "--frame", "12"]))
    assert result["shot_id"] == "s002"
    assert execute(parser().parse_args(["preflight", str(root), "--shots", "s001"]))["ok"]


def test_reference_free_identity_and_only_bound_character_roles(tmp_path):
    assert Character(id="text", identity="An adult fictional character").references == []
    assert (
        Character(id="text", identity="An adult fictional character", references=[]).references
        == []
    )
    root = strict_root(tmp_path)
    brief = read_json(root / "brief.json")
    unbound = copy.deepcopy(brief["characters"][0])
    unbound["id"] = "alice"
    brief["characters"].insert(0, unbound)
    write_json(root / "brief.json", brief)
    prompt = preflight.manifest(root, ["s001"])["shots"][0]["spec"]["positivePrompt"]
    assert "Image 1: juno identity reference" in prompt
    assert "alice" not in prompt
    assert "juno identity: Adult woman" in prompt


def test_alias_cannot_change_source_state_or_require_different_costume(tmp_path):
    root = strict_root(tmp_path)
    board = read_json(root / "work/storyboard.json")
    alias = board["shots"][2]
    alias.update(
        asset_shot_id="s001",
        character_states={"juno": "coat"},
        state_requirements={"juno": {"wardrobe": "coat"}},
    )
    write_json(root / "work/storyboard.json", board)
    result = preflight.manifest(root, ["s003"])
    assert {i["code"] for i in result["issues"]} >= {"alias-state", "state"}


def test_reject_revokes_prior_approval_even_with_unchanged_bytes(tmp_path):
    root = strict_root(tmp_path)
    approve_prerequisites(root)
    P.approve(root, "storyboard", "approved board")
    ids = P.proof_ids(P.load_board(root), P.load_brief(root))
    record_stills(root, ids)
    accept(root, ids)
    P.approve(root, "proof", "accepted exact versions")
    record_review(
        root,
        "s001",
        1,
        "reject",
        note="later inspection found duplicated limb",
        reviewer="test",
        inspected=True,
    )
    with pytest.raises(ValueError, match="accepted review"):
        P.require_approval(root, "proof")


def test_strict_quote_and_generate_uses_preflight_budget_and_no_implicit_acceptance(tmp_path):
    root = strict_root(tmp_path)
    approve_prerequisites(root)
    P.approve(root, "storyboard", "approved board")
    budget.set_budget(root, "1", "test spending authority")
    client = FakeRunware(root)
    quote = G.quote_images(root, "proof", "0.01", client=client)
    G.authorize(root, quote["id"], "0.03", "test exact proof scope")
    G.generate(root, quote["id"], client, concurrency=2)
    for sid in ("s001", "s002", "s004"):
        P.select_asset(root, sid, 1)
    with pytest.raises(ValueError, match="accepted review"):
        P.approve(root, "proof", "cannot approve unseen images")
    accept(root, ("s001", "s002", "s004"))
    P.approve(root, "proof", "inspected generated proof")


def test_strict_contact_sheet_versioned_with_byte_bound_labels(tmp_path):
    root = strict_root(tmp_path)
    record_stills(root, ["s001", "s002", "s003", "s004"])
    command = parser().parse_args(["sheet", str(root), "--scope", "stills"])
    first, second = execute(command), execute(command)
    assert first["contact_sheet"] != second["contact_sheet"]
    from pathlib import Path

    metadata = read_json(Path(first["contact_sheet"]).with_suffix(".json"))
    assert metadata["reviewed"] is False
    assert metadata["shots"][1]["start_frame"] == 12
    assert metadata["shots"][1]["version"] == 1
    assert len(metadata["shots"][1]["sha256"]) == 64
