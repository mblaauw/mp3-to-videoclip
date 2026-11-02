"""Engine tasks with no screen yet. Every human decision and every other stage is in the Studio."""

import argparse
import contextlib
import json
import os
import shutil
import sys
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from . import derivations, generation, operations, production
from .models import BrandPackage, Brief, EventMap, ListeningDraft, Lyrics, Storyboard
from .providers import RUNWARE_KEY_ENV
from .storage import project_lock

SCHEMAS = {
    "brief": Brief,
    "lyrics": Lyrics,
    "storyboard": Storyboard,
    "events": EventMap,
    "brand": BrandPackage,
    "listening": ListeningDraft,
}


def _doctor(_args) -> dict:
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


def _schema(args) -> dict:
    return SCHEMAS[args.kind].model_json_schema()


def _backup(args, root: Path):
    from .backup import backup_project

    return backup_project(root, args.directory.resolve())


def _quote_transcription(args, root: Path):
    return generation.quote_transcription(
        root,
        args.language,
        provider=args.provider,
        reserve=args.reserve,
        model=args.model,
        max_tokens=args.max_tokens,
    )


def _transcribe(args, root: Path):
    result = generation.transcribe_quote(root, args.quote)
    if result is not None:
        return result
    return {"lyrics": str(root / "work/lyrics.json"), "approved": False}


def _quote_music(args, root: Path):
    from .music_analysis import quote_music

    return quote_music(
        root,
        reserve=args.reserve,
        model=args.model,
        max_tokens=args.max_tokens,
        refine=args.refine,
    )


def _listen(args, root: Path):
    from .music_analysis import run_music

    return run_music(root, args.quote)


def _music_map(_args, root: Path):
    from .music_map import write_music_map

    return write_music_map(root)


def _recover(args, root: Path):
    return {"task": args.task, "recovered": generation.recover(root, args.task)}


def _resolve_task(args, root: Path):
    generation.resolve_task(root, args.task, args.cost, args.note)
    return {"reconciled": args.task, "submitted": False}


def _restage(args, root: Path):
    from .budget import authorize_restaging

    ids = [token.strip() for token in args.shots.split(",")]
    known = {shot.id for shot in production.load_board(root).shots}
    if not ids or len(set(ids)) != len(ids) or not set(ids) <= known:
        raise ValueError("restage needs unique, known storyboard shot IDs (no padding, no typos)")
    return authorize_restaging(root, ids, args.note)


def _reference_import(args, root: Path):
    from .references import import_reference

    return import_reference(
        root,
        args.source,
        note=args.note,
        permission_confirmed=args.permission_confirmed,
        box=args.crop,
    )


def _adopt(args, root: Path):
    return derivations.adopt_derivative(
        root,
        args.shot,
        args.source,
        operation=args.operation,
        note=args.note,
        permission_confirmed=args.permission_confirmed,
        from_version=args.from_version,
    )


def _progress(args, root: Path):
    return operations.report(
        root,
        limit=args.limit,
        running_only=args.running_only,
        reconcile_stale=args.reconcile,
    )


def _args_schema(cmd) -> None:
    cmd.add_argument("kind", choices=sorted(SCHEMAS))


def _args_backup(cmd) -> None:
    cmd.add_argument("--directory", type=Path, default=Path("backups"))


def _hosted_args(cmd) -> None:
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
    cmd.add_argument("--max-tokens", type=int, default=8192, help="Runware output-token limit")


def _args_quote_transcription(cmd) -> None:
    cmd.add_argument("--language")
    cmd.add_argument("--provider", choices=["runware", "openai"], default="runware")
    _hosted_args(cmd)


def _args_quote_music(cmd) -> None:
    cmd.add_argument(
        "--refine",
        action="store_true",
        help="Explicit new quoted pass; archive the existing unreviewed draft and use measured listening checkpoints",
    )
    _hosted_args(cmd)


def _args_quote(cmd) -> None:
    cmd.add_argument("--quote", required=True)


def _args_recover(cmd) -> None:
    cmd.add_argument("--task", required=True)


def _args_resolve_task(cmd) -> None:
    cmd.add_argument("--task", required=True)
    cmd.add_argument(
        "--cost", required=True, help="User-verified billed USD amount, including 0 if uncharged"
    )
    cmd.add_argument(
        "--note", required=True, help="Provider-status/billing evidence reviewed by the user"
    )


def _args_restage(cmd) -> None:
    cmd.add_argument("--shots", required=True)
    cmd.add_argument("--note", required=True)


def _args_reference_import(cmd) -> None:
    cmd.add_argument("--source", type=Path, required=True)
    cmd.add_argument("--crop", nargs=4, type=int, metavar=("X0", "Y0", "X1", "Y1"))
    cmd.add_argument("--note", required=True)
    cmd.add_argument("--permission-confirmed", action="store_true")


def _args_adopt(cmd) -> None:
    cmd.add_argument("--shot", required=True)
    cmd.add_argument("--source", type=Path, required=True)
    cmd.add_argument(
        "--operation",
        required=True,
        help="What was changed, e.g. 'native crop 0,90,984,732' or 'horizontal mirror'",
    )
    cmd.add_argument("--note", required=True)
    cmd.add_argument(
        "--from-version", type=int, help="Optional version this derivative was derived from"
    )
    cmd.add_argument(
        "--permission-confirmed",
        action="store_true",
        help="Attest that the source bytes are owned/authorized for this production",
    )


def _args_progress(cmd) -> None:
    cmd.add_argument(
        "--running-only", action="store_true", help="Only operations still marked running"
    )
    cmd.add_argument("--limit", type=int, help="Newest N receipts")
    cmd.add_argument(
        "--reconcile",
        action="store_true",
        help="Mark receipts whose owning process is provably gone as interrupted",
    )


@dataclass(frozen=True)
class Command:
    help: str
    run: Callable
    arguments: Callable | None = None
    #: "none" needs no film. "read" takes no writer lock, so monitoring works during a long render
    #: or paid batch; every artifact is written atomically, so a reader never sees half of one.
    scope: str = "write"


COMMANDS = {
    "doctor": Command("Show tool/credential availability without values", _doctor, scope="none"),
    "schema": Command("Print editable artifact JSON schemas", _schema, _args_schema, "none"),
    "backup": Command(
        "Save a private local production archive, excluding rebuildable plate caches",
        _backup,
        _args_backup,
    ),
    "quote-transcription": Command(
        "Estimate hosted transcription cost without uploading",
        _quote_transcription,
        _args_quote_transcription,
    ),
    "transcribe": Command(
        "PAID UPLOAD: submit an authorized transcription exactly once", _transcribe, _args_quote
    ),
    "quote-music": Command(
        "Quote a tracked, audio-blind musical listening pass (no upload)",
        _quote_music,
        _args_quote_music,
    ),
    "listen": Command(
        "PAID UPLOAD: execute the authorized musical listening quote", _listen, _args_quote
    ),
    "music-map": Command(
        "Build an unreviewed combined listening/measurement map locally", _music_map
    ),
    "recover": Command(
        "Recover/download a previously submitted task, never resubmit", _recover, _args_recover
    ),
    "resolve-task": Command(
        "Record user-verified billing/status for an ambiguous submission",
        _resolve_task,
        _args_resolve_task,
    ),
    "restage": Command(
        "Record diagnosis/restaging authority for another correction cycle; no spend",
        _restage,
        _args_restage,
    ),
    "reference-import": Command(
        "Import a permission-confirmed immutable local reference; no upload",
        _reference_import,
        _args_reference_import,
    ),
    "adopt": Command(
        "Record an inspected local derivative (crop/mirror/tone) as a new image version",
        _adopt,
        _args_adopt,
    ),
    "progress": Command(
        "Monitor local operations from their durable receipts; never approves or spends",
        _progress,
        _args_progress,
        "read",
    ),
}


def parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Engine tasks with no screen yet. Everything else is `uv run studio`."
    )
    commands = p.add_subparsers(dest="command", required=True)
    for name, command in COMMANDS.items():
        cmd = commands.add_parser(name, help=command.help)
        if command.scope == "none":
            cmd.set_defaults(project=None)
        else:
            cmd.add_argument("project", type=Path)
        if command.arguments is not None:
            command.arguments(cmd)
    return p


@contextlib.contextmanager
def _project_scope(root: Path, command: str):
    if COMMANDS[command].scope == "read":
        yield
    else:
        with project_lock(root):
            yield


def execute(args):
    command = COMMANDS[args.command]
    if command.scope == "none":
        return command.run(args)
    root = args.project.resolve()
    if not root.is_dir():
        raise ValueError("that production does not exist; make it in the Studio")
    with _project_scope(root, args.command):
        production.load_project(root)
        return command.run(args, root)


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
