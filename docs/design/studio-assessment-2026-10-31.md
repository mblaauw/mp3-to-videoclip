# Studio assessment, 31 October 2026

Reviewed: `main` at `c1414a3`, run from a fresh clone on Linux with Node 22, FFmpeg,
Chrome and the pinned Remotion renderer. Four passes: a live walkthrough of every
screen at 1440×900 and 390×844 on a 40 s synthetic song (music video and advert),
a backend read with the full test suite, a renderer read with real renders of a
synthetic film, and a read of every Director prompt, tool and gateway path. No
production was touched and no paid call was made. Where a number appears it was
measured here or taken from the repository's own acceptance records.

## What the app is for

One person makes finished films from their own songs on their own computer: a
music video from a full track, or a promo or advert from an excerpt. An AI Writer
turns the song and an idea into a story, a cast and a shot list; paid stills are
bought under a strict budget; an AI Editor cuts them to the music; Remotion renders
the film with titles and a grade, and the same composition plays live in the
browser. Everything is content-bound, journaled and reversible. The owner's taste
is the final gate at every stage.

That purpose is right and the app serves it honestly. What follows judges the app
against the bar the owner set: a one-of-its-kind, must-have tool.

## Verdict in one paragraph

The engine is of a quality most commercial tools never reach: integer-frame timing,
a money journal that cannot double-spend, approvals that go stale the moment their
bytes change, a job runner with durable receipts, 1,532 honest tests. The Studio
redesign has landed and the shell reads like a film tool. Three things keep it from
the top. The film still **looks like a slideshow**: two-dimensional crops of stills
upscaled from 1536 px, one font, one light leak. The Director **cannot hear the
song**: the Writer gets tempo and section labels, never energy, beats, key or the
lyrics with their times, and the automatic cut ignores the beats it has. And the
**blocked states are unfinished**: when the engine refuses something, the screen
shows a raw path or a tooltip or sends you to the page you are on. Fix those three
and this is the best tool of its kind.

## Scorecard

| Dimension | Grade | One line |
| --- | --- | --- |
| Engine correctness and money | A | Pre-submit journal, UUID recovery, quarantine of changed bytes, content-bound approvals. Preserve as is. |
| Security of a local app | A | Loopback and origin gates, slug and path guards, keys never returned, 0600 settings. |
| Tests and discipline | A− | 1,532 passed, 0 failed, real FFmpeg and DSP; golden fixture still pins the legacy path. |
| UX shell and happy path | B+ | Next-step bar, stepper, spine, lightbox, Film workspace all work and look right. |
| UX blocked states and copy | C− | Raw `[Errno 2]` paths, `network_error`, `TODO: approved story purpose`, "Go to Story" while on Story. |
| Phone layout | C | Library, New film, Track, Story fine; Storyboard, Images and Film overlap at 390 px. |
| Music understanding | C | librosa measurement only; fixed section count; deep pass computed but unused. |
| Automatic cut | C+ | Clean planner, snaps to sections and lines, but never to beats or downbeats; never changes density. |
| Writer and Editor prompts | B | Strong truth rules and technique table; no motif, colour script or section mapping; one example idiom. |
| Director context and tools | C+ | Safe writes with owner gate; model is blind to the song and sees stills only on request. |
| Gateway | C | Two paths, one model for both roles on the default path, zero token or cost visibility. |
| Image generation | B− | Single provider, text-to-image only, project-wide seed, no edit mode, no upscale. |
| Visual quality of the film | C+ | Tasteful, consistent, restrained; 2D only, soft on push-ins, no depth, no motion. |
| Render speed | C+ | ~14 fps capture in software Chrome; 7 min for a 4 min film; 1.9× and 3× gains measured here. |
| Output contract | B | Correct bt709/yuv420p/faststart 1080p; no loudness, chapters, captions, poster or vertical. |
| Brand neutrality | D | 25 s opening and 40 s credits mandatory for every music video, two names hard-coded. |
| Tech debt | C | Schema 1/3 branches in ten modules, 2,566-line legacy compositor, 550-line CLI dispatcher. |
| Install and portability | B− | `uv sync` and `uv run studio` work; still needs Node, FFmpeg, Chrome, two API keys, Apple Silicon for lyric timing. |

## What is excellent and must survive

- The paid-task journal (`generation.py:376-516`, `providers.py`): reservation and
  UUID written before the request, single coordinator, recovery that never
  resubmits, changed bytes quarantined. This is the heart of the trust model.
- `storage.py`: atomic writes with directory fsync, ordered locks with an enforced
  ordering assertion, scoped read snapshots.
- The content-bound approval chain (`production/approvals.py:170-220`) binding
  reference bytes, plate bytes, the cut, the brand and the renderer revision.
- Integer frames everywhere; `pacing.py` as a pure exact-coverage planner;
  transitions as incoming-owned handles that never shorten the film.
- One `Film.jsx` and `timing.mjs` for the MP4, the review stills and the Player.
- Chunk-per-shot rendering with shot-relative subtractive keys, stream-copy joins
  with packet proof, receipts, the stall watchdog and the flash refusal.
- The honest-medium framing in `writer/system.md:13-18`, the five truth rules, the
  owner-only permission gate and its tests, verbatim idea sorting and story
  placement, prompt versioning with hash provenance on every turn and write.
- The job runner: durable receipts, `interrupted` on restart, bounded SSE bus, a
  watcher that never reloads on reads.
- Analysis discipline: every number labelled, provenance recorded, octave
  ambiguity preserved rather than hidden.
- The task-record culture in `.opencode/tasks/`: every decision has an owner, a
  reason and an acceptance record.

## Findings by area

### 1. UX, screen by screen

The design direction in `docs/design/studio-redesign` is implemented: top bar with
stepper and state words, budget and jobs popovers, one next-step bar, the spine
with a shared time store, the Director drawer with role header, tool cards and
undo, the inspector swap, the contact sheet and lightbox with K/R keys, the Film
workspace, Settings with test buttons. The visual language is quiet and the
pictures are at picture size. What remains is the layer under it.

**Library.** Good. Posters, five-segment progress, next step, Delivered shelf with a
read-only player. No last-edited time, no search; fine at this scale.

**New film.** Per-kind fields, 9:16 gone, plain copy. The spec's probe line (name,
size, length after drop) is missing.

**Track.** Sections with names and loudness, plain-text or LRC lyrics, tap-to-time
at two speeds, nudge, local lyric tools with a clear download notice. At 390 px the
transport column is sized 64 px in `shell.css:1205` and 168 px in `polish.css:883`,
so the waveform gets about 220 px.

**Story.** The richest stage and the one with the most dead ends:

- An unconfirmed character permission makes the brief unavailable; the bar says
  "The story is not ready yet" with a *Go to Story* button while on Story
  (`nextStep.ts:170-178`). The real reason is only in the compact bar's tooltip
  (`NextStepBar.tsx:81`).
- Before the Writer has built the cast and places, the bar says "Build the cast,
  places and rules" with *Open Story*, on Story (`nextStep.ts:214-222`). The button
  that does it is on the World tab. With no model key the story can never be
  approved and nothing says so.
- "See what changed" renders raw JSON: `(empty) → ["s002", "s004", "s007"]`
  (`StoryChanges.tsx:14-22`).
- The advert Brief card is per spec but shows the raw URL rather than a hostname.

**Storyboard.** Pictures grouped by section, table with thumbs, stars with the
correct toast and violet Story step, an inspector with a kind picker and autosave,
draggable gold cuts with keyboard. But:

- The header still reads "Integer-frame timeline, stable shot IDs…"
  (`Storyboard.tsx:200`), the exact string the UX audit asked to replace.
- After *Create timing skeleton* every card says `TODO: approved story purpose`
  and `FRAMING TO SET` (`production/board.py:225`); the bar says "Read the
  storyboard and approve it"; Approve returns the raw toast "finish storyboard
  placeholders before approval" (`production/approvals.py:352`). The spec asked for
  "N shots still need a job and a prompt" with *Show them*.
- The rating control says "no storyboard yet" after the board exists
  (`ArtifactRating.tsx:57-78` never refetches on project change).
- The table scrolls sideways on the phone and the head pushes the first shot below
  the fold.

**Images.** The best stage. Style-check panel, chips with counts, lightbox with
focus trap and keys, one-step priced buttons, top-up card, local plates marked
"Made here". One P1: with no Runware key, *Make 3 style stills · $0.15* shows a
bare red `network_error` (`providers.py:227` → `images/paid.ts:96`) with no sentence
and no *Open settings*.

**Film.** A real editing workspace: viewer, seams you click, shift-click and drag,
a join panel with nine transitions and "Watch this join", camera moves per shot,
grade and look, *Make a first cut* and *Suggest a cut*, ⌘Z, `F`, `[` and `]`, a
delivery panel with attested samples. But:

- Opening Film on a film without a storyboard shows
  `[Errno 2] No such file or directory: '/…/work/storyboard.json'` three times:
  toast, inline error and the viewer body (`useFilmData.ts` calls `GET /edit`
  unconditionally and the route returns the exception text). The bar then says
  "Approve every picture before the final" with *Go to Images*, which is the wrong
  order (`nextStep.ts:395-402`).
- Panel notes are engine wording: "s003: third push_in move in a row", "Section 1:
  has no written feel" (`edits.py:603,660`, no case in `cutNotes.ts`), "The titles
  cannot be laid out yet: credits need cards and a lockup line" (`graphics.py:558`),
  "Grade: neutral", "push-in ×8".
- The renderer setup card did not appear although `/api/setup` reported the
  renderer missing (`Film.tsx:227`); the viewer showed the placeholder plate.
- At 390 px the Edit / Cut list / Rendered files tab row is covered by
  `.film-line-head` and cannot be clicked (`film.css:1115+`).

**Settings, budget, jobs, Director, archive.** All per spec. Small things: the
gear icon reads as a sun; "Opening names" is two unlabeled inputs; budget history
shows the raw reason "initial production budget 5.00"; the Director's suggestions
never say that the Writer is required to progress the story; error toasts are
`role=status`, not `alert`.

**Cross-cutting.** The error copy map in `api/errors.ts` covers fifteen director
codes; `approval_invalid`, `bad_request`, provider errors and `FileNotFoundError`
all fall through to the raw `detail`. On the phone the stepper shows colour-only
dots (`shell.css:1159`). Accessibility baseline is strong: `role=slider` with
`aria-valuetext`, `aria-pressed`, focus traps, `:focus-visible`,
`prefers-reduced-motion`, `aria-live`.

### 2. Frontend stack and efficiency

React 19.2, Vite 7, TypeScript 5.9 strict, `@remotion/player` 4.0.536, a self-hosted
variable font, committed `dist` verified by CI. Bundle: 512 KB main (158 KB gzip),
386 KB lazy Player (123 KB gzip), 109 KB CSS across twelve stylesheets with a
920-line `polish.css` override layer. No polling; SSE with coalesced
`studio:project-changed`. But every change makes `FilmShell.load` fire eight
requests (`FilmShell.tsx:310-330`) while the mounted stage refetches overlapping
data, so reads are two to three times duplicated. `schema.d.ts` is generated
(4,077 lines) yet `api.ts` uses six of its types and hand-writes 71. Frontend tests:
109 pure-logic cases, no component or end-to-end test, no ESLint. `Director.tsx`
is 943 lines, `Images.tsx` 886, `FilmShell.tsx` 789.

### 3. Backend, API and data

`uv run pytest`: 1,532 passed, 2 skipped, 0 failed in 368 s. `ruff check` and
`ruff format --check` clean. 29,789 source lines, 27,045 test lines.

The single-source-of-truth model holds; nothing is a second store. The one real
performance flaw: `production/project.py:395-400` SHA-256s the whole source MP3 on
every `load_project` outside a read snapshot, and `GET /api/projects` does that
twice per film inside an `async def` handler on the event loop. A 20-film library
hashes up to a gigabyte per refresh. Only the `@read_endpoint` routes (images,
film, approvals) use the snapshot and the thread pool.

Other backend findings:

- Error contract is inconsistent: HTTP 200 with `{"error"}` in
  `api/images.py:152-198` and `api/track.py:264-273`; unhandled engine errors become
  500s in `api/storyboard.py:217` and `api/story.py:20`; `FileNotFoundError` text
  forwarded in `api/images.py:85,181` and `api/film.py:193`.
- Library stage states are mtime heuristics with one second of slack
  (`api/projects.py:74-84`), so a same-second edit reads as done.
- The $0.05 per-shot reservation is a user default (`api/images.py:157`); the
  provider's published pricing is stored but not used.
- Upload buffers the whole body before the 25 MB check (`api/projects.py:390-394`).
- `graphics.py` (2,566 lines) is reached for composition only from `cli.py:854`,
  yet owns the ten slowest tests, about 150 s of the suite.
- Schema 1 versus 3, `workflow_version`, `prompt_version` and `renderer_backend`
  are branched on in ten modules; `render.py` (860 lines) is the FFmpeg path kept
  for `uses_remotion == False`; the golden fixture pins `workflow_version=2`, which
  keeps the legacy path alive.
- `cli.py:336 execute` is a 550-line if-chain over 33 subcommands. Still needed from
  it: transcription, listening, recover and resolve-task, backup, reference import,
  adopt, progress, doctor.

### 4. Music understanding and the automatic cut

`analysis.py` measures tempo and beats, a 1 s RMS energy curve, novelty candidates
and pulse candidates, and cuts sections by agglomerative clustering into
`round(duration / 25)` segments (`analysis.py:303-304`). The count comes from the
duration, not the music. `deep_analysis.py` computes a tempogram tempo with octave
rivalry, kick-band downbeats, bar length scores, a Krumhansl key with runner-up,
checkerboard self-similarity sections and bass and vocal onsets. Nothing consumes
it: `edits.cut_material` (`edits.py:865-905`) reads `music.json` only, and no
Director surface sees key, downbeats or the energy curve.

`first_cut.suggest` snaps existing joins within ±1.5 s to section starts, sung
lines and spectral changes (`first_cut.py:79-89`). Beats are in its material and
not used; downbeats never reach it. It never splits or merges, so cut density is
inherited from the storyboard. Travel follows a three-band loudness split; punch-in
on a loud arrival; a 12-frame dissolve on a drop. The report checks coverage,
flash rate, handles and reasons, hold ratio, density against target and energy,
repetition, reading time, advert rules.

A professional editor would miss: cuts on the bar grid and downbeats, cuts that
anticipate a hit by a frame or two, a shot-length rhythm planned per section from
energy rather than warned about afterwards, match-on-action and eyeline logic,
lead-ins for lyric cards, and any use of vocal phrasing beyond line starts. There
is no analysis of what the lyrics mean or of the song's emotional arc anywhere;
meaning enters only through the Writer prompt.

### 5. Visual quality of the film

From the primitives gallery, the real render done here and the code: the
primitives are clean, restrained and consistent. Dissolves, dips, push, slide,
whip with directional blur, grades as CSS filter plus soft-light tint and vignette,
grain as a moved 256 px SVG noise tile, a 0.12° drift. Text is one white system
font with drop shadow and five placements.

What keeps it a slideshow:

- Motion is two-dimensional crop only: zoom at most 1.3 (`timing.mjs:374`),
  smoothstep, no acceleration curves, no speed ramps, no beat-synced motion.
- No depth: no parallax, no foreground and background separation, no orbit, no
  generated motion. The depth experiment in `editor-first-cut.md` separated people
  from backgrounds cleanly and awaits a go.
- Stills are 1536×864 (`models.py:138`), upscaled to 1920 and then by 1.3 on a
  push-in, so the effective source is about 0.62× the output resolution. This is
  the single most visible fidelity leak.
- One light leak gradient and one white flash. No flares, bloom, chromatic
  aberration, bokeh, dust or atmosphere.
- Typography: the composition names "Avenir Next" and embeds no font
  (`remotion.py:992` passes `font: None`), while `implementation_hash` hashes a font
  file the renderer never loads. No per-word lyric timing, no outline or box styles,
  no portrait safe areas.
- Grain tiling is visible on large flat areas at 1080p.
- No 4K, HDR or 60 fps (`fps: Literal[24, 30]`); 9:16 exists in the model but the
  signature refuses it.

With a strong director's cut and strong stills it reads as a well-made photo film
or lyric video, not as a contemporary music video.

### 6. Rendering engine and speed

Measured here on 4 vCPUs with no GPU, one tab, JPEG q95: a 10 s 1080p synthetic
film with push, pan, fade, whip, dip, kinetic text, punch-in, grade and look.

| Run | Wall | Throughput |
| --- | --- | --- |
| Cold full render | 107 s | 2.2 fps end to end; 3.2 fps inside Chrome; bundle 18 s |
| One shot changed | 47 s | 2 of 4 chunks reused, bundle cached |
| Two browsers in parallel, two chunks each | 40 s vs 77 s serial | 1.9× on 4 cores |
| 960×540 proxy, same chunks | 26 s | 3.0× |

Output: H.264 High 4.0, yuv420p, tv range, bt709 tagged, crf 18, AAC 192 kbit/s,
faststart, exact frame count. Renderer tests: 61 of 61.

The 7 min 16 s for a four-minute film goes mostly to Chrome rasterising 1080p CSS
filters, grain and blur in software and JPEG-encoding screenshots over CDP at about
14 fps; libx264 is not the bottleneck, as the T9 record already showed.

Fragile points: every dip or flash trips the broken-frame scan and costs a fresh
Node start, bundle hash, browser launch and `renderStill` on every render; the
bundle key hashes every asset, so any new still selection is an 18 s rebundle; a
failed final leaks its `fresh-` store and cannot resume; the film is decoded twice
for frame counting; three overlapping locks and two cache systems are a lot of
surface for one user. A missing still fails before any browser because
`services/render.py` never passes `preview_placeholders` although the composition
supports them. Nothing automated compares Player and MP4; the record says "matched
by eye on one moment". Player pixels differ from the MP4 by design (RGB on sRGB
versus 4:2:0 tv range, GPU versus software raster, machine fonts) and the Player
seeks only when drift exceeds two frames.

### 7. Titles and the signature

`Titles.jsx` is one producer pair's identity: pink and purple defaults, a fixed
intro choreography, only the filmstrip mark accepted, and `signature.py:128-133`
refusing any opening other than 25 s or credits other than 40 s, any film under 65 s
and anything but 16:9. `kinds.py` calls the package an "editable settings default"
while the validator makes it mandatory for every music video. The names
`MAHA KALA` and `VJDJ69` are literals in `signature.py:18-20` and in the settings
defaults. A 25 s opening before the first picture is 10 to 15 percent of a 3:30 song
and no platform rewards it. For the owner's own releases it is a brand; for anyone
else it is a wall.

### 8. The Director

**Prompts.** Engineering is solid: a 2,000-word budget, versions in front matter,
a deterministic task chooser, a hash on every turn and write, truth rules that
forbid text in pixels and invented facts, a technique table with Use and Avoid
columns. Lines worth keeping verbatim: "Each still shows one decisive instant… a
hold is a creative choice; motion is added to a still, not performed inside it"
(`writer/system.md:13-18`); "A different location or colour grade is not a
different structure" (`writer/concepts.md:28-30`); "Does the last image change the
meaning of the first? Could the story be told with the sound off?"
(`writer/script_mv.md:48-51`); "A cut just before a line starts usually beats a cut
on a beat" (`editor/edit.md:20-21`).

Craft that is missing: no motif system (plant, transform, pay off), no colour
script per section, no mapping of sections to structure (chorus returns and
scales, bridge turns, last chorus is the largest image), no guidance against lyric
literalism, no cliché list, performance mode in one sentence, no vertical or
sound-off rules. All six worked examples share one idiom: courier, record, sleeping
city, neon. The model will anchor on it.

**Context.** The snapshot gives the Writer tempo and at most twelve section labels.
No energy, beats, key, loudness or lyrics with times; passage timings only for the
storyboard task; the treatment clipped to 420 characters. Deep analysis never
reaches it. Stills reach the model only when it calls `get_images`, at most eight
at 512 px; the owner's reference images are never shown. The Editor is asked to
follow the energy curve it cannot see.

**Tools.** Fourteen reads and writes with an owner-only permission gate and
whole-board validation; paid generation and renders are excluded from the MCP
path. On the direct path the model authorises spend itself within the cap
(`tools.py:651-655`). `update_shots` and `update_edit` items are untyped `object`.
Undo exists for five tools by restoring the previous snapshot, not the specific
change. Missing: a song map, describe-image captions, compare two versions,
propose alternatives, batch prompt rewrite, explain a decision, preview frames for
the Editor.

**Gateway.** The default `direct` path already points at OpenCode's hosted
inference as a plain OpenAI-compatible endpoint and uses one model for both roles
(`api/director.py:262-267` ignores `role`). The `opencode serve` path adds a version
window, a password, twelve deny rules, a warm-up session and re-sends the whole
prompt suite as user text every turn into a reused session (`opencode.py:547`).
Neither path shows a token or a dollar: `loop.py` ignores `Usage` and the gateway
ignores `session.usage.updated`. The first-cut acceptance record says it plainly:
"Spend wasn't measured."

**Conversation.** Streaming, stall limits with "Nothing was lost", Stop and undo
are right. No diff of what a write changed ("Story saved."), no record of why,
compaction keeps user snippets and tool names and drops the model's reasoning, the
roles cannot read each other's thread, and the rule is one task per turn.

**Images.** Runware, `imageInference` only, `google-nano-banana-2-1` default,
1376×768 native, one project-wide seed, negatives as prose "Avoid:", look before
subject, no edit mode (every redo is from scratch), no upscale, no generated
character sheet or scene plate. Identity rests on uploaded references plus one
prose line.

**Evaluation.** Honest plumbing that measures format, not quality: zero stored
runs, checks for schema, contiguity and regex facts, a rubric the harness never
sends.

**Autonomy.** Every stage needs a click by design. There is no orchestrator, and
`first_cut.py` is the only model-free step.

## The gap to number one

Three bars define a 2026 top-tier tool of this kind, and the app clears none yet:

1. **The film moves.** Viewers compare against generated video. A still with a
   push-in cannot compete unless it has depth, light and rhythm. The depth
   experiment already proved separation works; nothing in the product uses it.
2. **The AI hears the song.** Every decision in a music video follows the music.
   The Writer and Editor today get a tempo and a list of section labels.
3. **Nothing stops you.** A first draft should exist a few minutes after the drop,
   at a cost shown before you say yes, with every refusal naming the fix.

Everything the app already does well, trust, money, approvals, provenance, is what
the competition lacks. The roadmap below adds the three bars without touching that.

## Roadmap

Ordered by leverage. Each item names the files and the expected effect. Phases
follow the repository's rule: one PR per phase, `pytest` and `ruff` green, an app
that starts, hashes unchanged unless stated.

### Phase A. Finish the blocked-state layer (one to two days)

The cheapest and most visible improvement. Screenshots of every dead end are in the
review evidence.

1. One `engine_error()` helper in `api/_helpers.py` mapping `ValueError` to 400,
   `project_busy` to 409, `FileNotFoundError` to 404 with a stable `code`, applied as
   a router dependency; never forward `FileNotFoundError` text. Remove the HTTP 200
   `{"error"}` bodies in `api/images.py` and `api/track.py`.
2. Route every API error through the `api/errors.ts` copy map: `approval_invalid`,
   `bad_request`, provider codes, `network_error` and no-key become sentences with
   an action (*Open settings*, *Go to Storyboard*).
3. `nextStep.ts`: map permission to "Confirm permission for <name>" with *Go to
   World*; missing profile to "Ask the Writer to build cast and places" or "The
   director needs a model key" with *Open settings*; placeholders to "N shots still
   need a job and a prompt" with *Show them*; never link to the current stage;
   `filmStep` checks for a storyboard before anything else.
4. Show `step.detail` in compact bars as a second line, not a tooltip.
5. Film without a storyboard: skip `GET /edit`, show one card. Confirm the renderer
   setup card renders in the Film grid.
6. Replace skeleton placeholders with human empty states on cards and inspector;
   fix the `Storyboard.tsx:200` header; refresh `ArtifactRating` on project change;
   humanise the cut and titles notes in `cutNotes.ts` and `graphics.py:558`.
7. Phone: stop `.film-line-head` covering the tab row; a real 64 px transport
   variant; words next to the stepper dots.

### Phase B. Make it musical (one week)

1. **Song map.** One `music_map()` in the engine that merges `music.json` and
   `music-deep.json` into sections with names, energy, key, downbeats, bar grid,
   first sung line, candidate changes and a 20-point energy sparkline. Serve it as
   `GET /song-map`, inject it in the Writer snapshot for every task, add a
   `get_song_map` tool for both roles, and feed it to `cut_material`.
2. **Sections from the music.** Use the checkerboard novelty peaks already in
   `deep_analysis.py:560-610` as the primary section source with the count-based
   result as fallback; keep the owner's section map as the layer on top.
3. **Cut on the grid.** Add downbeat and beat tiers to `first_cut.snap_joins`;
   let `suggest` split a long shot on bar lines when the section is loud and merge
   when it is quiet; plan density per section from energy before the cut rather than
   warn afterwards; anticipate hits by one or two frames.
4. **Lyrics into the Writer.** Inject lines with times for `concepts`, `script_*`
   and `import`, not only `storyboard`; stop clipping the treatment.
5. **Auto captions.** Generate lyric text layers from `lyric-timing.json` with the
   Editor choosing which lines; export SRT and VTT with the final.

### Phase C. Make it move (two to three weeks)

1. **Resolution.** Generate or upscale stills to at least 2560 px wide as a new
   immutable version so a 1.3 push-in never shows softness. This is the largest
   visible gain per dollar.
2. **Depth.** Promote the depth experiment: a depth map per selected still
   (Depth Anything V2 Small, Apache-2.0, once, cached by still hash) and two or three
   parallax layers in `BaseFilm` with subtle orbit and dolly, as pure frame
   functions so the Player follows. Off for existing films, so hashes stay.
3. **Motion vocabulary.** Acceleration curves and speed ramps keyed to downbeats,
   a bump on the hit as a camera impulse, a slow drift on holds; bloom and halation,
   soft lens flare, dust and atmosphere as look options; per-pixel grain or a
   larger tile with rotation.
4. **Type.** Embed the font the composition names (the hash already pretends to);
   two or three display faces per style preset; per-word lyric timing; outline and
   box styles; portrait safe areas.
5. **Image-to-video, opt-in.** A paid clip per shot as a new journaled asset
   version through the existing provider path, chosen by the owner per shot, with
   the still kept as fallback. The journal already handles unknown cost.

### Phase D. Make it fast (one week)

1. Parallel browsers, not tabs: K `render.mjs` workers over disjoint chunk lists,
   K = cores ÷ 2, machine lock kept on renders. Measured 1.9× on 4 cores; expect 3 to
   4× on an 8-core Mac.
2. Half-size previews: `render_preview` at 960×540. Measured 3×. Together with
   parallelism a full preview takes under a minute.
3. GPU raster: `chromiumOptions.gl: "angle"` and measure on the Mac; 1.5 to 3× on
   look-heavy frames.
4. Timeline-aware frame scan: skip suspects inside planned dip and flash windows;
   reuse one browser for confirmation; count packets instead of decoding twice.
5. Serve selected assets beside a code-only bundle so a new still never rebundles.
6. Stop hashing the MP3 on every read: `@read_endpoint` on all GET routes,
   `verify_source=False` for views, a cache keyed by path, mtime and size; persist
   the stage hash to `work/stage-state.json` on every approve so the library reads
   exact state.

### Phase E. Make the Director a director (two weeks)

1. **One adapter, many providers.** Collapse the gateway into a multi-provider
   direct adapter with per-role model and provider in Settings (OpenAI-compatible,
   Anthropic, Gemini; OpenCode Go stays as one URL). Retire `opencode serve`, the
   warm-up and the version pin.
2. **Tokens and money.** Handle `Usage` in `loop.py`, price it from a settings
   table, write it to the chat row and the task journal, show per-turn and per-film
   model cost next to image spend.
3. **Craft layer.** A new `shared/craft.md` for the Writer, under 400 words: motif
   plant, transform and pay-off; section to structure mapping; a colour script per
   section; lyric-literalism avoidance; performance from stills; a fifteen-item
   cliché list; 9:16 and sound-off rules. Replace three of the six night-city
   examples with a daytime pastoral, a studio product and an abstract route.
4. **Evolving look.** Optional `creative.sections[]` with palette, light and lens,
   compiled per shot by section, serialised only when set so existing hashes hold.
5. **Consistency engine.** A generated character sheet and scene plate per profile
   entry bound as references (one paid still each, owner-confirmed); edit mode for
   redos instead of regeneration; a per-shot seed derived from the project seed and
   shot id; `negativePrompt` where the schema allows; subject before look.
6. **Richer, typed tools.** Full JSON schema for shot and edit items;
   `propose_alternatives`, `batch_update_prompts`, `describe_images` (cached
   captions), `compare_versions`, `get_preview_frames` for the Editor; every write
   returns `changed_fields` and takes a `reason` persisted to `work/decisions.jsonl`;
   diffs in the tool row; reasons fed to compaction.
7. **One-click first draft.** A server job that chains concepts (one), script,
   profile with fictional cast only, storyboard, prompts, proof batch, first cut and
   preview under one owner authorisation that sets a budget ceiling and records
   draft approvals as a distinct, content-bound kind. Stops only on a real person
   or on budget.
8. **Creative evaluation.** Committed synthetic reference runs per fixture, an LLM
   judge with anchored descriptors for originality, song-specificity, cliché density
   and shot variety, blind pairwise between prompt hashes, and an export of Studio
   thumbs into the report.

### Phase F. Open it up (one week)

1. **Signature as a preset.** Allow a 0 to 5 s opening, a 0 to 10 s end card or no
   titles, portrait layouts and a neutral palette; keep "joint-v1 25/40" as one
   selectable package; move the two names out of `signature.py` into the brand
   settings they already have.
2. **Delivery package.** Poster frame and contact sheet from the rendered film,
   chapters from edit sections, SRT and VTT, opt-in loudness normalisation with the
   measured values in the report for promo and advert, `-g 48`, a 48 kHz option,
   q90 or PNG capture for finals, vertical and square variants from the same cut.
3. **Portability.** Lyric timing beyond Apple Silicon (CPU path or a hosted
   option under the same journal); the headless-shell decision; a one-line doctor
   on the library when a tool is missing.

### Phase G. Pay down the debt (ongoing, behind the above)

1. `schema_version: Literal[3]` in the engine; delete `creative_workflow`,
   `prompt_look_first`, `strict_paid` branches and the FFmpeg `render.py` path;
   regenerate the golden on a schema-3 fixture and say so in the commit. Frozen
   films stay readable through `domain/archive.py`.
2. Move `graphics.compose` and its caches to `legacy/graphics_compose.py` behind
   the CLI; mark the slow tests.
3. A dispatch table for `cli.py`; split `edits.report` into finding families.
4. One shell-level resource cache so a change triggers one fetch per resource;
   type `api.ts` from `schema.d.ts` or delete the generator; split `Director.tsx`,
   `Images.tsx` and `FilmShell.tsx`; add three or four Playwright smoke tests over
   the blocked states, since that is where regressions hide.
5. Reservation from published pricing times 1.5 with the user value as a floor;
   stream the upload with a running byte count.
6. Pixel golden tests: `renderStill` for a dissolve, a whip, a look and a title at
   480×270 with an SSIM tolerance in `npm test`; `smoke-render` in CI; parity for
   `editCamera` and transitions.

## Decisions for the owner

| # | Question | Recommendation |
| --- | --- | --- |
| 1 | Is the 25 s / 40 s signature a brand for your own releases or a rule for the app? | A preset. Keep it default for your films, optional for everything else. |
| 2 | Depth parallax: go or no-go after watching the five clips? | Go, as an optional look per film, off for existing films. |
| 3 | Generated video per shot? | Opt-in per shot, journaled like a still, after depth has shipped. |
| 4 | Keep the OpenCode gateway? | No. Keep OpenCode Go as a provider URL in a multi-provider direct adapter. |
| 5 | One-click first draft under a budget ceiling? | Yes, with draft approvals distinct from yours. |
| 6 | Should the Director be allowed to authorise spend within the cap, as the direct path allows today? | No. Every paid batch asks, with the price. |
| 7 | Order of phases? | A, B, D, C, E, F, G. A and B are small and change how the app feels most. |

## Method and evidence

- UX: 97 screenshots and per-step console and HTTP logs under the session
  scratch folder `ux/shots/`; the app ran through `create_app` on a throwaway
  projects directory with a synthetic 40 s MP3; no key, no paid call.
- Backend: `uv run pytest -x -q --durations=15`, `uv run ruff check .`,
  `uv run ruff format --check .`; line and complexity counts by AST.
- Renderer: `npm ci --ignore-scripts`, `npm test` (61 of 61), four real renders of
  a synthetic 10 s production through `remotion.render_base`, frames inspected,
  `ffprobe` stream info recorded.
- Director: every prompt file read in full; tools, context, loop, gateway and
  compiler read; eval fixtures and reports inspected.

Nothing under `projects/`, `backups/` or `archive/` was present in the clone or
touched. No tracked file other than this document was changed.
