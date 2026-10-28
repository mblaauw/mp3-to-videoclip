"""Opt-in isolated local renderer benchmark; never installs or touches productions."""

import argparse
import hashlib
import json
import os
import platform
import shutil
import statistics
import subprocess
import time
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ENGINE = ROOT / "renderers/remotion"


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
                        subprocess.run(
                            [
                                "node",
                                str(ENGINE / "render.mjs"),
                                str(request_path),
                                "--cache-dir",
                                str(cache),
                            ],
                            stdout=log,
                            stderr=log,
                            check=True,
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
    except (subprocess.SubprocessError, TimeoutError) as error:
        summary["error"] = str(error)
    finally:
        summary["aggregate"] = aggregate(summary["runs"])
        save(output / "benchmark.json", summary)
    print(output / "benchmark.json")
    return 0 if summary["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
