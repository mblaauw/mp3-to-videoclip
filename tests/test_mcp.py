"""MCP surface: read/derive only, path-scoped, pages as app resources."""

import json

import pytest
from test_creative_production import approve_through_proof, make_root

from mp3_to_videoclip import mcp


@pytest.fixture()
def ctx(tmp_path):
    projects = tmp_path / "projects"
    projects.mkdir()
    root = make_root(projects)
    approve_through_proof(root)
    return mcp.Context(projects), root


def rpc(ctx, method, params=None, request_id=1):
    return mcp.handle(
        {"jsonrpc": "2.0", "id": request_id, "method": method, "params": params or {}}, ctx
    )


def test_initialize_reports_read_only_surface(ctx):
    response = rpc(ctx[0], "initialize", {"protocolVersion": "test-version"})
    assert response["result"]["protocolVersion"] == "test-version"
    assert "Read/derive only" in response["result"]["instructions"]
    assert mcp.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}, ctx[0]) is None


def test_tools_list_excludes_every_write_spend_and_decision(ctx):
    tools = {tool["name"]: tool for tool in rpc(ctx[0], "tools/list")["result"]["tools"]}
    assert {"status", "costs", "studio", "preflight", "dashboard", "inspect"} <= set(tools)
    forbidden = {"approve", "authorize", "generate", "shot-edit", "adopt", "render", "resolve-task"}
    assert not (forbidden & set(tools))
    for tool in tools.values():
        assert tool["annotations"]["destructiveHint"] is False
        if not tool["annotations"]["readOnlyHint"]:
            assert tool["_meta"]["ui"]["resourceUri"].startswith("ui://clip/")


def test_tools_call_returns_json_content(ctx):
    response = rpc(ctx[0], "tools/call", {"name": "status", "arguments": {"project": "production"}})
    payload = json.loads(response["result"]["content"][0]["text"])
    assert "approvals" in payload and "shots" in payload
    assert response["result"]["isError"] is False

    studio_payload = json.loads(
        rpc(ctx[0], "tools/call", {"name": "studio", "arguments": {}})["result"]["content"][0][
            "text"
        ]
    )
    assert len(studio_payload["productions"]) == 1


def test_project_paths_cannot_escape_the_projects_directory(ctx, tmp_path):
    response = rpc(ctx[0], "tools/call", {"name": "status", "arguments": {"project": "../../etc"}})
    assert "error" in response and "inside the projects directory" in response["error"]["message"]


def test_unknown_tool_and_method_are_errors(ctx):
    unknown = rpc(
        ctx[0], "tools/call", {"name": "generate", "arguments": {"project": "production"}}
    )
    assert unknown["error"]["code"] == -32602
    method = rpc(ctx[0], "nope/list")
    assert method["error"]["code"] == -32601


def test_dashboard_is_exposed_as_an_app_resource(ctx):
    built = rpc(
        ctx[0],
        "tools/call",
        {"name": "dashboard", "arguments": {"project": "production", "stage": "board"}},
    )
    page = json.loads(built["result"]["content"][0]["text"])
    assert page["html"].endswith(".html")

    resources = rpc(ctx[0], "resources/list")["result"]["resources"]
    assert resources and resources[0]["mimeType"] == mcp.WIDGET_MIME
    uri = resources[0]["uri"]
    assert uri.startswith("ui://clip/production/")

    read = rpc(ctx[0], "resources/read", {"uri": uri})["result"]["contents"][0]
    assert read["mimeType"] == mcp.WIDGET_MIME
    assert "<html" in read["text"]
    assert "http://" not in read["text"] and "https://" not in read["text"]


def test_resources_cannot_read_arbitrary_files(ctx):
    for uri in ("ui://clip/production/../../project.json", "ui://clip/only-one-part"):
        response = rpc(ctx[0], "resources/read", {"uri": uri})
        assert "error" in response


def test_plan_build_is_proposal_only(ctx, monkeypatch):
    before = sorted(path.name for path in (ctx[1] / "work").iterdir())
    payload = json.loads(
        rpc(
            ctx[0],
            "tools/call",
            {"name": "plan_build", "arguments": {"project": "production", "intent": "test"}},
        )["result"]["content"][0]["text"]
    )
    assert payload["steps"] and payload["intent"] == "test"
    assert sorted(path.name for path in (ctx[1] / "work").iterdir()) == before
