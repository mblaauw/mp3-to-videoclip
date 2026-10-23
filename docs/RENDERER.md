# Rendering: one timeline, two compatible backends

New `clip init` productions always use Remotion; the legacy creation switch has
been retired. Existing project JSON that omits `renderer_backend` keeps its
original FFmpeg path and remains readable/renderable. Remotion is visual
rendering, not generated character animation, a paid service or a second
production state store.

## Local dependencies

Node, FFmpeg/ffprobe and an existing local Chrome/Chromium executable are required.
Install the locked project package with:

```sh
npm ci --prefix renderers/remotion --ignore-scripts --no-audit --no-fund
npm test --prefix renderers/remotion
uv run pytest
uv run ruff check .
```

`REMOTION_CHROME` can select a local executable. The adapter never runs `npx`,
downloads a browser, uploads assets or silently falls back to a different renderer.
The user confirmed free-use eligibility; assess eligibility again if adopting it
for a different organisation. No licence key or font file belongs in git.

## Contracts

- `project.json` supplies fps/canvas/total duration; `work/storyboard.json` supplies
  contiguous integer shot allocations. Derived props are render receipts, not a
  competing editable timeline. Existing approved source selection is resolved first.
- An outgoing shot's `dissolve_frames` are extra handles. The next shot starts at
  its declared frame; no transition subtracts frames from the allocated film.
- `camera_path` preserves normalized available-crop x/y. `camera_keyframes` are
  explicit local integer frames, ordered from zero, within shot+handles. A hold
  can be followed by movement without inventing subject motion.
- `post_effects`: contrast1–1.2, saturation0.7–1.3, brightness0.9–1.1, vignette0–0.3.
  Optional `transition`: fade/wipe_left/wipe_right on the outgoing handle. Unknown
  or unsupported settings fail; FFmpeg legacy rejects Remotion-only controls.
- Graphics spec sets `renderer: "remotion"`, `design: "joint-v1"`; brand is the
  selected `filmstrip`, `plate: false`, so opening/credits render one identity.
  Legacy Pillow specs and earlier logo releases remain available, not rewritten.
- Remotion creates silent base visuals and transparent ProRes graphics. FFmpeg
  muxes the original audio once, assembles existing sparse alpha windows and copies
  base AAC packets verbatim into the final. Output is H264/yuv420p/AAC/faststart.
- Preflight decodes the actual cached Remotion overlay, not a Pillow approximation.
  Current implementation, locked dependencies, browser/font bytes, props, selected
  images and resolved identity are content-bound. Corrupt cache is an error,
  never an excuse to silently invent a new accepted version.
- Only selected image bytes are copied into flat renderer-public staging. Original
  media, reference photos, credentials and project artifacts are not web-served.
- Renderers publish versioned outputs without overwriting an earlier delivery.
  Existing preview/proof/graphics gates and durable provider ledger remain in charge.

## Acceptance is more than tests

Verify exact frames/canvas/fps, original source integrity, audio duration/alignment,
actual transitions and keyframe trajectories, alpha, current gate bindings and a
clean full decode. Inspect representative actual backgrounds and the final contact
sheet; review text/props/face clearance. Keep direct playback with sound separate:
signals and stills cannot prove musical pacing or a continuous audiovisual watch.

Production drafts: post-editor proposes purposeful movement/grade; visual-director
checks style; film-finisher executes; critic sees actual pixels; director integrates.
One bounded repair normally, no filter checklist, flashing or automatic beat cuts.
