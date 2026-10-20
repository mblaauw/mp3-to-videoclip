# Creative still-video workflow

Goal: a directed music video, not merely a sequence of attractive pictures.
The scripts enforce artifact/timing/provider contracts; an agent and the user
still supply and judge musical interpretation, composition and story.

## Current default (v2)

New productions default to the `photographic-painted-v2` preset (a photographic-
painted Alex Ross / Gabriele Dell'Otto fingerprint, not a flat comic) with a
style-first compiled prompt **for v2 only**; `photoreal-painted-v1` productions
keep their recorded prompt text and exact hashes. Timing follows the music
(typical 4–6 s holds, earned 1.5–3 s inserts, motivated long holds), references
are normally 2–4 useful images with the live schema as the only hard cap, and
every new film carries the required in-music signature (25 s opening overlay +
40 s credit package, factual roles). See
[STILL_FILM_WORKFLOW.md](STILL_FILM_WORKFLOW.md), [MUSIC_LED.md](MUSIC_LED.md)
and [../LOOP.md](../LOOP.md) for the crew and loop.

## Compatibility and scope

The current new-production look/model, stage skills, one-correction policy and
adaptive timing are in [STILL_FILM_WORKFLOW.md](STILL_FILM_WORKFLOW.md). The older
profile examples below illustrate editable contracts, not the current defaults.

New `clip init` defaults to workflow 2. Its state/reference/QC/budget contracts
and complete commands are in [PRODUCTION_WORKFLOW_V2.md](PRODUCTION_WORKFLOW_V2.md).
Those requirements augment the stage sequence below; existing projects are not
migrated. Use `--workflow-version 1` only for an explicitly legacy new project.

New `clip init` productions have `brief.creative` and an empty musical event map.
Existing productions without that profile retain exact legacy prompts, selected
image hashes, proof selection and approval chains. Optional camera paths are
also opt-in: old plate cache keys and movement remain unchanged.

Nothing here automatically upgrades, regenerates or re-approves the existing
Kortjakje pilot. To revise an existing project, explicitly review a creative
profile first; changing to it changes image inputs and requires renewed quotes,
authorization and approvals. Keep the previous asset/export versions.

## 1. Listen, measure and choose an approach

```sh
uv run clip init projects/new-song --slug new-song --mp3 /path/to/song.mp3
# Instrumental alternative: add --music-mode instrumental
uv run clip analyze projects/new-song
uv run clip schema events
```

Review local measurements with the user, then record their analysis decision.
For vocal tracks, use the existing quote/authorize/transcribe/review process.
For instrumental tracks, do not transcribe or invent lyrics: the brief depends
on analysis/events rather than a lyrics approval. The music_mode decision is
upfront and content-bound; do not silently change an approved project later.

Edit `work/events.json` after listening. The source hash/FPS/total are already
filled. The empty map means **no reviewed structural claims yet**, not silence.
You may explicitly approve an empty map and use free/beat timing; do not invent
events to satisfy a gate.

An event looks like this (example values, not inferred song facts):

```json
{"id":"release-a","frame":960,"end_frame":1200,"kind":"release",
 "label":"Arrangement opens","timing_basis":"manual",
 "note":"Reviewed by listening; edit opportunity, not a compulsory cut"}
```

Available kinds: section, vocal, instrumental, build, release, motif, silence,
accent. Frames are at the project's FPS. Events must be ordered, uniquely named
and within the full track; the map is bound to the exact source hash/format.
`pulse` may be steady, variable, free or unknown. Estimates remain estimates
until the user reviews their position; `--timing events` uses manual boundaries.

```sh
# Only after the user's respective decisions:
uv run clip approve projects/new-song analysis --note 'User reviewed measurements'
uv run clip approve projects/new-song events --note 'User reviewed these listening notes'
```

Propose 2–3 treatments. Choose narrative, symbolic or abstract based on this song,
not a fixed genre preset. Define the opening, development, visual peak and ending.
Describe how framing/light/motifs evolve, not only what each lyric depicts.

## 2. Separate appearance, scenes and shot content

`direction`, `style`, `treatment` and `visual_rules` remain editable planning
notes and approval content. In the new profile they are **not** blindly prefixed
to every image. The actual global image instructions are `creative.look` and
`creative.image_rules`; review them explicitly with the brief.

Example creative profile (add it inside a complete brief):

```json
{
  "mode":"symbolic",
  "look":"Photographic stills, soft available light, muted colours, fine grain",
  "image_rules":["Single coherent frame, no collage or split screen","No on-screen text"],
  "arc":[
    {"phase":"opening","intention":"Distance, withheld detail"},
    {"phase":"release","intention":"Closer framing, a previously hidden object revealed"}
  ],
  "scenes":[{"id":"room","description":"Small plain room, worn wood, one high window",
             "reference_ids":[]}],
  "references":[],
  "global_reference_ids":[],
  "proof_shot_ids":[]
}
```

Do not list every location in `look`: a book close-up must not be forced to
include a canal, café and church. Bind the relevant scene to each shot instead.

Approve the brief after the user selects the treatment/appearance. Build timing:

```sh
uv run clip skeleton projects/new-song --timing events --seconds 10
# Or --timing free for uniform slots without beat guesses; --timing beats is legacy default.
```

For an energetic mix, shape the cadence explicitly — typical 4–6-second holds
with earned 1.5–3-second inserts and only motivated long holds:
`uv run clip skeleton projects/new-song --timing adaptive --seconds 5
--min-seconds 1.5 --max-seconds 7`.

These are editable TODO slots, not a finished storyboard. Event timing snaps
near nominal targets to reviewed event start/end boundaries (within one second);
it does not guarantee every musical event is a cut or replace editorial judgment.

For each shot, write purpose, image_prompt, scene_id, framing (wide/medium/
close_up/detail), must_show and optional event_ids. Use one decisive still moment,
not an action that needs generated video to make sense. Put future motion ideas
in motion_prompt only with the understanding that they are not executed now.

Inspect the exact compiled prompts before buying images:

```sh
uv run clip prompts projects/new-song --shots s002,s005
```

Prompt order is shot → framing/required details → bound scene/references/character
appearance → global look/rules → avoid list. Unrelated scenes and editorial arc
are excluded. Story/proof/camera/timing-only edits require renewed review but
do not automatically invalidate image inputs; relevant appearance/ref bytes do.

## 3. Purposeful proof selection and visual QC

Set exactly three `creative.proof_shot_ids` (or all shots if fewer than three).
Choose the highest-risk requirements: e.g. exterior, close object/hands and an
interior/recurring figure. Include different scales and narrative functions,
not merely first/middle/last. IDs must refer to actual storyboard shots.

Because this selection is in the brief, reapprove the brief after adding/changing
it, then approve the completed storyboard. This is still before paid generation.
The software validates selection identity/count, not its artistic adequacy.

Quote/authorize/generate the proof using the existing CLI. The selected model,
native dimensions and spending allowance remain explicit; a new profile does
not silently upgrade models or buy extra alternatives.

Judge images individually **and together**:

- Does the subject and each must_show detail actually appear?
- Is the intended shot scale delivered, rather than another attractive wide shot?
- Are hands, props, geography and spatial relationships plausible?
- Do recurring elements remain recognisable without identical compositions?
- Does the visual arc evolve? Does repetition change meaning?
- Any distracting lettering, accidental split frames, anatomy or texture errors?

The rubric is a human/agent review, not a claim of automated visual validation.
Record approved exceptions explicitly. Generate selective alternatives only with
their own quote/authorization; compare the difficult shots before raising model
or resolution budgets. Native detail and crop margin matter more than export size.

## 4. Local timed preview before the remaining batch

```sh
# After the user approves the proof:
uv run clip approve projects/new-song proof --note 'User reviewed proof fidelity and cohesion'
uv run clip preview projects/new-song
```

New-profile default previews use the selected proof images and clearly labelled
placeholders for all other shots, on the complete original music and exact shot
timeline. They render at 640×360 (or 360×640 portrait). A persistent marker after
camera transforms says PREVIEW / NOT FINAL. No source images are modified, no
generation occurs, and no approval is implied by successful rendering.

Review musical phrasing, opening impact, attention loss, holds, reveals, cuts,
climax and ending. Do not cut on every beat or add motion merely to disguise
weak pictures. Placeholder sections let you assess allocation/structure, not the
unseen images' artistic success; review the full selected set again later.

Revise timing/camera/shot content as needed. Changed upstream content needs its
normal renewed approval; actual image-input changes may need selective
regeneration with explicit authorization. Workflow 2 retains an unchanged
proof-only preview after a non-proof generation-prompt correction, but still
requires approval of the revised storyboard. Changes visible in the movie
(timing, purpose, framing, camera, proof images) require a new preview/review.

```sh
# Only after actual user review:
uv run clip approve projects/new-song preview --note 'User watched this preview and approved pacing'
uv run clip quote projects/new-song --scope stills --reserve 0.01
```

New-profile full batches require current preview approval. The review binds the
movie bytes, storyboard and selected proof; generating the remaining images does
not stale that proof-only review. `preview --scope available` uses all current
selected stills for later editing checks, but never overwrites a creative
profile's proof-only batch-gate review. Every preview/export is versioned.

## 5. Controlled still-camera movement

`camera` still supports legacy hold/zoom/pan choices. An optional camera_path
overrides that choice:

```json
{"start":{"zoom":1.05,"x":0.2,"y":0.3},
 "end":{"zoom":1.12,"x":0.7,"y":0.6},"easing":"smoothstep"}
```

Zoom is 1..2; x/y are 0..1 positions **within the available crop overflow**,
not subject coordinates or pixels. At zoom 1 there is no crop room to pan.
Use modest ranges appropriate to the image's native detail. Linear and smoothstep
are choices, not universal rules; deliberate holds are still valid.
Paths interpolate through the full plate including dissolve handles. Changing
them rebuilds only affected cached plates, not generated images. They move the
frame—not people, smoke, rain or objects inside the photograph.

## 6. Continuity references

Declare style/location/prop references in creative.references:

```json
{"id":"book","kind":"prop","description":"The same worn book and silver clasp",
 "path":"media/references/book.jpg","permission_confirmed":true}
```

Bind IDs explicitly through shot.reference_ids, scene.reference_ids or
creative.global_reference_ids. Reuse approved owned project images if helpful.
Do not mark permission true without the user's actual authority to upload/use
the image. Reference bytes, descriptions and paths enter the quote before any
upload. Unbound references do not enter a shot's prompt. New stored-model profiles allow
up to fourteen references with normally only 2–4 useful ones; the selected live
model schema is the only hard cap and is never hard-capped at four at runtime.
Existing profiles retain their four-reference cap.
No automatic image-reference upload happens during prompt inspection or preview.

## 7. Finish and preserve

Review the full still set and available-set preview before final rendering.
Export still requires the full selected set's explicit approval; technical
validation cannot judge the artistic result. Preserve prior versions.

```sh
uv run clip preview projects/new-song --scope available
uv run clip backup projects/new-song
```

Local backups include source media, state, assets and outputs, not rebuildable
plate caches or environment files. They are private archives outside the
production directory, under ignored backups/ by default. No cloud backup or
automatic Git commit/publication is performed. Commit source deliberately and
keep private production archives in your own secure backup system.
