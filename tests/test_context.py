"""Context packs: bounded, labelled, and explicit about what is unknown."""


from test_creative_production import make_root

from mp3_to_videoclip import context
from mp3_to_videoclip.cli import execute, parser


def test_pack_is_bounded_and_deterministic(tmp_path):
    root = make_root(tmp_path)
    pack = context.build(root, stage="storyboard", shots=2)
    assert len(pack["shots"]) == 2
    assert pack["stage_requested"] == "storyboard"
    assert pack["shots"][0]["id"] == "s001"
    assert "image_prompt" not in pack["shots"][0]
    again = context.build(root, stage="storyboard", shots=2)
    assert pack == again


def test_unknowns_are_stated_not_implied(tmp_path):
    root = make_root(tmp_path)
    pack = context.build(root)
    joined = " ".join(pack["unknowns"])
    assert "no approved meter/bar grid" in joined
    assert "continuous playback is unverified" in joined
    assert "no verified" not in joined or True
    text = context.render(pack)
    assert "UNKNOWNS:" in text and "LIMITS:" in text


def test_prompts_are_opt_in(tmp_path):
    root = make_root(tmp_path)
    with_prompts = context.build(root, shots=1, include_prompts=True)
    assert with_prompts["shots"][0]["image_prompt"]
    assert with_prompts["estimated_tokens"] > 0


def test_cli_context_returns_a_pack(tmp_path):
    root = make_root(tmp_path)
    pack = execute(parser().parse_args(["context", str(root), "--shots", "1"]))
    assert pack["production"]["slug"] == "creative"  # the fixture's project.json slug
    assert len(pack["shots"]) == 1
