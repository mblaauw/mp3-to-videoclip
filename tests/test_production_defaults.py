"""New defaults and supported controls. Only synthetic audio and fake providers."""

import pytest
from test_creative_production import approve_prerequisites, jpeg
from test_native_size import init, synth_source
from test_production import FakeRunware, fake_schema
from test_workflow_v2 import strict_root

from mp3_to_videoclip import budget, profiles
from mp3_to_videoclip import generation as G
from mp3_to_videoclip import production as P
from mp3_to_videoclip.cli import execute, parser
from mp3_to_videoclip.models import ImageSettings
from mp3_to_videoclip.references import import_reference
from mp3_to_videoclip.storage import digest, read_json, write_json


def nano_schema():
    """Offline subset of the public 2026-10-17 contract, not a live-provider test."""
    schema = fake_schema()
    schema["info"]["x-air-id"] = profiles.DEFAULT_MODEL_AIR
    item = schema["components"]["schemas"]["RequestBody"]["items"]
    props = item["properties"]
    props["model"] = {"const": profiles.DEFAULT_MODEL_AIR}
    props["settings"] = ImageSettings.model_json_schema()
    props["seed"] = {"type": "integer", "minimum": 0, "maximum": 2147483647}
    props["inputs"]["properties"]["referenceImages"]["maxItems"] = 14
    item["oneOf"] = [
        {"properties": {"width": {"const": w}, "height": {"const": h}}}
        for w, h in ((1376, 768), (768, 1376), (2752, 1536), (1536, 2752))
    ]
    return schema


class Nano(FakeRunware):
    def schema(self, model):
        self.requested_model = model
        return nano_schema() if model == profiles.DEFAULT_MODEL else fake_schema()


def profiled(root):
    config = read_json(root / "project.json")
    config.update(
        image_model=profiles.DEFAULT_MODEL,
        image_settings=profiles.default_settings(),
        native_size=[1376, 768],
    )
    write_json(root / "project.json", config)
    return root


def test_new_init_persists_exact_profile_and_portrait_size(tmp_path):
    root = tmp_path / "default"
    result = init(root, synth_source(tmp_path), "--aspect", "9:16")
    assert result["image_model"] == profiles.DEFAULT_MODEL
    assert result["image_settings"] == profiles.default_settings()
    assert result["native_size"] == [768, 1376]
    assert result["style_preset"] == profiles.STYLE_PRESET_ID
    assert P.load_brief(root).creative.look == profiles.DEFAULT_STYLE
    assert P.load_brief(root).creative.image_rules == list(profiles.DEFAULT_IMAGE_RULES)
    assert read_json(root / "work/approvals.json") == {}
    assert read_json(root / "work/tasks.json") == {}


def test_explicit_init_overrides_replace_default_model_style_settings(tmp_path):
    root = tmp_path / "custom"
    result = init(
        root,
        synth_source(tmp_path),
        "--model",
        "other-model",
        "--style",
        "Flat charcoal illustration",
        "--native-size",
        "1536x864",
        "--image-settings",
        "{}",
        "--image-seed",
        "123",
    )
    assert result["image_model"] == "other-model" and result["image_settings"] == {}
    assert result["style_preset"] == "custom" and result["image_seed"] == 123
    assert P.load_brief(root).creative.look == "Flat charcoal illustration"
    assert result["native_size"] == [1536, 864]


@pytest.mark.parametrize(
    "args",
    [
        ["--image-settings", '{"thinking":"high"}'],
        ["--image-settings", '{"temperature":NaN}'],
        ["--image-settings", '{"webSearch":"false"}'],
        ["--image-settings", "[]"],
        ["--image-settings", "null"],
        ["--image-seed", "-1"],
        ["--style", "   "],
    ],
)
def test_invalid_overrides_fail_before_creating_project(tmp_path, args):
    source = synth_source(tmp_path)
    root = tmp_path / "bad"
    with pytest.raises(ValueError):
        init(root, source, *args)
    assert not root.exists()


def test_quotes_and_submissions_include_stored_supported_controls(tmp_path):
    root = profiled(strict_root(tmp_path))
    config = read_json(root / "project.json")
    config["image_seed"] = 19
    write_json(root / "project.json", config)
    approve_prerequisites(root)
    P.approve(root, "storyboard", "test approved exact board")
    budget.set_budget(root, "1", "test authorized production")
    client = Nano(root)
    quote = G.quote_images(root, "proof", "0.01", client=client)
    assert client.requested_model == profiles.DEFAULT_MODEL
    for task in quote["tasks"]:
        assert task["request"]["settings"] == profiles.default_settings()
        assert task["request"]["seed"] == 19
    G.authorize(root, quote["id"], "0.03", "test authorized proof")
    G.generate(root, quote["id"], client)
    assert len(client.submissions) == 3
    assert all(r["settings"]["thinkingLevel"] == "minimal" for r in client.submissions)


def test_quote_model_override_does_not_inherit_google_settings(tmp_path):
    root = profiled(strict_root(tmp_path))
    approve_prerequisites(root)
    P.approve(root, "storyboard", "test approved exact board")
    client = Nano(root)
    quote = G.quote_images(root, "proof", "0.01", model="other-model", client=client)
    assert client.requested_model == "other-model"
    assert all("settings" not in task["request"] for task in quote["tasks"])
    assert P.load_project(root).image_model == profiles.DEFAULT_MODEL


def test_foreign_model_assets_cannot_satisfy_canonical_currency(tmp_path):
    root = profiled(strict_root(tmp_path))
    approve_prerequisites(root)
    P.approve(root, "storyboard", "test approved exact board")
    budget.set_budget(root, "1", "test authorized production")
    client = Nano(root)
    alternate = G.quote_images(root, "proof", "0.01", model="other-model", client=client)
    G.authorize(root, alternate["id"], "0.03", "test authorized alternative model")
    G.generate(root, alternate["id"], client)
    with pytest.raises(ValueError, match="no current selected still"):
        P.resolved_assets(root, ["s001"])
    canonical = G.quote_images(root, "proof", "0.01", client=client)
    assert len(canonical["tasks"]) == 3
    assert {t["input_hash"] for t in alternate["tasks"]}.isdisjoint(
        {t["input_hash"] for t in canonical["tasks"]}
    )
    # Explicitly adopting the alternative's model AND controls makes its bytes
    # current; changed project/brief/board still need their normal approvals.
    config = read_json(root / "project.json")
    config.update(image_model="other-model", image_settings={})
    write_json(root / "project.json", config)
    assert len(P.resolved_assets(root, ["s001"])) == 1


def test_noncreative_legacy_reference_cap_is_still_four(tmp_path):
    root = strict_root(tmp_path)
    config = read_json(root / "project.json")
    config.pop("workflow_version")
    write_json(root / "project.json", config)
    brief = read_json(root / "brief.json")
    brief["creative"] = None
    paths = []
    for n in range(5):
        path = jpeg(root / f"ref{n}.jpg", (n + 10, 20, 30))
        paths.append(str(path.relative_to(root)))
    brief["characters"][0]["references"] = paths
    write_json(root / "brief.json", brief)
    board = read_json(root / "work/storyboard.json")
    for shot in board["shots"]:
        shot.update(scene_id=None, reference_ids=[])
    write_json(root / "work/storyboard.json", board)
    with pytest.raises(ValueError, match="at most 4 reference"):
        P.image_spec(root, P.load_board(root).shots[0])


def test_model_settings_change_input_hash_and_tampered_quote_is_rejected(tmp_path):
    root = profiled(strict_root(tmp_path))
    approve_prerequisites(root)
    P.approve(root, "storyboard", "test approved exact board")
    budget.set_budget(root, "1", "test authorized production")
    client = Nano(root)
    quote = G.quote_images(root, "proof", "0.01", client=client)
    quote["tasks"][0]["request"]["settings"]["thinkingLevel"] = "high"
    write_json(root / f"work/quotes/{quote['id']}.json", quote)
    G.authorize(root, quote["id"], "0.03", "test signed modified request")
    with pytest.raises(ValueError, match="matches its approved shot specification"):
        G.generate(root, quote["id"], client)
    assert client.submissions == []
    shot = P.load_board(root).shots[0]
    original = digest(P.image_spec(root, shot))
    config = read_json(root / "project.json")
    config["image_settings"]["thinkingLevel"] = "medium"
    write_json(root / "project.json", config)
    assert original != digest(P.image_spec(root, shot))


def test_more_than_four_references_allowed_but_selected_schema_still_limits(tmp_path):
    root = profiled(strict_root(tmp_path))
    brief = read_json(root / "brief.json")
    for n in range(3):
        path = jpeg(root / f"extra{n}.jpg", (30 + n, 40, 50))
        ref = import_reference(root, path, note="test-owned reference", permission_confirmed=True)
        brief["creative"]["references"].append(
            {
                "id": f"extra{n}",
                "kind": "style",
                "description": "Style only",
                "path": ref["path"],
                "permission_confirmed": True,
            }
        )
        brief["creative"]["global_reference_ids"].append(f"extra{n}")
    write_json(root / "brief.json", brief)
    approve_prerequisites(root)
    P.approve(root, "storyboard", "test approved exact board")
    quote = G.quote_images(root, "proof", "0.01", client=Nano(root))
    assert max(len(t["references"]) for t in quote["tasks"]) > 4
    with pytest.raises(ValueError, match="rejected by model schema"):
        G.quote_images(root, "proof", "0.01", model="other-model", client=Nano(root))


def test_one_correction_default_for_new_budget_not_existing_budget(tmp_path):
    root = strict_root(tmp_path)
    budget.set_budget(root, "1", "test allowance", max_corrections=2)
    assert budget.correction_policy(root) == (True, 2)
    other = execute(
        parser().parse_args(["budget", str(root), "--cap", "1", "--note", "test revised allowance"])
    )
    assert other["max_corrections"] == 2
    explicit = execute(
        parser().parse_args(
            [
                "budget",
                str(root),
                "--cap",
                "1",
                "--max-corrections",
                "1",
                "--note",
                "test explicitly revised correction limit",
            ]
        )
    )
    assert explicit["max_corrections"] == 1
    (root / "work/production-budget.json").unlink()
    fresh = execute(
        parser().parse_args(["budget", str(root), "--cap", "1", "--note", "test new allowance"])
    )
    assert fresh["max_corrections"] == 1


def test_default_correction_limit_on_the_journaled_generation_path(tmp_path):
    root = profiled(strict_root(tmp_path))
    approve_prerequisites(root)
    P.approve(root, "storyboard", "test approved exact board")
    budget.set_budget(root, "1", "test new production allowance")
    client = Nano(root)
    for _ in range(2):
        quote = G.quote_images(root, "proof", "0.01", ids=["s001"], regenerate=True, client=client)
        G.authorize(root, quote["id"], "0.01", "test explicitly authorized this attempt")
        G.generate(root, quote["id"], client)
    assert len(client.submissions) == 2
    guarded = Nano(root)
    with pytest.raises(ValueError, match="only 1 correction"):
        G.quote_images(root, "proof", "0.01", ids=["s001"], regenerate=True, client=guarded)
    assert not hasattr(guarded, "requested_model")
    journal = read_json(root / "work/tasks.json")
    assert len(journal) == 2 and all(t["status"] == "ready" for t in journal.values())
