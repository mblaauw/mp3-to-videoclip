"""Minimal MCP server: the read/derive surface, and generated pages as app resources.

Design constraints:

* only ``read`` and ``derive`` tools are exposed; anything that edits canon, spends or
  decides is absent from ``tools/list`` rather than merely "not recommended";
* project paths are resolved inside the projects directory, so a caller cannot point a
  tool at an arbitrary local path;
* generated pages are returned as ``text/html;profile=mcp-app`` resources, which a host
  may render in a sandboxed iframe. They are already self-contained and read-only.

Transport here is stdio JSON-RPC. The protocol version constant is the one this server
was written against; it must be checked against the live MCP specification when the app
is integrated, rather than assumed to be permanent.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from . import dashboard, generation, inspector, plans, preflight, production, studio

PROTOCOL_VERSION = "2026-01-26"
SERVER_INFO = {"name": "clip-studio", "version": "0.1.0"}
WIDGET_MIME = "text/html;profile=mcp-app"

TOOLS: list[dict] = [
    {
        "name": "status",
        "description": "Stage approvals, stale/missing shots and budget for one production.",
        "project": True,
        "read_only": True,
        "call": lambda ctx, args: production.status(ctx.project(args)),
    },
    {
        "name": "costs",
        "description": "Reported spend, reservations and unresolved tasks for one production.",
        "project": True,
        "read_only": True,
        "call": lambda ctx, args: generation.costs(ctx.project(args)),
    },
    {
        "name": "studio",
        "description": "All productions with next gate, blockers and action commands.",
        "project": False,
        "read_only": True,
        "call": lambda ctx, args: {"productions": studio.scan(ctx.projects_dir)},
    },
    {
        "name": "plan_build",
        "description": "Propose a plan of open steps for a production. Changes nothing.",
        "project": True,
        "read_only": True,
        "call": lambda ctx, args: plans.build(ctx.project(args), intent=args.get("intent")),
    },
    {
        "name": "preflight",
        "description": "Compiled prompts, references and known conflicts for shots.",
        "project": True,
        "read_only": True,
        "call": lambda ctx, args: preflight.manifest(
            ctx.project(args),
            args.get("shots").split(",") if args.get("shots") else None,
        ),
    },
    {
        "name": "dashboard",
        "description": "Build the beatmap/storyboard review page and return it as an app resource.",
        "project": True,
        "read_only": False,
        "ui": "ui://clip/dashboard.html",
        "call": lambda ctx, args: dashboard.build_dashboard(
            ctx.project(args), args.get("stage", "board")
        ),
    },
    {
        "name": "inspect",
        "description": "Build per-shot inspector pages (or the index) and return the path.",
        "project": True,
        "read_only": False,
        "ui": "ui://clip/inspector.html",
        "call": lambda ctx, args: inspector.build_inspector(ctx.project(args), args.get("shot")),
    },
]
TOOL_INDEX = {tool["name"]: tool for tool in TOOLS}


class Context:
    def __init__(self, projects_dir: Path):
        self.projects_dir = Path(projects_dir).resolve()

    def project(self, args: dict) -> Path:
        name = args.get("project")
        if not isinstance(name, str) or not name:
            raise ValueError("project is required")
        candidate = (self.projects_dir / name).resolve()
        if candidate.parent != self.projects_dir or not (candidate / "project.json").is_file():
            raise ValueError("project must name a production inside the projects directory")
        return candidate


def _tool_descriptor(tool: dict) -> dict:
    schema = {
        "type": "object",
        "properties": {
            "project": {"type": "string", "description": "production folder name"},
        },
        "required": ["project"] if tool["project"] else [],
        "additionalProperties": False,
    }
    if tool["name"] == "dashboard":
        schema["properties"]["stage"] = {"enum": ["board", "stills", "delivery"]}
    if tool["name"] == "inspect":
        schema["properties"]["shot"] = {"type": "string"}
    if tool["name"] == "preflight":
        schema["properties"]["shots"] = {"type": "string", "description": "comma-separated IDs"}
    if tool["name"] == "plan_build":
        schema["properties"]["intent"] = {"type": "string"}
    value = {
        "name": tool["name"],
        "description": tool["description"],
        "inputSchema": schema,
        "annotations": {"readOnlyHint": tool["read_only"], "destructiveHint": False},
    }
    if tool.get("ui"):
        value["_meta"] = {"ui": {"resourceUri": tool["ui"]}}
    return value


def tools_list() -> list[dict]:
    return [_tool_descriptor(tool) for tool in TOOLS]


def call_tool(name: str, arguments: dict | None, ctx: Context) -> dict:
    tool = TOOL_INDEX.get(name)
    if tool is None:
        raise ValueError(f"unknown or unavailable tool {name!r}")
    result = tool["call"](ctx, arguments or {})
    return {
        "content": [{"type": "text", "text": json.dumps(result, indent=2, default=str)}],
        "isError": False,
    }


def list_resources(ctx: Context) -> list[dict]:
    """Expose generated pages as app resources; nothing outside the projects is listed."""
    resources = []
    for entry in studio.scan(ctx.projects_dir):
        if entry.get("dashboard"):
            relative = entry["dashboard"]["name"]
            resources.append(
                {
                    "uri": f"ui://clip/{entry['slug']}/{relative}",
                    "name": f"{entry['slug']} dashboard",
                    "mimeType": WIDGET_MIME,
                    "description": "Beatmap, shot timeline and approval state (read-only).",
                }
            )
    return resources


def read_resource(uri: str, ctx: Context) -> dict:
    if not uri.startswith("ui://clip/"):
        raise ValueError("only generated studio pages are readable")
    parts = uri[len("ui://clip/") :].split("/")
    if len(parts) != 2:
        raise ValueError("resource URI must be ui://clip/<production>/<page>")
    slug, page = parts
    candidate = (ctx.projects_dir / slug / "work/dashboard" / page).resolve()
    expected = (ctx.projects_dir / slug / "work/dashboard").resolve()
    if candidate.parent != expected or not candidate.is_file():
        raise ValueError("resource not found")
    return {"contents": [{"uri": uri, "mimeType": WIDGET_MIME, "text": candidate.read_text()}]}


def handle(request: dict, ctx: Context) -> dict | None:
    """Pure JSON-RPC dispatch; notifications return ``None``."""
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
                "capabilities": {
                    "tools": {"listChanged": False},
                    "resources": {"subscribe": False},
                },
                "serverInfo": SERVER_INFO,
                "instructions": (
                    "Read/derive only. Editing canon, approving, spending and billing reconciliation "
                    "are human-only and are not exposed here."
                ),
            }
        )
    if method == "notifications/initialized":
        return None
    if method == "ping":
        return ok({})
    if method == "tools/list":
        return ok({"tools": tools_list()})
    if method == "tools/call":
        try:
            return ok(call_tool(params.get("name"), params.get("arguments"), ctx))
        except (OSError, ValueError, KeyError) as exc:
            return error(-32602, str(exc))
    if method == "resources/list":
        return ok({"resources": list_resources(ctx)})
    if method == "resources/read":
        try:
            return ok(read_resource(params.get("uri", ""), ctx))
        except (OSError, ValueError) as exc:
            return error(-32602, str(exc))
    return error(-32601, f"method not found: {method}")


def serve(projects_dir: Path) -> None:
    """stdio transport: one JSON-RPC object per line, one response per request."""
    ctx = Context(projects_dir)
    for raw in sys.stdin:
        line = raw.strip()
        if not line:
            continue
        try:
            request = json.loads(line)
        except ValueError:
            print(
                json.dumps(
                    {
                        "jsonrpc": "2.0",
                        "id": None,
                        "error": {"code": -32700, "message": "parse error"},
                    }
                ),
                flush=True,
            )
            continue
        response = handle(request, ctx)
        if response is not None:
            print(json.dumps(response, default=str), flush=True)
