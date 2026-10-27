"""Creative-profile production gates. Everything local; no paid provider calls.

These tests cover the new creative branch (shot-first prompts, explicit proof
selection, preview binding, instrumental gates, events/skeleton) and prove the
legacy pilot artifacts keep their exact approved hashes.
"""

import copy
import json
from pathlib import Path

import pytest
from PIL import Image
from test_production import FakeRunware

from mp3_to_videoclip import generation as G
from mp3_to_videoclip import production as P
from mp3_to_videoclip import profiles
from mp3_to_videoclip.models import (
    Brief,
    CreativeProfile,
    EventMap,
    Lyrics,
    MusicEvent,
    Project,
    Scene,
    Segment,
    Shot,
    Storyboard,
    VisualBeat,
    VisualReference,
)
from mp3_to_videoclip.storage import digest, file_hash, read_json, write_json

PILOT = Path(__file__).resolve().parents[1] / "projects" / "kortjakje"
REF_DIR = "media/refs"


def jpeg(path: Path, colour=(30, 60, 90)) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    Image.new("RGB", (16, 16), colour).save(path)
    return path


def creative_brief(proof_shot_ids=("s001", "s002", "s004"), look="LOOK: muted teal, soft grain"):
    return Brief(
        direction="DIRECTION-SECRET",
        style="STYLE-SECRET",
        treatment="TREATMENT-SECRET",
        visual_rules=["LEGACY-RULE-SECRET"],
        avoid=["AVOID-TEXT"],
        creative=CreativeProfile(
            mode="narrative",
            look=look,
            image_rules=["IMAGE-RULE no on-screen text"],
            arc=[VisualBeat(phase="dawn", intention="ARC-INTENTION-SECRET")],
            scenes=[
                Scene(id="street", description="SCENE-STREET wet brick", reference_ids=["lamp"]),
                Scene(id="interior", description="SCENE-INTERIOR amber room"),
                Scene(id="unused_scene", description="SCENE-UNUSED never bound"),
            ],
            references=[
                VisualReference(
                    id="lamp",
                    kind="prop",
                    description="REF-LAMP brass street lamp",
                    path=f"{REF_DIR}/lamp.jpg",
                    permission_confirmed=True,
                ),
                VisualReference(
                    id="style",
                    kind="style",
                    description="REF-STYLE 35mm grain",
                    path=f"{REF_DIR}/style.jpg",
                    permission_confirmed=True,
                ),
                VisualReference(
                    id="unused",
                    kind="location",
                    description="REF-UNUSED never bound",
                    path=f"{REF_DIR}/unused.jpg",
                    permission_confirmed=True,
                ),
            ],
            proof_shot_ids=list(proof_shot_ids),
        ),
    )


def make_root(
    tmp_path,
    *,
    name="production",
    creative=True,
    with_storyboard=True,
    with_events=True,
    music_mode="vocal",
    total_frames=48,
    proof_shot_ids=("s001", "s002", "s004"),
    extra_refs=0,
    beat_times=(0, 0.5, 1.0, 1.5),
):
    root = tmp_path / name
    (root / "media").mkdir(parents=True)
    (root / "media/song.mp3").write_bytes(b"mock audio: no upload")
    project = Project(
        slug="creative",
        title="Creative",
        source_sha256=file_hash(root / "media/song.mp3"),
        duration=total_frames / 24,
        width=192,
        height=108,
        fps=24,
        music_mode=music_mode,
    )
    config = project.model_dump()
    if config["music_mode"] is None:
        config.pop("music_mode")
    write_json(root / "project.json", config)
    write_json(root / "work/music.json", {"duration": project.duration, "beats": list(beat_times)})
    if music_mode != "instrumental":
        write_json(
            root / "work/lyrics.json",
            Lyrics(
                provider="manual",
                model="test",
                segments=[Segment(start=0, end=1, text="Reviewed line")],
            ).model_dump(),
        )
    for name_ in ("lamp", "style", "unused"):
        jpeg(root / f"{REF_DIR}/{name_}.jpg")
    if extra_refs:
        for i in range(extra_refs):
            jpeg(root / f"{REF_DIR}/extra{i}.jpg")
    if creative:
        brief = creative_brief(proof_shot_ids=proof_shot_ids)
        references = list(brief.creative.references)
        references += [
            VisualReference(
                id=f"extra{i}",
                kind="prop",
                description=f"REF-EXTRA{i}",
                path=f"{REF_DIR}/extra{i}.jpg",
                permission_confirmed=True,
            )
            for i in range(extra_refs)
        ]
        brief = brief.model_copy(
            update={"creative": brief.creative.model_copy(update={"references": references})}
        )
    else:
        brief = Brief(direction="Legacy", style="Legacy style", treatment="Legacy treatment")
    write_json(root / "brief.json", brief.model_dump())
    if with_events:
        write_json(
            root / P.STAGE_FILES["events"],
            EventMap(
                source_sha256=project.source_sha256,
                fps=project.fps,
                total_frames=project.total_frames,
            ).model_dump(),
        )
    if with_storyboard:
        count = total_frames // 12
        shots = []
        for index in range(count):
            shot_id = f"s{index + 1:03d}"
            scene = ["street", "interior", "interior", None][index % 4] if creative else None
            framing = ["wide", "close_up", "detail", None][index % 4] if creative else None
            shots.append(
                Shot(
                    id=shot_id,
                    start_frame=index * 12,
                    duration_frames=12,
                    purpose=f"Beat {index}",
                    image_prompt=f"SHOT-{shot_id} prompt",
                    scene_id=scene,
                    framing=framing,
                    must_show=["a brass lamp"] if index == 0 else [],
                )
            )
        write_json(
            root / P.STAGE_FILES["storyboard"],
            Storyboard(aspect="16:9", fps=24, total_frames=total_frames, shots=shots).model_dump(),
        )
    for name_ in ("approvals", "assets", "tasks"):
        write_json(root / f"work/{name_}.json", {})
    return root


def approve_prerequisites(root, note="test user approved"):
    P.approve(root, "analysis", note)
    if P.load_project(root).music_mode != "instrumental":
        P.approve(root, "lyrics", note, True)
    if (root / P.STAGE_FILES["events"]).exists():
        P.approve(root, "events", note)
    P.approve(root, "brief", note)


def record_stills(root, shot_ids):
    assets = read_json(root / "work/assets.json")
    for shot in P.load_board(root).shots:
        if shot.id not in shot_ids:
            continue
        path = root / f"assets/{shot.id}/v001-fake.jpg"
        jpeg(path)
        assets[shot.id] = {
            "versions": [
                {
                    "version": 1,
                    "path": str(path.relative_to(root)),
                    "sha256": file_hash(path),
                    "input_hash": digest(P.image_spec(root, shot)),
                    "task_id": "fake-local",
                }
            ],
            "selected": 1,
        }
    write_json(root / "work/assets.json", assets)


def approve_through_proof(root):
    approve_prerequisites(root)
    P.approve(root, "storyboard", "test user approved shots")
    record_stills(root, P.proof_ids(P.load_board(root), P.load_brief(root)))
    P.approve(root, "proof", "test user approved proof")


def write_preview_report(root, name="work/preview-v001.mp4"):
    movie = root / name
    movie.parent.mkdir(parents=True, exist_ok=True)
    movie.write_bytes(b"fake preview movie bytes")
    report = {
        "movie": name,
        "movie_sha256": file_hash(movie),
        "storyboard_hash": P.preview_board_hash(root),
        "proof_hash": P.stage_hash(root, "proof"),
        "input_hash": digest({"render_inputs": "fake"}),
    }
    if P.load_project(root).uses_remotion:
        from mp3_to_videoclip.remotion import implementation_hash

        report["renderer_revision"] = implementation_hash()
    write_json(root / P.STAGE_FILES["preview"], report)
    return report


# --------------------------------------------------------------------------- #
# 1. legacy artifacts stay byte/hash identical
# --------------------------------------------------------------------------- #
@pytest.mark.skipif(not PILOT.is_dir(), reason="local pilot production not present")
def test_legacy_pilot_approvals_and_assets_remain_current():
    approvals = read_json(PILOT / "work/approvals.json")
    for stage in ("analysis", "lyrics", "brief", "storyboard", "proof", "stills"):
        assert P.stage_hash(PILOT, stage) == approvals[stage]["hash"]
    assets = read_json(PILOT / "work/assets.json")
    for shot in P.load_board(PILOT).shots:
        entry = assets[shot.id]
        chosen = next(v for v in entry["versions"] if v["version"] == entry["selected"])
        assert digest(P.image_spec(PILOT, shot)) == chosen["input_hash"]


def test_legacy_brief_hash_and_project_payload_ignore_new_fields(tmp_path):
    root = make_root(tmp_path, creative=False, with_events=False, music_mode=None)
    brief = P.load_brief(root)
    shot = P.load_board(root).shots[0]
    spec = P.image_spec(root, shot)
    assert brief.creative is None
    assert spec["brief_hash"] == P.legacy_brief_hash(brief)
    assert "profile_version" not in spec
    assert "music_mode" not in P.project_payload(P.load_project(root))
    assert P.proof_ids(P.load_board(root)) == ["s001", "s003", "s004"]


# --------------------------------------------------------------------------- #
# 2. creative prompt: shot-first, isolated, explicit
# --------------------------------------------------------------------------- #
def test_creative_prompt_is_shot_first_and_scene_isolated(tmp_path):
    root = make_root(tmp_path)
    shot = P.load_board(root).shots[0]
    spec = P.image_spec(root, shot)
    prompt = spec["positivePrompt"]
    assert prompt.splitlines()[0] == "SHOT-s001 prompt"
    assert "Framing: wide establishing shot" in prompt
    assert "Must show: a brass lamp" in prompt
    assert "SCENE-STREET" in prompt
    assert "REF-LAMP" in prompt
    assert "LOOK: muted teal" in prompt
    assert "IMAGE-RULE no on-screen text" in prompt
    assert "Avoid: AVOID-TEXT" in prompt
    for excluded in (
        "DIRECTION-SECRET",
        "STYLE-SECRET",
        "TREATMENT-SECRET",
        "LEGACY-RULE-SECRET",
        "ARC-INTENTION-SECRET",
        "SCENE-INTERIOR",
        "SCENE-UNUSED",
        "REF-UNUSED",
        "REF-STYLE",
    ):
        assert excluded not in prompt
    # New spec carries only transmitted prompt/size/selected refs/profile version.
    assert set(spec) == {"shot_id", "positivePrompt", "size", "references", "profile_version"}
    assert spec["references"] == [
        {"path": f"{REF_DIR}/lamp.jpg", "sha256": file_hash(root / f"{REF_DIR}/lamp.jpg")}
    ]


def test_creative_reference_permission_bytes_and_count(tmp_path):
    root = make_root(tmp_path)
    shot = P.load_board(root).shots[0]
    baseline = digest(P.image_spec(root, shot))
    assert len(P.image_spec(root, shot)["references"]) == 1

    # Referenced file bytes are the appearance identity.
    jpeg(root / f"{REF_DIR}/lamp.jpg", (200, 10, 10))
    assert digest(P.image_spec(root, shot)) != baseline

    # Declared-but-unconfirmed references are rejected at generation and approval.
    brief = P.load_brief(root)
    blocked = [
        r.model_copy(update={"permission_confirmed": False}) if r.id == "lamp" else r
        for r in brief.creative.references
    ]
    blocked_brief = brief.model_copy(
        update={"creative": brief.creative.model_copy(update={"references": blocked})}
    )
    write_json(root / "brief.json", blocked_brief.model_dump())
    with pytest.raises(ValueError, match="permission"):
        P.image_spec(root, shot)
    P.approve(root, "analysis", "test user")
    P.approve(root, "lyrics", "test user", True)
    P.approve(root, "events", "test user")
    with pytest.raises(ValueError, match="permission"):
        P.approve(root, "brief", "user")

    # The MVP model accepts at most four reference images per shot.
    many = make_root(tmp_path, name="many", extra_refs=5)
    board = read_json(many / P.STAGE_FILES["storyboard"])
    board["shots"][0]["reference_ids"] = [f"extra{i}" for i in range(5)]
    write_json(many / P.STAGE_FILES["storyboard"], board)
    with pytest.raises(ValueError, match="four"):
        P.image_spec(many, P.load_board(many).shots[0])


def test_creative_dependencies_editorial_versus_appearance(tmp_path):
    root = make_root(tmp_path)
    board = P.load_board(root)
    baseline = {s.id: digest(P.image_spec(root, s)) for s in board.shots}

    # Editorial/timing/camera/event/proof changes must not invalidate images.
    edited = read_json(root / P.STAGE_FILES["storyboard"])
    for shot in edited["shots"]:
        shot["camera"] = "pan_left"
        shot["motion_prompt"] = "Future move"
        shot["purpose"] = "rewritten editorial purpose"
        shot["lyric_context"] = "rewritten lyric context"
        shot["music_context"] = "rewritten music context"
    write_json(root / P.STAGE_FILES["storyboard"], edited)
    brief = P.load_brief(root)
    editorial = brief.model_copy(
        update={
            "creative": brief.creative.model_copy(
                update={
                    "arc": [VisualBeat(phase="night", intention="another editorial arc")],
                    "proof_shot_ids": ["s002", "s003", "s001"],
                }
            )
        }
    )
    write_json(root / "brief.json", editorial.model_dump())
    after = P.load_board(root)
    assert {s.id: digest(P.image_spec(root, s)) for s in after.shots} == baseline

    # Global appearance changes invalidate every still.
    appearance = editorial.model_copy(
        update={"creative": editorial.creative.model_copy(update={"look": "LOOK: changed"})}
    )
    write_json(root / "brief.json", appearance.model_dump())
    assert digest(P.image_spec(root, P.load_board(root).shots[0])) != baseline["s001"]
    appearance_baseline = {s.id: digest(P.image_spec(root, s)) for s in P.load_board(root).shots}

    # A bound scene description changes only its own shots.
    scenes = [
        s.model_copy(update={"description": "SCENE-STREET rewritten"}) if s.id == "street" else s
        for s in appearance.creative.scenes
    ]
    write_json(
        root / "brief.json",
        appearance.model_copy(
            update={"creative": appearance.creative.model_copy(update={"scenes": scenes})}
        ).model_dump(),
    )
    scene_changed = {s.id: digest(P.image_spec(root, s)) for s in P.load_board(root).shots}
    assert scene_changed["s001"] != appearance_baseline["s001"]
    assert scene_changed["s002"] == appearance_baseline["s002"]

    # An unrelated scene or reference change leaves every image untouched.
    unrelated = [
        s.model_copy(update={"description": "SCENE-UNUSED rewritten"})
        if s.id == "unused_scene"
        else s
        for s in scenes
    ]
    refs = [
        r.model_copy(update={"description": "REF-UNUSED rewritten"}) if r.id == "unused" else r
        for r in appearance.creative.references
    ]
    write_json(
        root / "brief.json",
        appearance.model_copy(
            update={
                "creative": appearance.creative.model_copy(
                    update={"scenes": unrelated, "references": refs}
                )
            }
        ).model_dump(),
    )
    assert {s.id: digest(P.image_spec(root, s)) for s in P.load_board(root).shots} == scene_changed


# --------------------------------------------------------------------------- #
# 3. explicit proof selection
# --------------------------------------------------------------------------- #
def test_creative_requires_explicit_unique_known_proof_ids(tmp_path):
    root = make_root(tmp_path, proof_shot_ids=())
    board = P.load_board(root)
    brief = P.load_brief(root)
    with pytest.raises(ValueError, match="exactly 3"):
        P.proof_ids(board, brief)
    with pytest.raises(ValueError):
        P.require_approval(root, "proof")

    unknown = brief.model_copy(
        update={
            "creative": brief.creative.model_copy(
                update={"proof_shot_ids": ["s999", "s001", "s002"]}
            )
        }
    )
    with pytest.raises(ValueError, match="unique, known"):
        P.proof_ids(board, unknown)

    explicit = make_root(tmp_path, name="explicit")
    assert P.proof_ids(P.load_board(explicit), P.load_brief(explicit)) == [
        "s001",
        "s002",
        "s004",
    ]


def test_set_proof_ids_records_the_selection_and_invalidates_the_brief(tmp_path):
    root = make_root(tmp_path, proof_shot_ids=())
    approve_prerequisites(root)
    before = P.stage_hash(root, "brief")

    selected = P.set_proof_ids(root, ["s001", "s002", "s003"])
    assert selected == ["s001", "s002", "s003"]
    assert P.load_brief(root).creative.proof_shot_ids == selected
    assert P.stage_hash(root, "brief") != before
    with pytest.raises(ValueError, match="current user approval"):
        P.require_approval(root, "brief")

    with pytest.raises(ValueError, match="exactly 3"):
        P.set_proof_ids(root, ["s001", "s002"])
    with pytest.raises(ValueError, match="unique, known"):
        P.set_proof_ids(root, ["s999", "s001", "s002"])
    with pytest.raises(ValueError, match="list"):
        P.set_proof_ids(root, "s001")


def test_creative_storyboard_approval_requires_proof_selection(tmp_path):
    root = make_root(tmp_path, proof_shot_ids=())
    approve_prerequisites(root)
    with pytest.raises(ValueError, match="exactly 3"):
        P.approve(root, "storyboard", "user")


# --------------------------------------------------------------------------- #
# 4. stage gates: creative stills need preview, legacy stills need proof
# --------------------------------------------------------------------------- #
def test_creative_stills_require_preview_while_legacy_require_proof(tmp_path):
    creative = make_root(tmp_path)
    approve_through_proof(creative)
    with pytest.raises(ValueError, match="preview"):
        G.quote_images(creative, "stills", "0.01")

    legacy = make_root(tmp_path, name="legacy", creative=False, with_events=False)
    approve_prerequisites(legacy)
    P.approve(legacy, "storyboard", "user")
    with pytest.raises(ValueError, match="proof"):
        G.quote_images(legacy, "stills", "0.01")


def test_guided_stills_quote_and_generate_share_the_style_gate(tmp_path):
    from mp3_to_videoclip import flow

    root = make_root(tmp_path, name="guided")
    flow.mark(root)
    approve_through_proof(root)
    client = FakeRunware(root)
    quote = G.quote_images(root, "stills", "0.01", client=client)
    G.authorize(root, quote["id"], "0.01", "test user authorized the scoped full set")
    G.generate(root, quote["id"], client)
    assert "preview" not in read_json(root / "work/approvals.json")
    assert client.submissions, "a guided stills quote must generate once the style gate is approved"


def test_old_proof_quote_cannot_generate_now_nonproof_shots(tmp_path):
    root = make_root(tmp_path)
    approve_prerequisites(root)
    P.approve(root, "storyboard", "test user approved initial storyboard")
    client = FakeRunware(root)
    quote = G.quote_images(root, "proof", "0.01", client=client)
    G.authorize(root, quote["id"], "0.03", "test user authorized initial proof only")
    brief = read_json(root / "brief.json")
    brief["creative"]["proof_shot_ids"] = ["s001", "s002", "s003"]
    write_json(root / "brief.json", brief)
    P.approve(root, "brief", "test user changed proof selection")
    P.approve(root, "storyboard", "test user reapproved with new proof selection")
    with pytest.raises(ValueError, match="outside.*scope"):
        G.generate(root, quote["id"], client)
    assert not client.submissions and read_json(root / "work/tasks.json") == {}


def test_required_visible_placeholder_blocks_storyboard_approval(tmp_path):
    root = make_root(tmp_path)
    approve_prerequisites(root)
    board = read_json(root / P.STAGE_FILES["storyboard"])
    board["shots"][0]["must_show"] = ["TODO: the important prop"]
    write_json(root / P.STAGE_FILES["storyboard"], board)
    with pytest.raises(ValueError, match="placeholders"):
        P.approve(root, "storyboard", "test user")


# --------------------------------------------------------------------------- #
# 5. preview binding
# --------------------------------------------------------------------------- #
def test_preview_binding_validates_report_movie_and_note(tmp_path):
    root = make_root(tmp_path)
    approve_through_proof(root)
    report = write_preview_report(root)

    with pytest.raises(ValueError, match="note"):
        P.approve(root, "preview", "  ")

    def rewrite(update):
        value = copy.deepcopy(report)
        value.update(update)
        write_json(root / P.STAGE_FILES["preview"], value)

    rewrite({"proof_hash": "0" * 64})
    with pytest.raises(ValueError, match="proof set"):
        P.approve(root, "preview", "user")
    rewrite({"storyboard_hash": "0" * 64})
    with pytest.raises(ValueError, match="storyboard"):
        P.approve(root, "preview", "user")
    rewrite({"movie": "work/absent.mp4"})
    with pytest.raises(ValueError, match="missing"):
        P.approve(root, "preview", "user")
    rewrite({"movie": "../escape.mp4"})
    with pytest.raises(ValueError, match="inside"):
        P.approve(root, "preview", "user")

    write_preview_report(root)
    (root / "work/preview-v001.mp4").write_bytes(b"tampered after review")
    with pytest.raises(ValueError, match="changed"):
        P.approve(root, "preview", "user")

    write_preview_report(root)
    P.approve(root, "preview", "test user reviewed the local preview")
    P.require_approval(root, "preview")


def test_full_set_generation_does_not_stale_proof_only_preview(tmp_path):
    root = make_root(tmp_path)
    approve_through_proof(root)
    write_preview_report(root)
    P.approve(root, "preview", "test user reviewed proof-only preview")
    preview_hash = P.stage_hash(root, "preview")

    record_stills(root, ["s003"])  # the rest of the full set
    assert P.stage_hash(root, "stills")
    P.require_approval(root, "preview")
    assert P.stage_hash(root, "preview") == preview_hash


# --------------------------------------------------------------------------- #
# 6. events, board validation and skeleton timing
# --------------------------------------------------------------------------- #
def test_brief_binds_events_and_requires_their_approval(tmp_path):
    root = make_root(tmp_path)
    P.approve(root, "analysis", "user")
    P.approve(root, "lyrics", "user", True)
    with pytest.raises(ValueError, match="events"):
        P.approve(root, "brief", "user")
    baseline = None
    P.approve(root, "events", "user")
    baseline = P.stage_hash(root, "brief")
    write_json(
        root / P.STAGE_FILES["events"],
        EventMap(
            source_sha256=P.load_project(root).source_sha256,
            fps=24,
            total_frames=48,
            pulse="variable",
            events=[MusicEvent(id="e1", frame=24, kind="section", label="Reviewed lift")],
        ).model_dump(),
    )
    assert P.stage_hash(root, "brief") != baseline
    with pytest.raises(ValueError, match="events"):
        P.approve(root, "brief", "user")
    P.approve(root, "events", "test user reviewed changed events")
    P.approve(root, "brief", "user")

    legacy = make_root(tmp_path, name="legacy", creative=False, with_events=False)
    assert P.stage_hash(legacy, "analysis")
    assert not (legacy / P.STAGE_FILES["events"]).exists()


def test_event_map_source_identity_and_refuses_overwrite(tmp_path):
    root = make_root(tmp_path, with_storyboard=False, with_events=False)
    events = P.init_events(root)
    assert events.events == [] and events.pulse == "unknown"
    assert events.source_sha256 == P.load_project(root).source_sha256
    with pytest.raises(ValueError, match="already exist"):
        P.init_events(root)

    write_json(
        root / P.STAGE_FILES["events"],
        EventMap(source_sha256="0" * 64, fps=24, total_frames=48).model_dump(),
    )
    with pytest.raises(ValueError, match="does not match"):
        P.load_events(root)


def test_load_board_validates_bound_ids(tmp_path):
    root = make_root(tmp_path)
    original = read_json(root / P.STAGE_FILES["storyboard"])

    def with_shot(update):
        value = copy.deepcopy(original)
        value["shots"][0].update(update)
        write_json(root / P.STAGE_FILES["storyboard"], value)

    with_shot({"scene_id": "ghost"})
    with pytest.raises(ValueError, match="unknown scene"):
        P.load_board(root)
    with_shot({"reference_ids": ["ghost"]})
    with pytest.raises(ValueError, match="unknown reference"):
        P.load_board(root)
    with_shot({"character_ids": ["ghost"]})
    with pytest.raises(ValueError, match="unknown character"):
        P.load_board(root)
    with_shot({"event_ids": ["ghost"]})
    with pytest.raises(ValueError, match="unknown musical event"):
        P.load_board(root)

    write_json(
        root / P.STAGE_FILES["events"],
        EventMap(
            source_sha256=P.load_project(root).source_sha256,
            fps=24,
            total_frames=48,
            events=[MusicEvent(id="e1", frame=12, kind="accent", label="Reviewed accent")],
        ).model_dump(),
    )
    with_shot({"event_ids": ["e1"]})
    assert P.load_board(root).shots[0].event_ids == ["e1"]

    missing = make_root(tmp_path, name="noevents", with_events=False)
    value = read_json(missing / P.STAGE_FILES["storyboard"])
    value["shots"][0]["event_ids"] = ["e1"]
    write_json(missing / P.STAGE_FILES["storyboard"], value)
    with pytest.raises(ValueError, match="missing"):
        P.load_board(missing)


def test_skeleton_beats_free_and_events(tmp_path):
    beats = make_root(tmp_path, name="beats", with_storyboard=False)
    approve_prerequisites(beats)
    board = P.skeleton(beats, 0.4, "beats")
    assert [s.id for s in board.shots] == ["s001", "s002"]
    assert [s.duration_frames for s in board.shots] == [24, 24]

    free = make_root(tmp_path, name="free", with_storyboard=False)
    approve_prerequisites(free)
    board = P.skeleton(free, 0.5, "free")
    assert [s.duration_frames for s in board.shots] == [12, 12, 12, 12]
    assert sum(s.duration_frames for s in board.shots) == P.load_project(free).total_frames

    events = make_root(tmp_path, name="events", with_storyboard=False, total_frames=120)
    write_json(
        events / P.STAGE_FILES["events"],
        EventMap(
            source_sha256=P.load_project(events).source_sha256,
            fps=24,
            total_frames=120,
            pulse="free",
            events=[
                MusicEvent(id="e1", frame=30, kind="release", label="Reviewed release"),
                MusicEvent(id="e2", frame=60, kind="section", label="Reviewed section"),
                MusicEvent(id="e3", frame=90, kind="build", label="Reviewed build"),
            ],
        ).model_dump(),
    )
    approve_prerequisites(events)
    board = P.skeleton(events, 1.0, "events")
    assert [s.start_frame for s in board.shots] == [0, 30, 60, 90]
    assert sum(s.duration_frames for s in board.shots) == 120

    estimated = make_root(tmp_path, name="estimated", with_storyboard=False)
    write_json(
        estimated / P.STAGE_FILES["events"],
        EventMap(
            source_sha256=P.load_project(estimated).source_sha256,
            fps=24,
            total_frames=48,
            events=[
                MusicEvent(
                    id="e1",
                    frame=20,
                    kind="section",
                    label="Estimated",
                    timing_basis="estimated",
                )
            ],
        ).model_dump(),
    )
    approve_prerequisites(estimated)
    with pytest.raises(ValueError, match="estimated"):
        P.skeleton(estimated, 1.0, "events")

    empty = make_root(tmp_path, name="empty", with_storyboard=False)
    approve_prerequisites(empty)
    with pytest.raises(ValueError, match="needs reviewed"):
        P.skeleton(empty, 1.0, "events")
    with pytest.raises(ValueError, match="timing must be"):
        P.skeleton(empty, 1.0, "everybeat")


# --------------------------------------------------------------------------- #
# 7. instrumental mode
# --------------------------------------------------------------------------- #
def test_instrumental_init_and_stage_gates(tmp_path, monkeypatch):
    source = tmp_path / "song.mp3"
    source.write_bytes(b"original audio")
    monkeypatch.setattr(
        P, "probe", lambda _: {"format": {"duration": "2.0"}, "streams": [{"codec_type": "audio"}]}
    )
    monkeypatch.setattr(P, "audio_seconds", lambda _: 2.0)
    root = tmp_path / "instrumental"
    project = P.init_project(root, source, "instrumental", music_mode="instrumental")
    # Brandless fixture: this test covers instrumental music gates, and the default
    # identity intro is intentionally longer than the two-second test source.
    (root / "brand.json").unlink()
    # Signature approval is a separate gate; this fixture exercises instrumental
    # music gates only, so keep the required signature from blocking brief approval.
    stored = json.loads((root / "project.json").read_text())
    stored["signature_required"] = False
    write_json(root / "project.json", stored)
    assert project.music_mode == "instrumental"
    assert P.load_project(root).music_mode == "instrumental"
    assert P.load_brief(root).creative is not None
    assert P.load_events(root).events == []
    assert not (root / "work/lyrics.json").exists()
    assert P.effective_upstream(root, "brief") == "analysis"
    with pytest.raises(ValueError, match="instrumental"):
        P.approve(root, "lyrics", "user")
    with pytest.raises(ValueError, match="instrumental"):
        G.quote_transcription(root, provider="openai")

    brief = P.load_brief(root)
    write_json(root / "work/music.json", {"duration": 2.0, "beats": []})
    write_json(
        root / "brief.json",
        brief.model_copy(
            update={
                "direction": "Instrumental",
                "style": "Ambient",
                "treatment": "Abstract",
                "creative": brief.creative.model_copy(
                    update={
                        "look": profiles.DEFAULT_STYLE + "\n\nSoft monochrome",
                        "profile_version": 1,
                    }
                ),
            }
        ).model_dump(),
    )
    P.approve(root, "analysis", "user")
    P.approve(root, "events", "user")
    P.approve(root, "brief", "user")  # No lyrics approval is fabricated or required.
    P.require_approval(root, "brief")
    with pytest.raises(ValueError, match="instrumental"):
        P.require_approval(root, "lyrics")
