"""MCP stdio bridge for the Studio director tools.

OpenCode launches this module as a local MCP server. It exposes the safe,
non-paid director tools and keeps the production boundary: every call names a
slug that must resolve to a project directly under ``--projects-dir``.

Transport is newline-delimited JSON-RPC (the MCP stdio convention). Nothing is
written to stdout except protocol messages.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import re
import sys
from pathlib import Path
from typing import Any

from . import tools

PROTOCOL_VERSION = "2024-11-05"
SERVER_INFO = {"name": "clipstudio", "version": "0.1"}

# Paid and job-starting tools stay out of the Writer/Editor surface until the
# Studio's authorization UI owns them. ``ask_user`` is OpenCode's own question
# flow, not an MCP tool.
EXCLUDED = {
    "generate_images",
    "transcribe_lyrics",
    "render",
    "ask_user",
}

SLUG = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def tool_descriptors() -> list[dict[str, Any]]:
    descriptors = []
    for tool in tools.TOOLS:
        function = tool["function"]
        if function["name"] in EXCLUDED:
            continue
        descriptors.append(
            {
                "name": function["name"],
                "description": function["description"],
                "inputSchema": function["parameters"],
                "annotations": {
                    "readOnlyHint": function["name"].startswith("get_"),
                    "destructiveHint": False,
                },
            }
        )
    return descriptors


def _root(projects_dir: Path, arguments: dict[str, Any]) -> Path:
    slug = arguments.get("slug")
    if not isinstance(slug, str) or not SLUG.match(slug):
        raise ValueError("slug must name a production directly under projects/")
    base = projects_dir.resolve()
    root = (base / slug).resolve()
    if root.parent != base or not (root / "project.json").is_file():
        raise ValueError("slug must name a production directly under projects/")
    return root


def _content(value) -> dict[str, Any]:
    if isinstance(value, tools.ToolResult):
        content: list[dict[str, Any]] = [{"type": "text", "text": value.text}]
        for data_url in value.images:
            header, _, encoded = data_url.partition(",")
            mime = header.removeprefix("data:").split(";", 1)[0] or "image/jpeg"
            content.append({"type": "image", "data": encoded, "mimeType": mime})
        return {"content": content, "isError": False}
    is_error = False
    try:
        parsed = json.loads(value)
        is_error = isinstance(parsed, dict) and "error" in parsed
    except (TypeError, json.JSONDecodeError):
        pass
    return {"content": [{"type": "text", "text": str(value)}], "isError": is_error}


def call_tool(name: str, arguments: dict[str, Any] | None, projects_dir: Path) -> dict[str, Any]:
    if name not in {item["name"] for item in tool_descriptors()}:
        raise ValueError(f"unknown or unavailable tool {name!r}")
    args = dict(arguments or {})
    _root(projects_dir, args)
    result = asyncio.run(tools.dispatch(name, args, projects_dir=projects_dir))
    return _content(result)


def handle(request: dict[str, Any], projects_dir: Path) -> dict[str, Any] | None:
    method = request.get("method")
    request_id = request.get("id")
    params = request.get("params") or {}

    def ok(result):
        return {"jsonrpc": "2.0", "id": request_id, "result": result}

    def error(code, message):
        return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}

    if method == "initialize":
        return ok(
            {
                "protocolVersion": params.get("protocolVersion") or PROTOCOL_VERSION,
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": SERVER_INFO,
                "instructions": (
                    "Studio director tools. Read the project before writing; every "
                    "write returns the new artifact and is validated by the engine."
                ),
            }
        )
    if method == "notifications/initialized":
        return None
    if method == "ping":
        return ok({})
    if method == "tools/list":
        return ok({"tools": tool_descriptors()})
    if method == "tools/call":
        try:
            return ok(call_tool(params.get("name"), params.get("arguments"), projects_dir))
        except (OSError, ValueError, KeyError, IndexError) as exc:
            return error(-32602, str(exc))
    return error(-32601, f"method not found: {method}")


def read_message():
    line = sys.stdin.buffer.readline()
    if not line:
        return None
    if line.startswith(b"{"):
        return json.loads(line)
    headers: dict[str, str] = {}
    while line not in (b"\r\n", b"\n", b""):
        key, _, value = line.decode().partition(":")
        headers[key.strip().lower()] = value.strip()
        line = sys.stdin.buffer.readline()
    length = int(headers.get("content-length", "0"))
    return json.loads(sys.stdin.buffer.read(length))


def serve(projects_dir: Path) -> None:
    while True:
        message = read_message()
        if message is None:
            break
        try:
            response = handle(message, projects_dir)
        except (OSError, ValueError, KeyError) as exc:
            response = {
                "jsonrpc": "2.0",
                "id": message.get("id"),
                "error": {"code": -32602, "message": str(exc)},
            }
        if response is not None:
            print(json.dumps(response, default=str), flush=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Studio director MCP server")
    parser.add_argument("--projects-dir", default="projects")
    args = parser.parse_args(argv)
    serve(Path(args.projects_dir))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
