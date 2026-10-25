"""Recorded fake-provider probe: import, board, a mocked batch and one regeneration.

No network and no paid call. The scripted provider drives the real director turn
loop and the real tools; only the image service and the runner are fakes. This is
the Phase 3 probe record, and it also pins the stop time for a scripted turn.
"""

from __future__ import annotations

import asyncio
import json
import time

import pytest

from mp3_to_videoclip import production as P
from mp3_to_videoclip import services
from mp3_to_videoclip.director.llm import TextDelta, ToolCall, TurnResult
from mp3_to_videoclip.director.loop import run_turn
from mp3_to_videoclip.domain import intake
from mp3_to_videoclip.models import Lyrics, Segment
from mp3_to_videoclip.storage import write_json


class ScriptedLLM:
    def __init__(self, steps):
        self.steps = steps
        self.index = 0
        self.prompts = []
        self.systems = []

    async def stream(self, messages, tools=None, system=None):
        self.prompts.append(list(messages))
        self.systems.append(system)
        if self.index >= len(self.steps):
            yield TextDelta(text="Probe complete.")
            yield TurnResult(text="Probe complete.")
            return
        name, arguments = self.steps[self.index]
        self.index += 1
        call = ToolCall(id=f"probe-{self.index}", name=name, arguments=json.dumps(arguments))
        yield call
        yield TurnResult(text="", tool_calls=[call])


class RecordingRunner:
    def __init__(self):
        self.submitted = []

    def submit(self, kind, project, factory):
        self.submitted.append((kind, project))
        return f"probe-job-{len(self.submitted)}"


@pytest.fixture
def probe_project(tmp_path, monkeypatch):
    def fake_probe(path):
        return {"streams": [{"codec_type": "audio"}]}

    monkeypatch.setattr("mp3_to_videoclip.production.probe", fake_probe)
    monkeypatch.setattr("mp3_to_videoclip.production.audio_seconds", lambda path: 2.0)
    source = tmp_path / "probe.mp3"
    source.write_bytes(b"ID3probe")
    created = intake.create_from_upload(
        tmp_path / "projects", source, title="Probe Film", budget="5.00"
    )
    root = created["root"]
    write_json(
        root / "work" / "music.json",
        {"duration": 2.0, "beats": [0.0, 0.5, 1.0, 1.5], "sections": [], "warnings": []},
    )
    write_json(
        root / "work" / "lyrics.json",
        Lyrics(
            provider="manual",
            model="probe",
            segments=[Segment(start=0, end=1, text="probe line")],
        ).model_dump(),
    )
    brief = P.load_brief(root)
    brief.direction = "A scripted probe"
    brief.style = "A local probe"
    brief.treatment = "Import, board, one mocked batch, one regeneration."
    write_json(root / "brief.json", brief.model_dump())
    P.approve(root, "brief", "probe setup", via="studio", review_confirmed=True)
    return root


def test_scripted_provider_session_import_board_batch_and_regeneration(probe_project, monkeypatch):
    root = probe_project
    slug = root.name
    estimates = []
    authorized = []

    def fake_estimate(root_arg, shot_ids, *, scope, reserve, regenerate):
        estimates.append(
            {
                "shot_ids": list(shot_ids),
                "scope": scope,
                "reserve": reserve,
                "regenerate": regenerate,
            }
        )
        return {
            "quote_id": f"quote-{len(estimates)}",
            "scope": scope,
            "tasks": len(shot_ids),
            "reserve_usd": reserve,
            "cap_usd": "5.00",
            "uploads_required": False,
            "shot_ids": list(shot_ids),
        }

    def fake_authorize(root_arg, quote_id, *, note=None, **kwargs):
        authorized.append(quote_id)

    monkeypatch.setattr(services.generation, "estimate", fake_estimate)
    monkeypatch.setattr(services.generation, "authorize", fake_authorize)

    steps = [
        ("get_project", {"slug": slug}),
        ("create_storyboard", {"slug": slug, "seconds": 2, "timing": "adaptive"}),
        ("set_proof_shots", {"slug": slug, "shot_ids": ["s001"]}),
        (
            "generate_images",
            {"slug": slug, "shot_ids": ["s001"], "scope": "proof", "regenerate": False},
        ),
        (
            "generate_images",
            {
                "slug": slug,
                "shot_ids": ["s001"],
                "scope": "proof",
                "regenerate": True,
                "note": "one corrected proof",
            },
        ),
    ]
    llm = ScriptedLLM(steps)
    runner = RecordingRunner()

    async def collect():
        return [
            event
            async for event in run_turn(
                llm,
                root,
                slug,
                "Run the recorded probe.",
                "probe system",
                runner=runner,
                projects_dir=root.parent,
            )
        ]

    started = time.perf_counter()
    events = asyncio.run(collect())
    elapsed = time.perf_counter() - started

    completed = [event.tool for event in events if event.kind == "tool" and event.result]
    assert completed == [
        "get_project",
        "create_storyboard",
        "set_proof_shots",
        "generate_images",
        "generate_images",
    ]
    assert events[-1].kind == "done"
    assert elapsed < 1.0

    board = P.load_board(root)
    assert board.total_frames == P.load_project(root).total_frames
    assert P.load_brief(root).creative.proof_shot_ids == ["s001"]
    assert estimates[0]["regenerate"] is False
    assert estimates[1]["regenerate"] is True
    assert authorized == ["quote-1", "quote-2"]
    assert runner.submitted == [("images", slug), ("images", slug)]

    stored = [
        json.loads(line)
        for line in (root / "work" / "chat.jsonl").read_text().splitlines()
        if line.strip()
    ]
    recorded_tools = [
        message.get("name")
        for message in stored
        if message.get("role") == "tool" and message.get("name")
    ]
    assert "generate_images" in recorded_tools
    assert any(
        message.get("role") == "assistant" and message.get("content") == "Probe complete."
        for message in stored
    )
    assert len(llm.prompts) == len(steps) + 1
