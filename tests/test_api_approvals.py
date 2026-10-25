"""Approval state and typed approvals through the Studio API.

Uses a real guided project fixture; no provider call is made. The point is that
an approval binds its exact content and that a later edit turns it stale.
"""

from __future__ import annotations

from api_support import api_client, make_api_project

from mp3_to_videoclip.storage import read_json, write_json


def _client(tmp_path):
    return make_api_project(tmp_path), api_client(tmp_path)


def _stage(payload, name):
    return next(item for item in payload["stages"] if item["stage"] == name)


def test_missing_and_approved_and_stale_states(tmp_path):
    root, client = _client(tmp_path)
    with client:
        first = client.get("/api/projects/production/approvals")
        assert first.status_code == 200
        brief = _stage(first.json(), "brief")
        assert brief["state"] == "missing"
        assert len(brief["expected_hash"]) == 64

        approved = client.post(
            "/api/projects/production/approvals/brief",
            json={
                "expected_hash": brief["expected_hash"],
                "note": "read the treatment",
                "confirmed": True,
            },
        )
        assert approved.status_code == 200, approved.text
        assert approved.json()["approved"] == "brief"
        assert (
            _stage(client.get("/api/projects/production/approvals").json(), "brief")["state"]
            == "approved"
        )

        brief_data = read_json(root / "brief.json")
        brief_data["treatment"] += " One more beat."
        write_json(root / "brief.json", brief_data)
        assert (
            _stage(client.get("/api/projects/production/approvals").json(), "brief")["state"]
            == "stale"
        )


def test_wrong_hash_is_rejected_and_nothing_is_saved(tmp_path):
    root, client = _client(tmp_path)
    with client:
        _stage(client.get("/api/projects/production/approvals").json(), "brief")
        response = client.post(
            "/api/projects/production/approvals/brief",
            json={"expected_hash": "0" * 64, "note": "looks fine", "confirmed": True},
        )
        assert response.status_code == 409
        assert "changed" in response.text.lower() or "inspect" in response.text.lower()
        assert "brief" not in read_json(root / "work/approvals.json")


def test_approval_needs_a_note_and_confirmation(tmp_path):
    _, client = _client(tmp_path)
    with client:
        brief = _stage(client.get("/api/projects/production/approvals").json(), "brief")
        base = {"expected_hash": brief["expected_hash"], "note": "ok", "confirmed": True}
        assert (
            client.post(
                "/api/projects/production/approvals/brief",
                json={**base, "confirmed": False},
            ).status_code
            == 400
        )
        assert (
            client.post(
                "/api/projects/production/approvals/brief",
                json={**base, "note": "  "},
            ).status_code
            == 400
        )


def test_a_budget_topup_does_not_invalidate_a_creative_approval(tmp_path):
    from mp3_to_videoclip.domain import budget

    root, client = _client(tmp_path)
    with client:
        brief = _stage(client.get("/api/projects/production/approvals").json(), "brief")
        client.post(
            "/api/projects/production/approvals/brief",
            json={
                "expected_hash": brief["expected_hash"],
                "note": "read the treatment",
                "confirmed": True,
            },
        )
        budget.add_budget(root, "5.00", "test top-up")
        assert (
            _stage(client.get("/api/projects/production/approvals").json(), "brief")["state"]
            == "approved"
        )


def test_approvals_can_be_scoped_to_the_stages_on_screen(tmp_path):
    _, client = _client(tmp_path)
    with client:
        payload = client.get("/api/projects/production/approvals?stages=brief,proof").json()
        assert [item["stage"] for item in payload["stages"]] == ["brief", "proof"]
