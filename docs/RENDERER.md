# Rendering: one timeline, one composition

Every film is schema 3 and renders through Remotion, in the Player and in the MP4. FFmpeg probes, muxes and
verifies (`ffmpeg.py`) and draws no picture. Remotion is visual rendering, not generated character animation, a
paid service or a second production state store. Finished films from before schema 3 are read by
`domain/archive.py` and never rendered.

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

- `project.json` supplies fps/canvas/total duration. `work/storyboard.json`
  supplies content and, when no edit exists, the legacy contiguous integer shot
  allocations. `work/edit.json` supplies the authoritative order, spans, motion,
  transitions, accents, text timing and grade once it exists; the effective
  board is derived, never written back over the storyboard. Existing approved
  source selection is resolved first.
- An outgoing shot's `dissolve_frames` are extra handles. The next shot starts at
  its declared frame; no transition subtracts frames from the allocated film.
- `camera_path` preserves normalized available-crop x/y. `camera_keyframes` are
  explicit local integer frames, ordered from zero, within shot+handles. A hold
  can be followed by movement without inventing subject motion.
- `post_effects`: contrast1–1.2, saturation0.7–1.3, brightness0.9–1.1, vignette0–0.3.
  Legacy optional `transition`: fade/wipe_left/wipe_right on the outgoing handle.
  Edit transitions are a separate contract (`cut`, `fade`, wipes, dip to black or
  white, whip pan, push, slide) owned by the incoming shot; their handle is the
  overlap with the previous plate. Unknown or unsupported settings fail; FFmpeg
  legacy rejects Remotion-only controls.
- Edit motion is `hold`, `push_in`, `pull_back`, `pan_left` or `pan_right` with
  scale 1.00–1.30 and normalized anchors. Accents are `punch_in`, `flash` and
  `light_leak`; text animates with `fade`, `type_on`, `slide_up`, `pop` or
  `kinetic_words`; split panes use `row`, `column` or `grid`; grade presets are
  `neutral`, `warm-night`, `clean-day`, `monochrome`, `vivid` and `film-fade`,
  with the old sliders as advanced overrides.
- `request.mjs` validates the edit payload and refuses a base render with more
  than three flash accents in any one-second window. This is the photosensitivity
  limit, not merely a report warning.
- Graphics spec sets `renderer: "remotion"`, `design: "joint-v1"`; brand is the
  selected `filmstrip`, `plate: false`, so opening/credits render one identity.
  Legacy Pillow specs and earlier logo releases remain available, not rewritten.
- Titles are drawn inside the film. `titles.plan_titles` lays the opening,
  captions, credit cards and lockup out as integer-frame windows (shot-bound
  captions follow the edit's timing), and `Film.jsx` draws them with
  `Titles.jsx` over `BaseFilm`. FFmpeg muxes the original audio once. Output is
  H264/yuv420p/AAC/faststart.
- A spec with `package: "title-v1"` plans a `title` window (0 to 5 s) and an `end_card`
  window (0 to 10 s) instead. `title_assets` needs no filmstrip mark for it, the logo may
  be null, and text keeps clear of the edges by `timing.titleInsets`: 5 % in landscape,
  12 % top and bottom in portrait. A spec with no `package` is `joint-v1`, byte for byte.
- The titles review renders stills of that same composition (`stills` request
  kind, Remotion `renderStill`) at every opening phase and the middle of every
  other window. It needs no base movie. Renderer source, locked dependencies,
  font bytes, props, selected images, the planned titles, the cut and the
  resolved identity are content-bound. The browser binary is deliberately not
  hashed: a Chrome security update must not revoke a reviewed preview, and the
  renderer still refuses to start without a local executable. Corrupt cache is an
  error, never an excuse to silently invent a new accepted version.
- Only selected image bytes are copied into flat renderer-public staging. Original
  media, reference photos, credentials and project artifacts are not web-served.
- Renderers publish versioned outputs without overwriting an earlier delivery.
  Existing preview/proof/graphics gates and durable provider ledger remain in charge.

## Live Player and preview approval

`renderers/remotion/src/Film.jsx` is the one film composition: `BaseFilm.jsx`
with the planned titles from `Titles.jsx` drawn over it. The renderer registers
it in `index.jsx`; the Studio imports the same files through
`frontend/src/baseFilm.ts` and Vite dedupes React and Remotion to one copy. The
Player shows the titles at their planned frames, with a "Show titles" toggle. The
Player gets `GET /api/projects/<slug>/preview`: the effective renderer shot
fields, the matching edit decision and grade, selected-still URLs, native split
pane sources, the planned titles (or a note saying why there are none yet) and
the source audio. A missing still keeps its span and is marked
as a placeholder, never dropped. `tests/test_timing_parity.py` loads `timing.mjs`
with Node and compares its constants, enums, bounds, allocation acceptance and
legacy camera endpoints with the Python models and renderer;
`renderers/remotion/tests/edit-primitives.test.mjs` pins every edit primitive and
the flash refusal.

**A local Chrome or Chromium is required, and Remotion's headless shell is not pinned.** The shell is a
150 MB per-platform download that needs consent and saves at most about 20 %, and the candidate list plus
`REMOTION_CHROME` already covers Mac and Linux. The Library says when a render tool is missing. Revisit this
when someone without Chrome appears.

A Studio preview job writes `work/preview-review.json` itself, binding the movie
bytes to the current storyboard, proof set, brand and renderer revision, so the
preview approval is available as soon as the render finishes. Delivery for a
film with intro and credits is two steps: **Check titles** renders the review
stills (seconds, not a film), and after the titles approval a **final** render
draws the pictures and the reviewed titles in one pass. The final therefore needs
the `stills` and `graphics` approvals, and refuses titles that no longer hash to
the reviewed ones. A titles review made by the old compositor (`method` absent) is refused, and the titles are checked again; only
the CLI's `legacy/` still reads or makes one.

## Primitive samples

`docs/primitives/` contains two-second visual samples for every edit transition,
accent, split layout, text animation and grade preset. They are rendered through
the production `BaseFilm` and `timing.mjs` at 480×270, 24 fps and 48 frames; the
manifest records their hashes. `node docs/primitives/render_samples.mjs`
regenerates missing clips (it refuses to overwrite an existing sample). The
gallery is `docs/primitives/index.html`; the contact sheet is
`docs/primitives/contact-sheet.png`.

## Acceptance is more than tests

Verify exact frames/canvas/fps, original source integrity, audio duration/alignment,
actual transitions and keyframe trajectories, alpha, current gate bindings and a
clean full decode. Inspect representative actual backgrounds and the final contact
sheet; review text/props/face clearance. Keep direct playback with sound separate:
signals and stills cannot prove musical pacing or a continuous audiovisual watch.

Production drafts: post-editor proposes purposeful movement/grade; visual-director
checks style; film-finisher executes; critic sees actual pixels; director integrates.
One bounded repair normally, no filter checklist, flashing or automatic beat cuts.

## Workers, served stills and half-size previews

A render with several chunks left runs several browsers, one `render.mjs` process per
list: half the cores, at most 4, one fewer for each 600 MB short of free memory, and never
more than the chunks left. `STUDIO_RENDER_WORKERS` overrides it. The machine lock is taken
once for the whole render. The bundle is built first by `--bundle-only`. One worker failing
or stalling ends the rest and names itself; nothing retries silently.

`--serve-assets` loads stills from a loopback server for that one run, so the bundle holds
code only and a new still never rebundles. The server answers this computer alone and
refuses anything outside the selected directory. The request body and its hash do not
change, because the sources are added at run time. The bundle comes from a second such
server, because Remotion serving a folder itself takes the first free port from 3000 per
chunk and several renderers would reach each other's servers.

Previews render at 960×540 (540×960 portrait); bases and finals are untouched, so a preview
shares no chunks with a base. A preview labels any shot whose still is missing or stale
with a plate, names it, and cannot be approved. Frame checks skip frames inside a planned
dip, flash or crop cut, and report them as `expected`. A final's chunks live in a store
named by its own keys: a killed final resumes from it and any failure it survives clears
it, except broken frames, which keep it as evidence. `STUDIO_RENDER_GL` passes a GL mode to
Chrome and is recorded in the report; it is off by default.

## Depth, sharper stills and embedded type

`depth.py` estimates a still's depth in a private environment (Depth Anything V2 Small,
Apache-2.0, at a pinned revision), set up only on the owner's click. `work/depth/<still
sha>-<tools>-v<n>/` holds three feathered layers. Far covers the frame, so moving the others
never shows a hole, and behind each nearer layer the picture is replaced by the pixels
around it, so what a move uncovers is background and not the subject's edge a second time. `grade.look.depth` turns it on for a film and `depth: false` keeps one
shot flat. A render makes any missing layers itself where the tools are set up, and otherwise refuses
rather than draw a still flat without saying so; a preview's stand-in plate and the Player stay
flat. A new film starts at `new_films.depth` (0.6, the owner's choice from the real comparison)
only where the tools are set up, recorded at intake in `work/starting-look.json`, so an existing
film stays off.

A sharper still (`upscale.py`) is a journaled 2× version of a selected still with the same
`input_hash`, so the renderer simply stages whichever is selected.

`renderers/remotion/fonts/` holds Inter, Fraunces and Bebas Neue (OFL, latin subsets).
`grade.typeface` and a titles spec's `typeface` name one. A character outside the subset falls
back to the system stack. The renderer revision hashes these files, never this computer's fonts.
