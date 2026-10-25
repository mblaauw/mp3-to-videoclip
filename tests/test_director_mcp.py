"""The MCP bridge exposes only safe director tools and stays inside projects/."""

from __future__ import annotations

from pathlib import Path

from api_support import add_assets, make_api_project

from mp3_to_videoclip import production as P
from mp3_to_videoclip.director import mcp


def _call(name: str, arguments: dict, projects_dir: Path) -> dict:
    return mcp.handle(
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": name, "arguments": arguments},
        },
        projects_dir,
    )


def test_mcp_lists_editor_tools_and_hides_paid_jobs():
    names = {tool["name"] for tool in mcp.tool_descriptors()}
    assert {"get_project", "get_brief", "update_brief", "update_shots", "get_images"} <= names
    assert "generate_images" not in names
    assert "transcribe_lyrics" not in names
    assert "render" not in names
    assert "ask_user" not in names


def test_mcp_initialize_and_read_a_project(tmp_path):
    make_api_project(tmp_path)
    init = mcp.handle({"jsonrpc": "2.0", "id": 0, "method": "initialize", "params": {}}, tmp_path)
    assert init["result"]["serverInfo"]["name"] == "clipstudio"
    assert "tools" in init["result"]["capabilities"]

    result = _call("get_project", {"slug": "production"}, tmp_path)
    assert result["result"]["isError"] is False
    assert "production" in result["result"]["content"][0]["text"]


def test_mcp_update_brief_writes_through_the_engine(tmp_path):
    root = make_api_project(tmp_path)
    result = _call(
        "update_brief",
        {"slug": "production", "patch": {"treatment": "Written over MCP"}},
        tmp_path,
    )
    assert result["result"]["isError"] is False
    assert P.load_brief(root).treatment == "Written over MCP"


def test_mcp_get_images_returns_image_content(tmp_path):
    root = make_api_project(tmp_path)
    add_assets(root)
    result = _call("get_images", {"slug": "production", "shot_ids": ["s001", "s002"]}, tmp_path)
    content = result["result"]["content"]
    assert content[0]["type"] == "text"
    images = [part for part in content if part["type"] == "image"]
    assert len(images) == 2
    assert images[0]["mimeType"] == "image/jpeg"
    assert images[0]["data"]


def test_mcp_rejects_a_slug_outside_the_projects_directory(tmp_path):
    (tmp_path / "production").mkdir()
    (tmp_path / "production" / "project.json").write_text("{}")
    result = _call("get_project", {"slug": "../production"}, tmp_path)
    assert "error" in result
    assert "directly under projects" in result["error"]["message"]


def test_mcp_rejects_an_unavailable_tool(tmp_path):
    make_api_project(tmp_path)
    result = _call("generate_images", {"slug": "production", "shot_ids": ["s001"]}, tmp_path)
    assert "error" in result
    assert "unavailable" in result["error"]["message"]
