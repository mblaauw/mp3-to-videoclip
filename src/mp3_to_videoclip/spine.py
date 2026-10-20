"""Durable run spine: a replayable journal for every command the studio starts.

The spine is **not** canonical state. Artifacts stay the source of truth; this is a
rebuildable index of what was attempted, what it produced and what a human still
has to decide. Deleting the database must always be safe.

Semantics implemented here (the part that makes an app agentic rather than chatty):

* one run per intent, one step per tool invocation;
* an idempotency key per side effect, so a replay never repeats work or a charge;
* a lease per run, so a crashed owner is reported instead of silently re-run;
* append-only events, so a UI can tail a live run and a trace can be rebuilt later;
* durable human waits, with no timeout and no implied consent.
"""

from __future__ import annotations

import json
import os
import socket
import sqlite3
import subprocess
import time
from contextlib import contextmanager
from datetime import UTC, datetime
from hashlib import sha256
from pathlib import Path
from uuid import uuid4

DB = "studio/spine.sqlite3"
MAX_EVENTS_PER_RUN = 4000
MAX_OUTPUT_LINES = 400

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY,
  production TEXT,
  intent TEXT NOT NULL,
  plan_json TEXT,
  status TEXT NOT NULL,
  pid INTEGER,
  host TEXT,
  lease_heartbeat TEXT,
  error TEXT,
  created_at TEXT NOT NULL,
  ended_at TEXT
);
CREATE TABLE IF NOT EXISTS steps (
  run_id TEXT NOT NULL,
  idx INTEGER NOT NULL,
  name TEXT NOT NULL,
  capability TEXT,
  args_json TEXT,
  status TEXT NOT NULL,
  output_json TEXT,
  error TEXT,
  started_at TEXT,
  ended_at TEXT,
  PRIMARY KEY (run_id, idx)
);
CREATE TABLE IF NOT EXISTS tool_calls (
  id TEXT PRIMARY KEY,
  run_id TEXT,
  step_idx INTEGER,
  tool TEXT NOT NULL,
  args_json TEXT NOT NULL,
  idempotency_key TEXT NOT NULL UNIQUE,
  status TEXT NOT NULL,
  result_json TEXT,
  cost_usd TEXT,
  created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS interrupts (
  id TEXT PRIMARY KEY,
  run_id TEXT NOT NULL,
  kind TEXT NOT NULL,
  payload_json TEXT,
  status TEXT NOT NULL,
  created_at TEXT NOT NULL,
  resolved_at TEXT,
  resolution_json TEXT
);
CREATE TABLE IF NOT EXISTS events (
  seq INTEGER PRIMARY KEY AUTOINCREMENT,
  run_id TEXT,
  type TEXT NOT NULL,
  step_idx INTEGER,
  payload_json TEXT,
  at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS events_run ON events(run_id, seq);
CREATE INDEX IF NOT EXISTS runs_status ON runs(status, created_at);
"""


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _id(prefix: str) -> str:
    return f"{prefix}_{datetime.now(UTC).strftime('%Y%m%dT%H%M%S')}_{uuid4().hex[:8]}"


def resolve_db(path: str | Path | None = None) -> Path:
    return Path(path) if path else Path(DB)


@contextmanager
def connect(path: str | Path | None = None):
    """Open the spine in WAL mode; create the schema on first use."""
    target = resolve_db(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target, timeout=10)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.executescript(SCHEMA)
        yield conn
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# writes
# --------------------------------------------------------------------------- #
def append_event(conn, run_id, type_, payload=None, step=None) -> int:
    count = conn.execute("SELECT COUNT(*) FROM events WHERE run_id = ?", (run_id,)).fetchone()[0]
    if count >= MAX_EVENTS_PER_RUN:
        return -1
    cursor = conn.execute(
        "INSERT INTO events(run_id, type, step_idx, payload_json, at) VALUES (?,?,?,?,?)",
        (run_id, type_, step, json.dumps(payload or {}, default=str), _now()),
    )
    conn.commit()
    return int(cursor.lastrowid)


def start_run(conn, *, intent, production=None, plan=None, pid=None) -> str:
    run_id = _id("run")
    conn.execute(
        "INSERT INTO runs(id, production, intent, plan_json, status, pid, host, "
        "lease_heartbeat, created_at) VALUES (?,?,?,?,?,?,?,?,?)",
        (
            run_id,
            production,
            str(intent),
            json.dumps(plan, default=str) if plan is not None else None,
            "running",
            pid if pid is not None else os.getpid(),
            socket.gethostname(),
            _now(),
            _now(),
        ),
    )
    conn.commit()
    append_event(conn, run_id, "run.started", {"intent": intent, "production": production})
    return run_id


def heartbeat(conn, run_id) -> None:
    conn.execute("UPDATE runs SET lease_heartbeat = ? WHERE id = ?", (_now(), run_id))
    conn.commit()


def finish_run(conn, run_id, status="succeeded", error=None) -> None:
    conn.execute(
        "UPDATE runs SET status = ?, error = ?, ended_at = ? WHERE id = ?",
        (status, error, _now(), run_id),
    )
    conn.commit()
    append_event(conn, run_id, f"run.{status}", {"error": error} if error else {})


def begin_step(conn, run_id, idx, name, *, capability=None, args=None, key=None):
    """Return ``(replay, cached_output)``.

    A step whose idempotency key already succeeded is never executed twice: the
    caller gets the recorded output and the run continues from the journal.
    """
    args_json = json.dumps(args or {}, sort_keys=True, default=str)
    idempotency = key or sha256(f"{run_id}:{idx}:{name}:{args_json}".encode()).hexdigest()
    row = conn.execute(
        "SELECT status, result_json FROM tool_calls WHERE idempotency_key = ?", (idempotency,)
    ).fetchone()
    if row and row["status"] == "succeeded":
        conn.execute(
            "INSERT OR REPLACE INTO steps(run_id, idx, name, capability, args_json, status, "
            "output_json, started_at, ended_at) VALUES (?,?,?,?,?,?,?,?,?)",
            (
                run_id,
                idx,
                name,
                capability,
                args_json,
                "replayed",
                row["result_json"],
                _now(),
                _now(),
            ),
        )
        conn.commit()
        append_event(conn, run_id, "step.replayed", {"name": name}, idx)
        return True, json.loads(row["result_json"]) if row["result_json"] else {}
    conn.execute(
        "INSERT OR REPLACE INTO steps(run_id, idx, name, capability, args_json, status, started_at) "
        "VALUES (?,?,?,?,?,?,?)",
        (run_id, idx, name, capability, args_json, "running", _now()),
    )
    conn.execute(
        "INSERT OR REPLACE INTO tool_calls(id, run_id, step_idx, tool, args_json, "
        "idempotency_key, status, created_at) VALUES (?,?,?,?,?,?,?,?)",
        (_id("tc"), run_id, idx, name, args_json, idempotency, "running", _now()),
    )
    conn.commit()
    append_event(conn, run_id, "step.started", {"name": name, "args": args}, idx)
    return False, None


def finish_step(
    conn, run_id, idx, *, status="succeeded", output=None, error=None, key=None, cost=None
) -> None:
    output_json = json.dumps(output, default=str) if output is not None else None
    conn.execute(
        "UPDATE steps SET status=?, output_json=?, error=?, ended_at=? WHERE run_id=? AND idx=?",
        (status, output_json, error, _now(), run_id, idx),
    )
    if key:
        conn.execute(
            "UPDATE tool_calls SET status=?, result_json=?, cost_usd=? WHERE idempotency_key=?",
            (status, output_json, cost, key),
        )
    else:
        conn.execute(
            "UPDATE tool_calls SET status=?, result_json=?, cost_usd=? WHERE run_id=? AND step_idx=?",
            (status, output_json, cost, run_id, idx),
        )
    conn.commit()
    append_event(conn, run_id, f"step.{status}", {"error": error} if error else {}, idx)


def ask_human(conn, run_id, *, kind, payload=None) -> str:
    """A durable wait: recorded, never timed out, never treated as consent."""
    interrupt_id = _id("int")
    conn.execute(
        "INSERT INTO interrupts(id, run_id, kind, payload_json, status, created_at) "
        "VALUES (?,?,?,?,?,?)",
        (interrupt_id, run_id, kind, json.dumps(payload or {}, default=str), "open", _now()),
    )
    conn.execute("UPDATE runs SET status='waiting' WHERE id=? AND status='running'", (run_id,))
    conn.commit()
    append_event(conn, run_id, "interrupt.opened", {"kind": kind, **(payload or {})})
    return interrupt_id


def resolve_human(conn, interrupt_id, *, resolution=None) -> dict:
    """Record a human decision. A run is marked ``resolved``, never silently completed."""
    row = conn.execute("SELECT run_id, status FROM interrupts WHERE id=?", (interrupt_id,)).fetchone()
    if row is None:
        raise ValueError(f"unknown interrupt {interrupt_id!r}")
    if row["status"] != "open":
        raise ValueError("that wait is already resolved")
    conn.execute(
        "UPDATE interrupts SET status='resolved', resolved_at=?, resolution_json=? WHERE id=?",
        (_now(), json.dumps(resolution or {}, default=str), interrupt_id),
    )
    conn.commit()
    append_event(conn, row["run_id"], "interrupt.resolved", {"resolution": resolution})
    remaining = conn.execute(
        "SELECT COUNT(*) FROM interrupts WHERE run_id=? AND status='open'", (row["run_id"],)
    ).fetchone()[0]
    if remaining == 0:
        conn.execute(
            "UPDATE runs SET status='resolved', ended_at=? WHERE id=? AND status='waiting'",
            (_now(), row["run_id"]),
        )
        conn.commit()
        append_event(
            conn,
            row["run_id"],
            "run.resolved",
            {"note": "human answered; remaining steps need a new run"},
        )
    return {
        "interrupt": interrupt_id,
        "run_id": row["run_id"],
        "remaining_waits": remaining,
        "next": "run the printed command, then rebuild the plan; a resolution is not an execution",
    }


# --------------------------------------------------------------------------- #
# the command runner
# --------------------------------------------------------------------------- #
def run_command(
    conn,
    argv: list[str],
    *,
    production: str | None = None,
    intent: str | None = None,
    cwd: str | Path | None = None,
    idempotency_key: str | None = None,
    env: dict | None = None,
    timeout: float | None = None,
) -> dict:
    """Run one local command as a durable, replayable step.

    The command is executed exactly once per idempotency key. A replay returns the
    recorded result with ``replayed: True`` and performs no side effect.
    """
    if not isinstance(argv, list) or not argv or not all(isinstance(arg, str) for arg in argv):
        raise ValueError("run_command needs a non-empty argv list of strings")
    key = (
        idempotency_key
        or sha256(
            json.dumps({"argv": argv, "production": production}, sort_keys=True).encode()
        ).hexdigest()
    )
    prior = conn.execute(
        "SELECT status, result_json FROM tool_calls WHERE idempotency_key=?", (key,)
    ).fetchone()
    if prior and prior["status"] == "succeeded":
        return {
            **(json.loads(prior["result_json"]) if prior["result_json"] else {}),
            "replayed": True,
        }

    run_id = start_run(
        conn,
        intent=intent or " ".join(argv[:3]),
        production=production,
        plan={"argv": argv},
    )
    replay, _ = begin_step(
        conn, run_id, 0, "command", capability="execute-local", args={"argv": argv}, key=key
    )
    if replay:  # defensive: begin_step already handled an identical key
        finish_run(conn, run_id)
        return {"run_id": run_id, "replayed": True, "returncode": 0}

    lines: list[str] = []
    started = time.monotonic()
    try:
        process = subprocess.Popen(
            argv,
            cwd=str(cwd) if cwd else None,
            env={**os.environ, **(env or {})},
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
        )
        append_event(conn, run_id, "command.spawned", {"argv": argv, "pid": process.pid})
        deadline = started + timeout if timeout else None
        assert process.stdout is not None
        for line in process.stdout:
            lines.append(line.rstrip("\n"))
            if len(lines) <= MAX_OUTPUT_LINES:
                append_event(conn, run_id, "command.output", {"line": line.rstrip("\n")})
            if deadline and time.monotonic() > deadline:
                process.terminate()
                raise TimeoutError(f"command exceeded {timeout}s")
            if len(lines) % 25 == 0:
                heartbeat(conn, run_id)
        code = process.wait(timeout=30 if timeout else None)
    except Exception as exc:
        finish_step(conn, run_id, 0, status="failed", error=str(exc), key=key)
        finish_run(conn, run_id, "failed", str(exc))
        raise

    tail = "\n".join(lines[-40:])
    result = {
        "run_id": run_id,
        "returncode": code,
        "seconds": round(time.monotonic() - started, 2),
        "output_tail": tail,
        "lines": len(lines),
        "replayed": False,
    }
    status = "succeeded" if code == 0 else "failed"
    finish_step(
        conn,
        run_id,
        0,
        status=status,
        output=result,
        error=None if code == 0 else tail[-2000:],
        key=key,
    )
    finish_run(conn, run_id, status, None if code == 0 else f"exit {code}")
    return result


# --------------------------------------------------------------------------- #
# reads
# --------------------------------------------------------------------------- #
def rows(conn, sql, params=()) -> list[dict]:
    return [dict(row) for row in conn.execute(sql, params).fetchall()]


def run_list(conn, limit=20) -> list[dict]:
    runs = rows(conn, "SELECT * FROM runs ORDER BY created_at DESC LIMIT ?", (limit,))
    for run in runs:
        run["steps"] = rows(
            conn,
            "SELECT idx, name, status, error FROM steps WHERE run_id=? ORDER BY idx",
            (run["id"],),
        )
        run["open_interrupts"] = conn.execute(
            "SELECT COUNT(*) FROM interrupts WHERE run_id=? AND status='open'", (run["id"],)
        ).fetchone()[0]
    return runs


def event_list(conn, run_id=None, after=0, limit=200) -> list[dict]:
    if run_id:
        return rows(
            conn,
            "SELECT * FROM events WHERE run_id=? AND seq>? ORDER BY seq LIMIT ?",
            (run_id, after, limit),
        )
    return rows(conn, "SELECT * FROM events WHERE seq>? ORDER BY seq LIMIT ?", (after, limit))


def status(conn) -> dict:
    counts = {
        row["status"]: row["n"]
        for row in conn.execute("SELECT status, COUNT(*) AS n FROM runs GROUP BY status")
    }
    return {
        "db": str(conn.execute("PRAGMA database_list").fetchone()["file"]),
        "runs": counts,
        "open_interrupts": conn.execute(
            "SELECT COUNT(*) FROM interrupts WHERE status='open'"
        ).fetchone()[0],
        "steps": conn.execute("SELECT COUNT(*) FROM steps").fetchone()[0],
        "tool_calls": conn.execute("SELECT COUNT(*) FROM tool_calls").fetchone()[0],
        "events": conn.execute("SELECT COUNT(*) FROM events").fetchone()[0],
        "latest_seq": conn.execute("SELECT COALESCE(MAX(seq),0) FROM events").fetchone()[0],
        "note": "Rebuildable journal: artifacts remain canonical; deleting this file loses no work.",
    }


def _pid_alive(pid) -> bool:
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def reconcile(conn, *, alive=_pid_alive) -> dict:
    """Mark runs whose owning process is gone as interrupted. Never re-runs anything."""
    interrupted = []
    for run in rows(conn, "SELECT * FROM runs WHERE status IN ('running','waiting')"):
        if alive(run["pid"]):
            continue
        conn.execute(
            "UPDATE runs SET status='interrupted', error=?, ended_at=? WHERE id=?",
            ("owning process is gone; inspect outputs before any retry", _now(), run["id"]),
        )
        append_event(conn, run["id"], "run.interrupted", {"pid": run["pid"]})
        interrupted.append({"id": run["id"], "intent": run["intent"], "pid": run["pid"]})
    conn.commit()
    return {
        "interrupted": interrupted,
        "note": "interrupted is not failed and never authorises a retry",
    }


# --------------------------------------------------------------------------- #
# import of existing operation receipts
# --------------------------------------------------------------------------- #
_STATUS_MAP = {
    "running": "running",
    "succeeded": "succeeded",
    "failed": "failed",
    "interrupted": "interrupted",
}


def sync_operations(conn, projects_dir: str | Path) -> dict:
    """Import ``work/operations/*.json`` receipts as runs.

    The CLI's long local commands already write those receipts. Importing them keeps
    one run list in the app without rewiring those commands: the files stay the
    writers, the spine becomes the index. Import is idempotent per operation id.
    """
    projects_dir = Path(projects_dir)
    imported = skipped = 0
    for folder in sorted(projects_dir.iterdir()) if projects_dir.is_dir() else []:
        receipts = folder / "work/operations"
        if not receipts.is_dir():
            continue
        for path in sorted(receipts.glob("*.json")):
            try:
                record = json.loads(path.read_text())
            except (OSError, ValueError):
                skipped += 1
                continue
            if not isinstance(record, dict) or not record.get("id"):
                skipped += 1
                continue
            run_id = f"op:{record['id']}"
            exists = conn.execute("SELECT 1 FROM runs WHERE id=?", (run_id,)).fetchone()
            if exists:
                skipped += 1
                continue
            status = _STATUS_MAP.get(record.get("status"), "running")
            owner = record.get("owner") or {}
            conn.execute(
                "INSERT INTO runs(id, production, intent, plan_json, status, pid, host, "
                "lease_heartbeat, error, created_at, ended_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (
                    run_id,
                    folder.name,
                    f"{record.get('command')} {record.get('scope') or ''}".strip(),
                    json.dumps({"expected_outputs": record.get("expected_outputs")}),
                    status,
                    owner.get("pid"),
                    owner.get("host"),
                    record.get("heartbeat_at"),
                    record.get("error"),
                    record.get("started_at") or _now(),
                    record.get("ended_at"),
                ),
            )
            conn.execute(
                "INSERT OR REPLACE INTO steps(run_id, idx, name, capability, args_json, status, "
                "output_json, error, started_at, ended_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (
                    run_id,
                    0,
                    str(record.get("phase") or "operation"),
                    "execute-local",
                    "{}",
                    status,
                    json.dumps({"outputs": record.get("outputs") or []}),
                    record.get("error"),
                    record.get("started_at"),
                    record.get("ended_at"),
                ),
            )
            conn.commit()
            append_event(
                conn,
                run_id,
                "operations.imported",
                {"receipt": str(path), "status": status, "progress": record.get("progress") or {}},
            )
            imported += 1
    return {
        "imported": imported,
        "skipped": skipped,
        "note": "Receipts stay the writers; the spine only indexes them for one run list.",
    }

# --------------------------------------------------------------------------- #
# trace view
# --------------------------------------------------------------------------- #
def trace(conn, run_id: str, *, limit: int = 400) -> dict:
    """One run as evidence: steps, event types, output lines and timing."""
    run = conn.execute("SELECT * FROM runs WHERE id=?", (run_id,)).fetchone()
    if run is None:
        raise ValueError(f"unknown run {run_id!r}")
    events = event_list(conn, run_id, 0, limit)

    def payload(event):
        try:
            return json.loads(event.get("payload_json") or "{}")
        except ValueError:
            return {}

    outputs = [payload(event) for event in events if event["type"] == "command.output"]
    phases = []
    for event in events:
        if event["type"] in ("step.started", "step.succeeded", "step.failed", "step.replayed"):
            phases.append({"at": event["at"], "type": event["type"], "payload": payload(event)})
    interrupts = rows(conn, "SELECT * FROM interrupts WHERE run_id=? ORDER BY created_at", (run_id,))
    return {
        "run": dict(run),
        "steps": rows(
            conn, "SELECT idx, name, status, error FROM steps WHERE run_id=? ORDER BY idx", (run_id,)
        ),
        "event_types": sorted({event["type"] for event in events}),
        "events": len(events),
        "output_lines": [line.get("line") for line in outputs][-40:],
        "phases": phases,
        "interrupts": interrupts,
        "cost_usd": next(
            (
                row["cost_usd"]
                for row in rows(conn, "SELECT cost_usd FROM tool_calls WHERE run_id=?", (run_id,))
                if row["cost_usd"]
            ),
            None,
        ),
        "limits": "Replay evidence, not a creative review: it shows what ran, not whether it was good.",
    }


def render_trace(value: dict) -> str:
    run = value["run"]
    lines = [
        f"RUN {run['id']} · {run['status']} · {run['intent']}",
        f"production={run['production']} started={run['created_at']} ended={run['ended_at']}",
    ]
    if run.get("error"):
        lines.append(f"error={run['error']}")
    for step in value["steps"]:
        suffix = f" — {step['error']}" if step["error"] else ""
        lines.append(f"  step {step['idx']} {step['name']} [{step['status']}]{suffix}")
    for interrupt in value["interrupts"]:
        lines.append(f"  wait {interrupt['kind']} [{interrupt['status']}]")
    lines.append(f"events={value['events']} cost_usd={value['cost_usd']}")
    if value["output_lines"]:
        lines.append("output tail:")
        lines.extend(f"  | {line}" for line in value["output_lines"])
    return "\n".join(lines)

