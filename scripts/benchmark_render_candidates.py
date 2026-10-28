"""Bounded, serial T9 experiments against one existing synthetic T8 fixture."""

import argparse
import hashlib
import json
import os
import statistics
import subprocess
import time
from pathlib import Path

from benchmark_render import ENGINE, run_owned, save


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def candidate_cases(suite):
    cases = [("warmup", 2, None)]
    if suite in ("all", "software"):
        cases += [
            (f"software-c{c}-r{rep}", c, None)
            for rep, order in enumerate(((1, 2, 3), (3, 2, 1)))
            for c in order
        ]
    if suite in ("all", "hardware"):
        cases += [(f"videotoolbox-c2-r{rep}", 2, "videotoolbox-20m") for rep in range(2)]
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline-dir", required=True, type=Path)
    parser.add_argument("--output-dir", required=True, type=Path)
    parser.add_argument("--budget-seconds", type=int, default=660, choices=range(30, 901))
    parser.add_argument("--suite", choices=("all", "software", "hardware"), default="all")
    args = parser.parse_args()
    baseline = args.baseline_dir.resolve()
    output = args.output_dir.resolve()
    template = json.loads((baseline / "base-0-warm.request.json").read_text())
    if (template["frames"], template["width"], template["height"], template["fps"]) != (
        288,
        1920,
        1080,
        24,
    ) or template["kind"] != "base":
        parser.error("requires the fixed synthetic 12-second 1080p24 base fixture")
    chrome = template.get("chrome")
    if (
        not isinstance(chrome, str)
        or not chrome
        or not Path(chrome).is_absolute()
        or not Path(chrome).is_file()
        or not os.access(chrome, os.X_OK)
    ):
        parser.error(
            "baseline must name an existing explicit local Chrome executable; downloads are forbidden"
        )
    output.mkdir(parents=True, exist_ok=False)
    report = {
        "status": "partial",
        "baseline": str(baseline),
        "source_sha256": digest(ENGINE / "render.mjs"),
        "renderer_source_sha256": {
            str(p.relative_to(ENGINE)): digest(p)
            for p in [
                ENGINE / "render.mjs",
                ENGINE / "package-lock.json",
                *sorted((ENGINE / "src").glob("*")),
            ]
            if p.is_file()
        },
        "asset_sha256": {
            p.name: digest(p) for p in sorted(Path(template["assetRoot"]).glob("*.png"))
        },
        "policy": "serial; one bundle cache; warm-up excluded; OS/browser caches uncontrolled; synthetic only",
        "runs": [],
        "quality_acceptance": "no human visual acceptance; SSIM is not sufficient for adoption",
        "suite": args.suite,
        "budget_seconds": args.budget_seconds,
    }
    started = time.monotonic()

    def remaining():
        value = args.budget_seconds - (time.monotonic() - started)
        if value <= 0:
            raise TimeoutError("aggregate experiment budget exhausted")
        return value

    def owned(command, stem):
        with (
            (output / f"{stem}.stdout").open("w") as stdout,
            (output / f"{stem}.stderr").open("w") as stderr,
        ):
            run_owned(command, stdout=stdout, stderr=stderr, timeout=remaining())

    try:
        # A method call without required parameters cannot allocate a frame pool.
        # Missing-method vs invalid-parameters distinguishes CDP support locally.
        probe = f"""
          const {{openBrowser}} = await import({json.dumps(str(ENGINE / "node_modules/@remotion/renderer/dist/esm/index.mjs"))});
          const browser = await openBrowser('chrome', {{browserExecutable: {json.dumps(chrome)}, logLevel: 'error'}});
          try {{
            const page = await browser.newPage({{context: null, logLevel: 'error', indent: false, pageIndex: 0, onBrowserLog: null, onLog: null}});
            try {{ console.log(JSON.stringify(await page._client().send('Page.remotionCreateFramePool', {{}}))); }}
            catch (error) {{ console.log(JSON.stringify({{capability_error: error.message}})); }}
          }} finally {{ await browser.close({{silent: true}}); }}
        """
        owned(["node", "--input-type=module", "-e", probe], "raw-cdp-probe")
        report["raw_capture_probe"] = (output / "raw-cdp-probe.stdout").read_text()
        # Interleave replicate order rather than render all concurrency-1 runs first.
        cases = candidate_cases(args.suite)
        reference = baseline / "base-0-warm.mp4"
        for stem, concurrency, profile in cases:
            request = {
                **template,
                "output": str(output / f"{stem}.mp4"),
                "concurrency": concurrency,
            }
            request_file = output / f"{stem}.request.json"
            save(request_file, request)
            command = [
                "node",
                str(ENGINE / "render.mjs"),
                str(request_file),
                "--cache-dir",
                str(output / "bundle-cache"),
            ]
            if profile:
                command += ["--benchmark-profile", profile]
            t0 = time.monotonic()
            row = {
                "case": stem,
                "concurrency": concurrency,
                "profile": profile,
                "status": "partial",
            }
            report["runs"].append(row)
            save(output / "candidates.json", report)
            try:
                owned(command, stem)
            except subprocess.CalledProcessError as error:
                row.update(status="failed", error=str(error))
                continue
            row["subprocess_seconds"] = time.monotonic() - t0
            media = Path(request["output"])
            sidecar = json.loads(Path(f"{media}.render.json").read_text())
            row.update(
                status="rendered",
                renderer=sidecar,
                sha256=digest(media),
                bytes=media.stat().st_size,
            )
            row["cache_conditions_pass"] = stem == "warmup" or sidecar.get("bundle_cached") is True
            encoders = {
                encoder
                for command in sidecar.get("diagnostics", {}).get("ffmpeg", [])
                for encoder in command.get("video_encoders", [])
                if encoder != "copy"
            }
            row["encoder_pass"] = encoders == {"h264_videotoolbox" if profile else "libx264"}
            owned(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-count_frames",
                    "-show_streams",
                    "-of",
                    "json",
                    str(media),
                ],
                f"{stem}-probe",
            )
            row["probe"] = json.loads((output / f"{stem}-probe.stdout").read_text())
            streams = row["probe"]["streams"]
            video = streams[0]
            row["contract_pass"] = len(streams) == 1 and all(
                [
                    video["codec_type"] == "video",
                    video["codec_name"] == "h264",
                    video["width"] == 1920,
                    video["height"] == 1080,
                    video["r_frame_rate"] == "24/1",
                    video["nb_read_frames"] == "288",
                    video["pix_fmt"] == "yuv420p",
                    video.get("color_space") == "bt709",
                ]
            )
            owned(
                [
                    "ffmpeg",
                    "-nostdin",
                    "-hide_banner",
                    "-i",
                    str(reference),
                    "-i",
                    str(media),
                    "-lavfi",
                    "[0:v][1:v]ssim",
                    "-f",
                    "null",
                    "-",
                ],
                f"{stem}-ssim",
            )
            row["ssim"] = [
                line
                for line in (output / f"{stem}-ssim.stderr").read_text().splitlines()
                if "SSIM" in line
            ]
            row["status"] = "complete"
            save(output / "candidates.json", report)
        report["status"] = (
            "complete"
            if all(
                r["status"] == "complete"
                and r["contract_pass"]
                and r["cache_conditions_pass"]
                and r["encoder_pass"]
                and bool(r["ssim"])
                for r in report["runs"]
            )
            else "partial"
        )
    except (Exception, KeyboardInterrupt) as error:
        report["error"] = str(error)
    finally:
        report["elapsed_seconds"] = time.monotonic() - started
        report["medians"] = {
            key: statistics.median(
                r["subprocess_seconds"]
                for r in report["runs"]
                if r["status"] == "complete" and r["case"].rsplit("-r", 1)[0] == key
            )
            for key in {
                r["case"].rsplit("-r", 1)[0]
                for r in report["runs"]
                if r["status"] == "complete" and r["case"] != "warmup"
            }
        }
        save(output / "candidates.json", report)
    print(
        json.dumps(
            {
                "status": report["status"],
                "evidence": str(output),
                "medians": report["medians"],
                "error": report.get("error"),
            }
        )
    )
    return 0 if report["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
