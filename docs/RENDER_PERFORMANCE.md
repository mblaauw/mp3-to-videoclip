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
