"""Human action contract on temporary productions, without any provider calls."""

import json
import socket
import sys
import urllib.error
import urllib.request

import pytest
from test_creative_production import make_root

from mp3_to_videoclip import budget, cli, serve
from mp3_to_videoclip import generation as G
from mp3_to_videoclip import human_actions as H
from mp3_to_videoclip import production as P
from mp3_to_videoclip.storage import digest, read_json, write_json


@pytest.fixture
def action_server(tmp_path):
    projects = tmp_path / "projects"
    projects.mkdir()
    root = make_root(projects)
    budget.set_budget(root, "1.00", "test authority")
    server, url, thread = serve.start_in_thread(projects, tmp_path / "db.sqlite3", token="read")
    server.action_token = "human"
    base = url.split("?")[0]
    yield root, server, base
    server.shutdown()
    server.server_close()
    thread.join(timeout=2)


def request(base, path, body=None, *, headers=None, method=None):
    defaults = {
        "X-Studio-Token": "read",
        "X-Studio-Action": "human",
        "Origin": base.rstrip("/"),
        "Content-Type": "application/json",
    }
    defaults.update(headers or {})
    req = urllib.request.Request(
        base + path,
        data=json.dumps(body).encode() if body is not None else None,
        headers=defaults,
        method=method,
    )
    try:
        response = urllib.request.urlopen(req, timeout=5)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        return response.status, json.loads(response.read())


def approval_body(root, **changes):
    return {
        "expected_hash": P.stage_hash(root, "analysis"),
        "note": "Reviewed the actual evidence",
        "confirmed": True,
        **changes,
    }


def quote(root, **changes):
    return G.save_quote(
        root,
        {
            "kind": "images",
            "model": "test-model",
            "scope": "proof",
            "reserve_total_usd": "0.10",
            "tasks": [
                {
                    "shot_id": "s001",
                    "version": 1,
                    "references": [],
                    "input_hash": "a" * 64,
                    "reserve_usd": "0.10",
                    "request": {
                        "positivePrompt": "Test only",
                        "width": 192,
                        "height": 108,
                        "seed": 4,
                        "settings": {"quality": "test"},
                        "apiKey": "NEVER_RETURN",
                    },
                }
            ],
            **changes,
        },
    )


def test_stage_success_and_provenance(action_server):
    root, _server, base = action_server
    status, review = request(base, "api/project/production/approval/analysis")
    assert status == 200 and review["expected_hash"] == P.stage_hash(root, "analysis")
    status, result = request(base, "api/project/production/approve/analysis", approval_body(root))
    assert status == 200 and result["generated"] is False
    record = read_json(root / "work/approvals.json")["analysis"]
    assert record["via"] == "studio"
    assert record["hash"] == review["expected_hash"]


def test_stale_approval_is_conflict_without_write(action_server):
    root, _server, base = action_server
    body = approval_body(root)
    original = (root / "work/approvals.json").read_bytes()
    write_json(root / "work/music.json", {"duration": 2, "beats": [0.1]})
    status, _ = request(base, "api/project/production/approve/analysis", body)
    assert status == 409
    assert (root / "work/approvals.json").read_bytes() == original


@pytest.mark.parametrize(
    "headers,status",
    [
        ({"X-Studio-Action": ""}, 401),
        ({"X-Studio-Action": "wrong"}, 401),
        ({"Origin": ""}, 403),
        ({"Origin": "https://other.invalid"}, 403),
        ({"Content-Type": "text/plain"}, 415),
        ({"Host": "rebind.invalid"}, 400),
    ],
)
def test_action_transport_guards(action_server, headers, status):
    root, _server, base = action_server
    before = (root / "work/approvals.json").read_bytes()
    assert (
        request(
            base, "api/project/production/approve/analysis", approval_body(root), headers=headers
        )[0]
        == status
    )
    assert (root / "work/approvals.json").read_bytes() == before


@pytest.mark.parametrize(
    "changes",
    [
        {"confirmed": False},
        {"note": " "},
        {"expected_hash": "bad"},
        {"inspected": True},
        {"acknowledge_uncertain": True},
        {"preview_watched": True},
        {"arbitrary": "field"},
    ],
)
def test_invalid_stage_confirmation_never_writes(action_server, changes):
    root, _server, base = action_server
    before = (root / "work/approvals.json").read_bytes()
    assert (
        request(base, "api/project/production/approve/analysis", approval_body(root, **changes))[0]
        == 400
    )
    assert (root / "work/approvals.json").read_bytes() == before


def test_read_only_session_cannot_decide(action_server):
    root, server, base = action_server
    server.action_token = None
    assert request(base, "api/project/production/approve/analysis", approval_body(root))[0] == 401
    assert request(base, "api/session")[1]["actions_enabled"] is False


def test_quote_authorization_exact_cap_idempotency_and_no_provider(action_server, monkeypatch):
    root, _server, base = action_server

    def forbidden(*args, **kwargs):
        raise AssertionError("provider must never be called")

    monkeypatch.setattr(G, "RunwareClient", forbidden)
    q = quote(root)
    status, review = request(base, f"api/project/production/quote/{q['id']}")
    assert status == 200
    assert "NEVER_RETURN" not in json.dumps(review)
    assert review["tasks"][0]["settings"]["settings"] == {"quality": "test"}
    body = {
        "expected_quote_hash": review["expected_quote_hash"],
        "note": "Explicit bounded authority",
        "confirmed": True,
    }
    status, result = request(base, f"api/project/production/authorize/{q['id']}", body)
    assert status == 200 and result["record"]["cap_usd"] == "0.10"
    assert result["record"]["via"] == "studio" and result["generated"] is False
    before = (root / "work/authorizations.json").read_bytes()
    status, again = request(base, f"api/project/production/authorize/{q['id']}", body)
    assert status == 200 and again["already_authorized"] is True
    assert (root / "work/authorizations.json").read_bytes() == before
    assert read_json(root / "work/tasks.json") == {}


def test_quote_stale_upload_and_cap_guards(action_server):
    root, _server, base = action_server
    q = quote(root, kind="transcription", tasks=[], source_hash="b" * 64)
    body = {"expected_quote_hash": digest(q), "note": "Reviewed", "confirmed": True}
    path = f"api/project/production/authorize/{q['id']}"
    assert request(base, path, body)[0] == 400  # Upload permission is separate.
    assert request(base, path, {**body, "confirm_uploads": True, "cap": "10.00"})[0] == 400
    q["reserve_total_usd"] = "0.20"
    write_json(root / f"work/quotes/{q['id']}.json", q)
    assert request(base, path, {**body, "confirm_uploads": True})[0] == 409
    assert not (root / "work/authorizations.json").exists()


def test_kernel_preconditions_reject_without_overwriting(action_server):
    root, *_ = action_server
    before = (root / "work/approvals.json").read_bytes()
    with pytest.raises(ValueError, match="changed"):
        P.approve(root, "analysis", "Reviewed", expected_hash="0" * 64)
    assert (root / "work/approvals.json").read_bytes() == before
    q = quote(root)
    with pytest.raises(ValueError, match="changed"):
        G.authorize(root, q["id"], "0.10", "Reviewed", expected_quote_hash="0" * 64)
    assert not (root / "work/authorizations.json").exists()


@pytest.mark.parametrize("command", ["approve", "authorize"])
def test_public_cli_decisions_redirect_and_non_tty_actions_fail(
    tmp_path, monkeypatch, capsys, command
):
    arguments = ["analysis"] if command == "approve" else ["--quote", "test", "--cap", "0.10"]
    monkeypatch.setattr(
        sys, "argv", ["clip", command, str(tmp_path), *arguments, "--note", "No write"]
    )
    monkeypatch.setattr(cli, "execute", lambda _: pytest.fail("CLI must not decide"))
    assert cli.main() == 1
    assert "Studio" in capsys.readouterr().err
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False)
    with pytest.raises(ValueError, match="interactive terminal"):
        serve.serve(tmp_path, tmp_path / "db.sqlite3", actions=True)


def test_existing_authority_is_not_silently_inflated_or_replaced(action_server):
    root, _server, base = action_server
    q = quote(root)
    G.authorize(root, q["id"], "0.50", "prior explicit larger authority")
    before = (root / "work/authorizations.json").read_bytes()
    status, review = request(base, f"api/project/production/quote/{q['id']}")
    assert status == 200 and review["authorization_state"] == "different authority"
    assert review["authorization"]["cap_usd"] == "0.50"
    body = {"expected_quote_hash": digest(q), "note": "Do not overwrite", "confirmed": True}
    assert request(base, f"api/project/production/authorize/{q['id']}", body)[0] == 409
    assert (root / "work/authorizations.json").read_bytes() == before


def test_human_action_keeps_complete_proof_review_gate(tmp_path):
    from test_creative_production import approve_prerequisites, record_stills
    from test_workflow_v2 import accept, strict_root

    from mp3_to_videoclip.reviews import record_review

    root = strict_root(tmp_path)
    approve_prerequisites(root)
    P.approve(root, "storyboard", "approved board")
    ids = P.proof_ids(P.load_board(root), P.load_brief(root))
    record_stills(root, ids)
    accept(root, ids)
    P.approve(root, "proof", "accepted exact versions")
    reviewed = H.review_stage(root, "proof")
    record_review(root, "s001", 1, "reject", note="new defect", reviewer="test", inspected=True)
    before = (root / "work/approvals.json").read_bytes()
    assert P.stage_hash(root, "proof") == reviewed["expected_hash"]
    with pytest.raises(ValueError, match="accepted review"):
        H.approve_stage(
            root,
            "proof",
            {
                "expected_hash": reviewed["expected_hash"],
                "note": "Cannot bypass",
                "confirmed": True,
            },
        )
    assert (root / "work/approvals.json").read_bytes() == before


def test_invalid_json_large_body_and_unknown_id_are_refused(action_server):
    root, _server, base = action_server
    assert request(base, "api/project/production/approve/analysis", ["not", "object"])[0] == 400
    assert (
        request(
            base, "api/project/production/approve/analysis", approval_body(root, note="x" * 9000)
        )[0]
        == 413
    )
    assert (
        request(
            base,
            "api/project/production/authorize/not-a-uuid",
            {"expected_quote_hash": "a" * 64, "note": "No write", "confirmed": True},
        )[0]
        == 404
    )
    assert (
        request(base, "api/project/production/approve/not-a-stage", approval_body(root))[0] == 404
    )
    for method in ("PUT", "PATCH", "DELETE", "OPTIONS"):
        assert (
            request(
                base, "api/project/production/approve/analysis", approval_body(root), method=method
            )[0]
            == 405
        )


def test_upload_consent_is_durable_and_preview_watch_is_required(action_server):
    from test_creative_production import approve_through_proof, write_preview_report

    root, _server, base = action_server
    q = quote(root, kind="transcription", tasks=[], source_hash="b" * 64)
    body = {
        "expected_quote_hash": digest(q),
        "note": "Audio transfer explicitly permitted",
        "confirmed": True,
        "confirm_uploads": True,
    }
    status, result = request(base, f"api/project/production/authorize/{q['id']}", body)
    assert status == 200
    assert result["record"]["uploads_confirmed"] is True
    assert result["record"]["review_confirmed"] is True
    approve_through_proof(root)
    write_preview_report(root)
    P.approve(root, "preview", "Legacy fixture decision")
    P.require_approval(root, "preview")  # Legacy decisions need no new attestation fields.
    expected = H.review_stage(root, "preview")["expected_hash"]
    body = {
        "expected_hash": expected,
        "note": "Test fixture playback attestation",
        "confirmed": True,
    }
    assert request(base, "api/project/production/approve/preview", body)[0] == 400
    status, result = request(
        base, "api/project/production/approve/preview", {**body, "preview_watched": True}
    )
    assert status == 200
    assert result["record"]["preview_watched"] is True
    assert result["record"]["review_confirmed"] is True


def test_invalid_json_syntax_and_no_external_network(action_server, monkeypatch):
    root, _server, base = action_server
    original_connect = socket.socket.connect
    original_lookup = socket.getaddrinfo
    attempts = []

    def lookup(host, *args, **kwargs):
        if host not in {"127.0.0.1", "localhost", "::1"}:
            attempts.append(host)
            raise AssertionError("external network is forbidden in decisions")
        return original_lookup(host, *args, **kwargs)

    def connect(sock, address):
        if isinstance(address, tuple) and address[0] not in {"127.0.0.1", "::1"}:
            attempts.append(address)
            raise AssertionError("external network is forbidden in decisions")
        return original_connect(sock, address)

    monkeypatch.setattr(socket, "getaddrinfo", lookup)
    monkeypatch.setattr(socket.socket, "connect", connect)
    malformed = urllib.request.Request(
        base + "api/project/production/approve/analysis",
        data=b"{",
        headers={
            "X-Studio-Token": "read",
            "X-Studio-Action": "human",
            "Origin": base.rstrip("/"),
            "Content-Type": "application/json",
        },
    )
    before = (root / "work/approvals.json").read_bytes()
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(malformed, timeout=5)
    assert error.value.code == 400
    assert (root / "work/approvals.json").read_bytes() == before
    assert request(base, "api/project/production/approve/analysis", approval_body(root))[0] == 200
    q = quote(root)
    assert (
        request(
            base,
            f"api/project/production/authorize/{q['id']}",
            {"expected_quote_hash": digest(q), "note": "No network", "confirmed": True},
        )[0]
        == 200
    )
    assert attempts == []


def test_action_enable_requires_exact_terminal_phrase(tmp_path, monkeypatch):
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr("builtins.input", lambda _: "no")
    monkeypatch.setattr(serve, "build_server", lambda *args, **kwargs: pytest.fail("must not bind"))
    with pytest.raises(ValueError, match="not enabled"):
        serve.serve(tmp_path, tmp_path / "db.sqlite3", actions=True)


def test_corrupt_authority_is_not_treated_as_missing(action_server):
    root, _server, base = action_server
    q = quote(root)
    path = root / "work/authorizations.json"
    path.write_text("{broken")
    before = path.read_bytes()
    status, _ = request(base, f"api/project/production/quote/{q['id']}")
    assert status == 409
    body = {
        "expected_quote_hash": digest(q),
        "note": "Must not overwrite corruption",
        "confirmed": True,
    }
    assert request(base, f"api/project/production/authorize/{q['id']}", body)[0] == 400
    assert path.read_bytes() == before


def test_studio_kernel_authority_requires_and_retains_consent(action_server):
    root, *_ = action_server
    with pytest.raises(ValueError, match="explicit review"):
        P.approve(root, "analysis", "Cannot fabricate Studio provenance", via="studio")
    q = quote(root, kind="transcription", tasks=[], source_hash="c" * 64)
    with pytest.raises(ValueError, match="data-transfer"):
        G.authorize(root, q["id"], "0.10", "No upload consent", via="studio", review_confirmed=True)
    with pytest.raises(ValueError, match="exact quoted"):
        G.authorize(
            root,
            q["id"],
            "0.50",
            "Cannot inflate",
            via="studio",
            review_confirmed=True,
            uploads_confirmed=True,
        )
    G.authorize(
        root,
        q["id"],
        "0.10",
        "Explicit scope and upload consent",
        via="studio",
        review_confirmed=True,
        uploads_confirmed=True,
    )
    values = read_json(root / "work/authorizations.json")
    values[q["id"]]["uploads_confirmed"] = False
    write_json(root / "work/authorizations.json", values)
    with pytest.raises(ValueError, match="incomplete"):
        G.authorization(root, q)
    assert H.review_quote(root, q["id"])["authorization_state"] == "incomplete consent"
    body = {
        "expected_quote_hash": digest(q),
        "note": "Cannot silently repair",
        "confirmed": True,
        "confirm_uploads": True,
    }
    before = (root / "work/authorizations.json").read_bytes()
    with pytest.raises(H.ActionError) as incomplete:
        H.authorize_quote(root, q["id"], body)
    assert incomplete.value.status == 409
    assert (root / "work/authorizations.json").read_bytes() == before


def test_missing_quote_errors_do_not_disclose_local_paths(action_server):
    root, _server, base = action_server
    identity = "00000000-0000-4000-8000-000000000001"
    body = {"expected_quote_hash": "a" * 64, "note": "Missing quote", "confirmed": True}
    status, result = request(base, f"api/project/production/authorize/{identity}", body)
    assert status == 400
    assert "Refresh current records" in result["error"]
    assert str(root.resolve()) not in result["error"]
    assert "work/quotes" not in result["error"]
    assert not (root / "work/authorizations.json").exists()


@pytest.mark.parametrize("changes", [{"provider": "wrong"}, {"model": None}])
def test_quote_recipient_and_model_must_be_reviewable(action_server, changes):
    root, _server, base = action_server
    q = quote(root, **changes)
    assert request(base, f"api/project/production/quote/{q['id']}")[0] == 400
    body = {"expected_quote_hash": digest(q), "note": "No opaque scope", "confirmed": True}
    assert request(base, f"api/project/production/authorize/{q['id']}", body)[0] == 400
    assert not (root / "work/authorizations.json").exists()


def test_studio_stage_records_fail_closed_but_legacy_is_preserved(action_server):
    root, *_ = action_server
    P.approve(root, "analysis", "Legacy review")
    values = read_json(root / "work/approvals.json")
    legacy = dict(values["analysis"])
    P.require_approval(root, "analysis")
    values["analysis"]["via"] = "studio"
    write_json(root / "work/approvals.json", values)
    with pytest.raises(ValueError, match="Studio approval is incomplete"):
        P.require_approval(root, "analysis")
    values["analysis"]["review_confirmed"] = True
    write_json(root / "work/approvals.json", values)
    P.require_approval(root, "analysis")
    values["analysis"] = legacy
    write_json(root / "work/approvals.json", values)
    P.require_approval(root, "analysis")


def test_preview_and_flagged_lyrics_attestations_are_checked_on_read(action_server):
    from test_creative_production import approve_through_proof, write_preview_report

    root, *_ = action_server
    approve_through_proof(root)
    write_preview_report(root)
    body = {
        "expected_hash": P.stage_hash(root, "preview"),
        "note": "Fixture watch",
        "confirmed": True,
        "preview_watched": True,
    }
    H.approve_stage(root, "preview", body)
    values = read_json(root / "work/approvals.json")
    values["preview"]["preview_watched"] = False
    write_json(root / "work/approvals.json", values)
    with pytest.raises(ValueError, match="Studio approval is incomplete"):
        P.require_approval(root, "preview")
    lyrics = read_json(root / "work/lyrics.json")
    lyrics["segments"][0]["flags"] = ["uncertain"]
    write_json(root / "work/lyrics.json", lyrics)
    P.approve(root, "lyrics", "Legacy acknowledged flags", acknowledge_uncertain=True)
    P.require_approval(root, "lyrics")
    values = read_json(root / "work/approvals.json")
    values["lyrics"].update(via="studio", review_confirmed=True, acknowledge_uncertain=False)
    write_json(root / "work/approvals.json", values)
    with pytest.raises(ValueError, match="Studio approval is incomplete"):
        P.require_approval(root, "lyrics")
    values["lyrics"]["acknowledge_uncertain"] = True
    write_json(root / "work/approvals.json", values)
    P.require_approval(root, "lyrics")


def test_graphics_attestation_keeps_the_actual_review_gate(action_server, monkeypatch):
    from mp3_to_videoclip import signature

    root, *_ = action_server
    monkeypatch.setattr(P, "_required_parents", lambda *_: [])
    monkeypatch.setattr(P, "stage_hash", lambda *_: "a" * 64)
    calls = []
    monkeypatch.setattr(signature, "validate_review", lambda *_: calls.append("checked"))
    record = {"hash": "a" * 64, "note": "Fixture", "via": "studio", "review_confirmed": True}
    write_json(root / "work/approvals.json", {"graphics": record})
    with pytest.raises(ValueError, match="incomplete"):
        P.require_approval(root, "graphics")
    assert calls == []
    record["inspected"] = True
    write_json(root / "work/approvals.json", {"graphics": record})
    P.require_approval(root, "graphics")
    record.pop("via")
    record.pop("inspected")
    write_json(root / "work/approvals.json", {"graphics": record})
    P.require_approval(root, "graphics")
    assert calls == ["checked", "checked"]
