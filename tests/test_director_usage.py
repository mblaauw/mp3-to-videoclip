"""What a turn used is written down, an unknown cost stays unknown, and spending needs the owner."""

from __future__ import annotations

import asyncio
import json
from decimal import Decimal

import pytest
from api_support import api_client, make_api_project

from mp3_to_videoclip import catalog
from mp3_to_videoclip.config import Settings
from mp3_to_videoclip.director import conversation, loop, pricing, usage
from mp3_to_videoclip.director.llm import TextDelta, ToolCall, TurnResult, Usage


class Script:
    model = "m"

    def __init__(self, *turns):
        self.turns = list(turns)
        self.sent = []

    async def stream(self, messages, tools=None, system=None):
        self.sent.append(list(messages))
        for event in self.turns.pop(0):
            yield event


def _text(text, used=None):
    return [TextDelta(text), used or Usage(), TurnResult(text=text)]


def _call(name="get_brief", arguments='{"slug": "production"}', text="", used=None):
    call = ToolCall(id="c" + str(id(name)), name=name, arguments=arguments)
    return [TextDelta(text)] * bool(text) + [
        call,
        used or Usage(),
        TurnResult(text=text, tool_calls=[call]),
    ]


def _play(root, llm, role="writer", provider="openai", **kwargs):
    async def go():
        return [
            event
            async for event in loop.run_turn(
                llm, root, root.name, "Go", "System", role=role, provider=provider,
                projects_dir=root.parent, **kwargs,
            )
        ]  # fmt: skip

    return asyncio.run(go())


def test_counts_sum_across_a_turn_and_are_recorded(tmp_path):
    root = make_api_project(tmp_path)
    used = Usage(prompt_tokens=10, completion_tokens=2, reported=True)
    events = _play(root, Script(_call(used=used), _text("Done", used=used)))
    counts = events[-1].payload["usage"]
    assert (counts["prompt_tokens"], counts["completion_tokens"]) == (20, 4)
    rows = (root / usage.FILE).read_text().splitlines()
    assert len(rows) == 1
    assert json.loads(rows[0])["prompt_tokens"] == 20
    assert usage.summary(root)["turns"] == 1


def test_one_call_without_counts_makes_the_whole_turn_unknown(tmp_path):
    root = make_api_project(tmp_path)
    good = Usage(prompt_tokens=10, completion_tokens=2, reported=True)
    events = _play(root, Script(_call(used=good), _text("Done")))
    assert events[-1].payload["usage"]["cost_usd"] is None
    assert events[-1].payload["usage"]["cost_basis"] == pricing.UNREPORTED


def test_a_cost_is_only_stated_from_a_stated_price(monkeypatch):
    used = Usage(prompt_tokens=1000, completion_tokens=1000, reported=True)
    assert pricing.cost_of("openai", "no-such-model", used) == (None, pricing.UNPRICED)
    assert pricing.cost_of("openai", "gpt-6.1-sol", used)[0] is None
    priced = catalog.Model(
        id="m",
        provider="p",
        price=catalog.Price(amount="0.001", unit="1k_tokens_in"),
        price_out=catalog.Price(amount="0.002", unit="1k_tokens_out"),
    )
    monkeypatch.setattr(catalog, "load", lambda: catalog.Catalog(models=[priced]))
    assert pricing.cost_of("p", "m", used) == ("0.003000", pricing.ESTIMATE)
    assert pricing.cost_of("p", "m", Usage(reported=False))[0] is None


def test_a_film_total_counts_the_turns_with_no_price(tmp_path):
    for cost, basis in (("0.25", pricing.ESTIMATE), (None, pricing.UNPRICED)):
        usage.record(
            tmp_path, turn_id="t", role="writer", provider="p", model="m",
            usage=Usage(prompt_tokens=1, completion_tokens=1), cost_usd=cost, cost_basis=basis,
        )  # fmt: skip
    total = usage.summary(tmp_path)
    assert (total["turns"], total["cost_usd"], total["unpriced_turns"]) == (2, "0.25", 1)
    assert usage.summary(tmp_path / "nothing")["turns"] == 0


def test_the_model_never_sees_the_logs_bookkeeping(tmp_path):
    root = make_api_project(tmp_path)
    conversation.append_message(
        root, {"role": "user", "content": "Earlier", "prompt": {"hash": "h"}}, agent="writer"
    )
    conversation.append_message(
        root, {"role": "assistant", "content": "", "usage": {"x": 1}}, agent="writer"
    )
    conversation.append_message(
        root, {"role": "tool", "tool_call_id": "c", "name": "n", "content": "r"}, agent="writer"
    )
    conversation.append_message(root, {"role": "assistant", "content": "Said"}, agent="writer")
    llm = Script(_text("Now"))
    _play(root, llm)
    assert llm.sent[0] == [
        {"role": "user", "content": "Earlier"},
        {"role": "assistant", "content": "Said"},
        {"role": "user", "content": "Go"},
    ]


def test_a_critic_starts_with_fresh_eyes_every_time(tmp_path):
    root = make_api_project(tmp_path)
    conversation.append_message(root, {"role": "user", "content": "Old review"}, agent="critic")
    llm = Script(_text("Notes"))
    _play(root, llm, role="critic")
    assert llm.sent[0] == [{"role": "user", "content": "Go"}]


def test_reasoning_between_tools_is_kept_and_survives_compaction(tmp_path):
    root = make_api_project(tmp_path)
    _play(root, Script(_call(text="Because the chorus turns."), _text("Done")))
    rows = conversation.load_messages(root, "writer")
    assert any(row.get("with_tools") and "chorus" in row["content"] for row in rows)
    long = rows + [{"role": "user", "content": f"q{i}"} for i in range(80)]
    _, summary = conversation.compact_messages(long)
    assert "Because the chorus turns." in summary


def test_the_same_failing_call_twice_stops_the_turn(tmp_path):
    root = make_api_project(tmp_path)
    bad = '{"slug": "no-such-film"}'
    llm = Script(_call(arguments=bad), _call(arguments=bad), _text("never reached"))
    events = _play(root, llm)
    assert "repeating a failed call to get_brief" in events[-1].payload["error"]
    assert len(llm.turns) == 1


def test_the_step_limit_says_so_and_can_be_resumed(tmp_path):
    root = make_api_project(tmp_path)
    llm = Script(_call(), _call())
    events = _play(root, llm, max_tool_calls=2)
    done = events[-1]
    assert done.payload["limit"] is True
    assert done.payload["steps"] == 2
    assert "Stopped after 2 steps." in done.text
    assert loop.MAX_TOOL_CALLS == 40


def test_a_role_with_no_key_is_refused_by_name_and_no_other_model_answers(tmp_path, monkeypatch):
    root = make_api_project(tmp_path)
    settings = Settings(writer_model="openai/gpt-6.1-sol")
    monkeypatch.setattr("mp3_to_videoclip.api.director.effective_settings", lambda: settings)
    with api_client(tmp_path) as client:
        refused = client.post(
            f"/api/projects/{root.name}/chat", json={"message": "Hi", "stage": "story"}
        )
        assert refused.status_code == 503
        body = refused.json()
        assert body["code"] == "no_llm_key"
        assert "gpt-6.1-sol" in body["detail"] and "OpenAI" in body["detail"]
        said = client.get(f"/api/projects/{root.name}/director/model", params={"role": "writer"})
        assert said.json()["model"] == "gpt-6.1-sol"
        assert said.json()["has_key"] is False
        assert client.get(f"/api/projects/{root.name}/model-usage").json()["turns"] == 0


def test_a_chat_uses_the_roles_own_route(tmp_path, monkeypatch):
    root = make_api_project(tmp_path)
    seen = {}

    class Fake:
        model = "m"

        def __init__(self, base_url, api_key, model, kind, session_id):
            seen.update(base_url=base_url, key=api_key, model=model, kind=kind)
            self.model = model

        async def stream(self, messages, tools=None, system=None):
            yield TextDelta("Hi")
            yield Usage()
            yield TurnResult(text="Hi")

    monkeypatch.setattr("mp3_to_videoclip.api.director.DirectorLLM", Fake)
    settings = Settings(
        keys={"anthropic": "a"}, roles={"writer": {"provider": "anthropic", "model": "claude"}}
    )
    monkeypatch.setattr("mp3_to_videoclip.api.director.effective_settings", lambda: settings)
    with api_client(tmp_path) as client:
        answer = client.post(
            f"/api/projects/{root.name}/chat", json={"message": "Hi", "stage": "story"}
        )
    assert answer.status_code == 200
    assert seen == {"base_url": None, "key": "a", "model": "claude", "kind": "anthropic"}
    last = json.loads(answer.text.strip().splitlines()[-1])
    assert last["payload"]["usage"]["model"] == "claude"


class Luna(Script):
    model = "gpt-6-luna"


def _spend(root, cost):
    usage.record(
        root, turn_id="t", role="writer", provider="opencode-go", model="gpt-6-luna",
        usage=Usage(prompt_tokens=1, completion_tokens=1, reported=True), cost_usd=cost,
        cost_basis=pricing.ESTIMATE,
    )  # fmt: skip


def test_a_priced_turn_comes_out_of_the_films_cap(tmp_path):
    from mp3_to_videoclip import budget

    root = make_api_project(tmp_path)
    budget.set_budget(root, "1.00", "test")
    used = Usage(prompt_tokens=200_000, completion_tokens=20_000, reported=True)
    events = _play(root, Luna(_text("Done", used=used)), provider="opencode-go")
    assert events[-1].payload["usage"]["cost_usd"] == "0.030000"
    assert budget.commitment(root) == Decimal("0.03")
    assert budget.summary(root)["model_usd"] == "0.030000"
    assert budget.cost_summary(root)["by_kind"]["model"]["spent"] == Decimal("0.03")
    with pytest.raises(ValueError, match="exceeds the 1.00 cap"):
        budget.check_capacity(root, "0.98")


def test_a_priced_turn_does_not_start_once_the_cap_is_used(tmp_path):
    from mp3_to_videoclip import budget

    root = make_api_project(tmp_path)
    budget.set_budget(root, "1.00", "test")
    _spend(root, "1.00")
    llm = Luna(_text("Never"))
    events = _play(root, llm, provider="opencode-go")
    assert "has $0.00 left of its $1.00 budget" in events[-1].payload["error"]
    assert llm.sent == [] and conversation.load_messages(root, "writer") == []
    # A model with no stated price is held by the turn allowance instead.
    assert _play(root, Script(_text("Yes")))[-1].text == "Yes"


def test_a_turn_with_a_token_limit_needs_room_for_all_of_it(tmp_path):
    from mp3_to_videoclip import budget

    root = make_api_project(tmp_path)
    budget.set_budget(root, "1.00", "test")
    _spend(root, "0.95")
    events = _play(root, Luna(_text("Never")), provider="opencode-go", max_tokens=200_000)
    assert "may cost up to $0.10 at its 200,000-token limit" in events[-1].payload["error"]
    assert (
        _play(root, Luna(_text("Yes")), provider="opencode-go", max_tokens=50_000)[-1].text == "Yes"
    )


def test_the_token_limit_set_in_settings_stops_a_turn(tmp_path):
    root = make_api_project(tmp_path)
    used = Usage(prompt_tokens=900, completion_tokens=200, reported=True)
    llm = Script(_call(used=used), _text("Never"))
    events = _play(root, llm, max_tokens=1000)
    assert "stopped at the 1,000-token limit set in Settings" in events[-1].payload["error"]
    assert len(llm.sent) == 1
    assert usage.summary(root)["prompt_tokens"] == 900
