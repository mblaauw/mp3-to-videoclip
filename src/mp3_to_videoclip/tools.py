"""Capability registry for the command surface.

The studio is agent-driven, so the tool surface needs explicit scopes rather than
trust. This module classifies every `clip` command once, and gives the runtime a
single place to answer: may this capability read, derive, edit, spend, or is it a
human decision?

Nothing here executes anything; it is the policy table the runtime and the UI share.
"""

from __future__ import annotations

import io
from contextlib import redirect_stderr, redirect_stdout

from .cli import parser

#: read    - no writes at all
#: derive  - writes only derived artifacts (pages, sheets, previews, archives)
#: edit    - changes canonical production artifacts
#: spend   - can incur provider cost
#: human   - a decision only a person may make (approval, authorisation, billing)
KINDS = ("read", "derive", "edit", "spend", "human")

SCOPES: dict[str, dict] = {
    # pure reads
    "status": {"kind": "read", "note": "stage and shot state"},
    "costs": {"kind": "read", "note": "journal spend and reservations"},
    "locate": {"kind": "read", "note": "frame/second lookup"},
    "preflight": {"kind": "read", "note": "compiled prompts and conflicts"},
    "prompts": {"kind": "read", "note": "compiled prompt inspection"},
    "doctor": {"kind": "read", "note": "tool and credential availability"},
    "schema": {"kind": "read", "note": "artifact JSON schemas"},
    "progress": {"kind": "read", "note": "operation receipts", "writes": ["work/operations"]},
    "spine": {"kind": "read", "note": "durable run journal", "writes": ["studio/spine.sqlite3"]},
    "budget": {
        "kind": "read",
        "note": "report by default",
        "writes": ["work/production-budget.json"],
    },
    # derived artifacts only
    "dashboard": {"kind": "derive", "note": "review page", "writes": ["work/dashboard"]},
    "studio": {"kind": "derive", "note": "cross-project index", "writes": ["studio"]},
    "inspect": {"kind": "derive", "note": "shot inspector pages", "writes": ["work/inspector"]},
    "intake": {"kind": "derive", "note": "intake wizard page", "writes": ["studio"]},
    "sheet": {"kind": "derive", "note": "contact sheet", "writes": ["work"]},
    "preview": {"kind": "derive", "note": "local animatic", "writes": ["previews", "work/preview"]},
    "backup": {"kind": "derive", "note": "private archive", "writes": ["backups"]},
    "render": {"kind": "derive", "note": "local render", "writes": ["renders", "work"]},
    "serve": {"kind": "read", "note": "read-only live layer"},
    "plan": {"kind": "edit", "note": "propose or run a plan; running edits needs delegation"},
    "mcp": {"kind": "read", "note": "read/derive tool surface over stdio"},
    "eval": {"kind": "read", "note": "structural invariant report"},
    "context": {"kind": "read", "note": "labelled context pack for a step"},
    # canonical edits (no provider cost)
    "init": {"kind": "edit", "note": "create a production"},
    "analyze": {"kind": "edit", "note": "local measurement"},
    "events": {"kind": "edit", "note": "event map"},
    "skeleton": {"kind": "edit", "note": "timing skeleton"},
    "import-lyrics": {"kind": "edit", "note": "lyrics import"},
    "feedback": {
        "kind": "edit",
        "note": "Studio revision request",
        "writes": ["work/feedback.json"],
    },
    "select": {"kind": "edit", "note": "choose a version"},
    "review": {"kind": "edit", "note": "byte-bound verdict"},
    "adopt": {"kind": "edit", "note": "register a derivative"},
    "shot-edit": {"kind": "edit", "note": "presentation edit"},
    "restage": {"kind": "edit", "note": "new correction cycle"},
    "reference-import": {"kind": "edit", "note": "local reference asset"},
    "music-map": {"kind": "edit", "note": "combined measurement map"},
    # provider cost
    "quote": {"kind": "spend", "note": "scoped quote, no charge"},
    "quote-transcription": {"kind": "spend", "note": "estimate only"},
    "quote-music": {"kind": "spend", "note": "estimate only"},
    "generate": {"kind": "spend", "note": "paid image submission"},
    "transcribe": {"kind": "spend", "note": "paid upload + inference"},
    "listen": {"kind": "spend", "note": "paid audio listening"},
    "recover": {"kind": "spend", "note": "download a billed result"},
    "style-test": {"kind": "spend", "note": "one tracked control image"},
    # human decisions
    "approve": {"kind": "human", "note": "content-bound approval"},
    "authorize": {"kind": "human", "note": "spending authority"},
    "resolve-task": {"kind": "human", "note": "verified billing reconciliation"},
}

#: Capabilities an autonomous agent may hold without a human in the loop.
DEFAULT_AGENT_KINDS = frozenset({"read", "derive"})
#: Editing canonical artifacts is allowed when the project delegates it explicitly.
DELEGATED_AGENT_KINDS = frozenset({"read", "derive", "edit"})


def describe() -> list[dict]:
    """The tool surface as data, for a UI or an agent system prompt."""
    return [
        {"tool": name, **scope, "human_only": scope["kind"] == "human"}
        for name, scope in sorted(SCOPES.items())
    ]


def scope_for(tool: str) -> dict:
    if tool not in SCOPES:
        raise ValueError(f"unclassified command {tool!r}; classify it before exposing it")
    return SCOPES[tool]


def require(tool: str, granted=DEFAULT_AGENT_KINDS) -> dict:
    """Raise unless ``tool``'s kind is granted. Human decisions are never delegated."""
    scope = scope_for(tool)
    if scope["kind"] == "human":
        raise PermissionError(f"{tool} is a human decision and cannot be delegated")
    if scope["kind"] not in granted:
        raise PermissionError(f"{tool} needs {scope['kind']} capability, not {sorted(granted)}")
    return scope


def classify_argv(argv: list[str]) -> str:
    """Best-effort command name from an argv tail (``["clip", "status", ...]``)."""
    for token in argv:
        if token in SCOPES:
            return token
    raise ValueError("no known clip command in argv")


def human_capability(argv: list[str]) -> str | None:
    """Re-derive human-only modes from the same parser used by execution.

    A read command may have a human-only mode. Stored plan labels are never
    authority; parser-supported abbreviations must not evade this check.
    """
    tool = classify_argv(argv)
    if scope_for(tool)["kind"] == "human":
        return f"{tool} is a human decision and cannot be delegated"
    tail = argv[3:] if argv[:3] == ["uv", "run", "clip"] else argv
    # A leading `--` before the subcommand is valid; parse the unmodified tail.
    if tool not in {"serve", "budget"}:
        return None
    try:
        with redirect_stderr(io.StringIO()), redirect_stdout(io.StringIO()):
            args, _ = parser().parse_known_args(tail)
    except SystemExit as exc:
        return None if exc.code == 0 else "invalid human-capability arguments require review"
    if args.command == "serve" and args.actions:
        return "serve --actions opens the human action capability and cannot be delegated"
    if args.command == "budget" and args.cap is not None:
        return "budget --cap sets spending authority and cannot be delegated"
    return None


def unclassified() -> list[str]:
    """Every parser command without a scope, so the registry cannot silently drift."""
    known = set(SCOPES)
    return sorted(set(_command_names()) - known)


def _command_names() -> list[str]:
    action = next(a for a in parser()._actions if a.dest == "command")
    return list(action.choices)
