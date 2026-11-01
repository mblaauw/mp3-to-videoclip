# Make it move — plan

**Proposed** 1 Nov 2026 for owner approval; base `main` at `c1414a3`.

**Objective:** the film stops reading as a slideshow. Every push-in has enough source
pixels, pictures with people in them get depth that breathes, motion follows the song
instead of a smoothstep, titles and lyrics are set in a face the renderer actually
embeds, and, per shot and by choice, a bought clip replaces the still. Phase C of the
31 Oct assessment. Decisions 2, 3 and 11 are already given: depth goes in as an optional
look, off for existing films; clips are opt-in per shot, journaled like a still, and
land after depth. Order inside the phase: cheap and visible first (resolution, grain,
type), then depth, then motion and look options, then clips.

## What the code showed

**Resolution.**

- A film's picture size is `Project.image_size`: `native_size` when set, else 1536×864
  (`models.py:136-138`); new films get `profiles.default_size`, 1376×768 for the stored
  model (`profiles.py:81-82`). The validator allows up to 4096 px in steps of 16
  (`models.py:8-10`, `27-49`).
- The size is part of the paid spec (`production/image_specs.py:139`, `:289`), so it is
  inside every still's `input_hash` (`generation.py:177`), and `resolved_assets` refuses
  a selected still whose `input_hash` is not the current spec's
  (`production/assets.py:152-153`). Raising an existing film's native size would
  un-select every still it owns. A larger native size is therefore for new films only;
  existing films need a derived version.
- A version is `{version, path, sha256, input_hash, task_id}` and can never be
  overwritten (`production/assets.py:174-194`). `finish_image` writes
  `assets/<shot>/v00N-<uuid>.jpg` and verifies it with PIL (`generation.py:453-501`).
  `begin_task` branches on the journal `kind` (`generation.py:384-445`) and `recover`
  dispatches by kind (`generation.py:749-760`), so a new kind fits the journal without
  touching how money is reserved.
- `quote_images` requires the model schema's `taskType` const to be `imageInference`
  (`generation.py:164-165`). `RunwareClient.submit` accepts any `*Inference` task and
  asks for cost (`providers.py:306-307`), but calls a result without `imageURL`
  pending (`providers.py:291`, `:322`), and `download` verifies the bytes as an image
  under a 50 MB cap (`providers.py:35`, `:376`). An upscale task returns an image, so it
  fits as is; a clip does not.
- In the composition one `Img` fills the camera rect with `objectFit: cover`
  (`BaseFilm.jsx:253-256`); zoom is capped at 1.3 (`timing.mjs:374`) and crop cuts at
  1.6 (`models.py:878`). At 1.3 a 1376 px still gives about 1058 source pixels across a
  1920 px frame. (`render.py:59`, `PLATE_UPSCALE = 3`, is the legacy FFmpeg path and
  does not apply to Remotion films.)

**Depth.**

- `ShotLayer` draws exactly one picture inside one camera rect, with the look transform
  on the rect (`BaseFilm.jsx:208-260`). Nothing in the renderer knows a depth map.
- The lyric tools are the pattern for a private local tool: own lock file, `uv venv`
  plus `uv pip sync`, a worker run with `python -I`, a `status()` with a reason, a cache
  under `~/.cache/mp3-to-videoclip/`, jobs through the runner
  (`lyric_tools.py:48-54`, `:126-141`, `:236-248`; `api/track.py:109-117`).
- Chunk keys are subtractive: everything in a shot's compiled entry except relative
  positions and written reasons, and "a new field invalidates by default"
  (`chunks.py:1-18`). `compile_shots` stages each selected still by its sha and builds
  the entry (`remotion.py:41-46`, `:467-480`), so a layer file added to the entry is in
  the key for free, and a shot without it hashes as today.
- `grade.look` is serialised only when set (`models.py:1005-1007`); `timing.mjs`
  validates its three keys (`:676-683`) and `lookState` is a pure frame function
  (`:805-838`). That is the shape depth must follow.
- The first-cut record: Depth Anything V2 Small, Apache-2.0, about 95 MB, on five
  stills; "depth maps separate people from backgrounds cleanly". The Base and Large
  variants and DepthFlow are excluded by licence.

**Motion.**

- `EditMotion.easing` is `linear | smoothstep` (`models.py:834`), scale 1.00 to 1.30;
  accents are `punch_in | flash | light_leak` (`models.py:791`) with amount up to 1.2 and
  duration up to 24 frames; `editCamera` (`timing.mjs:361-386`) and `accentState`
  (`timing.mjs:840+`) are the pure counterparts.
- `cut_material` offers sections, lines, changes and beats, never downbeats
  (`edits.py:865-905`); `deep_analysis` computes downbeats with a strength
  (`deep_analysis.py:427-430`) and nothing reads them; `first_cut.suggest` snaps joins to
  three tiers (`first_cut.py:79-89`). Phase B's song map is where downbeats, bar grid
  and energy arrive; this phase consumes it and does not define it.
- Grain is one 256 px SVG noise tile (`timing.mjs:797`, `BaseFilm.jsx:196-201`) moved
  per frame by `grainX/grainY` (`timing.mjs:834-835`) as a repeating background
  (`BaseFilm.jsx:278-287`). The repeat is what shows on flat areas at 1080p.
- `docs/primitives/render_samples.mjs` renders every primitive at 480×270 through the
  production composition and refuses to overwrite a sample.

**Type.**

- The composition names Avenir Next (`BaseFilm.jsx:20`) and embeds nothing:
  `title_assets` passes `font: None` with a note that `.ttc` is not a portable webfont
  (`remotion.py:974-992`). `Titles.jsx:82-110` already turns a `data:` font into an
  `@font-face` and delays the render until it has loaded, so the loader exists.
- `implementation_hash` hashes `resolve_font()[0]` (`remotion.py:117-138`), which is
  `/System/Library/Fonts/Avenir Next.ttc` on a Mac and the bundled OFL Inter elsewhere
  (`graphics.py:146`, `:150-155`, `:358-376`). The renderer revision therefore depends
  on the machine and on a file the composition never loads. Inter already ships at
  `src/mp3_to_videoclip/fonts/` with its OFL; the frontend self-hosts Schibsted Grotesk
  through `@fontsource-variable` (`frontend/src/main.tsx:3`, `frontend/package.json:14`).
- The golden pins `remotion_titled_request`, which carries `titles_input(...)` and so
  the `font` value (`tests/test_contract_golden.py:148-158`). A spec without a typeface
  must keep producing `font: None`.
- Text sizes are height-relative and margins width-relative (`BaseFilm.jsx:78-83`,
  `:96`, `:108`); there is no safe area for 9:16.
- Lyric timing stores a start and end per line (`domain/lyric_timing.py:18`,
  `lyric_tools.py:304-330`), but the heard words with their own times are cached in
  `work/heard/` (`lyric_tools.py:236-248`, `heard_words` at `:151-163`). `EditText` is one
  string with in and out frames (`models.py:891-900`); `kinetic_words` exists as an
  animation (`models.py:792`) and splits the string evenly.

**Clips.**

- `RenderShot` is shot, image, edit, grade (`models.py:1089-1095`). The Player gets a
  `src` per shot from `services/preview.player_input` (`api/film.py:215-226`) and plays
  the audio with Remotion's `<Audio>` (`LivePreview.tsx:17`); the renderer uses `Img`
  only. Both sides run Remotion 4.0.536 (`renderers/remotion/package.json`,
  `frontend/package.json:15,18`), which has `OffthreadVideo` and `Video`.
- The stills stage hash binds `{id, image sha}` per resolved shot plus the edit
  (`production/approvals.py:212-217`); a clip must be bound the same way, and only when
  one is selected.
- Assessment Part 2: Runware `videoInference` covers image-to-video, priced per second;
  `costs` already keeps an unpriced task's reservation (`generation.py:914-953`).

**Renderer revision.** Every commit that changes `renderers/remotion/src` changes
`implementation_hash`, which previews and titles reviews bind (render-speed record,
"Any renderer change clears approvals tied to it"). Each PR here does that once, as PR 54
did; the owner re-checks a preview and the titles after merging. Content hashes
(stills, brief, chunk keys, the request bytes) do not move unless a new field is set.

## Decisions for the owner

| # | Question | Recommendation |
| --- | --- | --- |
| D1 | Where do the extra pixels come from? | A journaled 2× **upscale as a derived version** of the selected still, for new and existing films alike. Keep 1376×768 as the native default: it is the size the approved style benchmark was judged at (`profiles.py:66-79`), and a bigger native size changes how the model composes. Offer native 2048×1152 as a per-film intake option to try later, not as the default. |
| D2 | Which upscale model and factor? | Runware's upscale task at factor 2, the model picked in Settings from Phase H's catalogue under the `upscale` capability; until H lands, one settings string. Factor 2 keeps a still under 3000 px and the file under the 50 MB download cap. |
| D3 | Depth as a per-film amount or a per-shot switch? | Both, in that order: `grade.look.depth` 0 to 1 for the film, and a per-shot `depth: false` to flatten a shot (a card, a face filling the frame, a clip). Off for every existing film. |
| D4 | Grain: per-pixel noise or a larger tile? | A **1024 px tile rotated and mirrored per frame**. Per-pixel noise means rasterising a fresh 1080p noise field every frame in software Chrome; the tile costs nothing measurable. Per-pixel only if you still see repetition at full screen. |
| D5 | Which three display faces? | OFL only, self-hosted like Schibsted Grotesk: **Inter** (already bundled; clean-photographic, product-studio), **Fraunces** (photographic-painted), **Bebas Neue** (brand-graphic). One per style preset as the default, all three selectable per film. |
| D6 | First clip model and length? | One image-to-video model from the catalogue (Kling or Gemini Omni Flash through Runware), **5 s clips at the project's fps and canvas**, price per second shown before each batch. The model is a Settings choice so the plan does not hard-code a vendor's model id. |
| D7 | Paid batches for acceptance on a scratch copy? | Please authorise two capped batches, each listed in Acceptance: **upscale up to 10 stills** of Tree of Love at the published price, and **clips for up to 3 shots × 5 s** at the catalogue price, cap stated before the run. Everything else in this phase is $0. |

## Tasks (one commit each, one PR)

### PR C-1, sharper and typed (about a week)

1. **Upscale as a derived version.** `generation.quote_upscale(root, ids, reserve, model)`
   builds one task per selected still against the upscale model's schema: journal kind
   `upscale`, next `version`, the still's own `input_hash` (so selection, staleness and
   `resolved_assets` work unchanged), plus `derived_from: {version, sha256}` and
   `derivation: {kind: "upscale", model, factor}`. `begin_task` gets an `upscale` branch
   with the same guards as images (storyboard approved, no unresolved task on the shot,
   reservation written before the request). `finish_image` records the derived fields;
   `recover` and `costs` know the kind. `record_asset` serialises `derived_from` and
   `derivation` only when present, so every existing `assets.json` is byte-identical.
   Tests with a fake client: quote, finish, recover, no resubmit, lost bytes quarantined.
   Files: `generation.py`, `production/assets.py`, `services/generation.py`. 2 days.
2. **Upscale in the Studio and the report.** `POST /images/upscale/estimate` and
   `POST /images/upscale` on the generate route's decision and authorisation flow
   (`api/images.py:172-214`). Images shows the derived version as `v004 · 2×` beside the
   versions with its price; selecting it is `select_asset` as today; "Make sharper ·
   $0.xx" on the lightbox. `edits.report` warns "soft: push-in past 1.15 on a still
   narrower than 1.2× the canvas" so the Editor and the owner see where it pays. The
   renderer changes nothing: it stages whichever still is selected.
   Files: `api/images.py`, `edits.py`, `frontend/src/stages/Images.tsx`, `cutNotes.ts`. 1.5 days.
3. **Grain tile.** `GRAIN_TILE` 256 to 1024; `lookState` returns a per-frame rotation
   (0, 90, 180, 270) and mirror from `frameNoise` as `grainTransform`; `BaseFilm` draws
   the grain in an oversized rotated layer instead of a repeating background. Render
   time measured on the 10 s synthetic film; over 10 % slower needs a rethink. Grain
   sample regenerated. Files: `timing.mjs`, `BaseFilm.jsx`, `edit-primitives.test.mjs`,
   `docs/primitives/`. 1 day.
4. **Embedded type.** `renderers/remotion/fonts/` with the three OFL faces (D5) and
   their licences; `title_assets` resolves `spec["typeface"]` to a `data:` URL from
   those bytes and keeps `font: None` when the key is absent, so the golden is
   unchanged; `BaseFilm` text layers take `input.typeface` the same way with the current
   stack as fallback; `draft_spec` writes the style preset's face for new films.
   `implementation_hash` hashes the bundled renderer fonts instead of the machine font,
   so the revision stops depending on the computer. Legacy `graphics.implementation_revision`
   is untouched. Files: `remotion.py`, `signature.py`, `Titles.jsx`, `BaseFilm.jsx`,
   `request.mjs`, `docs/RENDERER.md`. 1.5 days.

### PR C-2, depth (about a week)

5. **`depth.py`, a local job.** A private environment under
   `~/.cache/mp3-to-videoclip/depth-tools` with its own `depth_tools.lock.txt` (Depth
   Anything V2 Small, Apache-2.0, CPU and Apple Silicon), on the lyric tools pattern:
   `status()` with a reason, `install()` after saying what it downloads, a worker run
   with `-I`. `depth_for(still)` writes `~/.cache/mp3-to-videoclip/depth/<sha>/depth.png`
   once per still hash, and `layers_for(root, still)` writes a production-local derived
   set `work/depth/<still sha>-<model hash>/{far,mid,near}.png`: three feathered RGBA
   band cut-outs (far is the whole still) with a `layers.json` naming the bands and
   their hashes. Immutable once written, never under `assets/`, never paid.
   `POST /depth/run` over the selected stills as a runner job; `GET /depth` per still.
   Tests with a fake worker as in `test_lyric_tools.py`. Files: `depth.py`,
   `depth_tools_worker.py`, `depth_tools.lock.txt`, `api/images.py`. 2.5 days.
6. **Parallax in the composition.** `FilmLook.depth` 0 to 1, serialised only when above
   zero; `EditShot.depth: bool | None`, serialised only when set. `timing.mjs`:
   `validateGrade` accepts `depth`; `parallaxState(depth, camera, localFrame, shotId,
   width, height, fps)` returns one transform per layer: far 0, mid 0.5, near 1.0 of an
   amplitude of `depth × 1.2 %` of the short side, a push-in becoming a dolly (near
   scales more than far), a pan an orbit (layers slide against each other), a hold the
   slow drift that `lookState` already phases. `BaseFilm` draws three `Img` layers when
   the span carries `depth`. `compile_shots` stages the three layer files and adds
   `depth: {far, mid, near, sha256, model}` to the entry only when the film's look has
   depth and the shot is not flattened; a missing layer set makes the render refuse
   with "run depth for N stills", never a silently flat shot. The chunk key therefore
   includes the layer hashes. `player_input` serves the layer URLs so the Player draws
   the same thing. `request.mjs` validates the field; the parity test pins the bound.
   Files: `models.py`, `timing.mjs`, `BaseFilm.jsx`, `request.mjs`, `remotion.py`,
   `services/preview.py`, `tests/test_timing_parity.py`, `edit-primitives.test.mjs`. 3 days.
7. **Depth in the Studio.** The Film panel's look gains Depth with a status line ("12 of
   38 stills have depth · Make the rest") and a per-shot Flat toggle; Images shows a
   depth badge on a still; the render refusal has its sentence and button. The owner
   watches flat against parallax on the scratch copy (see Acceptance). Files:
   `FilmPanel.tsx`, `Images.tsx`, `nextStep.ts`, `errors.ts`. 1 day.

### PR C-3, motion and look (about a week)

8. **Curves, ramps and impulses.** `EditMotion.easing` gains `ease_in`, `ease_out` and
   `snap` (fast start, long settle); `EditMotion.ramp: {frame, share} | None`, serialised
   only when set, is the share of the travel reached by absolute frame `frame`, so a
   push-in lands its weight on a downbeat; `EditAccentType` gains `impulse`, a camera
   bump that decays like a damped spring (amount 1.0 to 1.1, 2 to 12 frames, optional
   direction). `timing.mjs` mirrors all three in `ease`, `editCamera` and `accentState`;
   both validators refuse a ramp outside the shot and a share outside 0 to 1. Enums and
   bounds pinned in the parity test; samples regenerated. Files: `models.py`,
   `timing.mjs`, `request.mjs`, `edits.py` (report), `baseFilm.ts`. 1.5 days.
9. **The cut uses the song.** When Phase B's song map is present, `first_cut.suggest`
   puts `ramp.frame` on the nearest downbeat inside a push-in in a loud section, an
   `impulse` on a strong downbeat at a section start (at most one per four seconds),
   `ease_out` on holds and `snap` on a chorus entry; `edits.report` warns on an impulse
   off the grid. `editor/edit.md` v4 names the new vocabulary in its technique table.
   Without a song map nothing changes. Files: `first_cut.py`, `edits.py`,
   `director/prompts/editor/edit.md`, eval checks. 1.5 days.
10. **Look options.** `FilmLook` gains `bloom`, `halation`, `flare`, `dust` and `haze`,
    each 0 to 1 and serialised only when above zero. `lookState` returns their per-frame
    parameters (flare anchored by the shot seed and drifting slowly, dust from a second
    sparse tile, haze a vertical gradient, bloom a blurred screen-blended copy, halation
    a warm blurred highlight layer); `BaseFilm` draws them under the text. Each option is
    measured alone on the 10 s synthetic film; anything over 25 % slower is recorded
    and stays off by default. Sliders in the Film panel; the Editor may set them.
    Files: `models.py`, `timing.mjs`, `BaseFilm.jsx`, `FilmPanel.tsx`, `docs/primitives/`. 2 days.
11. **Text styles and safe areas.** `EditText.decoration: shadow | outline | box`
    (default shadow, serialised only when not default) and a safe inset: text boxes
    measure from `min(width, height)` and keep 5 % clear in landscape and 12 % top and
    bottom in portrait. Shared with Phase F's portrait titles; whichever lands first
    carries it. Files: `models.py`, `BaseFilm.jsx`, `timing.mjs`, `baseFilm.ts`. 1 day.
12. **Per-word lyric timing.** `match_lines` also returns the heard words it matched per
    line; `lyric_timing.save` keeps `words: [{text, start, end}]` on an auto line only
    when present; Track shows word ticks under a timed line; `EditText.words:
    [{text, in_frame}]`, serialised only when set, and `kinetic_words` uses them when
    present, the even split otherwise. Phase B5's caption layers are generated from
    these. Files: `lyric_tools.py`, `domain/lyric_timing.py`, `models.py`, `timing.mjs`,
    `BaseFilm.jsx`, Track. 1.5 days.

### PR C-4, clips (about a week, after depth)

13. **A clip as a journaled asset version.** `generation.quote_clips(root, ids,
    reserve_per_second, model, seconds)` builds `videoInference` tasks from the selected
    still (uploaded through `reference_image` as references are today), the project's
    canvas and fps and the shot's `motion_prompt`; journal kind `clip`, reservation
    seconds × the Settings price, unknown cost kept reserved. `providers._result`
    learns that a video task completes with `videoURL`; `download_video` verifies the
    file with ffprobe (h264 in MP4, duration, frame count) under a clip cap of 200 MB.
    The version is `assets/<shot>/v00N-<uuid>.mp4` with `media: "video"`, `frames`,
    `fps`, the still's `input_hash` (staleness semantics kept) and
    `clip_input_hash` (model, seconds, source sha, prompt). Selection: `selected` stays
    the still, a new `clip` field names the clip version, so the still is always the
    fallback and `resolved_assets` keeps returning `image`; `RenderShot.clip` carries
    path, sha, frames and fps when one is selected. Files: `generation.py`,
    `providers.py`, `production/assets.py`, `models.py`, `services/generation.py`. 2.5 days.
14. **The clip layer.** `compile_shots` stages the clip by sha (ffprobe, not PIL) and adds
    `clip: {file, sha256, frames, fps}` to the entry, so the chunk key includes it.
    `BaseFilm` draws `OffthreadVideo` in the MP4 and `Video` in the Player (Remotion's
    environment flag), inside the same camera rect, grade and look; depth layers are
    skipped for a clip shot because it moves on its own. `timing.mjs clipFrame(span,
    localFrame)` maps the film frame to the clip frame at the clip's fps and holds the
    last frame when the clip is shorter, by rule; a longer clip is cut at the shot's end.
    `request.mjs` validates `clip`; the stills and titles review paths render the clip
    frame too. `approvals.stage_hash("stills")` binds `{id, image, clip}` only when a
    clip is selected, so a film without clips hashes as before. Files: `remotion.py`,
    `chunks.py` (tests), `BaseFilm.jsx`, `timing.mjs`, `request.mjs`,
    `production/approvals.py`, `services/preview.py`. 2 days.
15. **Clips in the Studio.** Images: "Make a clip · $0.xx for 5 s" per shot with the
    Settings model, a clip card beside the versions with play, Use clip and Use still;
    Film: a clip badge on the timeline, the Player plays it, the report warns when a clip
    is shorter than its shot by more than a second. The Writer may propose which shots
    earn motion (Phase E's tools); nothing here spends without the owner's price click.
    Files: `Images.tsx`, `FilmTimeline.tsx`, `cutNotes.ts`, `api/images.py`. 1.5 days.

## Not changing

The money journal's rules (reservation and UUID before the request, no resubmission,
quarantine of changed bytes); source audio and stills as immutable; existing films'
stage hashes, chunk keys and request bytes, because every new field is absent until set;
the golden contract, which is not regenerated in this phase; the legacy FFmpeg path;
one composition for the MP4, the review stills and the Player; the approval chain and
its gates; the 25/40 signature, which is Phase F; Phase B's song map, which this phase
reads and does not define; the Director's permission gate. No new stage in the Studio.

## Acceptance

- `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`,
  `npm test --prefix renderers/remotion`, frontend `tsc`, `npm test` and `npm run build`
  pass. `tests/test_contract_golden.py` passes without regeneration.
- `tests/test_timing_parity.py` pins the new enums and bounds (easing values, impulse
  limits, look keys, `depth` bound, `clip` shape) against `timing.mjs`;
  `edit-primitives.test.mjs` pins `parallaxState` (zero amplitude is the identity,
  deterministic by frame and shot id), the ramp (monotonic, reaches its share on its
  frame), the impulse (returns to 1 within its duration), each look option alone, the
  grain transform, `clipFrame` holding the last frame, and the request refusals.
- New Python tests: upscale and clip quotes, finish, recover and no-resubmit with a fake
  client; a derived version keeps its still's `input_hash`; the depth job with a fake
  worker, cached by still hash, refusing when layers are missing; chunk keys change
  with a depth set or a clip and not otherwise; compiled entries and `assets.json` are
  byte-identical for a film with none of the new fields; the stills stage hash is
  unchanged for a film without a clip; word timing is optional everywhere.
- On a **scratch copy of Tree of Love**, real films only read, $0 unless the two
  batches below are authorised:
  - depth on five shots with people and hands, flat against parallax at amplitudes
    0.3, 0.6 and 1.0, side by side at full length; the owner's eye decides and the
    result is written down;
  - grain at 1080p full screen on a flat sky frame, before and after;
  - the three faces on the opening, an edit title and a lyric line; a 9:16 synthetic
    film's text inside its safe area;
  - an impulse and a ramp on a chorus downbeat from the song map; each look option
    alone, with its render time against the plain render;
  - the Player and the MP4 on sampled frames of a parallax shot, an impulse and a clip
    boundary, judged by eye and recorded, as in the first-cut record. The automatic
    pixel comparison is Phase G6.
- **Paid batch, separate authorisation:** upscale up to 10 stills of the scratch copy at
  the published price (D7); the 2× still under a 1.3 push-in before and after, full
  screen.
- **Paid batch, separate authorisation:** clips for up to 3 shots × 5 s at the
  catalogue price with the cap stated before the run (D7); the still as fallback shown
  to work by un-selecting the clip.
- No other paid call of any kind, in tests or by hand.

## Risks

- **Render time.** Bloom and halation are blurred full-frame layers in software Chrome;
  parallax triples the picture layers. Each is measured alone and stays off by default;
  Phase D's parallel browsers are the real answer.
- **Depth artefacts.** Three feathered bands with a small amplitude keep silhouettes
  honest, but hair, glass and water will halo. The amplitude is small by design and the
  per-shot Flat switch exists for the shots that fail. The depth environment is larger
  than the model: a CPU torch wheel is a few hundred megabytes, said plainly before the
  download.
- **Upscalers invent texture.** A 2× model can sharpen skin and fabric past the approved
  style; the owner judges the first batch at full screen before it becomes a habit, and
  the still it came from is one click away.
- **Clips vary and cost.** Two runs of the same still give two clips; the reported cost
  can exceed the reservation; a clip may not match the shot's length or mood. The
  journal already stops on an overrun, and the still stays selected until the owner
  chooses the clip.
- **The broken-frame scan** flags frames unlike both neighbours; a clip's real motion
  may raise suspects and cost a confirmation render per chunk. Measured on the first
  clip batch; the scan's timeline awareness is Phase D4.
- **Disk.** Layer sets, 2× stills and clips all land in the chunk store and the asset
  cache, which nothing cleans; Phase H's cache sizes with Clear is where that is shown.
- **One revision change per PR** re-checks previews and titles once each, as PR 54 did.

## Out of scope

Phase B's song map and auto captions, Phase D's speed work, Phase H's catalogue (consumed
for model choice; a settings string until it lands), narrative films, 4K, HDR and 60 fps,
text-to-video and video-to-video, lip-sync, generated character sheets and scene plates
(Phase E5), vertical and square deliveries (Phase F2), the Critic, and any change to the
FFmpeg legacy path.
