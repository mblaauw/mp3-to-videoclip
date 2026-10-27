"""State transactions, optimistic edits and crash recovery; no live providers."""

import errno
import os
import stat
import subprocess
import sys
import threading
from decimal import Decimal

import pytest
from api_support import add_assets, api_client, make_api_project
from test_creative_production import (
    approve_prerequisites,
    jpeg,
    record_stills,
    write_preview_report,
)
from test_edits import _energetic_edit, _energetic_root
from test_production import FakeRunware
from test_workflow_v2 import accept, strict_root

from mp3_to_videoclip import budget, edits, reviews, storage
from mp3_to_videoclip import generation as G
from mp3_to_videoclip import production as P
from mp3_to_videoclip.domain import budget as domain_budget
from mp3_to_videoclip.storage import digest, file_hash, read_json, write_json


def _worker(function, *, name):
    errors = []

    def run():
        try:
            function()
        except BaseException as exc:
            errors.append(exc)

    thread = threading.Thread(target=run, name=name, daemon=True)
    thread.start()
    return thread, errors


def _join(worker):
    thread, errors = worker
    thread.join(timeout=3)
    assert not thread.is_alive(), f"{thread.name} deadlocked"
    assert not errors, errors


def _serialized_pair(monkeypatch, module, path, first, second):
    """Pause after the first snapshot; the second writer must not read it yet."""
    original = module.read_json
    snapshot = threading.Event()
    release = threading.Event()
    second_started = threading.Event()
    second_read = threading.Event()

    def gated_read(candidate, *args, **kwargs):
        value = original(candidate, *args, **kwargs)
        if candidate == path:
            if threading.current_thread().name == "first-writer":
                snapshot.set()
                assert release.wait(2), "test failed to release first snapshot"
            elif threading.current_thread().name == "second-writer":
                second_read.set()
        return value

    def run_second():
        second_started.set()
        second()

    monkeypatch.setattr(module, "read_json", gated_read)
    a = _worker(first, name="first-writer")
    b = None
    try:
        assert snapshot.wait(2)
        b = _worker(run_second, name="second-writer")
        assert second_started.wait(2)
        assert not second_read.wait(0.1), "second writer read an uncommitted snapshot"
    finally:
        release.set()
        _join(a)
        if b is not None:
            _join(b)
    assert second_read.is_set()


def test_state_lock_is_reentrant_and_enforces_operation_first(tmp_path):
    with storage.project_lock(tmp_path):
        with storage.state_lock(tmp_path):
            with storage.state_lock(tmp_path):
                pass
    with storage.state_lock(tmp_path):
        with pytest.raises(RuntimeError, match="before state locks"):
            with storage.project_lock(tmp_path):
                pytest.fail("reverse lock order was accepted")
    assert (tmp_path / ".state.lock").is_file()
    assert (tmp_path / ".lock").is_file()


def test_operation_lock_does_not_block_a_state_only_editor(tmp_path):
    with storage.project_lock(tmp_path):
        worker = _worker(lambda: _state_editor(tmp_path), name="editor")
        _join(worker)
    assert read_json(tmp_path / "editor.json") == {"saved": True}


@storage.state_mutation
def _state_editor(root):
    with storage.state_lock(root):
        write_json(root / "editor.json", {"saved": True})


def test_state_lock_coordinates_a_fresh_process(tmp_path):
    script = """
import sys
from pathlib import Path
from mp3_to_videoclip.storage import ProjectBusy, state_lock
try:
    with state_lock(Path(sys.argv[1]), timeout=0.05):
        print('acquired')
except ProjectBusy:
    print('busy')
"""
    with storage.state_lock(tmp_path):
        blocked = subprocess.run(
            [sys.executable, "-c", script, str(tmp_path)],
            capture_output=True,
            text=True,
            timeout=5,
            check=True,
        )
    assert blocked.stdout.strip() == "busy"
    acquired = subprocess.run(
        [sys.executable, "-c", script, str(tmp_path)],
        capture_output=True,
        text=True,
        timeout=5,
        check=True,
    )
    assert acquired.stdout.strip() == "acquired"


def test_selection_and_new_generation_index_both_survive(tmp_path, monkeypatch):
    root = make_api_project(tmp_path)
    add_assets(root)
    path = jpeg(root / "assets/s002/v003-new.jpg")
    input_hash = digest(P.image_spec(root, P.load_board(root).shots[1]))
    _serialized_pair(
        monkeypatch,
        P,
        root / "work/assets.json",
        lambda: P.select_asset(root, "s001", 2),
        lambda: P.record_asset(root, "s002", 3, path, input_hash, "new-task"),
    )
    assets = read_json(root / "work/assets.json")
    assert assets["s001"]["selected"] == 2
    assert [v["version"] for v in assets["s002"]["versions"]] == [1, 2, 3]
    assert assets["s002"]["selected"] == 1


def test_concurrent_reviews_append_without_lost_history(tmp_path, monkeypatch):
    root = make_api_project(tmp_path)
    add_assets(root)
    path = root / "work/reviews.json"
    write_json(path, [])
    _serialized_pair(
        monkeypatch,
        reviews,
        path,
        lambda: reviews.record_review(
            root,
            "s001",
            1,
            "accept",
            reviewer="first",
            inspected=True,
        ),
        lambda: reviews.record_review(
            root,
            "s002",
            1,
            "reject",
            reviewer="second",
            inspected=True,
        ),
    )
    assert [(r["reviewer"], r["verdict"]) for r in read_json(path)] == [
        ("first", "accept"),
        ("second", "reject"),
    ]


def test_concurrent_cap_admission_reserves_only_one_task(tmp_path, monkeypatch):
    root = strict_root(tmp_path)
    (root / "work/lyrics.json").unlink()
    budget.set_budget(root, "0.01", "test-owned hard ceiling")
    quote = {"id": "concurrent", "kind": "transcription", "reserve_total_usd": "0.01"}
    write_json(
        root / "work/authorizations.json",
        {
            quote["id"]: {"quote_hash": digest(quote), "cap_usd": "1"},
        },
    )
    entered = threading.Event()
    release = threading.Event()
    original = budget.check_capacity
    outcomes = []

    def check(*args, **kwargs):
        value = original(*args, **kwargs)
        if threading.current_thread().name == "admission-first":
            entered.set()
            assert release.wait(2)
        return value

    monkeypatch.setattr(budget, "check_capacity", check)

    def admit(uuid):
        try:
            G.begin_task(root, quote, {"uuid": uuid, "reserve_usd": "0.01"})
            outcomes.append((uuid, "admitted"))
        except ValueError as exc:
            outcomes.append((uuid, str(exc)))

    first = _worker(lambda: admit("first"), name="admission-first")
    second = None
    try:
        assert entered.wait(2)
        second = _worker(lambda: admit("second"), name="admission-second")
    finally:
        release.set()
        _join(first)
        if second is not None:
            _join(second)
    assert ("first", "admitted") in outcomes
    assert any(uuid == "second" and "exhausted" in result for uuid, result in outcomes)
    assert list(read_json(root / "work/tasks.json")) == ["first"]


def test_finish_download_releases_lock_and_merges_latest_journal(tmp_path):
    root = make_api_project(tmp_path)
    add_assets(root)
    task = {
        "uuid": "download",
        "kind": "images",
        "status": "submitted",
        "quote_id": "q",
        "shot_id": "s001",
        "version": 3,
        "reserve_usd": "0.01",
        "input_hash": "test-input",
        "cost_usd": None,
    }
    write_json(root / "work/tasks.json", {"download": task})
    downloading = threading.Event()
    release = threading.Event()

    class GatedDownload(FakeRunware):
        def download(self, url, path):
            downloading.set()
            assert release.wait(2)
            super().download(url, path)

    client = GatedDownload(root)
    worker = _worker(
        lambda: G.finish_image(root, "download", client.result("download"), client),
        name="download",
    )
    try:
        assert downloading.wait(2)
        with storage.state_lock(root, timeout=0.2):
            journal = read_json(root / "work/tasks.json")
            assert journal["download"]["status"] == "result"
            assert journal["download"]["cost_usd"] == "0.001"
            journal["independent"] = {"status": "ready", "cost_usd": "0.002"}
            journal["download"]["operator_note"] = "preserve during download"
            write_json(root / "work/tasks.json", journal)
            P.select_asset(root, "s002", 2)
    finally:
        release.set()
        _join(worker)
    journal = read_json(root / "work/tasks.json")
    assert journal["independent"]["cost_usd"] == "0.002"
    assert journal["download"]["status"] == "ready"
    assert journal["download"]["operator_note"] == "preserve during download"
    assert read_json(root / "work/assets.json")["s002"]["selected"] == 2


def test_schema_three_budget_is_canonical_and_appends_history(tmp_path):
    root = make_api_project(tmp_path)
    first = budget.set_budget(root, "1.00", "first explicit cap", 2)
    before = read_json(root / "project.json")
    second = budget.set_budget(root, "2.00", "explicit top up", 3)
    after = read_json(root / "project.json")
    assert after["budget"][:-1] == before["budget"]
    assert after["budget"][-1] == {
        "at": second["at"],
        "cap_usd": "2.00",
        "reason": "explicit top up",
        "max_corrections": 3,
    }
    assert before["budget"][-1]["at"] == first["at"]
    assert budget.read_budget(root)["cap_usd"] == "2.00"
    assert not (root / budget.BUDGET_PATH).exists()


@pytest.mark.parametrize("legacy_cap,conflict", [("1.00", False), ("0.50", True)])
def test_schema_three_refuses_conflicting_legacy_budget(tmp_path, legacy_cap, conflict):
    root = make_api_project(tmp_path)
    record = budget.set_budget(root, "1.00", "canonical project cap", 2)
    write_json(root / budget.BUDGET_PATH, {**record, "cap_usd": legacy_cap})
    if conflict:
        with pytest.raises(ValueError, match="conflict"):
            budget.read_budget(root)
        with pytest.raises(ValueError, match="conflict"):
            budget.check_capacity(root, "0.001")
    else:
        assert budget.read_budget(root) == record


@pytest.mark.parametrize("index_exists", [True, False])
def test_ready_recovery_rebuilds_missing_index_offline(tmp_path, monkeypatch, index_exists):
    root = make_api_project(tmp_path)
    path = jpeg(root / "assets/s001/v001-paid.jpg")
    task = {
        "uuid": "paid",
        "kind": "images",
        "status": "ready",
        "shot_id": "s001",
        "version": 1,
        "path": path.relative_to(root).as_posix(),
        "sha256": file_hash(path),
        "input_hash": digest(P.image_spec(root, P.load_board(root).shots[0])),
        "cost_usd": "0.001",
        "quote_id": "q",
    }
    write_json(root / "work/tasks.json", {"paid": task})
    write_json(root / "work/assets.json", {})
    if not index_exists:
        (root / "work/assets.json").unlink()

    def no_network(*args, **kwargs):
        pytest.fail("intact ready recovery must not create a provider or obtain credentials")

    monkeypatch.setattr(G, "RunwareClient", no_network)
    monkeypatch.setattr(G, "runware_api_key", no_network)
    assert G.recover(root, "paid") is True
    first = read_json(root / "work/assets.json")
    assert first["s001"]["selected"] == 1
    assert first["s001"]["versions"][0]["task_id"] == "paid"
    assert G.recover(root, "paid") is True
    assert read_json(root / "work/assets.json") == first
    assert read_json(root / "work/tasks.json") == {"paid": task}
    assert not (root / "work/reviews.json").exists()


@pytest.mark.parametrize("document", ["brief", "storyboard"])
def test_stale_if_match_is_409_without_overwrite(tmp_path, document):
    root = make_api_project(tmp_path)
    get_path = f"/api/projects/production/{document}"
    patch_path = get_path if document == "brief" else get_path + "/shots"
    payload = (
        {"direction": "first accepted edit"}
        if document == "brief"
        else {
            "changes": [{"id": "s001", "purpose": "first accepted edit"}],
        }
    )
    artifact = root / ("brief.json" if document == "brief" else "work/storyboard.json")
    with api_client(tmp_path) as client:
        response = client.get(get_path)
        assert response.status_code == 200
        etag = response.headers["etag"]
        assert etag == f'"{digest(response.json())}"'
        saved = client.patch(patch_path, json=payload, headers={"If-Match": etag})
        assert saved.status_code == 200, saved.text
        assert saved.headers["etag"] != etag
        before = artifact.read_bytes()
        stale = client.patch(patch_path, json=payload, headers={"If-Match": etag})
        assert stale.status_code == 409, stale.text
        assert artifact.read_bytes() == before


def test_edit_expected_hash_rejects_stale_cut_without_overwrite(tmp_path):
    root = _energetic_root(tmp_path)
    edit = _energetic_edit()
    edits.save_edit(root, edit, record=False)
    expected = digest(read_json(root / "work/edit.json"))
    updated = edit.model_dump(by_alias=True)
    updated["shots"][0]["motion"]["reason"] = "new editorial reason"
    edits.save_edit(root, updated, expected_hash=expected, record=False)
    before = (root / "work/edit.json").read_bytes()
    with pytest.raises(storage.RevisionConflict):
        edits.save_edit(root, edit, expected_hash=expected, record=False)
    assert (root / "work/edit.json").read_bytes() == before


def test_atomic_write_syncs_file_before_replace_and_directory_after(tmp_path, monkeypatch):
    events = []
    fsync = os.fsync
    replace = os.replace

    def sync(fd):
        events.append("directory" if stat.S_ISDIR(os.fstat(fd).st_mode) else "file")
        fsync(fd)

    def publish(*args):
        events.append("replace")
        replace(*args)

    monkeypatch.setattr(os, "fsync", sync)
    monkeypatch.setattr(os, "replace", publish)
    write_json(tmp_path / "journal.json", {"reserved": True})
    assert events == ["file", "replace", "directory"]


def test_directory_fsync_io_failure_is_not_silently_accepted(tmp_path, monkeypatch):
    fsync = os.fsync

    def fail_directory(fd):
        if stat.S_ISDIR(os.fstat(fd).st_mode):
            raise OSError(errno.EIO, "durability failure")
        fsync(fd)

    monkeypatch.setattr(os, "fsync", fail_directory)
    with pytest.raises(OSError, match="durability failure"):
        write_json(tmp_path / "journal.json", {"reserved": True})


@pytest.mark.parametrize("gate", ["proof", "preview"])
def test_fullset_admission_rechecks_gate_during_earlier_download(tmp_path, monkeypatch, gate):
    root = make_api_project(tmp_path) if gate == "proof" else strict_root(tmp_path)
    budget.set_budget(root, "1", "test-owned generation cap")
    approve_prerequisites(root)
    P.approve(root, "storyboard", "test-owned storyboard")
    ids = P.proof_ids(P.load_board(root), P.load_brief(root))
    record_stills(root, ids)
    accept(root, ids)
    P.approve(root, "proof", "inspected test proof")
    if gate == "preview":
        write_preview_report(root)
        P.approve(root, "preview", "watched test preview")
    downloading = threading.Event()
    release = threading.Event()
    invalidated = threading.Event()

    class GatedDownload(FakeRunware):
        def download(self, url, path):
            downloading.set()
            assert release.wait(2)
            super().download(url, path)

    client = GatedDownload(root)
    quote = G.quote_images(
        root,
        "stills",
        "0.01",
        ids=["s001", "s002"],
        regenerate=True,
        client=client,
    )
    assert len(quote["tasks"]) == 2
    G.authorize(root, quote["id"], "0.02", "test-owned exact fullset scope")
    first, second = quote["tasks"]
    original = G.require_approval
    checked_after_invalidation = []

    def require(current_root, stage, *args, **kwargs):
        if stage == gate and invalidated.is_set():
            checked_after_invalidation.append(stage)
            raise ValueError(f"{gate} approval invalidated during download")
        return original(current_root, stage, *args, **kwargs)

    monkeypatch.setattr(G, "require_approval", require)
    G.begin_task(root, quote, first)
    result = client.submit(first["request"])
    worker = _worker(
        lambda: G.finish_image(root, first["uuid"], result, client),
        name="gate-download",
    )
    try:
        assert downloading.wait(2)
        with storage.state_lock(root):
            invalidated.set()
        before = (root / "work/tasks.json").read_bytes()
        with pytest.raises(ValueError, match=f"{gate} approval invalidated"):
            G.begin_task(root, quote, second, admitted=(first["uuid"],))
        assert checked_after_invalidation == [gate]
        assert (root / "work/tasks.json").read_bytes() == before
        assert second["uuid"] not in read_json(root / "work/tasks.json")
        assert [request["taskUUID"] for request in client.submissions] == [first["uuid"]]
    finally:
        release.set()
        _join(worker)


@pytest.mark.parametrize(
    "outcome,duration", [("conflict", 1.25), ("invalid", 1.25), ("ready", None)]
)
def test_openai_finalizer_keeps_billed_evidence_before_validation(
    tmp_path,
    monkeypatch,
    outcome,
    duration,
):
    root = make_api_project(tmp_path)
    lyrics_path = root / "work/lyrics.json"
    imported_bytes = lyrics_path.read_bytes()
    lyrics_path.unlink()
    project = P.load_project(root)
    quote = {"uuid": "openai-paid", "id": "q", "kind": "transcription"}
    write_json(
        root / "work/tasks.json",
        {
            quote["uuid"]: {
                "uuid": quote["uuid"],
                "kind": "transcription",
                "status": "submitted",
                "quote_id": quote["id"],
                "reserve_usd": "0.01",
                "cost_usd": None,
            },
        },
    )
    raw = {
        "language": "dutch",
        "segments": [{"start": 0, "end": -1 if outcome == "invalid" else 1, "text": "Paid draft"}],
        "words": [],
    }
    if duration is not None:
        raw["duration"] = duration
    expected_cost = (
        Decimal(str(duration if duration is not None else project.duration)) * G.WHISPER_RATE
    )
    original = G._openai_lyrics
    validated = []

    def validate(value):
        assert read_json(root / "work/transcription-raw.json") == raw
        journal = read_json(root / "work/tasks.json")[quote["uuid"]]
        assert journal["status"] == "result"
        assert Decimal(journal["cost_usd"]) == expected_cost
        assert journal["cost_basis"] == "duration-rate estimate, not provider invoice"
        validated.append(True)
        return original(value)

    monkeypatch.setattr(G, "_openai_lyrics", validate)
    started = threading.Event()

    def finalize():
        started.set()
        if outcome == "ready":
            G.finish_openai_transcript(root, quote, project, raw)
        else:
            message = (
                "existing lyrics preserved"
                if outcome == "conflict"
                else "raw evidence and cost retained"
            )
            with pytest.raises(ValueError, match=message):
                G.finish_openai_transcript(root, quote, project, raw)

    with storage.state_lock(root):
        worker = _worker(finalize, name="transcript-finalizer")
        assert started.wait(2)
        if outcome == "conflict":
            # Import wins while the finalizer waits for the state transaction.
            lyrics_path.write_bytes(imported_bytes)
    _join(worker)
    assert validated == [True]
    journal = read_json(root / "work/tasks.json")[quote["uuid"]]
    assert journal["status"] == outcome
    assert Decimal(journal["cost_usd"]) == expected_cost
    assert read_json(root / "work/transcription-raw.json") == raw
    assert budget.commitment(root) == expected_cost
    if outcome == "conflict":
        assert journal["validation_error"] == "lyrics_conflict_preserved"
        assert lyrics_path.read_bytes() == imported_bytes
    elif outcome == "invalid":
        assert journal["validation_error"] == "invalid_transcript"
        assert not lyrics_path.exists()
    else:
        assert read_json(lyrics_path)["segments"][0]["text"] == "Paid draft"


def test_matching_dual_budgets_refuse_domain_topup_without_mutating_project(tmp_path):
    root = make_api_project(tmp_path)
    record = budget.set_budget(root, "1.00", "canonical test cap", 2)
    write_json(root / budget.BUDGET_PATH, record)
    assert budget.read_budget(root) == record
    before_project = (root / "project.json").read_bytes()
    before_legacy = (root / budget.BUDGET_PATH).read_bytes()
    with pytest.raises(ValueError, match="reconcile the legacy budget"):
        domain_budget.add_budget(root, "2.00", "must not create conflicting authorities")
    assert (root / "project.json").read_bytes() == before_project
    assert (root / budget.BUDGET_PATH).read_bytes() == before_legacy
    assert budget.read_budget(root) == record
