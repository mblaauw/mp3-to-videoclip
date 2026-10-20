"""Plan objects: the unit of work an agent proposes and a human authorises.

A plan is data, not prose: ordered steps, the command each step runs, whether it needs
a human decision or missing input, and what it would invalidate. Building a plan costs
nothing and changes nothing; running one executes concrete local steps through the
durable spine and **stops** at the first human decision or placeholder instead of
guessing.

This is the grammar the app and the agent share: intent → plan → approval → run →
evidence.
"""

from __future__ import annotations

import shlex
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from . import spine, studio, tools
from .storage import file_hash, read_json, write_json

FOLDER = "work/plans"
HUMAN_COMMANDS = frozenset({"approve", "authorize", "resolve-task"})


def _id() -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    return f"plan-{stamp}-{uuid4().hex[:6]}"


def _argv(command: str) -> list[str] | None:
    """Concrete argv, or ``None`` when the command is a template needing a human."""
    if "<" in command or ">" in command:
        return None
    try:
        parts = shlex.split(command)
    except ValueError:
        return None
    if not parts or parts[0] in {"uv", "python", "python3"}:
        return parts or None
    return parts


def _step(command: str, label: str, reason: str, *, invalidates=()) -> dict:
    argv = _argv(command)
    tool = None
    if argv:
        try:
            tool = tools.classify_argv(argv)
        except ValueError:
            tool = None
    scope = tools.scope_for(tool) if tool else {"kind": "edit"}
    human = (
        scope["kind"] == "human"
        or tool in HUMAN_COMMANDS
        or (tool == "budget" and "--cap" in (argv or []))
    )
    needs_input = argv is None
    return {
        "label": label,
        "reason": reason,
        "command": command,
        "tool": tool,
        "kind": scope["kind"],
        "human": bool(human),
        "needs_input": needs_input,
        "invalidates": list(invalidates),
        "status": "pending",
    }


def build(root: Path, *, intent: str | None = None) -> dict:
    """Turn a production's open actions into a plan. Records nothing, runs nothing."""
    root = Path(root)
    entry = studio.scan_project(root)
    if entry is None:
        raise ValueError("not a production: missing project.json")
    steps = []
    for action in entry["actions"]:
        if action.get("href") or not action.get("command"):
            continue
        invalidates = ()
        if action["id"].startswith(("approve-", "edit")):
            invalidates = ("storyboard", "proof", "preview", "stills", "graphics")
        steps.append(
            _step(action["command"], action["label"], action["reason"], invalidates=invalidates)
        )
    plan = {
        "schema_version": 1,
        "id": _id(),
        "production": root.name,
        "intent": intent or f"advance {root.name} from {entry['next_step']}",
        "created_at": datetime.now(UTC).isoformat(),
        "inputs": {
            "project": file_hash(root / "project.json"),
            "storyboard": file_hash(root / "work/storyboard.json")
            if (root / "work/storyboard.json").is_file()
            else None,
        },
        "steps": steps,
        "blocked_by": [step["label"] for step in steps if step["human"] or step["needs_input"]],
        "executable": [
            step["label"] for step in steps if not step["human"] and not step["needs_input"]
        ],
        "warning": (
            "A plan changes nothing until it is run. Human decisions and placeholder inputs stop "
            "execution and open a durable wait; nothing here authorises spending."
        ),
    }
    return plan


def save(root: Path, plan: dict) -> Path:
    root = Path(root)
    if not plan.get("id") or not plan.get("steps"):
        raise ValueError("a plan needs an id and at least one step")
    target = root / FOLDER / f"{plan['id']}.json"
    if target.exists():
        raise ValueError("plans are immutable; build a new one")
    write_json(target, plan)
    return target


def load(root: Path, plan_id: str) -> dict:
    path = Path(root) / FOLDER / f"{plan_id}.json"
    if not path.is_file():
        raise ValueError(f"unknown plan {plan_id!r}")
    return read_json(path)


def history(root: Path) -> list[dict]:
    folder = Path(root) / FOLDER
    if not folder.is_dir():
        return []
    plans = []
    for path in sorted(folder.glob("plan-*.json"), reverse=True):
        record = read_json(path)
        plans.append(
            {
                "id": record.get("id"),
                "intent": record.get("intent"),
                "created_at": record.get("created_at"),
                "steps": len(record.get("steps") or []),
                "blocked_by": record.get("blocked_by") or [],
                "executable": len(record.get("executable") or []),
            }
        )
    return plans


def run(
    root: Path,
    plan_id: str,
    *,
    db: str | Path | None = None,
    cwd: str | Path | None = None,
    allow_edit: bool = False,
) -> dict:
    """Execute the concrete steps in order, stopping at the first human decision.

    ``allow_edit`` is explicit: without it, steps that would change canonical artifacts
    stop the run like a human decision, so an unattended caller cannot edit canon.
    """
    root = Path(root)
    plan = load(root, plan_id)
    granted = set(tools.DELEGATED_AGENT_KINDS) if allow_edit else set(tools.DEFAULT_AGENT_KINDS)
    executed, stopped = [], None
    with spine.connect(db) as conn:
        run_id = spine.start_run(
            conn, intent=plan["intent"], production=plan.get("production") or root.name, plan=plan
        )
        for index, step in enumerate(plan["steps"]):
            if step.get("needs_input"):
                interrupt = spine.ask_human(
                    conn,
                    run_id,
                    kind="input",
                    payload={"step": index, "command": step["command"], "reason": step["reason"]},
                )
                stopped = {**step, "why": "needs input", "interrupt": interrupt}
                break
            if step.get("human"):
                interrupt = spine.ask_human(
                    conn,
                    run_id,
                    kind="approval",
                    payload={"step": index, "command": step["command"], "reason": step["reason"]},
                )
                stopped = {**step, "why": "human decision", "interrupt": interrupt}
                break
            try:
                if step.get("tool"):
                    tools.require(step["tool"], granted)
            except PermissionError as exc:
                interrupt = spine.ask_human(
                    conn,
                    run_id,
                    kind="capability",
                    payload={"step": index, "command": step["command"], "reason": str(exc)},
                )
                stopped = {**step, "why": str(exc), "interrupt": interrupt}
                break
            argv = _argv(step["command"])
            if argv is None:
                interrupt = spine.ask_human(
                    conn,
                    run_id,
                    kind="input",
                    payload={"step": index, "command": step["command"]},
                )
                stopped = {**step, "why": "unparseable command", "interrupt": interrupt}
                break
            result = spine.run_command(
                conn,
                argv,
                production=root.name,
                intent=step["label"],
                cwd=cwd or Path.cwd(),
            )
            executed.append(
                {
                    "label": step["label"],
                    "run_id": result["run_id"],
                    "returncode": result["returncode"],
                    "replayed": result.get("replayed", False),
                    "seconds": result.get("seconds"),
                }
            )
            if result["returncode"] != 0:
                spine.finish_run(
                    conn, run_id, "failed", f"{step['label']} exited {result['returncode']}"
                )
                return {
                    "plan": plan_id,
                    "run_id": run_id,
                    "status": "failed",
                    "executed": executed,
                    "failed_step": step["label"],
                }
        else:
            spine.finish_run(conn, run_id, "succeeded")
            return {
                "plan": plan_id,
                "run_id": run_id,
                "status": "succeeded",
                "executed": executed,
                "stopped_at": None,
            }
        return {
            "plan": plan_id,
            "run_id": run_id,
            "status": "waiting",
            "executed": executed,
            "stopped_at": stopped,
            "note": "The plan is waiting for a human. Resolve or run the printed command; nothing retries.",
        }
