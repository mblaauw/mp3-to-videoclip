# Local renderer diagnostics and benchmark

## How a base film renders now (31 October 2026)

A base, preview or final renders **one chunk per shot** through one browser with one tab, and joins them
without re-encoding. See `.opencode/tasks/render-speed.md` for decisions and the acceptance record.

- **Reuse:** previews and bases reuse any chunk whose key matches, so changing one shot took 34 s instead of
  12–14 minutes on Tree of Love. An interrupted render resumes. Finals render every chunk fresh.
- **Keys** (`chunks.py`) take everything in a shot's compiled entry except named position fields, made relative
  to the chunk, and written reasons. A new field invalidates by default.
- **Capture:** previews and bases use JPEG at quality 95. Finals and alpha graphics stay PNG.
- **Tabs:** one, because above that Remotion cycles the browser's tabs every 200 ms so each can capture.
- **Broken frames** (`framecheck.py`): a scan flags frames unlike both neighbours, and a fresh render of each decides.
  A broken chunk is set aside and rendered once more; a second failure fails the render and names the frames.
- **Stalls:** a render whose phase and frame count stop moving is ended with its browser. A closed lid does this.
- **One at a time:** a machine-wide lock makes a second render wait. Chunks live in `work/remotion-chunks/`, each with a
  receipt, and nothing is cleaned up.

| Tree of Love, Editor's cut | Time |
| --- | --- |
| Full render | 7 min 16 s |
| One shot changed | 34 s |
| Two lengths changed, 25 shots moved | 66 s |

The sections below are the earlier history. Statements there about defaults describe those dates.

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
Bundle cache v2 verifies a full-SHA key, exact file/directory membership and every
file's SHA-256 before reuse. Missing, malformed, partial, symlinked or corrupt
entries fail closed without rebuilding, overwriting or deleting the evidence.
New bundles use unique private staging and validated, serialized atomic
publication. Existing v1 caches stay untouched. A crash-left publication lock
fails visibly; recovery is not automatic. The lock coordinates cooperating
publishers, not hostile external filesystem writers.
Silent-movie creation has its own per-key cross-process lock through validation
and receipt publication. Concurrent consumers wait for a complete receipt rather
than racing the same request/movie paths. Final audio muxes occur after release;
no project-state lock is held during the render.
Selection publication deliberately copies bytes for isolation. It reduces the
asset set copied into each bundle, not total existing disk use; publications and
all historical staging/bundle entries are retained. No cleanup or global storage
saving is claimed.

Reports expose `visual_cache_hit`; on a hit, `renderer_report` is null and any
creation-time renderer timers are labelled `historical_renderer_report`, rather
than presented as work performed by the current render. No encoder defaults or
Node renderer code changed. Tests mock rendering/muxing and make no provider or
browser calls.

## T9 bounded candidate experiments (28 October 2026)

**Decision: keep every production default unchanged.** Encoder, capture,
concurrency, resolution, fps and quality remain as before. The opt-in command is:

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

### Completed replicated comparisons

The resumed synthetic series completed two measured runs per candidate, plus an
excluded warm-up. All runs confirmed the expected encoder, warm bundle, 288
frames, 1920×1080/24 fps, BT.709/yuv420p and no audio:

| Synthetic candidate | Median subprocess wall | Median renderMedia | Decoded SSIM vs software baseline |
| --- | --- | --- | --- |
| libx264, concurrency 1 | 18.64 s | 17.88 s | 1.000000 |
| libx264, concurrency 2 | 46.82 s | 20.66 s | 1.000000 |
| libx264, concurrency 3 | 47.21 s | 24.78 s | 1.000000 |
| h264_videotoolbox, concurrency 2, 20M | 46.63 s | 20.51 s | 0.999306 |

VideoToolbox encoder selection was observed in actual FFmpeg arguments; physical
device utilization was not measured. This bitrate policy is not equivalent to
the software quality policy, and showed no material subprocess improvement.

A second serial series used SHA-verified copies of three selected real stills
from the latest production in a separate synthetic 12-second test cut. The
original image bytes and production timeline were not changed. Two measured
runs per software candidate yielded:

| Real-image candidate | Median subprocess wall | Median renderMedia |
| --- | --- | --- |
| concurrency 1 | 45.85 s | 34.70 s |
| concurrency 2 | 46.43 s | 32.71 s |
| concurrency 3 | 46.08 s | 32.69 s |

The synthetic concurrency-1 improvement did **not** generalize. Exact decoded
frame hashes also differed between real-image outputs, including same-setting
replicates: 93/288 differing frames for most comparisons to the first c2 run;
177/288 for the second c3 run. SSIM was near—but not exactly—one. Reduced-size
visual samples showed no conspicuous framing/dissolve/artifact difference, but
that does not override failed exact parity or establish temporal quality.
No encoder/concurrency candidate qualifies for adoption. Pixel components were
not changed; the cause of real-image rerender variation remains unestablished.

An external, opt-in Node resource probe observed a TCP server and pipe resources
after final JSON, followed by delayed process exit. It observed no referenced
timeout in that tail. This narrows the investigation but does not establish a
root cause; no forced exit, blanket timer unref, browser replacement or dependency
patch was introduced. Do not attribute the whole wall-time gap to encoding.

Completed evidence is retained locally in `t9-resumed-comparison/` and
`t9-real-image-comparison/`, including per-source hashes, probes, logs, copied
inputs, outputs and frame-hash comparisons. The following partial trial remains
historical, not the basis for a claimed speedup.

### Initial partial trial

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
is not quality-equivalent to the default software policy and was not reached in
the initial partial trial; the resumed series above did exercise it. Graphics requests reject the profile; the normal PNG /
ProRes 4444 alpha path is untouched. No GUI surface or default adoption is added.

Evidence: local approved temporary directory `t9-render-candidates-final/`, with
`candidates.json`, per-run requests, sidecars, probes, SSIM logs and output movies.
The earlier `t9-render-candidates/` contains a retained failed probe attempt
(incorrect module import path), not benchmark evidence. Decision: defer raw
capture, concurrency adoption and hardware adoption pending complete replicated
measurements that generalize, an explained wall-time gap and quality acceptance.

## Final runtime/cache acceptance

A real local two-second fixture verified budget/history-only reuse of the same
silent movie, camera invalidation with bundle reuse, selected-pixel invalidation,
unchanged source bytes and identical output audio packets on reuse. Each selected
publication contained one 614-byte fixture image; 1,179,648 bytes of deliberately
unused history stayed outside those publications and remained preserved. This is
not a production storage-reduction or full-film speedup claim.

A final real 48-frame 1080p ProRes 4444 alpha render used the unchanged graphics
concurrency 2, retained alpha extrema 0/255, and matched the T8 frame-24 decoded
RGBA bytes exactly. Checkerboard review showed no full-frame opaque black matte.
Full engine/golden tests additionally cover timing, compositing and audio checks.
