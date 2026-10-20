# Still-film defaults and stage routing

This is the default for **new** productions unless the user explicitly chooses
otherwise. Existing productions, approvals, paid requests and selected images are
not migrated. Approved scope: [STILL_FILM_DEFAULTS_PLAN.md](STILL_FILM_DEFAULTS_PLAN.md).

## Locked creative baseline, explicit overrides

`src/mp3_to_videoclip/profiles.py` is the executable source of truth:

- `photographic-painted-v2` (current default): both **Alex Ross** and **Gabriele
  Dell'Otto** named exactly in the prompt; photographic craft painted by brush
  (not a flat comic or cel-shaded look). Roughly 70/30 in prose:
  anatomy/material/believable light versus deep blacks/highlights/gritty texture.
  The 70/30 split is prose, not a numeric mixing parameter or an
  affiliation/endorsement claim. The compiler is **style-first for v2 only**;
  `photoreal-painted-v1` productions keep their recorded prompt text and exact
  hashes and are never migrated or regenerated.
- **Nano Banana 2.1** (`google:nano-banana@2.1`; schema slug
  `google-nano-banana-2-1`), 1376×768 landscape or 768×1376 portrait.
- `settings.thinkingLevel: minimal`, `settings.imageSearch: false`,
  `settings.webSearch: false`; one JPG result, sync delivery, cost reporting.
- **One correction after the original**, then an explicit diagnosis/restaging
  decision. A budget cap is still required; these defaults authorize no spend.

`clip init` copies these choices into `project.json` and the actual look/rules
into `brief.json`. Later code/default changes do not rewrite them. Inspect the
exact style without generating:

```sh
uv run python -c 'from mp3_to_videoclip.profiles import DEFAULT_STYLE; print(DEFAULT_STYLE)'
```

The successful rooftop/rain/50mm test is retained verbatim as the style-control
fixture (`profiles.ROOFTOP_CONTROL_PROMPT`). Its generated image has now been
explicitly user-approved as the rendering benchmark (`profiles.STYLE_BENCHMARK`),
not a scene template or permission to upload it. Preserve `DEFAULT_STYLE` verbatim
at the start of `creative.look`; append film-specific palette/light after a blank
line. Brief approval and prompt compilation reject an altered core for this
default preset. Compare new proofs with the original; no repeat calibration is
needed merely because the story changes. Subject, action, environment, time, lens
and depth of field are chosen per production/shot and belong in each shot's
`image_prompt`; there is no separate lens schema. The universal medium lives in
`creative.look`. All final words stay locally rendered unless explicitly
overridden — the control image's own lettering request is the single planned
exception. Old "not a photograph" recipes are labelled heritage, not silently
blended into the new photographic style.

```sh
uv run clip init projects/new-story --slug new-story --mp3 /path/to/music.mp3
# Instrumental: add --music-mode instrumental
# Explicit replacement examples, decided BEFORE approval/spending:
uv run clip init projects/other-story --slug other-story --mp3 /path/to/music.mp3 \
  --style 'Charcoal illustration on rough paper' --model APPROVED_SCHEMA_SLUG \
  --native-size 1536x864 --image-settings '{}'
```

`--style` replaces the global look; it does not append a second style. `--model`
at init persists the choice. `--image-settings` replaces the settings object;
an explicit `{}` leaves provider defaults unspecified. Optional supported
controls: `thinkingLevel` (minimal/medium/high), `imageSearch`, `webSearch`,
`temperature` (0–2), `topP` (0–1), `systemPrompt`; numeric sampling controls use
0.01 increments. Leave them unspecified unless justified; there is no proven
"identity temperature". `--image-seed` is optional, not a character lock.

The chosen model's live schema still validates everything: another model may
reject the example size/settings. No automatic paid model comparison, resolution
upgrade or reasoning upgrade occurs. `clip quote --model SLUG` is a **per-quote**
override and does not change the stored default. A foreign model override does
not inherit Google-specific settings, and its alternatives are not current for
the canonical model/settings. To use those images as final selections, explicitly
persist that model and its effective settings and obtain renewed approvals.
Persist intended production-wide changes before approval; a per-quote comparison
remains labelled in its quote/journal and does not silently satisfy a later
canonical-model quote.

Preflight exposes stored generation controls; changing them changes new-profile
image input hashes and content-bound approvals. Old projects without these
fields retain their historical FLUX fallback, not a silent model switch. Use
`--workflow-version 1` for an explicitly legacy new production.

## Nine focused skills, one director

Load `clip-music-director` for routing. It links nine on-demand original skills:
music-analysis → story → storyboard, supported by art-direction/image-prompts,
then image-production, visual-review, edit-graphics and delivery. These are
capabilities, **not nine extra approval gates**. The crew is six specialists plus
`film-director`; `../LOOP.md` is the authority on who owns what, including
`post-editor` for motion/transitions/grade and `visual-critic` as the read-only
pixel control. The working order is:

1. Review actual music evidence. Develop story and art direction together, then
   approve the **complete brief**.
2. Develop storyboard and complete prompts together. Inspect compiled preflight,
   then approve the **storyboard**.
3. Quote/generate risk proofs; inspect each version and approve **proof**.
4. Invoke edit skill for a watched proof-only preview; approve **preview before
   stills quoting**.
5. Release/review 6–8 diverse shots; expand only if the pilot holds. Inspect and
   approve the final selected **stills**.
6. Check available-set edit/graphics on real footage, export, verify and back up.

The story skill requires cause/consequence, a visible turning point, cost and
payoff—not a tour of pretty frames. A place/object/process can carry a film
without a protagonist; symbolic/abstract directions remain legitimate. Use
existing brief/arc fields, not new mandatory schemas. The storyboard skill turns
each beat into decisive stills with purpose/change, subject/action, essential
visible details, framing, state, references, musical binding and transitions.

## Adaptive timing and instrumental music

New preset productions default to adaptive skeleton timing; older projects keep
beat-snapped timing. Timing follows the music rather than one universal range:
typical **4–6-second holds with earned 1.5–3-second inserts** for an energetic
mix, and only motivated long holds; calmer passages may hold longer. The planner
default for newly versioned films is five seconds within 1.5–7 seconds; older
adaptive projects retain eight seconds / 4–12 seconds. These are editable skeleton
proposals, not genre inference or mandatory edit cadence; shape them to the mix:

```sh
uv run clip skeleton PROJECT --timing adaptive --seconds 5 --min-seconds 1.5 --max-seconds 7
# Legacy-shaped default and explicit alternatives remain:
uv run clip skeleton PROJECT --timing adaptive --seconds 8 --min-seconds 4 --max-seconds 12
uv run clip skeleton PROJECT --timing free --seconds 10
```

This is a timing proposal full of TODOs, never a story or approval. It prefers
approved manual event boundaries, then local measured changes and nearby beats;
it does not infer meter/downbeats, emotion or a mandatory cut on each beat.
Rebalance tails to exact source frame coverage. A whole track shorter than four
seconds is one labelled exception. Do not overwrite an existing board to adopt
new pacing; edit/review the affected stable shots deliberately.

Bounds apply to output frames, not unrounded MP3 seconds. An explicitly chosen
very narrow range can be mathematically impossible for the exact track length;
the planner then asks to widen the range instead of silently stretching a hold.
Analysis is an existing prerequisite (the analysis/brief approval chain remains).
Estimated-only events are not promoted to reviewed structural boundaries: they
are ignored for that priority, and the CLI reports its fallback to local
measurements/beat estimates and target holds. `--timing events` remains stricter:
it requires reviewed manual events because that mode uses events exclusively.

**Instrumental means no lyric transcription and no lyric/word timestamps.** It
does not mean deleting the structural frame/time map needed to edit. Local music
analysis and reviewed events remain. Paid listening is optional; `music-map`
requires a listening draft, so without one review local music/events directly.

## Consistency, economical QC and Runware surfaces

Freeze imported identity/state/style refs and label their jobs in the prompt.
Use only views the shot needs; normally 2–4 references, with the live model
schema (up to 14) as the only hard cap — never hard-cap at 4 at runtime. Bind
identity and load-bearing refs only; a populated full-scene anchor is for
geography/scale continuity, not for pinning people, poses or wardrobe of
unrelated shots. Do not chain every latest image as the next anchor, automatically
replace identity refs when selecting another panel, or force a reference's costume
into the wrong state.

Do one quick actual inspection of every source image. Deep-check obvious or
load-bearing problems, not distant paw pads/fingers. Accept intentional
stylisation with notes. Uncertain/rejected selected bytes cannot pass approval.
Try a targeted crop/repair/restage before replacing a good whole frame; edits
are not automatically free. One paid correction then stop/diagnose. The existing
budget can explicitly authorize a different limit; no historical limit changes.

MCP/public schemas support targeted discovery; the **clip executor** handles paid
work with durable journal, reservations and recovery. The optional `runware`
binary is not installed or required by this change. Its `run --validate` validates
**and then generates**—not a no-spend dry run. No global auth/key changes, new
MCP servers or SDK migration. Pinned upstream recipes are unchanged; project
policy overrides their generic model defaults/parameter advice. Their two motion
skills are deselected and denied in this project only, preserved for a future
release. Camera crops/zooms remain local still-film tools, not generated motion.

## Required film signature

Every new film is delivered as a **composited final**, not a bare base render,
with a **25-second opening overlay and a final 40-second credit package** inside
the original music: the shared MAHA KALA × VJDJ69 identity, the joint-production
line `A JOINT MAHA KALA & VJDJ69 PRODUCTION`, and this production's factual credit
roles supplied once at intake. Reuse the existing `graphics.py` visual family. If
the track cannot hold the package inside the music, stop for an alternate plan —
never append or stretch audio. Delivery records the base and final composite
hashes and the actual sample frames inspected; a clean ffprobe is technical, not
creative, and an audio transcode is not MP3 packet identity. `MUSIC_LED.md` holds
the identity detail and `../LOOP.md` the crew and loop.

### One identity source: `brand.json`

The collaboration identity lives in the project's `brand.json` — the selected `filmstrip`
emblem, one palette, the partnership wordmark. A graphics spec opts into it with
`design: "joint-v1"` and then **adopts** the palette and emblem instead of
restating them, so the opening and the credits cannot drift apart. A production
whose opening already renders the identity sets `plate: false`; otherwise the
renderer also composites the plate over the opening and the emblem is drawn twice.
Legacy specs without a `design` key keep their exact previous rendering.

### Motion is part of the edit

A deliberate hold is a valid edit. Remotion is the primary visual renderer for
new CLI productions, with FFmpeg for encode/mux/probe and legacy compatibility.
`dissolve_frames`, `camera_path`, explicit `camera_keyframes`, bounded contrast/
saturation/brightness/vignette and optional fade/wipe transitions are the motion
tools; `post-editor` designs their use and `film-finisher` executes it. Judge
motion on decoded frames, never on a description of intent, and never retune a
reviewed crop. Scales and evidence method: the
`clip-edit-graphics` skill's `references/motion-and-grade.md`.

The canonical storyboard remains the only timeline; renderer props are derived.
Older projects opt in explicitly, never silently migrate. See [RENDERER.md](RENDERER.md).
Use the story/board feedback loop in `LOOP.md` before approval: independent critic
and music/edit feasibility feedback, then one bounded author revision.

### A deeper local music map

`uv run clip analyze PROJECT --deep` writes `work/music-deep.json`
(`analysis_version: 3`): a refined pulse with its half/double ambiguity, a
candidate downbeat phase with bar-length scores, a key candidate reported next to
its runner-up, candidate section boundaries, and bass- and vocal-band onsets. It
is **local and free** — no provider call, no upload — and it is a separate
artifact so it can never silently rewrite an approved `work/music.json`. It is
unreviewed measurement: it does not approve anything and never retimes an
approved edit on its own. On a real track it located all nine sections a user had
marked by ear, where the older change detector missed two by more than 30 s.

See [PRODUCTION_WORKFLOW_V2.md](PRODUCTION_WORKFLOW_V2.md) for version-bound
reviews, reference import, cumulative budgets and graphics preflight commands.
