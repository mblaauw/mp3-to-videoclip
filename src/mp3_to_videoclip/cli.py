"""Explicit stage commands for use by a human or an approval-respecting agent."""

import argparse
import contextlib
import json
import math
import os
import re
import shutil
import sys
from fractions import Fraction
from pathlib import Path

from . import derivations, generation, operations, production, profiles
from .analysis import analyze
from .branding import brand_hash, load_brand
from .models import (
    BrandPackage,
    Brief,
    EventMap,
    ListeningDraft,
    Lyrics,
    Storyboard,
    native_size_problem,
)
from .preview import build_preview
from .providers import RUNWARE_KEY_ENV
from .render import contact_sheet, render
from .storage import digest, file_hash, inside, project_lock, read_json, write_json


def parse_native_size(text: str, aspect: str) -> list[int]:
    """Strict ``WxH`` parse; unusable sizes fail before any project file is written."""
    match = re.fullmatch(r"([0-9]+)[xX]([0-9]+)", text.strip())
    if match is None:
        raise ValueError(f"--native-size must be two positive integers like 1376x768, got {text!r}")
    width, height = (int(group) for group in match.groups())
    a, b = map(int, aspect.split(":"))
    problem = native_size_problem([width, height], a, b)
    if problem:
        raise ValueError(problem)
    return [width, height]


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Agent-operated MP3 → storyboard → stills → video. No automatic paid stages."
    )
    commands = p.add_subparsers(dest="command", required=True)
    control = commands.add_parser(
        "style-test", help="One tracked style control; no audio or fake film"
    )
    style_operations = control.add_subparsers(dest="operation", required=True)
    for operation in ("quote", "run", "recover", "approve"):
        action = style_operations.add_parser(operation)
        action.add_argument("directory", type=Path)
        if operation == "quote":
            action.add_argument("--reserve", default="0.10")
        elif operation == "run":
            action.add_argument("--quote", required=True)
            action.add_argument("--cap", required=True)
            action.add_argument("--note", required=True)
        else:
            action.add_argument("--task", required=True)
            if operation == "approve":
                action.add_argument(
                    "--note",
                    required=True,
                    help="The user's actual visual style decision, not automatic agent acceptance",
                )
    doctor = commands.add_parser("doctor", help="Show tool/credential availability without values")
    doctor.set_defaults(project=None)
    schema = commands.add_parser("schema", help="Print editable artifact JSON schemas")
    schema.add_argument(
        "kind", choices=["brief", "lyrics", "storyboard", "events", "brand", "listening"]
    )
    schema.set_defaults(project=None)
    spine = commands.add_parser("spine", help="Inspect the durable run journal")
    spine_ops = spine.add_subparsers(dest="operation", required=True)
    for name, help_text in {
        "status": "Counts, open human waits and the journal location",
        "runs": "Recent runs with steps and open interrupts",
        "events": "Append-only event stream, optionally for one run",
        "reconcile": "Mark runs whose owning process is gone as interrupted",
        "trace": "One run as evidence: steps, waits, output and cost",
        "resolve": "Record a human decision for one durable wait",
    }.items():
        action = spine_ops.add_parser(name, help=help_text)
        action.add_argument("--db", help="Journal path (default studio/spine.sqlite3)")
        if name in ("runs", "events"):
            action.add_argument("--limit", type=int, default=20)
        if name == "events":
            action.add_argument("--run")
            action.add_argument("--after", type=int, default=0)
        if name == "trace":
            action.add_argument("--run", required=True)
        if name == "resolve":
            action.add_argument("--interrupt", required=True)
            action.add_argument("--note", required=True)
    sync = spine_ops.add_parser("sync", help="Import work/operations receipts as runs")
    sync.add_argument("--db", help="Journal path (default studio/spine.sqlite3)")
    sync.add_argument("--projects-dir", type=Path, default=Path("projects"))
    spine.set_defaults(project=None)
    plan = commands.add_parser("plan", help="Propose, inspect and run a validated plan")
    plan_ops = plan.add_subparsers(dest="operation", required=True)
    plan_build = plan_ops.add_parser("build", help="Turn open actions into a plan; changes nothing")
    plan_build.add_argument("project", type=Path)
    plan_build.add_argument("--intent", help="Why this run exists")
    for name, help_text in {"list": "Recent plans", "show": "One plan"}.items():
        action = plan_ops.add_parser(name, help=help_text)
        action.add_argument("project", type=Path)
        if name == "show":
            action.add_argument("--id", required=True)
    plan_run = plan_ops.add_parser("run", help="Execute concrete steps, stop at humans")
    plan_run.add_argument("project", type=Path)
    plan_run.add_argument("--id", required=True)
    plan_run.add_argument("--db", help="Journal path (default studio/spine.sqlite3)")
    plan_run.add_argument(
        "--allow-edit", action="store_true", help="Delegate canonical edits to this run"
    )
    plan.set_defaults(project=None)
    context_cmd = commands.add_parser("context", help="Assemble the labelled context pack for a step")
    context_cmd.add_argument("project", type=Path)
    context_cmd.add_argument("--stage")
    context_cmd.add_argument("--shots", type=int, default=0)
    context_cmd.add_argument("--include-prompts", action="store_true")
    eval_cmd = commands.add_parser("eval", help="Run structural invariant checks over the repo")
    eval_cmd.add_argument("--root", type=Path, default=Path("."))
    eval_cmd.set_defaults(project=None)
    mcp_cmd = commands.add_parser("mcp", help="MCP stdio server exposing read/derive tools")
    mcp_cmd.add_argument("--projects-dir", type=Path, default=Path("projects"))
    mcp_cmd.set_defaults(project=None)
    serve_cmd = commands.add_parser("serve", help="Read-only live studio over loopback + SSE")
    serve_cmd.add_argument("--projects-dir", type=Path, default=Path("projects"))
    serve_cmd.add_argument("--db", help="Journal path (default studio/spine.sqlite3)")
    serve_cmd.add_argument("--port", type=int, default=8765)
    serve_cmd.add_argument("--token", help="Session token; generated when omitted")
    serve_cmd.set_defaults(project=None)
    intake = commands.add_parser("intake", help="Build a static intake wizard that emits commands")
    intake.add_argument("--output-dir", type=Path, help="Where the page is written")
    intake.add_argument("--name", help="Explicit safe .html basename; never overwritten")
    intake.set_defaults(project=None)
    inspect = commands.add_parser("inspect", help="Build a static per-shot inspector page")
    inspect.add_argument("project", type=Path)
    inspect.add_argument("--shot", help="One shot ID; omit for the whole board")
    studio = commands.add_parser(
        "studio", help="Build one static index page for every production on disk"
    )
    studio.add_argument(
        "--projects-dir", type=Path, default=Path("projects"), help="Folder containing productions"
    )
    studio.add_argument("--output-dir", type=Path, help="Where the page is written")
    studio.add_argument("--name", help="Explicit safe .html basename; never overwritten")
    studio.set_defaults(project=None)
    init = commands.add_parser("init", help="Copy an MP3 into a new production")
    init.add_argument("project", type=Path)
    init.add_argument("--mp3", type=Path, required=True)
    init.add_argument("--slug", help="Explicit film folder ID; otherwise derived from --title")
    init.add_argument(
        "--title",
        help="Film title, separate from source filename; choose the folder/slug from this title",
    )
    init.add_argument("--aspect", choices=["16:9", "9:16"], default="16:9")
    init.add_argument("--fps", type=int, choices=[24, 30], default=24)
    init.add_argument(
        "--renderer",
        choices=["remotion", "ffmpeg"],
        default="remotion",
        help="Visual renderer for this new production; legacy projects remain unchanged",
    )
    init.add_argument(
        "--music-mode", choices=["vocal", "instrumental", "music-led"], default="vocal"
    )
    init.add_argument(
        "--native-size",
        metavar="WxH",
        help="Image-generation size for this production, e.g. 1376x768; omit to keep the default",
    )
    init.add_argument("--model", help="Persist a model schema slug override for this production")
    init.add_argument(
        "--style", help="Replace the default global look; do not include shot content"
    )
    init.add_argument("--image-settings", help="JSON settings object replacing the model defaults")
    init.add_argument("--image-seed", type=int, help="Optional seed, not an identity guarantee")
    init.add_argument(
        "--workflow-version",
        type=int,
        choices=[1, 2],
        default=2,
        help="New productions use strict workflow 2; 1 retains legacy gates",
    )
    for name, help_text in {
        "analyze": "Local beat/energy/rough section analysis; no upload",
        "status": "Show current approvals and stale/missing shots",
        "approve": "Record an explicit user decision for a creative stage",
        "import-lyrics": "Import supplied/corrected timestamped lyrics",
        "skeleton": "Make a beat-snapped timing skeleton, NOT a creative storyboard",
        "events": "Create an empty, editable musical event map (no automatic interpretations)",
        "prompts": "Inspect compiled shot prompts and required visible details without generating",
        "preview": "Render a marked local animatic with actual audio and labelled placeholders",
        "backup": "Save a private local production archive, excluding rebuildable plate caches",
        "quote-transcription": "Estimate hosted transcription cost without uploading",
        "quote-music": "Quote a tracked, audio-blind musical listening pass (no upload)",
        "listen": "PAID UPLOAD: execute the authorized musical listening quote",
        "music-map": "Build an unreviewed combined listening/measurement map locally",
        "quote": "Inspect live image schema/pricing and save a scoped spending request",
        "authorize": "Record spending authorization; does NOT generate/upload",
        "transcribe": "PAID UPLOAD: submit an authorized transcription exactly once",
        "generate": "PAID: execute an authorized image scope with durable tracking",
        "recover": "Recover/download a previously submitted task, never resubmit",
        "resolve-task": "Record user-verified billing/status for an ambiguous submission",
        "select": "Choose an immutable image version; does not approve it",
        "sheet": "Build a local contact sheet for visual review",
        "render": "Render an approved full still set to a versioned MP4",
        "costs": "Show reported/calculated costs and unresolved reservations",
        "budget": "Set an authorized production cap, or report cumulative spending",
        "restage": "Record diagnosis/restaging authority for another correction cycle; no spend",
        "preflight": "Inspect resolved states, references, exact prompts and known conflicts",
        "review": "Record an inspected image version's accept/reject/uncertain judgement",
        "reference-import": "Import a permission-confirmed immutable local reference; no upload",
        "locate": "Resolve a frame or second to its exact shot and source owner",
        "adopt": "Record an inspected local derivative (crop/mirror/tone) as a new image version",
        "progress": "Monitor local operations from their durable receipts; never approves or spends",
        "dashboard": "Render a self-contained beatmap/storyboard review page from canonical artifacts",
        "shot-edit": "Change one shot's transition, dissolve, camera or grade (validated re-edit)",
    }.items():
        cmd = commands.add_parser(name, help=help_text)
        cmd.add_argument("project", type=Path)
        if name == "analyze":
            cmd.add_argument("--force", action="store_true")
            cmd.add_argument(
                "--deep",
                action="store_true",
                help=(
                    "Also run the deeper local pass (downbeat phase, key, candidate "
                    "sections, band onsets) into work/music-deep.json; still unreviewed "
                    "measurements and still no provider call"
                ),
            )
        elif name == "approve":
            cmd.add_argument("stage", choices=list(production.UPSTREAM))
            cmd.add_argument("--note", required=True)
            cmd.add_argument("--ack-uncertain", action="store_true")
            cmd.add_argument(
                "--inspected",
                action="store_true",
                help="Acknowledgement of actual composited graphics inspection",
            )
        elif name == "budget":
            cmd.add_argument("--cap")
            cmd.add_argument("--note")
            cmd.add_argument(
                "--max-corrections",
                type=int,
                help=f"New budgets default to {profiles.DEFAULT_MAX_CORRECTIONS}; existing limits are retained unless explicit",
            )
        elif name == "restage":
            cmd.add_argument("--shots", required=True)
            cmd.add_argument("--note", required=True)
        elif name == "review":
            cmd.add_argument("--shot", required=True)
            cmd.add_argument("--version", type=int, required=True)
            cmd.add_argument("--verdict", choices=["accept", "reject", "uncertain"], required=True)
            cmd.add_argument("--reviewer", required=True)
            cmd.add_argument("--note", required=True)
            cmd.add_argument("--inspected", action="store_true")
        elif name == "reference-import":
            cmd.add_argument("--source", type=Path, required=True)
            cmd.add_argument("--crop", nargs=4, type=int, metavar=("X0", "Y0", "X1", "Y1"))
            cmd.add_argument("--note", required=True)
            cmd.add_argument("--permission-confirmed", action="store_true")
        elif name == "adopt":
            cmd.add_argument("--shot", required=True)
            cmd.add_argument("--source", type=Path, required=True)
            cmd.add_argument(
                "--operation",
                required=True,
                help="What was changed, e.g. 'native crop 0,90,984,732' or 'horizontal mirror'",
            )
            cmd.add_argument("--note", required=True)
            cmd.add_argument(
                "--from-version",
                type=int,
                help="Optional version this derivative was derived from",
            )
            cmd.add_argument(
                "--permission-confirmed",
                action="store_true",
                help="Attest that the source bytes are owned/authorized for this production",
            )
        elif name == "progress":
            cmd.add_argument(
                "--running-only",
                action="store_true",
                help="Only operations still marked running",
            )
            cmd.add_argument("--limit", type=int, help="Newest N receipts")
            cmd.add_argument(
                "--reconcile",
                action="store_true",
                help="Mark receipts whose owning process is provably gone as interrupted",
            )
        elif name == "shot-edit":
            cmd.add_argument("--shot", required=True)
            cmd.add_argument(
                "--transition",
                choices=["fade", "wipe_left", "wipe_right", "none"],
                help="Incoming transition for this shot (needs dissolve handle frames)",
            )
            cmd.add_argument(
                "--dissolve", type=int, help="Handle frames allocated to the incoming transition"
            )
            cmd.add_argument(
                "--camera",
                choices=["hold", "zoom_in", "zoom_out", "pan_left", "pan_right"],
            )
            cmd.add_argument(
                "--effect",
                action="append",
                default=[],
                metavar="KEY=VALUE",
                help="Bounded grade, e.g. contrast=1.05 (repeatable)",
            )
            cmd.add_argument("--clear-effects", action="store_true")
            cmd.add_argument("--note", required=True)
        elif name == "dashboard":
            cmd.add_argument(
                "--stage",
                choices=["board", "stills", "delivery"],
                default="board",
                help="Which review moment this page is for",
            )
            cmd.add_argument(
                "--no-embed-images",
                action="store_true",
                help="Reference stills relatively instead of embedding downscaled thumbnails",
            )
            cmd.add_argument(
                "--embed-audio",
                action="store_true",
                help="Embed the private source audio (larger file) instead of referencing it",
            )
            cmd.add_argument("--name", help="Explicit safe .html basename; never overwritten")
        elif name == "locate":
            when = cmd.add_mutually_exclusive_group(required=True)
            when.add_argument("--frame", type=int)
            when.add_argument("--seconds", type=float)
        elif name == "preflight":
            cmd.add_argument("--shots", help="Comma-separated shot IDs; default all")
        elif name == "import-lyrics":
            cmd.add_argument("file", type=Path)
        elif name == "skeleton":
            cmd.add_argument(
                "--seconds",
                type=float,
                help="Target hold: default 5s new-film adaptive, 8s older adaptive, 10s legacy",
            )
            cmd.add_argument(
                "--timing",
                choices=["adaptive", "beats", "events", "free"],
                help="Default adaptive for new presets, beats for legacy projects",
            )
            cmd.add_argument(
                "--min-seconds",
                type=float,
                help="Adaptive timing only; default 1.5s new-film, 4s older",
            )
            cmd.add_argument(
                "--max-seconds",
                type=float,
                help="Adaptive timing only; default 7s new-film, 12s older",
            )
        elif name == "prompts":
            cmd.add_argument("--shots", help="Comma-separated stable shot IDs; default all")
        elif name == "preview":
            cmd.add_argument(
                "--scope",
                choices=["proof", "available"],
                help="Default proof for new creative projects, available for legacy",
            )
        elif name == "backup":
            cmd.add_argument("--directory", type=Path, default=Path("backups"))
        elif name in ("quote-transcription", "quote-music"):
            if name == "quote-music":
                cmd.add_argument(
                    "--refine",
                    action="store_true",
                    help="Explicit new quoted pass; archive the existing unreviewed draft and use measured listening checkpoints",
                )
            if name == "quote-transcription":
                cmd.add_argument("--language")
                cmd.add_argument("--provider", choices=["runware", "openai"], default="runware")
            cmd.add_argument(
                "--reserve",
                default="0.05",
                help="Runware scope USD reservation, not an exact estimate or provider cap",
            )
            cmd.add_argument(
                "--model",
                default="google-gemini-3-1-flash-lite",
                help="Runware public model schema slug",
            )
            cmd.add_argument(
                "--max-tokens", type=int, default=8192, help="Runware output-token limit"
            )
        elif name == "quote":
            cmd.add_argument("--scope", choices=["proof", "stills"], default="proof")
            cmd.add_argument(
                "--reserve",
                required=True,
                help="Explicit per-shot USD reservation (not a provider cap)",
            )
            cmd.add_argument("--shots", help="Comma-separated stable shot IDs")
            cmd.add_argument(
                "--model",
                help="Explicit model schema slug override; otherwise use the stored production model",
            )
            cmd.add_argument("--regenerate", action="store_true")
        elif name in ("authorize", "transcribe", "generate", "listen"):
            cmd.add_argument("--quote", required=True)
            if name == "authorize":
                cmd.add_argument("--cap", required=True, help="USD allowance for this scoped quote")
                cmd.add_argument("--note", required=True)
            if name == "generate":
                cmd.add_argument("--concurrency", type=int, choices=[1, 2, 3], default=1)
        elif name == "recover":
            cmd.add_argument("--task", required=True)
        elif name == "resolve-task":
            cmd.add_argument("--task", required=True)
            cmd.add_argument(
                "--cost",
                required=True,
                help="User-verified billed USD amount, including 0 if uncharged",
            )
            cmd.add_argument(
                "--note",
                required=True,
                help="Provider-status/billing evidence reviewed by the user",
            )
        elif name == "select":
            cmd.add_argument("--shot", required=True)
            cmd.add_argument("--version", type=int, required=True)
        elif name == "sheet":
            cmd.add_argument("--scope", choices=["proof", "stills"], default="proof")
        elif name == "render":
            cmd.add_argument("--name", help="Optional new MP4 basename, no directories")
            cmd.add_argument(
                "--base-only",
                action="store_true",
                help="Render the base and prepare signature preflight; not a final delivery",
            )
    return p


#: Commands that only read project artifacts. They run without the exclusive
#: writer lock so monitoring and inspection keep working during a long render or
#: paid batch. Every artifact is written atomically (temp file + replace), so a
#: reader sees either the previous or the next complete document, never a partial
#: one. Anything that writes must stay out of this set.
READ_ONLY_COMMANDS = frozenset({"status", "progress", "costs", "locate", "preflight", "prompts"})


@contextlib.contextmanager
def _project_scope(root: Path, command: str):
    if command in READ_ONLY_COMMANDS:
        yield
    else:
        with project_lock(root):
            yield


def execute(args):
    if args.command == "style-test":
        from .calibration import approve_control, quote_control, recover_control, run_control

        if args.operation == "quote":
            return quote_control(args.directory, args.reserve)
        if args.operation == "run":
            return run_control(args.directory, args.quote, args.cap, args.note)
        if args.operation == "approve":
            return approve_control(args.directory, args.task, args.note)
        return recover_control(args.directory, args.task)
    if args.command == "doctor":
        return {
            "ffmpeg": shutil.which("ffmpeg"),
            "ffprobe": shutil.which("ffprobe"),
            "node": shutil.which("node"),
            "remotion_dependencies_installed": (
                Path(__file__).resolve().parents[2]
                / "renderers/remotion/node_modules/@remotion/renderer"
            ).is_dir(),
            "local_chrome": Path(
                os.environ.get(
                    "REMOTION_CHROME",
                    "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                )
            ).is_file(),
            "runware_key_environment_variable": RUNWARE_KEY_ENV,
            "project_RUNWARE_API_KEY_present": bool(os.environ.get(RUNWARE_KEY_ENV, "").strip()),
            "shared_RUNWARE_API_KEY_ignored": bool(os.environ.get("RUNWARE_API_KEY")),
            "OPENAI_API_KEY_present": bool(os.environ.get("OPENAI_API_KEY")),
        }
    if args.command == "spine":
        from . import spine

        with spine.connect(args.db) as conn:
            if args.operation == "status":
                return spine.status(conn)
            if args.operation == "runs":
                return {"runs": spine.run_list(conn, args.limit)}
            if args.operation == "events":
                return {"events": spine.event_list(conn, args.run, args.after, args.limit)}
            if args.operation == "trace":
                return spine.trace(conn, args.run)
            if args.operation == "resolve":
                return spine.resolve_human(
                    conn, args.interrupt, resolution={"note": args.note}
                )
            if args.operation == "sync":
                return spine.sync_operations(conn, args.projects_dir)
            return spine.reconcile(conn)
    if args.command == "plan":
        from . import plans

        if args.operation == "build":
            built = plans.build(args.project, intent=args.intent)
            target = plans.save(args.project, built)
            return {**built, "path": str(target.relative_to(args.project))}
        if args.operation == "list":
            return {"plans": plans.history(args.project)}
        if args.operation == "show":
            return plans.load(args.project, args.id)
        return plans.run(
            args.project,
            args.id,
            db=spine.resolve_db(args.db),
            allow_edit=args.allow_edit,
        )
    if args.command == "eval":
        from . import evals

        return evals.run(args.root)
    if args.command == "mcp":
        from . import mcp

        mcp.serve(args.projects_dir)
        return None
    if args.command == "serve":
        from . import serve, spine

        serve.serve(args.projects_dir, spine.resolve_db(args.db), port=args.port, token=args.token)
        return None
    if args.command == "intake":
        from .intake import build_intake

        return build_intake(output_dir=args.output_dir, name=args.name)
    if args.command == "studio":
        from .studio import build_studio

        return build_studio(args.projects_dir, output_dir=args.output_dir, name=args.name)
    if args.command == "schema":
        return {
            "brief": Brief,
            "lyrics": Lyrics,
            "storyboard": Storyboard,
            "events": EventMap,
            "brand": BrandPackage,
            "listening": ListeningDraft,
        }[args.kind].model_json_schema()
    root = args.project.resolve()
    if args.command == "init":
        slug = args.slug
        if slug is None:
            if not args.title or not args.title.strip():
                raise ValueError(
                    "choose a film --title (or explicit --slug), not the source filename"
                )
            slug = re.sub(r"[^a-z0-9]+", "-", args.title.casefold()).strip("-")[:64].rstrip("-")
            if not slug:
                raise ValueError("provide an explicit ASCII --slug for this film title")
            if root.name != slug:
                raise ValueError(
                    f"film title derives folder '{slug}'; use that project path or provide an explicit --slug"
                )
        native_size = (
            parse_native_size(args.native_size, args.aspect)
            if args.native_size is not None
            else None
        )
        image_settings = (
            json.loads(args.image_settings) if args.image_settings is not None else None
        )
        if args.image_settings is not None and not isinstance(image_settings, dict):
            raise ValueError("--image-settings must be a JSON object")
        project = production.init_project(
            root,
            args.mp3,
            slug,
            args.aspect,
            args.fps,
            args.music_mode,
            workflow_version=2 if args.workflow_version == 2 else None,
            image_model=args.model,
            image_settings=image_settings,
            image_seed=args.image_seed,
            style=args.style,
            native_size=native_size,
            title=args.title,
            renderer_backend=args.renderer,
        )
        return project.model_dump()
    if not root.is_dir():
        raise ValueError("production does not exist; use init first")
    with _project_scope(root, args.command):
        project = production.load_project(root)
        cmd = args.command
        if cmd == "budget":
            from . import budget

            if args.cap is None and (args.note is not None or args.max_corrections is not None):
                raise ValueError(
                    "--note/--max-corrections only apply with --cap; run plain `budget` to report"
                )
            if args.cap is not None:
                budget.set_budget(root, args.cap, args.note or "", args.max_corrections)
            return budget.summary(root)
        if cmd == "restage":
            from .budget import authorize_restaging

            ids = [token.strip() for token in args.shots.split(",")]
            known = {shot.id for shot in production.load_board(root).shots}
            if not ids or len(set(ids)) != len(ids) or not set(ids) <= known:
                raise ValueError(
                    "restage needs unique, known storyboard shot IDs (no padding, no typos)"
                )
            return authorize_restaging(root, ids, args.note)
        if cmd == "reference-import":
            from .references import import_reference

            return import_reference(
                root,
                args.source,
                note=args.note,
                permission_confirmed=args.permission_confirmed,
                box=args.crop,
            )
        if cmd == "review":
            from .reviews import record_review

            return record_review(
                root,
                args.shot,
                args.version,
                args.verdict,
                note=args.note,
                reviewer=args.reviewer,
                inspected=args.inspected,
            )
        if cmd == "preflight":
            from .preflight import manifest

            return manifest(root, args.shots.split(",") if args.shots else None)
        if cmd == "locate":
            from .timeline import label_at_frame, label_at_seconds

            board = production.load_board(root)
            label = (
                label_at_frame(board, args.frame)
                if args.frame is not None
                else label_at_seconds(board, args.seconds)
            )
            assets = read_json(root / "work/assets.json")
            entry = assets.get(label["owner_shot_id"], {})
            selected = next(
                (v for v in entry.get("versions", []) if v["version"] == entry.get("selected")), {}
            )
            return {
                **label,
                "selected_version": selected.get("version"),
                "selected_sha256": selected.get("sha256"),
                "note": "Current storyboard selection; not proof of bytes in a historical export.",
            }
        if cmd == "analyze":
            path = root / "work/music.json"
            result = None
            if path.exists() and not args.force:
                result = {"analysis": str(path), "reused": True}
            else:
                data = analyze(inside(root, project.source), project.duration)
                write_json(path, data)
                result = {
                    "analysis": str(path),
                    "duration": data["duration"],
                    "estimated_tempo_bpm": data["estimated_tempo_bpm"],
                    "sections": data["sections"],
                    "warnings": data["warnings"],
                }
            if getattr(args, "deep", False):
                # A separate artifact on purpose: the deep pass must never
                # silently rewrite the approved analysis, and it stays unreviewed
                # measurements. Local only, no provider call.
                from .deep_analysis import deep_analyze

                deep_path = root / "work/music-deep.json"
                deep = deep_analyze(inside(root, project.source), project.duration)
                write_json(deep_path, deep)
                result = {
                    **result,
                    "deep": str(deep_path),
                    "deep_analysis_version": deep["analysis_version"],
                    "deep_warnings": deep["warnings"],
                }
            return result
        if cmd == "status":
            return {**production.status(root), "operations": operations.summary(root)}
        if cmd == "progress":
            return operations.report(
                root,
                limit=args.limit,
                running_only=args.running_only,
                reconcile_stale=args.reconcile,
            )
        if cmd == "shot-edit":
            from .edits import UNSET, edit_shot

            return edit_shot(
                root,
                args.shot,
                note=args.note,
                transition=UNSET if args.transition is None else args.transition,
                dissolve=args.dissolve,
                camera=args.camera,
                effects=args.effect,
                clear_effects=args.clear_effects,
            )
        if cmd == "dashboard":
            from .dashboard import build_dashboard

            return build_dashboard(
                root,
                args.stage,
                embed_images=not args.no_embed_images,
                embed_audio=args.embed_audio,
                name=args.name,
            )
        if cmd == "context":
            from .context import build

            return build(
                root,
                stage=args.stage,
                shots=args.shots,
                include_prompts=args.include_prompts,
            )
        if cmd == "inspect":
            from .inspector import build_inspector

            return build_inspector(root, args.shot)
        if cmd == "adopt":
            return derivations.adopt_derivative(
                root,
                args.shot,
                args.source,
                operation=args.operation,
                note=args.note,
                permission_confirmed=args.permission_confirmed,
                from_version=args.from_version,
            )
        if cmd == "approve":
            production.approve(
                root, args.stage, args.note, args.ack_uncertain, inspected=args.inspected
            )
            return {"approved": args.stage}
        if cmd == "import-lyrics":
            lyrics = Lyrics.model_validate(read_json(args.file))
            previous = root / "work/lyrics.json"
            if previous.exists():
                value = read_json(previous)
                archive = root / f"work/lyrics-history/{digest(value)}.json"
                if not archive.exists():
                    write_json(archive, value)
            write_json(root / "work/lyrics.json", lyrics.model_dump())
            return {"imported": "lyrics", "segments": len(lyrics.segments), "approved": False}
        if cmd == "skeleton":
            timing = args.timing or ("adaptive" if project.image_model is not None else "beats")
            if timing != "adaptive" and (
                args.min_seconds is not None or args.max_seconds is not None
            ):
                raise ValueError("--min-seconds/--max-seconds only apply to --timing adaptive")
            new_film = project.prompt_version == 2
            min_seconds = (1.5 if new_film else 4) if args.min_seconds is None else args.min_seconds
            max_seconds = (7 if new_film else 12) if args.max_seconds is None else args.max_seconds
            target = (
                args.seconds
                if args.seconds is not None
                else ((5 if new_film else 8) if timing == "adaptive" else 10)
            )
            if not 1 <= target <= 30:
                raise ValueError("nominal storyboard duration must be 1–30 seconds")
            board = production.skeleton(
                root, target, timing, min_seconds=min_seconds, max_seconds=max_seconds
            )
            short = (
                timing == "adaptive"
                and len(board.shots) == 1
                and board.shots[0].duration_frames < math.ceil(Fraction(min_seconds) * project.fps)
            )
            notes = []
            if short:
                notes.append(
                    "Track is shorter than one minimum shot in output frames; retained the full track as one shot."
                )
            if timing == "adaptive":
                events_path = root / production.STAGE_FILES["events"]
                events = production.load_events(root).events if events_path.exists() else []
                ignored = sum(e.timing_basis != "manual" for e in events)
                if ignored:
                    notes.append(
                        f"Ignored {ignored} estimated event(s); only reviewed manual events get structural priority."
                    )
                if not any(e.timing_basis == "manual" for e in events):
                    notes.append(
                        "No reviewed manual event boundaries; using local measured changes/beat estimates, then target holds. Review this timing proposal."
                    )
            return {
                "shots": len(board.shots),
                "total_frames": board.total_frames,
                "warning": "Timing skeleton only; replace every TODO before approval",
                "timing": timing,
                "short_track_exception": short,
                "timing_notes": notes,
            }
        if cmd == "events":
            event_map = production.init_events(root)
            return {
                "events": str(root / "work/events.json"),
                "map": event_map.model_dump(),
                "approved": False,
            }
        if cmd == "prompts":
            board = production.load_board(root)
            ids = args.shots.split(",") if args.shots else [s.id for s in board.shots]
            if len(set(ids)) != len(ids) or not set(ids) <= {s.id for s in board.shots}:
                raise ValueError("unknown or duplicate shot IDs")
            return {
                "generated": False,
                "shots": [
                    {
                        "id": s.id,
                        "purpose": s.purpose,
                        "must_show": s.must_show,
                        "spec": production.image_spec(root, s),
                    }
                    for s in board.shots
                    if s.id in ids
                ],
            }
        if cmd == "preview":
            production.require_approval(root, "storyboard")
            board = production.load_board(root)
            brief = production.load_brief(root)
            scope = args.scope or ("proof" if brief.creative else "available")
            ids = (
                production.proof_ids(board, brief)
                if scope == "proof"
                else [s.id for s in board.shots]
            )
            if scope == "proof":
                proof_sources = set(ids)
                ids = [s.id for s in board.shots if (s.asset_shot_id or s.id) in proof_sources]
            available = []
            for shot_id in ids:
                try:
                    available.extend(production.resolved_assets(root, [shot_id]))
                except (ValueError, OSError):
                    pass  # Missing/stale stills are conspicuously labelled placeholders.
            directory = root / "previews"
            version = 1
            while (directory / f"animatic-v{version:03d}.mp4").exists():
                version += 1
            output = directory / f"animatic-v{version:03d}.mp4"
            with operations.operation(
                root,
                "preview",
                scope=scope,
                expected_outputs=[str(output.relative_to(root))],
                next_action=(
                    "watch the marked animatic with sound and decide; missing stills stay "
                    "labelled placeholders, and a proof-scope preview binds the review gate"
                ),
            ):
                report = build_preview(
                    root, project, board, available, output, root / "work/preview"
                )
            write_json(output.with_suffix(".json"), report)
            review_bound = False
            # New full-generation gate binds proof-only previews. Available-set
            # previews remain useful locally but never silently replace that gate.
            if scope == "proof" or brief.creative is None:
                try:
                    proof_hash = production.stage_hash(root, "proof")
                except (ValueError, OSError):
                    proof_hash = None
                if proof_hash:
                    write_json(
                        root / "work/preview-review.json",
                        {
                            "movie": str(output.relative_to(root)),
                            "movie_sha256": file_hash(output),
                            "storyboard_hash": production.preview_board_hash(root),
                            "proof_hash": proof_hash,
                            **(
                                {"brand_hash": brand_hash(root)}
                                if load_brand(root) is not None
                                else {}
                            ),
                            "input_hash": report["input_hash"],
                            **(
                                {"renderer_revision": report["renderer_revision"]}
                                if "renderer_revision" in report
                                else {}
                            ),
                        },
                    )
                    review_bound = True
            return {
                "output": str(output),
                "report": str(output.with_suffix(".json")),
                "placeholder_shots": report["placeholder_shots"],
                "actual_shots": report["actual_shots"],
                "review_bound": review_bound,
                "approved": False,
            }
        if cmd == "backup":
            from .backup import backup_project

            return backup_project(root, args.directory.resolve())
        if cmd == "quote-music":
            from .music_analysis import quote_music

            return quote_music(
                root,
                reserve=args.reserve,
                model=args.model,
                max_tokens=args.max_tokens,
                refine=args.refine,
            )
        if cmd == "listen":
            from .music_analysis import run_music

            return run_music(root, args.quote)
        if cmd == "music-map":
            from .music_map import write_music_map

            return write_music_map(root)
        if cmd == "quote-transcription":
            return generation.quote_transcription(
                root,
                args.language,
                provider=args.provider,
                reserve=args.reserve,
                model=args.model,
                max_tokens=args.max_tokens,
            )
        if cmd == "quote":
            return generation.quote_images(
                root,
                args.scope,
                args.reserve,
                args.model,
                args.shots.split(",") if args.shots else None,
                args.regenerate,
            )
        if cmd == "authorize":
            generation.authorize(root, args.quote, args.cap, args.note)
            return {"authorized_quote": args.quote, "generated": False}
        if cmd == "transcribe":
            result = generation.transcribe_quote(root, args.quote)
            if result is not None:
                return result
            return {"lyrics": str(root / "work/lyrics.json"), "approved": False}
        if cmd == "generate":
            # Read the quote first: an unknown/unauthorized quote must fail before a receipt exists.
            quote = generation.read_quote(root, args.quote)
            with operations.operation(
                root,
                "generate",
                scope=args.quote,
                expected_outputs=[],
                next_action=(
                    "inspect every new image version and record clip review verdicts; "
                    "recover unknown UUIDs by task ID — never resubmit them"
                ),
            ) as operation:
                operation.tick(done=0, total=len(quote["tasks"]), unit="images")
                generation.generate(root, args.quote, concurrency=args.concurrency)
            return {"scope_finished": args.quote, "approved": False}
        if cmd == "recover":
            return {"task": args.task, "recovered": generation.recover(root, args.task)}
        if cmd == "resolve-task":
            generation.resolve_task(root, args.task, args.cost, args.note)
            return {"reconciled": args.task, "submitted": False}
        if cmd == "select":
            production.select_asset(root, args.shot, args.version)
            return {"selected": args.shot, "version": args.version, "approved": False}
        if cmd == "sheet":
            board = production.load_board(root)
            ids = (
                production.proof_ids(board, production.load_brief(root))
                if args.scope == "proof"
                else None
            )
            shots = production.resolved_assets(root, ids)
            path = root / f"work/contact-sheet-{args.scope}.jpg"
            labels = None
            if project.workflow_version == 2:
                assets = read_json(root / "work/assets.json")
                labels, metadata = {}, []
                number = 0
                while True:
                    number += 1
                    path = root / f"work/contact-sheet-{args.scope}-v{number:03d}.jpg"
                    if not path.exists() and not path.with_suffix(".json").exists():
                        break
                for rs in shots:
                    shot = rs.shot
                    owner = shot.asset_shot_id or shot.id
                    entry = assets[owner]
                    selected = next(
                        v for v in entry["versions"] if v["version"] == entry["selected"]
                    )
                    end = shot.start_frame + shot.duration_frames
                    labels[shot.id] = [
                        f"frames {shot.start_frame}:{end} | owner {owner}",
                        f"v{selected['version']:03d} sha256 {selected['sha256'][:16]}",
                    ]
                    metadata.append(
                        {
                            "id": shot.id,
                            "owner_shot_id": owner,
                            "start_frame": shot.start_frame,
                            "end_frame": end,
                            "version": selected["version"],
                            "sha256": selected["sha256"],
                            "path": selected["path"],
                            "input_hash": selected["input_hash"],
                        }
                    )
                write_json(path.with_suffix(".json"), {"reviewed": False, "shots": metadata})
            contact_sheet(shots, path, labels=labels)
            return {"contact_sheet": str(path), "shots": len(shots)}
        if cmd == "render":
            production.require_approval(root, "stills")
            shots = production.resolved_assets(root)
            directory = root / "renders"
            if args.name:
                if not re.fullmatch(r"[a-zA-Z0-9_-]+\.mp4", args.name):
                    raise ValueError("render name must be a safe .mp4 basename")
                name = args.name
            else:
                version = 1
                prefix = (
                    f"{project.slug}-{'base' if args.base_only else 'stills'}"
                    if project.signature_required
                    else "stills"
                )
                while (directory / f"{prefix}-v{version:03d}.mp4").exists():
                    version += 1
                name = f"{prefix}-v{version:03d}.mp4"
            scope = "base-only" if args.base_only else "final-composite"
            with operations.operation(
                root,
                "render",
                scope=scope,
                expected_outputs=[f"renders/{name}"],
                next_action=(
                    "the base is not delivery: inspect the composited graphics samples, record the "
                    "graphics decision, then render the final composite"
                    if project.signature_required and args.base_only
                    else "inspect the export report, samples and audio before delivery"
                ),
            ):
                if project.signature_required and not args.base_only:
                    from .graphics import compose
                    from .signature import validate_review

                    production.require_approval(root, "graphics")
                    review = validate_review(root, project)
                    report = compose(root, inside(root, review["base"]), directory / name)
                    report["delivery_ready"] = True
                    report["graphics_approval_hash"] = production.stage_hash(root, "graphics")
                    write_json(directory / name.replace(".mp4", ".json"), report)
                    return report
                report = render(
                    project,
                    shots,
                    inside(root, project.source),
                    directory / name,
                    root / "work",
                    brand=load_brand(root),
                )
                from .signature import current_input_hash

                report["input_hash"] = current_input_hash(root)
                if project.signature_required:
                    from .signature import prepare_review

                    report["delivery_ready"] = False
                    write_json(directory / name.replace(".mp4", ".json"), report)
                    report["graphics_review"] = prepare_review(root, directory / name, project)
                write_json(directory / name.replace(".mp4", ".json"), report)
            return report
        if cmd == "costs":
            return generation.costs(root)
        raise ValueError("unknown command")


def main():
    args = parser().parse_args()
    try:
        result = execute(args)
    except (OSError, ValueError, RuntimeError, KeyError) as e:
        # No raw provider payloads or credential-bearing URLs are printed.
        if isinstance(e, KeyError):
            message = "artifact/provider contract is missing required fields"
        else:
            message = str(e)
        print(f"Error: {message}", file=sys.stderr)
        return 1
    if result is not None:  # long-running transports own stdout
        print(json.dumps(result, indent=2, allow_nan=False))
    return 0
