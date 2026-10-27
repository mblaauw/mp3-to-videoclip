"""Bounded-concurrency paid generation: one journal writer, no blind retries.

Every client is a controlled fake; no provider is contacted. A gated stub makes
worker overlap deterministic, so bounded concurrency, out-of-order result
association and the stop/drain behaviour are verified exactly rather than by
timing luck.
"""

import sys
import threading
import time
import types

import pytest
from PIL import Image
from test_production import fake_schema

from mp3_to_videoclip import budget
from mp3_to_videoclip import generation as G
from mp3_to_videoclip import production as P
from mp3_to_videoclip.models import Brief, Lyrics, Project, Segment, Shot, Storyboard
from mp3_to_videoclip.providers import ProviderError
from mp3_to_videoclip.storage import file_hash, read_json, write_json


@pytest.fixture
def production(tmp_path):
    root = tmp_path / "production"
    (root / "media").mkdir(parents=True)
    (root / "media/song.mp3").write_bytes(b"mock audio: no upload")
    project = Project(
        slug="test",
        title="Test",
        source_sha256=file_hash(root / "media/song.mp3"),
        duration=1,
        width=192,
        height=108,
    )
    write_json(root / "project.json", project.model_dump())
    write_json(root / "work/music.json", {"duration": 1, "beats": [0, 0.25, 0.5, 0.75]})
    write_json(
        root / "work/lyrics.json",
        Lyrics(
            provider="manual",
            model="test",
            segments=[Segment(start=0, end=1, text="Reviewed example", flags=["unreviewed"])],
        ).model_dump(),
    )
    write_json(
        root / "brief.json",
        Brief(direction="A story", style="Cinematic", treatment="Chosen treatment").model_dump(),
    )
    shots = [
        Shot(
            id=f"s{i + 1:03d}",
            start_frame=i * 6,
            duration_frames=6,
            purpose="Story beat",
            image_prompt=f"A different scene {i}",
        )
        for i in range(4)
    ]
    write_json(
        root / "work/storyboard.json",
        Storyboard(aspect="16:9", fps=24, total_frames=24, shots=shots).model_dump(),
    )
    for name in ["approvals", "assets", "tasks"]:
        write_json(root / f"work/{name}.json", {})
    P.approve(root, "analysis", "test user approved")
    P.approve(root, "lyrics", "test user approved", True)
    P.approve(root, "brief", "test user chose treatment")
    P.approve(root, "storyboard", "test user approved shots")
    return root


class StubClient:
    """Schema/download support shared by every fake image client."""

    def __init__(self, root):
        self.root = root
        self.submissions = []
        self.schema_calls = 0

    def schema(self, _):
        self.schema_calls += 1
        return fake_schema()

    def reference_image(self, _):
        return "data:image/jpeg;base64,ZmFrZQ=="

    def download(self, _, path):
        path.parent.mkdir(parents=True, exist_ok=True)
        Image.new("RGB", (64, 36), (40, 80, 120)).save(path)

    def submit(self, request):
        raise AssertionError("unexpected submit")


class ScriptedStub(StubClient):
    """Per-UUID outcomes: cost, optional delay, pending result or provider error."""

    def __init__(self, root, outcomes):
        super().__init__(root)
        self.outcomes = outcomes
        self.lock = threading.Lock()

    def submit(self, request):
        uuid = request["taskUUID"]
        # The ordering that matters: durable intent exists BEFORE submission.
        assert read_json(self.root / "work/tasks.json")[uuid]["status"] == "submitted"
        with self.lock:
            self.submissions.append(uuid)
        spec = self.outcomes[uuid]
        if spec.get("delay"):
            time.sleep(spec["delay"])
        if spec.get("error"):
            raise ProviderError("network_error")
        if spec.get("pending"):
            return {"taskUUID": uuid}
        return {
            "taskUUID": uuid,
            "imageURL": "https://assets.example/image.jpg",
            "cost": spec["cost"],
        }


class GateStub(StubClient):
    """The first ``limit`` workers block inside submit until the test releases them."""

    def __init__(self, root, *, limit=2):
        super().__init__(root)
        self.limit = limit
        self.lock = threading.Lock()
        self.active = 0
        self.max_active = 0
        self.arrivals = 0
        self.reached_limit = threading.Event()
        self.release = threading.Event()

    def submit(self, request):
        uuid = request["taskUUID"]
        assert read_json(self.root / "work/tasks.json")[uuid]["status"] == "submitted"
        with self.lock:
            self.active += 1
            self.arrivals += 1
            self.max_active = max(self.max_active, self.active)
            self.submissions.append(uuid)
            if self.active >= self.limit:
                self.reached_limit.set()
        if self.arrivals <= self.limit:
            assert self.reached_limit.wait(5)
            assert self.release.wait(5)
        with self.lock:
            self.active -= 1
        return {"taskUUID": uuid, "imageURL": "https://assets.example/image.jpg", "cost": 0.001}


def quote_and_authorize(root, client, **kwargs):
    quote = G.quote_images(root, "proof", "0.01", client=client, **kwargs)
    G.authorize(root, quote["id"], "0.03", "test user authorized exactly this scope")
    return quote


def run_in_thread(result, function):
    try:
        result["value"] = function()
    except BaseException as exc:  # noqa: BLE001 - test harness records any outcome
        result["error"] = exc


def outcome_map(quote, **spec):
    return {task["uuid"]: dict(spec) for task in quote["tasks"]}


# --------------------------------------------------------------------------- #
# bounded overlap and journal-before-charge
# --------------------------------------------------------------------------- #
def test_bounded_overlap_journals_before_charge_and_never_exceeds_concurrency(production):
    client = GateStub(production, limit=2)
    quote = quote_and_authorize(production, client)
    result = {}
    worker = threading.Thread(
        target=run_in_thread,
        args=(result, lambda: G.generate(production, quote["id"], client, concurrency=2)),
    )
    worker.start()
    assert client.reached_limit.wait(5)
    journal = read_json(production / "work/tasks.json")
    assert sum(1 for t in journal.values() if t["status"] == "submitted") == 2
    assert client.max_active == 2  # never all three admitted at once
    client.release.set()
    worker.join(10)
    assert not worker.is_alive() and "error" not in result
    assert len(client.submissions) == 3
    assert client.max_active == 2 and client.active == 0
    journal = read_json(production / "work/tasks.json")
    assert sum(1 for t in journal.values() if t["status"] == "ready") == 3


# --------------------------------------------------------------------------- #
# out-of-order results
# --------------------------------------------------------------------------- #
def test_out_of_order_results_keep_their_own_cost_and_asset(production):
    planner = ScriptedStub(production, {})
    quote = quote_and_authorize(production, planner)
    uuids = [task["uuid"] for task in quote["tasks"]]
    delays = {uuid: 0.15 - index * 0.05 for index, uuid in enumerate(uuids)}
    costs = {uuid: round(0.001 * (index + 1), 6) for index, uuid in enumerate(uuids)}
    client = ScriptedStub(
        production,
        {uuid: {"cost": costs[uuid], "delay": delays[uuid]} for uuid in uuids},
    )
    G.generate(production, quote["id"], client, concurrency=3)
    journal = read_json(production / "work/tasks.json")
    for uuid in uuids:
        assert journal[uuid]["status"] == "ready"
        assert journal[uuid]["cost_usd"] == str(costs[uuid])
    assert G.costs(production)["reported_or_calculated_usd"] == "0.006"
    assets = read_json(production / "work/assets.json")
    for task in quote["tasks"]:
        assert {v["task_id"] for v in assets[task["shot_id"]]["versions"]} == {task["uuid"]}


# --------------------------------------------------------------------------- #
# pending / error / overrun stop admission, drain and persist
# --------------------------------------------------------------------------- #
def test_pending_result_stops_admission_and_stays_recoverable(production):
    planner = ScriptedStub(production, {})
    quote = quote_and_authorize(production, planner)
    client = ScriptedStub(production, outcome_map(quote, pending=True))
    with pytest.raises(ValueError, match="pending"):
        G.generate(production, quote["id"], client, concurrency=2)
    assert len(client.submissions) == 2  # bounded by concurrency, no third admitted
    journal = read_json(production / "work/tasks.json")
    assert [t["status"] for t in journal.values()] == ["submitted", "submitted"]
    with pytest.raises(ValueError, match="recover"):
        G.generate(production, quote["id"], client, concurrency=2)
    assert len(client.submissions) == 2


def test_worker_error_drains_inflight_and_persists_the_known_result(production):
    planner = ScriptedStub(production, {})
    quote = quote_and_authorize(production, planner)
    uuids = [task["uuid"] for task in quote["tasks"]]
    outcomes = {
        uuids[0]: {"cost": 0.001, "delay": 0.05},
        uuids[1]: {"error": True},
    }
    client = ScriptedStub(production, outcomes)
    with pytest.raises(ProviderError):
        G.generate(production, quote["id"], client, concurrency=2)
    assert len(client.submissions) == 2
    journal = read_json(production / "work/tasks.json")
    assert journal[uuids[0]]["status"] == "ready" and journal[uuids[0]]["cost_usd"] == "0.001"
    assert journal[uuids[1]]["status"] == "submitted"  # uncertain, recoverable, never resubmitted
    assert uuids[2] not in journal
    with pytest.raises(ValueError, match="recover"):
        G.generate(production, quote["id"], client, concurrency=2)
    assert len(client.submissions) == 2


def test_overrun_stops_further_admission_but_keeps_inflight_results(production):
    planner = ScriptedStub(production, {})
    quote = quote_and_authorize(production, planner)  # cap 0.03, reserve 0.01 per shot
    client = ScriptedStub(production, outcome_map(quote, cost=0.04))
    with pytest.raises(ValueError, match="exceeded"):
        G.generate(production, quote["id"], client, concurrency=2)
    assert len(client.submissions) == 2  # the third was never admitted
    journal = read_json(production / "work/tasks.json")
    assert sum(1 for t in journal.values() if t["status"] == "ready") == 2
    assert G.costs(production)["reported_or_calculated_usd"] == "0.08"


# --------------------------------------------------------------------------- #
# no spend without authorization/budget, and concurrency validation
# --------------------------------------------------------------------------- #
def test_no_submission_without_authorization(production):
    client = ScriptedStub(production, {})
    quote = G.quote_images(production, "proof", "0.01", client=client)
    with pytest.raises(ValueError, match="authorization"):
        G.generate(production, quote["id"], client, concurrency=2)
    assert client.submissions == [] and read_json(production / "work/tasks.json") == {}


@pytest.mark.parametrize("value", [0, 4, -1, "2", 1.5, True])
def test_concurrency_is_validated_before_any_call(production, value):
    client = ScriptedStub(production, {})
    quote = quote_and_authorize(production, client)
    with pytest.raises(ValueError, match="concurrency"):
        G.generate(production, quote["id"], client, concurrency=value)
    assert client.submissions == []


# --------------------------------------------------------------------------- #
# cumulative production cap across independent quotes and unknown reservations
# --------------------------------------------------------------------------- #
def test_cross_quote_cap_counts_unknown_upload_reservation(production):
    # A ready mediaStorage upload reports no cost, so its reservation stays unknown.
    write_json(
        production / "work/tasks.json",
        {
            "up": {
                "uuid": "up",
                "kind": "audio-upload",
                "status": "ready",
                "quote_id": "q0",
                "reserve_usd": "0.02",
            }
        },
    )
    budget.set_budget(production, "0.03", "user set a production ceiling")
    client = ScriptedStub(production, {})
    full = G.quote_images(production, "proof", "0.01", client=client)
    with pytest.raises(ValueError, match="production budget"):
        G.authorize(production, full["id"], "0.03", "user authorized the full proof")
    single = G.quote_images(
        production, "proof", "0.01", ids=["s001"], regenerate=True, client=client
    )
    G.authorize(production, single["id"], "0.01", "user authorized one remaining shot")
    finish = ScriptedStub(production, {single["tasks"][0]["uuid"]: {"cost": 0.001}})
    G.generate(production, single["id"], finish)
    assert budget.commitment(production) == budget.money("0.021")
    third = G.quote_images(
        production, "proof", "0.01", ids=["s003"], regenerate=True, client=client
    )
    with pytest.raises(ValueError, match="production budget"):
        G.authorize(production, third["id"], "0.01", "user authorized another shot")
    assert len(finish.submissions) == 1


# --------------------------------------------------------------------------- #
# correction-cycle integration
# --------------------------------------------------------------------------- #
def test_correction_cap_blocks_quote_before_any_schema_get_and_restage_recovers(production):
    budget.set_budget(production, "1.00", "user enabled correction limits", 1)
    write_json(
        production / "work/tasks.json",
        {
            "a": {
                "uuid": "a",
                "kind": "images",
                "status": "ready",
                "quote_id": "q",
                "shot_id": "s001",
                "version": 1,
                "reserve_usd": "0.01",
                "cost_usd": "0.001",
            },
            "b": {
                "uuid": "b",
                "kind": "images",
                "status": "ready",
                "quote_id": "q",
                "shot_id": "s001",
                "version": 2,
                "reserve_usd": "0.01",
                "cost_usd": "0.001",
            },
        },
    )
    client = StubClient(production)
    with pytest.raises(ValueError, match="restaging"):
        G.quote_images(production, "proof", "0.01", ids=["s001"], client=client)
    assert client.schema_calls == 0  # refused before the provider schema GET
    budget.authorize_restaging(
        production, ["s001"], "shot rendered malformed anatomy; restage after diagnosis"
    )
    quote = G.quote_images(production, "proof", "0.01", ids=["s001"], client=client)
    assert client.schema_calls == 1
    assert quote["tasks"][0]["retry_cycle"] == budget.correction_cycle(production, "s001")


def test_quote_from_a_superseded_cycle_cannot_bypass_restaging(production):
    budget.set_budget(production, "1.00", "user enabled correction limits", 2)
    client = ScriptedStub(production, {})
    quote = G.quote_images(production, "proof", "0.01", ids=["s001"], client=client)
    assert quote["tasks"][0]["retry_cycle"] == {"baseline": 0, "restage_hash": None}
    G.authorize(production, quote["id"], "0.01", "user authorized this shot")
    budget.authorize_restaging(
        production, ["s001"], "diagnosed a wrong prop and deliberately restaged"
    )
    with pytest.raises(ValueError, match="cycle changed"):
        G.generate(production, quote["id"], client)
    assert client.submissions == []


# --------------------------------------------------------------------------- #
# preflight hook wiring (parent-owned, optional)
# --------------------------------------------------------------------------- #
def install_preflight_hook(monkeypatch, calls, error=None):
    module = types.ModuleType("mp3_to_videoclip.preflight")

    def validate_before_spend(root, ids):
        calls.append(list(ids))
        if error is not None:
            raise error

    module.validate_before_spend = validate_before_spend
    monkeypatch.setitem(sys.modules, "mp3_to_videoclip.preflight", module)


def test_legacy_projects_pass_the_installed_noop_preflight(production):
    planner = ScriptedStub(production, {})
    quote = quote_and_authorize(production, planner)
    client = ScriptedStub(production, outcome_map(quote, cost=0.001))
    G.generate(production, quote["id"], client)
    assert len(client.submissions) == 3


def test_preflight_hook_runs_before_schema_get_and_submission(production, monkeypatch):
    calls = []
    install_preflight_hook(monkeypatch, calls)
    client = ScriptedStub(production, {})
    quote = G.quote_images(production, "proof", "0.01", client=client)
    assert calls == [["s001", "s003", "s004"]]
    assert client.schema_calls == 1
    G.authorize(production, quote["id"], "0.03", "user authorized this scope")
    runner = ScriptedStub(production, outcome_map(quote, cost=0.001))
    G.generate(production, quote["id"], runner)
    assert calls[-1] == ["s001", "s003", "s004"]


def test_preflight_rejection_prevents_schema_get_and_submission(production, monkeypatch):
    calls = []
    install_preflight_hook(monkeypatch, calls, ValueError("preflight rejected this scope"))
    client = ScriptedStub(production, {})
    with pytest.raises(ValueError, match="preflight rejected"):
        G.quote_images(production, "proof", "0.01", client=client)
    assert client.schema_calls == 0
    # A quote made before the hook existed is still blocked at generate time.
    monkeypatch.undo()
    clear = ScriptedStub(production, {})
    quote = quote_and_authorize(production, clear)
    install_preflight_hook(monkeypatch, calls, ValueError("preflight rejected at generate"))
    with pytest.raises(ValueError, match="preflight rejected at generate"):
        G.generate(production, quote["id"], clear)
    assert clear.submissions == [] and read_json(production / "work/tasks.json") == {}


def test_final_allowed_correction_is_idempotent_when_replayed(production):
    budget.set_budget(production, "1", "test authorized cap", max_corrections=0)
    planner = ScriptedStub(production, {})
    quote = G.quote_images(production, "proof", "0.01", ids=["s001"], client=planner)
    G.authorize(production, quote["id"], "0.01", "test approved exact shot")
    runner = ScriptedStub(production, outcome_map(quote, cost=0.001))
    G.generate(production, quote["id"], runner)
    G.generate(production, quote["id"], runner)
    assert len(runner.submissions) == 1


def test_ambiguity_in_another_quote_blocks_new_shot(production):
    budget.set_budget(production, "1", "test authorized cap")
    planner = ScriptedStub(production, {})
    first = G.quote_images(production, "proof", "0.01", ids=["s001"], client=planner)
    second = G.quote_images(production, "proof", "0.01", ids=["s003"], client=planner)
    for quote in (first, second):
        G.authorize(production, quote["id"], "0.01", "test approved exact shot")
    pending = ScriptedStub(production, outcome_map(first, pending=True))
    with pytest.raises(ValueError, match="pending"):
        G.generate(production, first["id"], pending)
    runner = ScriptedStub(production, outcome_map(second, cost=0.001))
    with pytest.raises(ValueError, match="unresolved tasks"):
        G.generate(production, second["id"], runner)
    assert runner.submissions == []


def test_budgeted_concurrency_allows_only_its_own_active_workers(production):
    budget.set_budget(production, "1", "test authorized cap")
    client = ScriptedStub(production, {})
    quote = quote_and_authorize(production, client)
    runner = ScriptedStub(production, outcome_map(quote, cost=0.001))
    G.generate(production, quote["id"], runner, concurrency=3)
    assert len(runner.submissions) == 3


# --------------------------------------------------------------------------- #
# a user stop admits nothing new and keeps every sent task recorded
# --------------------------------------------------------------------------- #
def test_a_stop_before_admission_sends_nothing(production):
    from mp3_to_videoclip import operations

    planner = ScriptedStub(production, {})
    quote = quote_and_authorize(production, planner)
    client = ScriptedStub(production, outcome_map(quote, cost=0.001))
    stop = threading.Event()
    stop.set()
    token = operations.watch_stop(stop)
    try:
        with pytest.raises(ValueError, match="stopped by the user"):
            G.generate(production, quote["id"], client, concurrency=2)
    finally:
        operations.unwatch_stop(token)
    assert client.submissions == []
    assert read_json(production / "work/tasks.json") == {}


def test_a_stop_mid_batch_drains_the_sent_task_and_admits_no_more(production):
    from mp3_to_videoclip import operations

    planner = ScriptedStub(production, {})
    quote = quote_and_authorize(production, planner)
    stop = threading.Event()

    class StopAfterFirst(ScriptedStub):
        def submit(self, request):
            result = super().submit(request)
            stop.set()  # the user presses Cancel while the first still is out
            return result

    client = StopAfterFirst(production, outcome_map(quote, cost=0.001))
    token = operations.watch_stop(stop)
    try:
        with pytest.raises(ValueError, match="stopped by the user; 2 still"):
            G.generate(production, quote["id"], client, concurrency=1)
    finally:
        operations.unwatch_stop(token)
    assert len(client.submissions) == 1
    journal = read_json(production / "work/tasks.json")
    assert [t["status"] for t in journal.values()] == ["ready"]
    assert G.costs(production)["reported_or_calculated_usd"] == "0.001"
