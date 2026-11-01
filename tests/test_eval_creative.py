"""The cliché count, shot variety and a judge that only ever speaks when spending is allowed."""

from __future__ import annotations

import json

import pytest
from evals import judge, lexicon, reference, runner


def test_the_cliché_count_finds_stems_per_thousand_words():
    text = "A lone figure on a rooftop watches the neon. " + "plain " * 90
    value = lexicon.cliche_report(text)
    assert value["hits"] == {"lone figure": 1, "rooftop": 1, "neon": 1}
    assert value["per_thousand"] > 8 and value["ok"] is False
    assert lexicon.cliche_report("a whetstone on the field edge")["ok"] is True


def test_every_cliché_named_in_the_craft_file_is_counted():
    for stem in ("rain on a window", "hourglass", "phones up", "candle blown", "page turned"):
        assert stem in lexicon.CLICHES


def test_a_board_of_one_kind_of_shot_has_no_entropy():
    same = {"shots": [{"framing": "wide", "kind": "scene", "scene_id": "a"} for _ in range(8)]}
    assert lexicon.entropy_report(same) == {"framing": 0, "kind": 0, "scene_id": 0, "total": 0, "ok": False}  # fmt: skip
    mixed = {
        "shots": [{"framing": f, "kind": "scene", "scene_id": "a"} for f in ("wide", "detail")]
    }
    assert lexicon.entropy_report(mixed)["framing"] == 1.0


def test_every_fixture_has_a_reference_run_that_passes(tmp_path):
    made = reference.write_all(tmp_path)
    assert len(made) == 4
    for run in made:
        value = runner.evaluate_run(run)
        assert value["ok"], (run.name, value["error"], value["checks"])
        assert value["checks"]["cliches"]["per_thousand"] == 0
        assert value["synthetic"] is True


def test_the_committed_reference_runs_match_the_generator(tmp_path):
    reference.write_all(tmp_path)
    for run in tmp_path.iterdir():
        for name in ("treatments.json", "storyboard.json", "meta.json"):
            assert (run / name).read_text() == (reference.RUNS / run.name / name).read_text()


def test_a_judge_needs_spending_allowed():
    with pytest.raises(judge.SpendNotAllowed):
        judge.require_spend("openai/x", False)
    judge.require_spend("openai/x", True)
    judge.require_spend(None, False)
    with pytest.raises(judge.SpendNotAllowed):
        runner.main(["--judge", "openai/x"])


class Fake:
    def __init__(self, reply):
        self.reply = reply
        self.seen = []

    async def stream(self, messages, tools=None, system=None):
        from mp3_to_videoclip.director.llm import TextDelta
        from mp3_to_videoclip.director.providers.base import TurnResult, Usage

        self.seen.append(messages[0]["content"])
        yield TextDelta(text=self.reply)
        yield Usage(prompt_tokens=7, completion_tokens=3)
        yield TurnResult(text=self.reply)


SCORE = json.dumps(
    {
        "originality": 3,
        "song_specificity": 2,
        "cliche_density": 5,
        "shot_variety": 4,
        "sentence": "Good.",
    }
)


def test_a_score_keeps_what_the_judge_used():
    value = judge.score(Fake(SCORE), {"concepts": []}, {"shots": []})
    assert value["scores"]["cliche_density"] == 5
    assert value["usage"] == {"prompt_tokens": 7, "completion_tokens": 3}
    with pytest.raises(ValueError, match="outside"):
        judge.score(Fake(SCORE.replace('"originality": 3', '"originality": 9')), {}, {})


def test_a_pair_is_blind_and_the_answer_comes_back_unshuffled():
    first = {"treatments": {"concepts": [{"title": "first film"}]}, "board": {}}
    second = {"treatments": {"concepts": [{"title": "second film"}]}, "board": {}}
    client = Fake(json.dumps({"prefer": "A", "sentence": "Clearer."}))
    value = judge.blind_pair(client, first, second, seed=1)
    shown = client.seen[0]
    expected = "first" if shown.index("first film") < shown.index("second film") else "second"
    assert value["prefer"] == expected
    assert "hash" not in shown


def test_judging_writes_to_real_runs_and_leaves_references_alone(tmp_path):
    reference.write_all(tmp_path)
    assert runner.judge_runs(tmp_path, "x/y", llm=Fake(SCORE)) == 0
    real = tmp_path / "reference-advert-30s"
    meta = json.loads((real / "meta.json").read_text())
    meta["synthetic"] = False
    (real / "meta.json").write_text(json.dumps(meta))
    assert runner.judge_runs(tmp_path, "x/y", llm=Fake(SCORE)) == 1
    assert json.loads((real / "meta.json").read_text())["judge"]["model"] == "x/y"
