"""Durable lifecycle receipts for long-running local operations.

A long render, preview or paid batch leaves one JSON receipt under
``work/operations/`` so its phase, progress, heartbeat and outcome survive the
session that started it. A receipt is written only by the process that owns it
and is read **without** the project lock: monitoring must never block an active
writer, and an active writer must never block monitoring.

Nothing here schedules, retries, approves or spends. Reconciliation reports that
an owning process is gone; it never deletes evidence, never resolves billing,
never re-submits a paid task and never promotes an output to approved.

Phases come from the work itself (bundling, rendering frames, muxing, verifying),
never from a guessed percentage or an invented ETA.
"""

from __future__ import annotations

import contextlib
import contextvars
import os
import socket
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from .storage import file_hash, inside, read_json, write_json

DIRECTORY = "work/operations"
SCHEMA_VERSION = 1
#: A running receipt with no heartbeat for this long is reported as quiet. Quiet
#: is information for a human/agent reader, never an automatic failure verdict:
#: the operation may legitimately be inside one long non-reporting step.
QUIET_SECONDS = 120.0
MAX_PHASES = 40


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _parse(value):
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def directory(root: Path) -> Path:
    return Path(root) / DIRECTORY


def _path(root: Path, operation_id: str) -> Path:
    return directory(root) / f"{operation_id}.json"


def _pid_alive(pid) -> bool | None:
    """``True``/``False`` when the OS answers, ``None`` when inconclusive.

    A recycled PID can make a dead operation look alive. That error direction is
    deliberate: an inconclusive or apparently-live owner is never rewritten.
    """
    if isinstance(pid, bool) or not isinstance(pid, int) or pid <= 0:
        return None
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except (OverflowError, TypeError, ValueError):
        return False
    except OSError:
        return None
    return True


class Operation:
    """One operation's receipt; only its owning process may update it."""

    def __init__(self, root: Path, record: dict):
        self.root = Path(root)
        self.record = record

    @property
    def id(self) -> str:
        return self.record["id"]

    @property
    def path(self) -> Path:
        return _path(self.root, self.id)

    # -- writing ---------------------------------------------------------- #
    def _save(self) -> None:
        """Persist the receipt best-effort: monitoring never breaks the observed work.

        The in-memory record stays authoritative for the running process, so a
        read-only filesystem or a full disk degrades visibility instead of failing
        a render that would otherwise have completed.
        """
        self.record["updated_at"] = _now()
        try:
            write_json(self.path, self.record)
        except Exception:
            pass

    def phase(self, name, *, note=None, done=None, total=None, unit=None) -> Operation:
        stamp = _now()
        self.record["phase"] = str(name)
        self.record["heartbeat_at"] = stamp
        phases = self.record.setdefault("phases", [])
        entry = {"name": str(name), "at": stamp}
        if note is not None:
            entry["note"] = str(note)
        phases.append(entry)
        del phases[:-MAX_PHASES]
        if done is not None or total is not None or unit is not None:
            self._progress(done=done, total=total, unit=unit)
        self._save()
        return self

    def tick(self, *, done=None, total=None, unit=None, phase=None, message=None) -> Operation:
        if phase is not None:
            self.record["phase"] = str(phase)
        self.record["heartbeat_at"] = _now()
        if done is not None or total is not None or unit is not None or message is not None:
            self._progress(done=done, total=total, unit=unit, message=message)
        self._save()
        return self

    def _progress(self, *, done=None, total=None, unit=None, message=None) -> None:
        progress = self.record.setdefault("progress", {})
        for key, value in (("done", done), ("total", total), ("unit", unit), ("message", message)):
            if value is not None:
                progress[key] = value
        progress["at"] = _now()

    def finish(self, result=None, *, outputs=None, next_action=None) -> Operation:
        self.record["status"] = "succeeded"
        self.record["ended_at"] = _now()
        self.record["heartbeat_at"] = self.record["ended_at"]
        self._record_outputs(outputs)
        if result is not None:
            self.record["result"] = result
        if next_action is not None:
            self.record["next_action"] = str(next_action)
        self._save()
        return self

    def fail(self, error, *, next_action=None) -> Operation:
        self.record["status"] = "failed"
        self.record["ended_at"] = _now()
        self.record["heartbeat_at"] = self.record["ended_at"]
        self.record["error"] = (
            error if isinstance(error, str) else f"{type(error).__name__}: {error}"
        )
        if next_action is not None:
            self.record["next_action"] = str(next_action)
        self._record_outputs(None)
        self._save()
        return self

    def _record_outputs(self, outputs) -> None:
        """Hash the declared outputs so a partial run is visible, not implied."""
        declared = self.record.get("expected_outputs", []) if outputs is None else list(outputs)
        recorded = []
        for name in declared:
            try:
                path = inside(self.root, str(name))
            except ValueError:
                continue
            try:
                if path.is_file():
                    recorded.append(
                        {
                            "path": str(name),
                            "sha256": file_hash(path),
                            "bytes": path.stat().st_size,
                        }
                    )
                else:
                    recorded.append({"path": str(name), "missing": True})
            except OSError:
                recorded.append({"path": str(name), "unreadable": True})
        if recorded:
            self.record["outputs"] = recorded


# The receipt a library call may annotate without threading a parameter through
# every intermediate function. One process owns at most one operation because the
# CLI holds the exclusive project lock for any writing command.
_ACTIVE: Operation | None = None


def active() -> Operation | None:
    return _ACTIVE


# A live listener for the same phase/progress calls. The Studio's job runner sets
# it (through a context variable, so ``asyncio.to_thread`` carries it into the
# worker thread) to stream progress to the browser. Like the receipt, it is
# observation only: an observer error is swallowed and never reaches the work.
_OBSERVER: contextvars.ContextVar = contextvars.ContextVar("operation_observer", default=None)
_PROGRESS_SCOPE: contextvars.ContextVar = contextvars.ContextVar("progress_scope", default=None)


@contextlib.contextmanager
def progress_scope(*, stage=None, part=None, part_index=None, part_total=None):
    """Label observed work without changing rendering or operation ownership.

    Also usable as a decorator. Nested scopes inherit their delivery stage;
    counters belong only to the current phase and part, never the whole job.
    """
    values = dict(_PROGRESS_SCOPE.get() or {})
    if stage is not None and stage != values.get("stage"):
        values = {"stage": stage}
    values.update(
        {
            key: value
            for key, value in {
                "stage": stage,
                "part": part,
                "part_index": part_index,
                "part_total": part_total,
            }.items()
            if value is not None
        }
    )
    token = _PROGRESS_SCOPE.set(values)
    try:
        _notify("phase", {"phase": "starting"})
        yield
    finally:
        _PROGRESS_SCOPE.reset(token)


# A cooperative stop request for the same context (the Studio's Cancel button).
# Work that can stop safely between steps checks it; nothing is interrupted
# mid-step, so a paid task that was already sent still finishes and is recorded.
_STOP: contextvars.ContextVar = contextvars.ContextVar("operation_stop", default=None)


def watch_stop(event):
    """Install a ``threading.Event`` that asks this context's work to stop."""
    return _STOP.set(event)


def unwatch_stop(token) -> None:
    _STOP.reset(token)


def stop_requested() -> bool:
    event = _STOP.get()
    try:
        return bool(event is not None and event.is_set())
    except Exception:  # noqa: BLE001 - a broken flag never stops real work
        return False


def observe(callback):
    """Install ``callback(event, data)`` for this context; returns a reset token."""
    return _OBSERVER.set(callback)


def unobserve(token) -> None:
    _OBSERVER.reset(token)


def _notify(event: str, data: dict) -> None:
    callback = _OBSERVER.get()
    if callback is None:
        return
    try:
        callback(
            event,
            {
                key: value
                for key, value in {**(_PROGRESS_SCOPE.get() or {}), **data}.items()
                if value is not None
            },
        )
    except Exception:  # noqa: BLE001 - monitoring never breaks the observed work
        pass


def tick(**kwargs) -> None:
    """Advance the active operation; a no-op when nothing is being observed.

    Persistence is already best-effort inside :meth:`Operation._save`, so a
    monitoring failure can never break the work it observes.
    """
    _notify("tick", kwargs)
    if _ACTIVE is None:
        return
    _ACTIVE.tick(**kwargs)


def phase(name, **kwargs) -> None:
    _notify("phase", {"phase": name, **kwargs})
    if _ACTIVE is None:
        return
    _ACTIVE.phase(name, **kwargs)


def begin(root, command, *, scope=None, expected_outputs=(), next_action=None) -> Operation:
    root = Path(root)
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%S")
    record = {
        "schema_version": SCHEMA_VERSION,
        "id": f"op-{stamp}-{uuid4().hex[:6]}",
        "project": root.name,
        "command": str(command),
        "scope": scope,
        "started_at": _now(),
        "heartbeat_at": _now(),
        "updated_at": _now(),
        "status": "running",
        "phase": "starting",
        "phases": [],
        "progress": {},
        "owner": {"pid": os.getpid(), "host": socket.gethostname()},
        "expected_outputs": [str(name) for name in expected_outputs],
        "outputs": [],
        "result": None,
        "error": None,
        "next_action": next_action,
        "reconciled_at": None,
        "reconcile_note": None,
    }
    operation = Operation(root, record)
    operation.phase("starting")
    return operation


@contextlib.contextmanager
def operation(root, command, *, scope=None, expected_outputs=(), next_action=None):
    """Record one local operation; a nested call only annotates the active phase."""
    global _ACTIVE
    if _ACTIVE is not None:
        phase(f"{command}:{scope}" if scope else str(command), note="nested local stage")
        yield _ACTIVE
        return
    current = begin(
        root, command, scope=scope, expected_outputs=expected_outputs, next_action=next_action
    )
    _ACTIVE = current
    try:
        yield current
    except BaseException as exc:  # a receipt must not stay "running" after a crash
        current.fail(exc)
        raise
    else:
        current.finish()
    finally:
        _ACTIVE = None


# -- reading -------------------------------------------------------------- #
def _records(root: Path) -> tuple[list[dict], list[str]]:
    folder = directory(root)
    records: list[dict] = []
    unreadable: list[str] = []
    if not folder.is_dir():
        return records, unreadable
    for path in sorted(folder.glob("*.json")):
        try:
            record = read_json(path)
        except (OSError, ValueError):
            unreadable.append(str(path))
            continue
        if not isinstance(record, dict) or not record.get("id"):
            unreadable.append(str(path))
            continue
        records.append(record)
    return records, unreadable


def _derived(record: dict, root: Path, now: datetime) -> dict:
    status = record.get("status")
    started = _parse(record.get("started_at"))
    heartbeat = _parse(record.get("heartbeat_at"))
    ended = _parse(record.get("ended_at"))
    progress = record.get("progress") or {}
    done, total = progress.get("done"), progress.get("total")
    fraction = None
    if isinstance(done, (int, float)) and isinstance(total, (int, float)) and total:
        fraction = max(0.0, min(1.0, float(done) / float(total)))
    heartbeat_age = None
    if heartbeat is not None:
        try:
            heartbeat_age = round((now - heartbeat).total_seconds(), 1)
        except TypeError:
            heartbeat_age = None
    running_seconds = None
    if started is not None:
        try:
            running_seconds = round(((ended or now) - started).total_seconds(), 1)
        except TypeError:
            running_seconds = None
    pid = (record.get("owner") or {}).get("pid")
    try:
        relative = str(_path(root, record["id"]).relative_to(root))
    except (KeyError, ValueError):
        relative = None
    return {
        "id": record.get("id"),
        "command": record.get("command"),
        "scope": record.get("scope"),
        "status": status,
        "phase": record.get("phase"),
        "phases": record.get("phases") or [],
        "started_at": record.get("started_at"),
        "ended_at": record.get("ended_at"),
        "heartbeat_age_seconds": heartbeat_age,
        "elapsed_seconds": running_seconds,
        "progress": progress,
        "fraction": fraction,
        "owner_pid": pid,
        "owner_process_alive": _pid_alive(pid),
        "quiet": bool(
            status == "running" and heartbeat_age is not None and heartbeat_age > QUIET_SECONDS
        ),
        "expected_outputs": record.get("expected_outputs") or [],
        "outputs": record.get("outputs") or [],
        "result_present": record.get("result") is not None,
        "error": record.get("error"),
        "next_action": record.get("next_action"),
        "reconciled_at": record.get("reconciled_at"),
        "receipt": relative,
    }


def _attention(entries: list[dict]) -> list[dict]:
    flagged = []
    for entry in entries:
        status = entry.get("status")
        if status == "interrupted":
            flagged.append(
                {
                    "id": entry["id"],
                    "status": status,
                    "reason": "owning process is gone; inspect partial outputs before any retry",
                }
            )
        elif status == "failed":
            flagged.append({"id": entry["id"], "status": status, "reason": entry.get("error")})
        elif status == "running" and entry.get("quiet"):
            flagged.append(
                {
                    "id": entry["id"],
                    "status": status,
                    "reason": (
                        f"no heartbeat for {entry['heartbeat_age_seconds']}s; it may still be "
                        "working inside one long step — never re-submit automatically"
                    ),
                }
            )
    return flagged


def list_operations(root, *, limit=None, running_only=False) -> dict:
    """Read-only snapshot; never creates, repairs or locks anything."""
    root = Path(root)
    now = datetime.now(UTC)
    records, unreadable = _records(root)
    entries = [_derived(record, root, now) for record in records]
    entries.sort(
        key=lambda item: (item.get("started_at") or "", item.get("id") or ""), reverse=True
    )
    if running_only:
        entries = [entry for entry in entries if entry.get("status") == "running"]
    if limit is not None:
        entries = entries[: max(0, int(limit))]
    return {
        "directory": DIRECTORY,
        "operations": entries,
        "unreadable": unreadable,
        "quiet_threshold_seconds": QUIET_SECONDS,
    }


def summary(root) -> dict:
    """Compact counts for ``clip status``; read-only and lock-free."""
    snapshot = list_operations(root)
    entries = snapshot["operations"]
    counts: dict[str, int] = {}
    for entry in entries:
        counts[entry["status"]] = counts.get(entry["status"], 0) + 1
    newest_running = next((e for e in entries if e["status"] == "running"), None)
    return {
        "counts": counts,
        "unreadable": len(snapshot["unreadable"]),
        "newest_running": (
            {
                "id": newest_running["id"],
                "command": newest_running["command"],
                "phase": newest_running["phase"],
                "heartbeat_age_seconds": newest_running["heartbeat_age_seconds"],
                "fraction": newest_running["fraction"],
                "quiet": newest_running["quiet"],
            }
            if newest_running
            else None
        ),
        "needs_attention": _attention(entries),
        "note": "Completion is not approval; quiet is not failure.",
    }


def reconcile(root) -> dict:
    """Mark receipts whose owning process is gone as ``interrupted``.

    Rewrites only the status of receipts whose PID is provably gone. Inconclusive
    or apparently-live owners are left untouched, no output is claimed valid, no
    billing is resolved and nothing is re-run.
    """
    root = Path(root)
    interrupted, left_running = [], []
    for record in _records(root)[0]:
        if record.get("status") != "running":
            continue
        pid = (record.get("owner") or {}).get("pid")
        alive = _pid_alive(pid)
        if alive is not False:
            left_running.append(
                {
                    "id": record.get("id"),
                    "owner_pid": pid,
                    "owner_process_alive": alive,
                    "reason": "cannot confirm the owning process ended; left untouched",
                }
            )
            continue
        record["status"] = "interrupted"
        record["reconciled_at"] = _now()
        record["reconcile_note"] = (
            "owning process is gone; partial outputs may exist. Inspect them before any retry. "
            "This does not resolve billing and never re-submits work."
        )
        # Record which declared outputs exist, so "partial" is visible evidence
        # rather than a guess. Missing outputs are listed, never inferred as clean.
        Operation(root, record)._record_outputs(None)
        write_json(_path(root, record["id"]), record)
        interrupted.append(
            {"id": record.get("id"), "command": record.get("command"), "phase": record.get("phase")}
        )
    return {"interrupted": interrupted, "left_running": left_running}


def report(root, *, limit=None, running_only=False, reconcile_stale=False) -> dict:
    """One read-only monitoring payload, with optional explicit reconciliation."""
    reconciled = reconcile(root) if reconcile_stale else None
    payload = list_operations(root, limit=limit, running_only=running_only)
    if reconciled is not None:
        payload["reconciled"] = reconciled
    payload["needs_attention"] = _attention(payload["operations"])
    payload["note"] = (
        "Receipts record what a process did. Completion is not approval, and a quiet "
        "or interrupted receipt never authorises a retry or a charge."
    )
    return payload
