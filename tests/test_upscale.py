"""A sharper still is a journaled version of that still. Every client here is a fake."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from api_support import add_assets, api_client, make_api_project
from test_creative_production import approve_prerequisites, jpeg

from mp3_to_videoclip import budget, edits, upscale
from mp3_to_videoclip import generation as G
from mp3_to_videoclip import production as P
from mp3_to_videoclip.providers import ProviderError
from mp3_to_videoclip.storage import file_hash, read_json, write_json


def schema(status="live", task="upscale"):
    return {
        "info": {"x-status": status, "x-air-id": "runware:504@1", "x-pricing": {"measured": []}},
        "components": {
            "schemas": {
                "RequestBody": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "required": ["taskType", "taskUUID", "model", "inputs"],
                        "additionalProperties": False,
                        "properties": {
                            "taskType": {"const": task},
                            "taskUUID": {"type": "string"},
                            "model": {"const": "runware:504@1"},
                            "upscaleFactor": {"enum": [2, 4]},
                            "outputType": {"enum": ["URL"]},
                            "outputFormat": {"enum": ["JPG"]},
                            "deliveryMethod": {"const": "sync"},
                            "includeCost": {"type": "boolean"},
                            "inputs": {
                                "type": "object",
                                "properties": {"image": {"type": "string"}},
                                "additionalProperties": False,
                            },
                        },
                    },
                }
            }
        },
    }


class FakeClient:
    def __init__(self, *, pending=False, fail=None):
        self.pending = pending
        self.fail = fail
        self.submitted = []
        self.downloads = 0

    def schema(self, slug):
        return schema()

    def reference_image(self, path):
        return "data:image/jpeg;base64,AAAA"

    def submit(self, request):
        if self.fail:
            raise self.fail
        self.submitted.append(request)
        uuid = request["taskUUID"]
        if self.pending:
            return {"taskUUID": uuid}
        return {"taskUUID": uuid, "imageURL": "https://x.test/a.jpg", "cost": 0.0006}

    def recover(self, uuid):
        return {"taskUUID": uuid, "imageURL": "https://x.test/a.jpg", "cost": 0.0006}

    def download(self, url, path):
        self.downloads += 1
        jpeg(Path(path), colour=(200, 10, 10))

    def close(self):
        pass


@pytest.fixture
def film(tmp_path):
    root = make_api_project(tmp_path)
    add_assets(root, versions=1)
    write_json(root / "work/tasks.json", {})
    budget.set_budget(root, "5.00", "test budget")
    approve_prerequisites(root)
    P.approve(root, "storyboard", "test user approved shots")
    return root


def _authorized(root, shot_ids=("s001",)):
    quote = upscale.quote_upscale(root, list(shot_ids), client=FakeClient())
    G.authorize(
        root, quote["id"], quote["reserve_total_usd"], "owner", via="studio", review_confirmed=True
    )
    return quote


def test_a_quote_reserves_a_new_version_of_the_selected_still(film):
    quote = _authorized(film)
    task = quote["tasks"][0]
    still = read_json(film / "work/assets.json")["s001"]["versions"][0]
    assert quote["kind"] == "upscale"
    assert task["version"] == 2
    assert task["input_hash"] == still["input_hash"]
    assert task["derived_from"] == {"version": 1, "sha256": still["sha256"]}
    assert task["derivation"] == {"kind": "upscale", "model": "real-esrgan", "factor": 2}
    assert quote["reserve_total_usd"] == "0.01"
    assert read_json(film / "work/tasks.json") == {}


def test_buying_records_the_reported_cost_and_selects_nothing(film):
    quote = _authorized(film)
    client = FakeClient()
    result = upscale.generate_upscale(film, quote["id"], client=client)
    assert result["done"] == ["s001"]
    assert client.submitted[0]["inputs"]["image"].startswith("data:image/")
    entry = read_json(film / "work/assets.json")["s001"]
    assert entry["selected"] == 1
    derived = entry["versions"][1]
    assert derived["version"] == 2
    assert derived["input_hash"] == entry["versions"][0]["input_hash"]
    assert derived["derivation"]["factor"] == 2
    task = read_json(film / "work/tasks.json")[quote["tasks"][0]["uuid"]]
    assert (task["status"], task["kind"], task["cost_usd"]) == ("ready", "upscale", "0.0006")


def test_the_derived_version_can_be_selected_and_resolves_as_the_same_picture(film):
    quote = _authorized(film)
    upscale.generate_upscale(film, quote["id"], client=FakeClient())
    P.select_asset(film, "s001", 2)
    resolved = P.resolved_assets(film, ["s001"])[0]
    assert "v002-" in resolved.image


def test_a_second_quote_for_the_same_still_is_refused_not_rebilled(film):
    quote = _authorized(film)
    upscale.generate_upscale(film, quote["id"], client=FakeClient())
    with pytest.raises(ValueError, match="already has a sharper version"):
        upscale.quote_upscale(film, ["s001"], client=FakeClient())
    P.select_asset(film, "s001", 2)
    with pytest.raises(ValueError, match="already has a sharper version"):
        upscale.quote_upscale(film, ["s001"], client=FakeClient())


def test_an_unauthorized_quote_spends_nothing(film):
    quote = upscale.quote_upscale(film, ["s001"], client=FakeClient())
    client = FakeClient()
    with pytest.raises(ValueError, match="authorization"):
        upscale.generate_upscale(film, quote["id"], client=client)
    assert client.submitted == []


def test_the_journal_is_written_before_the_request(film):
    quote = _authorized(film)
    seen = []

    class Watching(FakeClient):
        def submit(self, request):
            seen.append(read_json(film / "work/tasks.json")[request["taskUUID"]]["status"])
            return super().submit(request)

    upscale.generate_upscale(film, quote["id"], client=Watching())
    assert seen == ["submitted"]


def test_a_pending_task_is_recovered_never_resubmitted(film):
    quote = _authorized(film)
    client = FakeClient(pending=True)
    assert upscale.generate_upscale(film, quote["id"], client=client)["pending"] == ["s001"]
    with pytest.raises(ValueError, match="need recovery"):
        upscale.generate_upscale(film, quote["id"], client=client)
    assert len(client.submitted) == 1
    assert G.recover(film, quote["tasks"][0]["uuid"], client=FakeClient()) is True
    versions = read_json(film / "work/assets.json")["s001"]["versions"]
    assert versions[1]["derived_from"]["version"] == 1


def test_a_provider_failure_leaves_a_journal_entry_to_reconcile(film):
    quote = _authorized(film)
    with pytest.raises(ProviderError):
        upscale.generate_upscale(film, quote["id"], client=FakeClient(fail=ProviderError("boom")))
    assert read_json(film / "work/tasks.json")[quote["tasks"][0]["uuid"]]["status"] == "submitted"


def test_lost_bytes_are_quarantined_and_restored_not_rebilled(film):
    quote = _authorized(film)
    upscale.generate_upscale(film, quote["id"], client=FakeClient())
    uuid = quote["tasks"][0]["uuid"]
    task = read_json(film / "work/tasks.json")[uuid]
    path = film / task["path"]
    original = file_hash(path)
    path.unlink()
    assert G.asset_intact(film, task) is False
    client = FakeClient()
    journal = read_json(film / "work/tasks.json")
    journal[uuid]["status"] = "result"
    write_json(film / "work/tasks.json", journal)
    G.recover(film, uuid, client=client)
    assert client.submitted == [] and client.downloads == 1
    assert file_hash(path) == original


def test_a_still_chosen_after_the_quote_stops_the_spend(film):
    add_assets(film, versions=2)
    assets = read_json(film / "work/assets.json")
    other = assets["s001"]["versions"][1]
    jpeg(film / other["path"], colour=(1, 200, 1))
    other["sha256"] = file_hash(film / other["path"])
    write_json(film / "work/assets.json", assets)
    quote = _authorized(film)
    P.select_asset(film, "s001", 2)
    client = FakeClient()
    with pytest.raises(ValueError, match="changed since the quote"):
        upscale.generate_upscale(film, quote["id"], client=client)
    assert client.submitted == []


def test_a_model_that_is_not_live_or_not_an_upscaler_is_refused(film):
    class Offline(FakeClient):
        def schema(self, slug):
            return schema(status="retired")

    class Other(FakeClient):
        def schema(self, slug):
            return schema(task="imageInference")

    with pytest.raises(ValueError, match="not confirmed live"):
        upscale.quote_upscale(film, ["s001"], client=Offline())
    with pytest.raises(ValueError, match="not an upscale model"):
        upscale.quote_upscale(film, ["s001"], client=Other())


def test_an_index_without_derived_versions_keeps_its_bytes(film):
    before = (film / "work/assets.json").read_bytes()
    entry = read_json(film / "work/assets.json")["s001"]["versions"][0]
    P.record_asset(film, "s001", 1, film / entry["path"], entry["input_hash"], entry["task_id"])
    assert json.loads((film / "work/assets.json").read_bytes()) == json.loads(before)


def test_a_reprise_names_its_owner_once(film):
    quote = upscale.quote_upscale(film, ["s001", "s001"], client=FakeClient())
    assert [task["shot_id"] for task in quote["tasks"]] == ["s001"]
    with pytest.raises(ValueError):
        upscale.quote_upscale(film, ["nope"], client=FakeClient())


def test_the_routes_never_buy_without_the_second_click(film, tmp_path, monkeypatch):
    monkeypatch.setenv("PROJECT_VEIL_RUNWARE_API", "fake-key")
    monkeypatch.setattr("mp3_to_videoclip.upscale.RunwareClient", lambda *a, **k: FakeClient())
    with api_client(tmp_path) as client:
        base = f"/api/projects/{film.name}/images/upscale"
        shown = client.post(f"{base}/estimate", json={"shot_ids": ["s001"]}).json()
        assert shown["estimate"]["reserve_usd"] == "0.01"
        assert shown["decision"]["ok"] is True
        assert read_json(film / "work/tasks.json") == {}
        assert client.post(base, json={}).status_code == 400


def test_no_key_shows_no_price(film, tmp_path, monkeypatch):
    monkeypatch.setattr("mp3_to_videoclip.upscale.RunwareClient", lambda *a, **k: FakeClient())
    with api_client(tmp_path) as client:
        refused = client.post(
            f"/api/projects/{film.name}/images/upscale/estimate", json={"shot_ids": ["s001"]}
        )
    assert refused.status_code == 409
    assert refused.json()["code"] == "no_runware_key"


def test_the_report_says_where_a_sharper_still_would_pay(film):
    edit = edits.seed_edit(film)
    from mp3_to_videoclip.models import EditMotion

    shot = edit.shots[0]
    shot.motion = EditMotion(type="push_in", **{"from": 1.0, "to": 1.25}, anchor=[0.5, 0.5])
    edits.save_edit(film, edit)
    wide = P.load_project(film).model_copy(update={"width": 1920, "height": 1080})

    def soft():
        return [
            w for w in edits.report(film, project=wide)["warnings"] if w["code"] == "soft_push_in"
        ]

    found = soft()
    assert [w["shot_id"] for w in found] == [shot.shot_id]
    quote = _authorized(film, [shot.shot_id])
    upscale.generate_upscale(film, quote["id"], client=FakeClient())
    P.select_asset(film, shot.shot_id, 2)
    assert soft() == []
