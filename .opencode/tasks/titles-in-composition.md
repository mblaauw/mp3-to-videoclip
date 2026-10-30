# Titles in the composition — plan

**Approved** by the owner on 30 Oct 2026 with the recommended D1–D5. Work starts
on a new branch off `main` once PR #43 is merged.

**Objective:** draw the opening, captions and credits inside the one Remotion
composition the MP4 and the Studio Player already share. The Player shows the
titles live, the titles review takes seconds instead of a base render, and a
music-video final becomes one render pass instead of base + overlay + composite.

Phase 1 of the 29 Oct 2026 full assessment. Base: `main` at `d4149db`, after PR #43.

## Why

- Checking titles today renders a full base first. Tree of Love v002 took about
  14 min for 5,749 frames, then 17 sample PNGs (2.3 MB each).
- All four productions already draw titles in Remotion (`graphics-spec.json`
  `renderer: remotion`). Each title part becomes its own ProRes 4444 alpha clip.
  `graphics.py` joins those clips into a qtrle alpha track, and FFmpeg layers that
  over the base. That is the 12 GB in Tree of Love's `work/graphics` and 7.5 GB in
  Stof en Stilte's.
- The Player shows no titles at all, so no one sees them in motion before the final.
- `_plan_parts` plans title windows in float seconds with a running float cursor.
  Everything else is integer frames from `timeline.py`.
- The title components live in `renderers/remotion/src/index.jsx` next to
  `registerRoot`, so the frontend cannot import them the way it imports `BaseFilm.jsx`.

## Target

```text
graphics-spec.json ──► timeline: plan_titles() ─► integer-frame title windows
                                                     │
stills + edit ──► resolved_assets ─► RenderShot[] ───┤
                                                     ▼
                        Remotion "Film" = BaseFilm + TitleLayer (one input)
                         │                    │                    │
                   Studio Player       renderStill samples     final MP4
                   (live titles)       (titles review)         (one pass)
```

## Decisions for the owner

| # | Question | Recommendation |
| --- | --- | --- |
| D1 | What does the titles attestation bind to? | Stills rendered with `renderStill` from the real Film composition at the planned sample frames, plus the Player for motion. This keeps "inspect actual frames" without needing a base movie. |
| D2 | What does the graphics approval hash cover? | The resolved spec, planned windows, renderer implementation hash, logo/font identity, the stills/edit input hash and the sample bytes. No base movie. Record it as `method: composition-v1`; old `composite` reviews stay readable. |
| D3 | What happens to `graphics.py` compose? | Keep it unused but readable for this phase so frozen films keep their records. Delete it in the legacy-retirement phase. |
| D4 | Tree of Love's pending v002 review | It is unapproved, so it is superseded by a new review. The v002 base, its 17 samples and the old final stay on disk untouched. |
| D5 | Adopt the editorial title design? | Not in this phase. Once the pipeline moves, it becomes a `design` option with its own owner approval. The prototype in `.opencode/scratch/tree-of-love-title-proofs-v1/` is a hard-coded mock-up and serves as the design reference, not as code. |

## Tasks (one commit each, one PR)

1. **Integer-frame title windows.** Move `_plan_parts` into the timing layer as
   `plan_titles(spec, project, board/edit)`, returning `start_frame`/`frames`.
   Keep its current rules: no caption inside the intro, no overlap, credits end
   with the music. Compare against today's float plan for all four specs and
   record any one-frame differences.
2. **Shared title module.** Move the title parts and `CompactGraphics` out of
   `index.jsx` into `src/Titles.jsx`, which exports `TitleLayer({titles})`: it
   picks the active part by frame and computes local time. The `Graphics`
   composition wraps one part, so nothing breaks mid-phase. Node tests cover
   part selection at window edges.
3. **Film composition and request.** `BaseFilm` takes an optional `input.titles`.
   `request.mjs` validates integer frames, no overlap and windows inside the
   duration. Regenerate `tests/golden/contract.json` and state why in the commit.
4. **Live titles in the Player.** `player_input` adds the planned titles. The
   logo goes in as an inline SVG data URL and the font uses the same system
   stack as the render. Film's preview gets a "Show titles" toggle. Overflow
   checks that throw at render time must show an error card in the Player
   instead of crashing the preview.
5. **Titles review from stills.** `prepare_review` renders the sample frames with
   `renderStill` from the Film composition, with no base, and writes
   `method: composition-v1`. `validate_review` handles both methods. "Check
   titles" now means "make samples", and the three copy sites that say it
   renders a base first are updated (`deliveryWorkflow.ts`, `Film.tsx`, `nextStep.ts`).
6. **Final in one pass.** For signature films `render_final` renders Film with
   titles. The report stamps `graphics_approval_hash`, `input_hash` and
   `verified`. It is checked like any final: frames, fps, faststart, audio
   duration, and a source-music fingerprint equal to the base render's. No compose step.
7. **Stop the per-part cache and update docs.** New renders no longer write
   `work/graphics/**` ProRes clips. Existing caches are left alone; a reclaim
   policy is a separate decision. Update `docs/ARCHITECTURE.md`,
   `docs/RENDERER.md`, the README and the Film copy.

## Acceptance

- `pytest`, `ruff check`, `ruff format --check`, frontend `tsc`/tests/build and
  renderer tests all pass. The app starts.
- On a **scratch copy** of Tree of Love (no production mutation, $0 provider spend):
  - The Player shows the intro, cards and lockup at their planned frames.
  - The titles review is ready in under a minute.
  - One final render passes verification.
  - At every sample frame, compare against the old composite and report the
    difference. Small alpha-blending differences are expected; any layout
    difference blocks acceptance.
- Record the time for review samples and for the final, next to today's
  14 min base + composite.
- Delivered films (Forward Ever, Stof en Stilte) still classify exactly as
  before in Film's export list.

## Risks

- **Alpha blending.** ProRes 4444 over H.264 versus drawing in the page can
  shift edge pixels slightly. Measured in acceptance and not hidden.
- **Fonts.** Titles use the system Avenir Next through Chromium, the same as the
  current Remotion graphics. The Player matches on this Mac; another machine
  could fall back to a different font. The review records the font identity.
- **Render time.** Text layers add some cost per frame during title windows. It
  is measured, and should still be far less than base + composite.
- **Approvals.** The graphics hash changes meaning for new reviews only, and
  existing approvals and finals keep their recorded method. Proved by a test
  that the delivered films' export classification is unchanged.

## Out of scope

The editorial title design (D5), portrait titles, moving the hard-coded joint
identity (`signature.NAMES`, `PRODUCTION_LINE`) into settings, a cache reclaim
policy, and deleting the FFmpeg/Pillow paths (assessment phase 2).

## Progress

- **T1 done.** `titles.plan_titles` returns integer-frame windows, and
  `graphics._plan_parts` adapts it for the compositor that remains this phase.
  - 168 parametrised layouts match the old planner frame for frame.
  - The real specs plan identically: Forward Ever (6 windows), Stof en Stilte (5)
    and Tree of Love (8).
  - Zero Bars' `end-line` caption (235.75–239.83 s) overlaps its own credits
    (from 199.8 s), and the old planner refuses it too. Its spec needs a creative
    fix before it can have titles.
  - Shot-bound captions now follow the edit's timing; before, they used the
    storyboard's. No current production had both.
  - `titles.py` joins the graphics implementation revision, so the existing
    titles reviews need renewing. Tree of Love's is unapproved and superseded
    anyway (D4).
- **T2 done.** The title parts moved from `index.jsx` to `src/Titles.jsx`, which
  exports `GraphicsFrame` (one element, as before) and `TitleLayer` (every
  planned window, each in a `Sequence` on its own local clock).
  `timing.titleWindowAt` picks the window and has Node tests. A Forward Ever
  intro and card rendered through the moved code are frame-for-frame identical
  (framemd5) to the previous code. Any renderer source change moves the
  renderer revision, and with it the current-input check for existing bases.
- **T3 done.** The `Base` composition renders `Film.jsx`, which is `BaseFilm` plus
  `TitleLayer` in a new overlay slot: above the pictures and brand plate, below
  the placeholder and preview markings. `request.mjs` validates `input.titles`
  (integer, ordered, unique, inside the film, local logo/font).
  `titles.render_input(root)` builds it, and `remotion.render_base(..., titles=)`
  draws it in the same pass. A render without titles has the same request and
  visual cache key as before. The golden contract gained only
  `remotion_titled_request`; its three existing entries are byte-identical. A
  320×180 render through the Film composition drew a credit card on its own
  local clock.
- **T4 done.** `player_input` adds the planned `titles`, or a `titles_note` saying
  why there are none (Zero Bars: its caption conflict). The Player renders the
  renderer's `Film.jsx`, Film has a "Show titles" toggle, and a render error
  shows as an error card instead of breaking the preview. Live on a scratch copy
  of Tree of Love: the opening title at 0:10 and the VJDJ69 credit card with
  its filmstrip mark at 3:30 drew in the Player, and the toggle removed them.
  Follow-up outside this phase: `index.html` has no `Cache-Control`, so a
  browser can keep running an old build after an update.
- **T5 done.** "Check titles" is a `titles` render job that calls
  `signature.prepare_titles_review`. It renders review stills of the Film
  composition through a new `stills` request kind (Remotion `renderStill`,
  published as a whole directory) and writes a `composition-v1` review. That
  review binds the spec, the planned titles, the stills/storyboard input hash,
  `input_metadata_hash` (so the cut too), the renderer revision and every
  sample's bytes. `validate_review` handles both methods. A base render no
  longer prepares or replaces the titles review. The job runner allows the
  `titles` kind, including when restoring jobs after a restart; the scratch run
  first failed on the runner's own list of kinds.
  - Scratch Tree of Love through the UI: the job took **14.1 s** (the old route
    was a ~14 min base render plus samples). It produced the same 17 moments
    as the old review: 10 opening phases, identity, 5 cards and lockup, 46 MB.
  - Against the old composite samples of the same frames: 44.8–47.7 dB PSNR,
    99.9th percentile ≤ 7 levels, no pixel more than 64 levels off. No layout
    difference, only H.264 noise.
