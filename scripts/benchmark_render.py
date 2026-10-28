"""Opt-in isolated local renderer benchmark; never installs or touches productions."""

import argparse
import hashlib
import json
import os
import platform
import secrets
import shutil
import signal
import statistics
import subprocess
import time
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "renderers/remotion"


OWNER_ENV = "MP3_VIDEO_BENCHMARK_OWNER"


def _processes(nonce, *, timeout=1):
    """Return marked live PIDs on our UID; never expose raw ps environments.

    BSD/macOS and Linux ps support eww (untruncated environment). Capture only
    internally, discard stderr, and replace all inspection errors with a fixed
    message, outside the exception handler so no secret-bearing context escapes.
    """
    result = None
    try:
        result = subprocess.run(
            ["ps", "eww", "-U", str(os.getuid()), "-o", "pid=,stat=,command="],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            errors="replace",
            check=False,
            timeout=timeout,
            env={**os.environ, "LC_ALL": "C"},
        )
    except (OSError, subprocess.SubprocessError):
        pass
    if result is None or result.returncode:
        raise RuntimeError("benchmark process inspection failed")
    marker = f"{OWNER_ENV}={nonce}"
    rows = set()
    for line in result.stdout.splitlines():
        fields = line.split()
        if len(fields) >= 3 and fields[0].isdigit():
            if marker in fields[2:] and not fields[1].startswith("Z"):
                rows.add(int(fields[0]))
    return rows


def _signal_owned(nonce, pids, sig, *, deadline):
    for pid in pids:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        # Start times have only second precision on macOS. Recheck the nonce,
        # not ancestry/start time, immediately before each individual signal.
        if pid in _processes(nonce, timeout=min(1, remaining)):
            try:
                os.kill(pid, sig)
            except ProcessLookupError:
                pass


def _cleanup_owned(process, nonce):
    # Popen protects the unreaped direct child's identity independently of ps.
    process.terminate()
    cleanup_deadline = time.monotonic() + 6.0
    kill_at = time.monotonic() + 2.0
    inspection_failed = False
    while time.monotonic() < cleanup_deadline:
        sig = signal.SIGKILL if time.monotonic() >= kill_at else signal.SIGTERM
        if sig == signal.SIGKILL:
            process.kill()
        process.poll()
        try:
            alive = _processes(
                nonce, timeout=max(0.001, min(1, cleanup_deadline - time.monotonic()))
            )
            if not alive and process.returncode is not None:
                if inspection_failed:
                    break
                return
            _signal_owned(nonce, alive - {process.pid}, sig, deadline=cleanup_deadline)
        except RuntimeError:
            inspection_failed = True
        time.sleep(0.02)
    # Never let failed snapshots bypass direct-child kill/reap.
    process.kill()
    try:
        process.wait(timeout=1)
    except subprocess.TimeoutExpired:
        raise RuntimeError("benchmark direct child could not be reaped") from None
    if inspection_failed:
        raise RuntimeError("benchmark cleanup process inspection failed")
    raise RuntimeError("benchmark cleanup could not confirm all marked processes stopped")


def run_owned(command, *, stdout, stderr, timeout):
    """Run and clean environment-inheriting children, including detached orphans.

    Supported on macOS/Linux where ps exposes our UID's inherited environments.
    Remotion BrowserRunner passes process.env to Chrome. This is not a sandbox:
    arbitrary programs that scrub/change the marker are outside this contract.
    No process groups, names, ancestry or second-resolution times confer ownership.
    """
    nonce = secrets.token_hex(32)
    process = None
    signals = (signal.SIGINT, signal.SIGTERM, signal.SIGHUP)
    handlers = {sig: signal.getsignal(sig) for sig in signals}

    def interrupted(signum, frame):
        raise KeyboardInterrupt(f"benchmark interrupted by signal {signum}")

    try:
        for sig in signals:
            signal.signal(sig, interrupted)
        process = subprocess.Popen(
            command,
            stdout=stdout,
            stderr=stderr,
            start_new_session=True,
            env={**os.environ, OWNER_ENV: nonce},
        )
        deadline = time.monotonic() + timeout
        while True:
            _processes(nonce)
            code = process.poll()
            if code is not None:
                if code:
                    raise subprocess.CalledProcessError(code, command)
                return
            if time.monotonic() >= deadline:
                raise subprocess.TimeoutExpired(command, timeout)
            time.sleep(0.02)
    finally:
        try:
            # Repeated interrupts must not interrupt the bounded cleanup itself.
            for sig in signals:
                signal.signal(sig, signal.SIG_IGN)
            if process is not None:
                _cleanup_owned(process, nonce)
        finally:
            for sig, handler in handlers.items():
                signal.signal(sig, handler)


def save(path, value):
    path.write_text(json.dumps(value, indent=2) + "\n")


def aggregate(runs):
    result = {}
    for kind in {r["kind"] for r in runs}:
        result[kind] = {}
        for state in ("cold", "warm"):
            group = [r for r in runs if r["kind"] == kind and r["state"] == state]
            if not group:
                continue
            phases = {
                key: statistics.median(r["diagnostics"][key] for r in group)
                for key in ("bundle_ms", "composition_setup_ms", "render_media_ms")
            }
            phases["process_overhead_ms"] = statistics.median(
                max(0, r["wall_seconds"] * 1000 - r["diagnostics"]["total_ms"]) for r in group
            )
            result[kind][state] = {
                "count": len(group),
                "median_wall_seconds": statistics.median(r["wall_seconds"] for r in group),
                "median_fps": statistics.median(r["throughput_fps"] for r in group),
                "median_phases_ms": phases,
                "dominant_phase": max(phases, key=phases.get),
                "frame_encoding": "overlapping completion durations, not additive; see per-run diagnostics",
            }
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--seconds", type=int, choices=range(10, 21), default=12)
    parser.add_argument("--kind", choices=("both", "base", "graphics"), default="both")
    parser.add_argument("--budget-seconds", type=int, choices=range(30, 601), default=480)
    args = parser.parse_args()
    chrome = Path(
        os.environ.get(
            "REMOTION_CHROME", "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"
        )
    )
    if (
        not chrome.is_file()
        or not shutil.which("node")
        or not (ENGINE / "node_modules/@remotion/renderer").is_dir()
    ):
        parser.error(
            "local Chrome, Node and already-installed pinned renderer required; nothing is downloaded"
        )
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=False)
    assets = output / "assets"
    assets.mkdir()
    for i in range(3):
        image = Image.new("RGB", (1920, 1080))
        # Deterministic colour/gradient plates, not private or provider assets.
        row = Image.new("RGB", (1920, 1))
        row.putdata(
            [((x // 8 + i * 60) % 256, (x // 12 + 40) % 256, 80 + i * 50) for x in range(1920)]
        )
        image = row.resize((1920, 1080))
        image.save(assets / f"shot-{i}.png")
    frames = args.seconds * 24
    shots = [
        {
            "id": f"s{i}",
            "image": f"shot-{i}.png",
            "start_frame": i * (frames // 3),
            "duration_frames": frames // 3,
            "dissolve_frames": 12 if i < 2 else 0,
            "camera": ["hold", "zoom_in", "pan_left"][i],
        }
        for i in range(3)
    ]
    svg = '<svg xmlns="http://www.w3.org/2000/svg" width="20" height="20"><rect width="20" height="20" fill="red"/></svg>'
    import base64

    summary = {
        "renderer_source_sha256": {
            str(p.relative_to(ENGINE)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [
                ENGINE / "render.mjs",
                ENGINE / "package-lock.json",
                *sorted((ENGINE / "src").glob("*")),
            ]
            if p.is_file()
        },
        "machine": {
            "platform": platform.platform(),
            "processor": platform.processor(),
            "cpu_count": os.cpu_count(),
            "python": platform.python_version(),
            "node": subprocess.check_output(["node", "--version"], text=True).strip(),
            "chrome": str(chrome),
        },
        "settings": {
            "width": 1920,
            "height": 1080,
            "fps": 24,
            "seconds": args.seconds,
            "graphics_seconds": 2,
            "concurrency": 2,
        },
        "cache_policy": "two independent bundle cache roots per kind; cold then warm in each; OS/browser caches uncontrolled",
        "runs": [],
        "status": "partial",
    }
    started = time.perf_counter()
    try:
        for kind in ("base", "graphics") if args.kind == "both" else (args.kind,):
            for pair in range(2):
                cache = output / f"cache-{kind}-{pair}"
                for state in ("cold", "warm"):
                    remaining = args.budget_seconds - (time.perf_counter() - started)
                    if remaining <= 0:
                        raise TimeoutError("benchmark time budget exhausted")
                    stem = f"{kind}-{pair}-{state}"
                    target = output / (stem + (".mp4" if kind == "base" else ".mov"))
                    request = {
                        "kind": kind,
                        "output": str(target),
                        "assetRoot": str(assets),
                        "width": 1920,
                        "height": 1080,
                        "fps": 24,
                        "frames": frames if kind == "base" else 48,
                        "chrome": str(chrome),
                        "concurrency": 2,
                        "input": {"shots": shots}
                        if kind == "base"
                        else {
                            "part": {
                                "kind": "caption",
                                "id": "bench",
                                "frames": 48,
                                "caption": {
                                    "id": "bench",
                                    "style": "caption",
                                    "text": "LOCAL ALPHA BENCHMARK",
                                },
                            },
                            "spec": {},
                            "intro": {},
                            "palette": {},
                            "logo": "data:image/svg+xml;base64,"
                            + base64.b64encode(svg.encode()).decode(),
                        },
                    }
                    request_path = output / f"{stem}.request.json"
                    save(request_path, request)
                    before = time.perf_counter()
                    with (output / f"{stem}.log").open("w") as log:
                        run_owned(
                            [
                                "node",
                                str(ENGINE / "render.mjs"),
                                str(request_path),
                                "--cache-dir",
                                str(cache),
                            ],
                            stdout=log,
                            stderr=log,
                            timeout=remaining,
                        )
                    wall = time.perf_counter() - before
                    report = json.loads(Path(f"{target}.render.json").read_text())
                    summary["runs"].append(
                        {
                            **report,
                            "state": state,
                            "pair": pair,
                            "cache_root": str(cache),
                            "wall_seconds": wall,
                            "throughput_fps": request["frames"] / wall,
                            "request_file_sha256": hashlib.sha256(
                                request_path.read_bytes()
                            ).hexdigest(),
                        }
                    )
                    save(
                        output / "benchmark.json",
                        {**summary, "aggregate": aggregate(summary["runs"])},
                    )
        summary["status"] = "complete"
    except (subprocess.SubprocessError, TimeoutError, RuntimeError) as error:
        summary["error"] = str(error)
    finally:
        summary["aggregate"] = aggregate(summary["runs"])
        save(output / "benchmark.json", summary)
    print(output / "benchmark.json")
    return 0 if summary["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
