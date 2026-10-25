# Rendering: one timeline, two compatible backends

New schema-3 productions always use Remotion; the legacy creation switch has been
retired. Legacy schema-1 project JSON that omits `renderer_backend` keeps its
original FFmpeg path and remains readable/renderable; a schema-3 document without
the field is Remotion, because schema 3 is the native form. Remotion is visual
rendering, not generated character animation, a paid service or a second
production state store.

## Local dependencies

Node, FFmpeg/ffprobe and an existing local Chrome/Chromium executable are required.
`uv run studio` installs the locked renderer package on first launch when it is
missing; the same install, for diagnosis or CI, is:

```sh
npm ci --prefix renderers/remotion --ignore-scripts --no-audit --no-fund
npm test --prefix renderers/remotion
uv run pytest
uv run ruff check .
```

The launcher only runs `npm ci --ignore-scripts`; it never downloads a browser,
opens a paid provider or invokes `npx`. The Film screen repeats the capability
check and can retry the install from the GUI.

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
  Renderer source, locked dependencies, font bytes, props, selected images and the
  resolved identity are content-bound. The browser binary is deliberately not
  hashed: a Chrome security update must not revoke a reviewed preview, and the
  renderer still refuses to start without a local executable. Corrupt cache is an
  error, never an excuse to silently invent a new accepted version.
- Only selected image bytes are copied into flat renderer-public staging. Original
  media, reference photos, credentials and project artifacts are not web-served.
- Renderers publish versioned outputs without overwriting an earlier delivery.
  Existing preview/proof/graphics gates and durable provider ledger remain in charge.

## Live Player and preview approval

`renderers/remotion/src/BaseFilm.jsx` is the one still-film composition. The
renderer imports it from `index.jsx`; the Studio imports the same file through
`frontend/src/baseFilm.ts` and Vite dedupes React and Remotion to one copy. The
Player gets `GET /api/projects/<slug>/preview`: the renderer's shot fields,
selected-still URLs and the source audio. A missing still keeps its span and is
marked as a placeholder, never dropped. `tests/test_timing_parity.py` loads
`timing.mjs` with Node and compares its constants, enums, bounds, allocation
acceptance and legacy camera endpoints with the Python models and renderer.

A Studio preview job writes `work/preview-review.json` itself, binding the movie
bytes to the current storyboard, proof set, brand and renderer revision, so the
preview approval is available as soon as the render finishes. The final render
still requires the `stills` approval. Schema 3 selects Remotion even when a
migrated document no longer carries the legacy `renderer_backend` field; an
explicit backend wins for older schema-1 projects.

## Acceptance is more than tests

Verify exact frames/canvas/fps, original source integrity, audio duration/alignment,
actual transitions and keyframe trajectories, alpha, current gate bindings and a
clean full decode. Inspect representative actual backgrounds and the final contact
sheet; review text/props/face clearance. Keep direct playback with sound separate:
signals and stills cannot prove musical pacing or a continuous audiovisual watch.

Production drafts: post-editor proposes purposeful movement/grade; visual-director
checks style; film-finisher executes; critic sees actual pixels; director integrates.
One bounded repair normally, no filter checklist, flashing or automatic beat cuts.
