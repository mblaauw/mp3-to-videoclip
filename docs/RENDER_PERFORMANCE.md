# Local renderer diagnostics and benchmark

Opt-in, synthetic, no production access or paid calls:

```sh
uv run python scripts/benchmark_render.py --output-dir /absolute/new/benchmark-directory
```

The directory must not exist. Install the pinned renderer separately first; this
command never installs packages or downloads a browser. `REMOTION_CHROME` selects
an already-installed browser. Outputs, inputs, logs and `benchmark.json` are kept.
Default: 12 seconds, 1920×1080, 24 fps, holds, cameras and dissolves; a separate
two-second real alpha caption uses the normal ProRes 4444 graphics pipeline.
Two independent cold/warm pairs per kind use separate bundle cache roots. Warm
means bundle reuse, not output reuse; OS/browser caches are not controlled. Each
pair uses equivalent inputs and renderer settings, with exclusive output names.
`--seconds` accepts 10–20; `--budget-seconds` caps total render time (default 480,
maximum 600). Interrupted/failed runs retain a partial report and all evidence.
Cleanup has a separate bounded grace period (up to seven seconds). Each command
inherits a cryptographic per-run environment marker; only matching processes on
the current UID can be signalled, with revalidation immediately before each
signal. This covers Remotion's environment-inheriting detached Chrome children,
not arbitrary programs that scrub their environments. Direct children are reaped
even if process inspection fails; uncertainty is reported, not silently accepted.
No raw process environments are written to reports or logs.

`benchmark.json` records machine/settings, exact synthetic request hashes, cache
state, per-run throughput, timings and grouped medians/dominant measured phase.
Request hashes differ with output names; compare settings and pair identity, not
hash equality. No private production content is included here.

## Interpretation

The renderer sidecar separates bundle, composition setup and `renderMedia` wall
time. `onStart` supplies actual resolved concurrency and parallel encoding.
`onProgress` supplies `renderedDoneIn` / `encodedDoneIn` **in milliseconds**;
missing values remain null. These completion durations can overlap and must not
be added or subtracted to invent isolated encoding cost. `renderMedia` includes
its own setup/teardown; it is not pure frame capture time.

The supported `ffmpegOverride({type,args})` observer returns the original args
unchanged and records only encoder and format flags, not private paths. Actual
encoder is never inferred from hardware availability. Capture mode is observed
from format flags or labelled unavailable. Fallback reason is unavailable because
the pinned API exposes no fallback event; this is not evidence a fallback occurred.
PNG capture, software codec, pixel format, quality and concurrency defaults are
unchanged. No encoder optimisation is part of this task.

Python reports expose `perf_counter` mux and output-verification seconds, renderer
sidecars, graphics element/track/composite/verification times. ProRes-to-qtrle
conversion timings live next to the converted clip in `.timings.json`; these are
historical creation times, not a claim that a warm cache reran conversion.

## T8 bounded baseline (28 October 2026)

A repeat on the frozen T8 renderer completed **two cold and two warm runs for
each kind**. The earlier partial series is retained separately below:

| Case | Median cold/warm subprocess wall | Median cold/warm renderMedia |
| --- | --- | --- |
| 12 s 1080p base | 47.49 / 47.10 s | 20.83 / 20.80 s |
| 2 s 1080p alpha caption | 6.00 / 5.17 s | 4.63 / 4.52 s |

The complete report is in local `t8-render-final/benchmark.json`, including exact
renderer-source hashes. Base process overhead remains the dominant measured
category and is unexplained. This baseline predates the opt-in T9 profile and
the benchmark-owned-process cleanup correction; it is not final-snapshot
acceptance of those later changes.

macOS 26.6.2 arm64, 8 logical CPUs, Node 26.7.0, Remotion 4.0.536,
concurrency 2. No hardware-encoder experiment was performed.

| Case | Completed cold/warm | Median cold/warm subprocess wall | Median cold/warm renderMedia |
| --- | --- | --- | --- |
| 12 s 1080p base | 2 / 1 | 52.53 / 46.95 s | 20.77 / 20.72 s |
| 2 s 1080p alpha caption | 2 / 2 | 6.51 / 5.18 s | 4.92 / 4.54 s |

Base baseline is **partial**: the fourth subprocess exceeded the deliberately
short 180-second aggregate budget. Its output may exist, but is not counted as a
completed run. Base process overhead (outside the renderer's measured total) is
substantial and unexplained; do not call it encoding time. Alpha observed
`prores_ks`, base observed `libx264`; both used `image2pipe`, resolved concurrency
2 and parallel encoding. Exact timing values and retained outputs are in the
local benchmark evidence directories, not production folders. This sample does
not justify changing any quality or concurrency default.

## T10 visual identity and selected-asset publication

The silent base cache now uses a versioned identity containing output width,
height, fps, total frames, compiled inputs and implementation revision, not the
whole administrative project record. A budget-only top-up reuses visuals while
audio is still muxed and verified for each requested output. Preview flags,
selected bytes, native panes, camera, grade, text, timing and embedded brand data
remain dependencies. Cache hits require both the full recorded key and movie
SHA-256; missing, malformed or mismatched receipts fail closed without repair.

The accumulating `work/remotion-assets` staging cache is preserved. Each render
publishes an immutable manifest-keyed sibling directory containing exactly the
compiled shot images and native pane images. Publication uses a process lock
and a complete-directory atomic rename; existing publications and staged bytes
are verified, never rewritten or cleaned. Failed private publication staging is
retained for investigation. Node receives only this selected directory, so old
image versions cannot force rebundling. Node's bundle identity still combines
renderer code and selected asset bytes: code-only bundle reuse is deliberately
not introduced because it is unsafe without changing the bundle serving model.
Silent-movie creation has its own per-key cross-process lock through validation
and receipt publication. Concurrent consumers wait for a complete receipt rather
than racing the same request/movie paths. Final audio muxes occur after release;
no project-state lock is held during the render.

Reports expose `visual_cache_hit`; on a hit, `renderer_report` is null and any
creation-time renderer timers are labelled `historical_renderer_report`, rather
than presented as work performed by the current render. No encoder defaults or
Node renderer code changed. Tests mock rendering/muxing and make no provider or
browser calls.

## T9 bounded candidate experiments (28 October 2026)

No production default was changed. The opt-in command is:

```sh
uv run python scripts/benchmark_render_candidates.py --baseline-dir /absolute/t8-render-final --output-dir /absolute/new/t9-evidence --suite all --budget-seconds 660
```

The script uses the exact T8 12-second synthetic input (288 frames, 1920×1080,
24 fps, holds, camera moves and two 12-frame dissolves). One excluded warm-up
populates a single bundle cache; every measured completed candidate reported
`bundle_cached=true`. Runs are serial, with reversed replicate order. Browser
and OS caches remain uncontrolled. Requests, asset hashes, FFmpeg observations,
probe output, full-frame SSIM logs and partial results are retained.
`--suite software` or `--suite hardware` selects a smaller replicated set.
The aggregate subprocess budget defaults to 660 seconds (maximum 900); this is
opt-in, never a Studio job. An existing explicit executable in the baseline is
required before any probe, so the raw CDP probe never requests an implicit browser.
Measured runs must confirm a warm bundle and the actual expected encoder. A
partial or contract-failing series exits nonzero and preserves its evidence.

| Software concurrency | Completed replicates | Subprocess wall | renderMedia |
| --- | --- | --- | --- |
| 1 | 1 | 18.46 s | 17.77 s |
| 2 | 1 | 48.60 s | 20.85 s |
| 3 | 2 | median 45.72 s | median 24.71 s |

These are incomplete observations, **not qualified speedups**. The run was
interrupted by signal 15 during the second concurrency-2 replicate, after
228.79 reported seconds; the enclosing tool also reported a timeout. The second
concurrency-1 replicate and both hardware candidates were not reached. Large
subprocess overhead outside renderer timers remains unexplained. All four
completed measured outputs passed probe checks for exact dimensions, 288 decoded
frames, 24 fps, H.264/yuv420p, BT.709 and no audio. Full-frame SSIM against the T8
warm baseline was 1.000000 in every channel, including the dissolve frames.
This synthetic result does not replace real-production visual acceptance.

A local read-only CDP capability probe returned
`Protocol error (Page.remotionCreateFramePool): 'Page.remotionCreateFramePool' wasn't found`.
Installed Remotion 4.0.536 explicitly handles this capability failure by falling
back to encoded screenshots. Completed candidates independently observed
`image2pipe` and `libx264` in the actual FFmpeg arguments. No patched browser was
installed and no raw-capture performance claim is supported.

`render.mjs --benchmark-profile videotoolbox-20m` is a separate base-only
experiment: PNG capture and BT.709/yuv420p stay unchanged, hardware acceleration
is required, and target bitrate is explicitly 20 Mbit/s with no CRF. Unsupported
hardware must fail rather than silently fall back. Actual encoder is recorded
by the existing FFmpeg observer, not inferred from the profile name. This policy
is not quality-equivalent to the default software policy and was **not rendered
within this budget**. Graphics requests reject the profile; the normal PNG /
ProRes 4444 alpha path is untouched. No GUI surface or default adoption is added.

Evidence: local approved temporary directory `t9-render-candidates-final/`, with
`candidates.json`, per-run requests, sidecars, probes, SSIM logs and output movies.
The earlier `t9-render-candidates/` contains a retained failed probe attempt
(incorrect module import path), not benchmark evidence. Decision: defer raw
capture, concurrency adoption and hardware adoption pending complete replicated
measurements, an explained wall-time gap and human quality acceptance.
