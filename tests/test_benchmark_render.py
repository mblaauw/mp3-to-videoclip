"""Local Python processes only; no browser, renderer, provider or productions."""

import importlib.util
import os
import signal
import subprocess
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location(
    "benchmark_render", Path(__file__).resolve().parents[1] / "scripts/benchmark_render.py"
)
benchmark = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(benchmark)


@pytest.mark.parametrize("exit_code", [None, 0, 7, "interrupt"])
def test_owned_detached_descendant_cleanup(tmp_path, monkeypatch, exit_code):
    pids = tmp_path / "pids"
    child = """
import os, subprocess, sys, time
from pathlib import Path
grandchild = subprocess.Popen(
    [sys.executable, '-c',
     'import signal,time; signal.signal(signal.SIGTERM, signal.SIG_IGN); time.sleep(60)'],
    start_new_session=True,
)
Path(sys.argv[1]).write_text(f'{os.getpid()} {grandchild.pid}')
if sys.argv[2] != 'None':
    os._exit(int(sys.argv[2]))
time.sleep(60)
"""
    owner = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    real_popen = subprocess.Popen
    roots = []
    nonce = None

    def spawn(*args, **kwargs):
        nonlocal nonce
        process = real_popen(*args, **kwargs)
        if benchmark.OWNER_ENV in kwargs.get("env", {}):
            roots.append(process)
            nonce = kwargs["env"][benchmark.OWNER_ENV]
        return process

    monkeypatch.setattr(subprocess, "Popen", spawn)
    inspect = benchmark._processes
    first = True

    def snapshot(marker, **kwargs):
        nonlocal first
        if first:
            first = False
            deadline = time.monotonic() + 3
            while not pids.exists() and time.monotonic() < deadline:
                time.sleep(0.005)
            assert pids.exists()
            if exit_code in (0, 7):
                # Parent is already reaped before the first snapshot: ancestry
                # cannot recover this detached grandchild. No artificial hold.
                roots[0].wait(timeout=3)
            if exit_code == "interrupt":
                raise KeyboardInterrupt
            observed = inspect(marker, **kwargs)
            assert int(pids.read_text().split()[1]) in observed
            return observed
        return inspect(marker, **kwargs)

    monkeypatch.setattr(benchmark, "_processes", snapshot)
    command = [
        sys.executable,
        "-c",
        child,
        str(pids),
        str(exit_code if exit_code != "interrupt" else None),
    ]
    try:
        expected = {
            None: subprocess.TimeoutExpired,
            7: subprocess.CalledProcessError,
            "interrupt": KeyboardInterrupt,
        }.get(exit_code)
        if expected:
            with pytest.raises(expected):
                benchmark.run_owned(
                    command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1
                )
        else:
            benchmark.run_owned(
                command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=1
            )
        assert roots[0].returncode is not None
        assert not inspect(nonce)
        assert owner.poll() is None
    finally:
        owner.terminate()
        owner.wait(timeout=2)
        # Fail-safe confined to the nonce, never names/groups or stale PID lists.
        if nonce:
            for pid in inspect(nonce):
                benchmark._signal_owned(nonce, {pid}, signal.SIGKILL, deadline=time.monotonic() + 2)


@pytest.mark.parametrize("persistent", [False, True])
def test_snapshot_failure_still_reaps_direct_child(tmp_path, monkeypatch, persistent):
    real_popen = subprocess.Popen
    roots = []

    def spawn(*args, **kwargs):
        process = real_popen(*args, **kwargs)
        if benchmark.OWNER_ENV in kwargs.get("env", {}):
            roots.append(process)
        return process

    monkeypatch.setattr(subprocess, "Popen", spawn)
    inspect = benchmark._processes
    calls = 0
    ready = tmp_path / "ready"

    def snapshot(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 1:
            deadline = time.monotonic() + 3
            while not ready.exists() and time.monotonic() < deadline:
                time.sleep(0.005)
            assert ready.exists()
        if calls == 1 or persistent:
            raise RuntimeError("benchmark process inspection failed")
        return inspect(*args, **kwargs)

    monkeypatch.setattr(benchmark, "_processes", snapshot)
    before = time.monotonic()
    with pytest.raises(RuntimeError, match="inspection failed"):
        benchmark.run_owned(
            [
                sys.executable,
                "-c",
                "import signal,time,sys; from pathlib import Path; "
                "signal.signal(signal.SIGTERM, signal.SIG_IGN); "
                "Path(sys.argv[1]).touch(); time.sleep(60)",
                str(ready),
            ],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=20,
        )
    assert roots[0].returncode is not None
    assert time.monotonic() - before < 9
    assert calls >= 2


def test_same_second_replacement_requires_exact_nonce(monkeypatch):
    nonce = "a" * 64
    outputs = iter(
        [
            f"123 S python {benchmark.OWNER_ENV}={nonce}",
            f"123 S python {benchmark.OWNER_ENV}={'b' * 64}",
        ]
    )
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=0, stdout=next(outputs))
    )
    monkeypatch.setattr(os, "kill", lambda *args: pytest.fail("signalled replacement PID"))
    observed = benchmark._processes(nonce)
    assert observed == {123}
    benchmark._signal_owned(nonce, observed, signal.SIGKILL, deadline=time.monotonic() + 2)


def test_environment_scan_errors_do_not_expose_secrets(monkeypatch):
    def fail(*args, **kwargs):
        raise subprocess.TimeoutExpired("ps", 1, output="SECRET_ENV=value", stderr="OTHER_SECRET")

    monkeypatch.setattr(subprocess, "run", fail)
    with pytest.raises(RuntimeError) as error:
        benchmark._processes("a" * 64)
    assert error.value.__context__ is None
    assert "SECRET" not in str(error.value)


def test_marker_matching_is_exact_and_ignores_zombies(monkeypatch):
    nonce = "a" * 64
    output = f"1 S python {benchmark.OWNER_ENV}={nonce}suffix\n2 Z python {benchmark.OWNER_ENV}={nonce}\n3 S python {benchmark.OWNER_ENV}={nonce}\n"
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **kw: SimpleNamespace(returncode=0, stdout=output)
    )
    assert benchmark._processes(nonce) == {3}
