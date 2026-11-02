# Architecture

Two layers: a deterministic engine that owns timing, money and pixels, and a
Studio that presents it. The project folder is the single source of truth; nothing
in the app is a second state store.

## Engine (stable)

| Module | Responsibility |
| --- | --- |
| `models.py` | Pydantic contracts. All timing is integer output frames; dissolve handles cannot exceed either neighbour. |
| `timeline.py`, `pacing.py` | Frame/second lookup, shot-bound caption resolution, adaptive boundary planning with a validated tail. |
| `production/` | Artifact IO, storyboard skeleton, reference binding, the prompt compiler (`image_specs.py`) and the content-bound approval chain (`approvals.py`). |
| `analysis.py`, `deep_analysis.py` | Local measurement only. Every estimate is labelled; nothing invents meter, sections or lyrics. |
| `lyric_tools.py`, `lyric_tools_worker.py` | Optional local lyric timing: Demucs and Parakeet in a private environment, as a separate process. No provider, no upload. |
| `generation.py`, `providers.py` | Runware client with pre-submit journaling: reservation and task UUID are durable before the request; recovery is by UUID and never resubmits; changed bytes are quarantined. |
| `budget.py` | Cap, committed cost, unresolved reservations, admission. |
| `remotion.py`, `ffmpeg.py` | Remotion render entry (film, titles review stills). `ffmpeg.py` holds the probe, mux and verification helpers; no FFmpeg path draws a picture. Every film is schema 3. |
| `chunks.py`, `framecheck.py` | One render chunk per shot and its reuse key; finding broken frames in a rendered movie. |
| `titles.py`, `graphics.py` | Integer-frame title windows; the graphics spec, palette and frame drawers. |
| `legacy/` | The old compositor and reviews of its samples. Only `cli.py` and `signature.validate_review` reach it; a test holds `api/`, `services/`, `director/` and `jobs/` to never importing it. |
| `domain/archive.py` | Read-only view of frozen productions (title, duration, newest final render, selected stills). |

## Production folder

```text
projects/<slug>/
  project.json          slug, title, duration, fps, aspect, model settings, source hash
  media/song.mp3        immutable source audio
  brief.json            intent, treatment, look, characters, scenes, references
  work/idea.jsonl       append-only: your pasted idea, word for word, and how it was sorted
  work/story-beats.json when each passage of the treatment plays (outside any approval)
  work/audio/           derived excerpt WAV for promo/advert (source stays untouched)
  work/music.json       measured beats/energy/sections
  work/lyrics.json      supplied or transcribed lyrics (drafts until reviewed)
  work/lyric-timing.json when each line starts (tapped or estimated), matched by text
  work/section-map.json the owner's corrected sections, a layer over the measurement
  work/heard/           words the local tools heard, cached by audio and tool versions
  work/storyboard.json  shots: stable ID, frames, kind, purpose, message, text, prompt, camera
  work/assets.json      generated versions per shot: path, sha256, input_hash, selected
  work/local-plates/    deterministic cards, splits, bridges, logos and end cards
  work/tasks.json       paid-task journal (reservation before submit)
  work/prompt-current.json / prompt-artifacts.jsonl
                        assembled prompt hash and file versions per turn/write
  renders/, previews/   versioned outputs plus a report JSON
  work/reviews/         titles review stills (not the verdict record)
```

`projects/`, `backups/` and `archive/` are never deleted and never rewritten in
place. Code rollback is the git tag `pre-gui-rework`; production rollback is the
metadata snapshot in `backups/` written by `scripts/snapshot_projects.py`.

## Track: words on the song, and corrected sections

`work/music.json` and `work/lyrics.json` sit in the approval chain, so nothing on
Track writes to them after the words are saved. Two layers sit beside them:

- `domain/lyric_timing.py` keeps when each line starts in `work/lyric-timing.json`.
  Lines match back to the words by text, so editing a line clears only that line's
  time. `[Spoken Hook]` lines are headings and are never timed; production notes after
  a colon or comma stay out of the name. A time is either tapped, automatic or an LRC
  line's own, and a time is never guessed.
- `domain/section_map.py` keeps moved, added and joined sections in
  `work/section-map.json`. Reset writes the layer empty, so it needs no re-measuring.
  The Writer, the Director and newly seeded cuts read the layer; existing cuts keep
  their own sections, and their names match by start frame.

`lyric_tools.py` is optional. A button installs pinned tools
(`lyric_tools.lock.txt`, Python 3.11) under `~/.cache/mp3-to-videoclip/lyric-tools`,
apart from the Studio's environment, after saying what it downloads. A job isolates
vocals with Demucs, hears words with Parakeet and aligns them to the known lyrics.
Heard words are cached in `work/heard/` by audio and lock hash. Lines not heard stay
untimed, and tapped lines are never overwritten. It runs on Apple Silicon only, because the
word recogniser is MLX: other machines keep tap-along, and a story film's captions stay per line,
which are exact by construction. Tests use a fake runner.

Suno's MP3s carry their lyrics and tags in the file, which Track offers as a starting
point. Section proposals start a sung part at its first word and an instrumental part
at the last word before it, then move a start to a detected edge up to 5 s earlier,
never back across a sung word.

Licences: Parakeet TDT 0.6 v3 is CC BY 4.0 (NVIDIA). Demucs is MIT; its repository is
archived and its README states no separate licence for the pretrained weights.

## Production kinds and intake

Every new production carries `project.kind` (`music_video`, `promo`, `advert` or
`narrative`, the story film). The code table in `kinds.py` is authoritative for lengths, default
style, text density, pacing, opening/closing and whether the 25/40 graphics
signature is required; the prose block the Writer reads is
`director/prompts/kinds/<kind>.md`. Music videos keep the 25 s opening and 40 s
credits. Promo and advert are created with `signature_required=false`, no
`brand.json` and no `graphics-spec.json`; their final render is the film itself,
without intro or credits.

The Story intake is one card over `GET/PUT /api/projects/<slug>/intake`. It
writes `brief.intent` (objective, audience, message, reasons, tone,
mandatories, avoid, CTA, length, window), selects a style preset and, for
promo/advert, the excerpt window. The optionals are serialized only when set, so
legacy brief and project payloads keep their approval hashes.

Story opens on a choice. **Your idea** goes through `idea.py`: the paste is kept
in `work/idea.jsonl` and saved whole as the treatment, so a failed Writer turn
loses nothing. The Writer's `sort_idea` tool may only say which sentences are
story, style, rules or avoid: anything not word for word in the paste, used twice
or left out is refused, and the brief receives the paste's own characters. A sort
is refused once the brief has been edited since, because it would overwrite those
edits. **Concepts from the music** asks for one to three routes, each with beats
timed on the song. `story_beats.py` stores when each passage plays outside the
brief, so placing never un-approves the story. The treatment stays the only copy
of the words: a passage that no longer matches reads as not on the song, and is
never given a guessed time. The Writer's storyboard task sees these passages in its
project snapshot and keeps each one's shots inside its time; they stay evidence, in
no approval hash.

`project.duration` is the film duration. `project.source_duration` is the full
recording and `project.audio_window` is the absolute source window with fades.
`audio.py` writes a derived PCM WAV under `work/audio/`, keyed by source hash and
window; the source MP3 is only read. Analysis, the live Player, preview, base and
final all render the excerpt. A window change is refused once a storyboard,
non-empty event map or lyrics exist, and it deletes stale measurement. A new start
or end also moves the story's timings to `work/story-beats-history/`, because they
count from the film's first frame: every passage then reads as not on the song. A
new fade keeps them.

Style presets are Markdown files in `director/prompts/styles/` with a small
JSON-valued header (look, image rules, model settings, protected flag). The
settings API exposes the list. `photographic-painted-v2` keeps its approved core
verbatim and is the only protected preset; choosing it or inheriting it still
requires the core at the start of `creative.look`. Custom looks and the other
presets are not prefixed with that core.

## Writer/Editor prompts

Every prompt file starts with a `version:` front-matter block. The app assembles
one task at a time: `writer|editor/system.md`, `shared/truth.md`,
`kinds/<kind>.md`, `styles/<preset>.md` (Writer only), the task file and its
worked example. `director/prompts.py` chooses the task deterministically from
the stage and the artifacts already written: Story moves from brief to concepts
to script to revise, and a treatment with no concepts on file goes straight to the
script. A Story button that means one job (sort, concepts, place, script) names
its task in the chat request; Storyboard loads the board task; Images loads prompts or
review; Track and Film route to the Editor. The assembled text is under 2,000
words per Writer task, excluding the project snapshot appended by the API.

`work/prompt-current.json` carries the assembled hash and every file version for
the current turn; `work/prompt-artifacts.jsonl` appends the same metadata when a
tool writes the brief, treatments, proof shots or storyboard. Chat history keeps
the metadata on the user turn. A bad output can therefore be traced to the exact
prompt revision without changing any artifact schema or approval hash.

`permission_confirmed` is an owner-only gate. `production.update_brief` and
`set_creative_profile` keep the stored value on every write and start new entries
at false; only `PATCH /brief`, the Characters card's route, passes `owner=True`.
A Writer learns who is waiting from `owner_must_confirm` in those tools' results,
the project snapshot and the refusal itself, and asks the owner.

`shared/craft.md` loads for the writing tasks, and storyboard and profile carry a digest of
it inside the budget. New films use prompt version 3: subject before look, a look per section,
`brief.avoid` in `negativePrompt` where the live schema has it, and a seed per shot. Version 2
films keep every hash until the owner switches on Story's Look card, which marks their stills out
of date. `sheets.py` buys character sheets and scene plates through the journal; binding one is the
owner's click and asks for the story to be approved again.

## Story films

`spine: "soundtrack"` means the film has no source: `source` and `source_sha256` are absent and
`render_audio` returns `production/soundtrack.py`'s WAV, keyed on every input. Its length is written
only by `soundtrack.set_duration` and stays out of the stage hashes, so re-recording a line leaves the
script approved. The chain is brief, `script`, `voice`, storyboard. `narration_timing.py` says when each
line is said, estimated or measured; `board.retime_lines` re-derives bound shots' frames from it and
`edits.retime_by_lines` moves the cut with them. `narration.py` buys takes through the same journal as
stills. `production/soundtrack.py` mixes the takes with a bed and ambience spans, measures the result, and
keeps a receipt the render report copies. `clips.py` buys a clip of a selected still through the same journal
and keeps it beside the versions in `work/assets.json`; `production.selected_clip` is the one rule for
whether it plays. `delivery.py` writes the package beside a final and `reframe.py` is the arithmetic of a version of another
shape. `structures.py` is the template table, and `analysis.analyze_narration` keeps the keys of
`analyze` so the Spine and `cut_material` read speech without knowing.

## Decisions and first drafts

Every write a Director turn makes needs a `reason`. `director/decisions.py` works out what changed from the
artifact itself, before and after, and appends one line to `work/decisions.jsonl`. No approval reads it. The
other role gets a short "From the Writer" block in its prompt, not the whole thread.

`services/first_draft.py` runs one owner-authorised job from concept to a preview. What it approves is
recorded `via: "draft"`, only brief, storyboard and proof can be, and a later stage refuses to build on a draft
until the owner has made it theirs. It spends at most three stills out of its reserve and checks its model
allowance before every turn, in tokens as well as dollars because text models have no known price.

## Evaluation and ratings

Three frozen fixtures and their automatic checks live in `tests/evals/`. The
Writer checks cover one to three distinct concept structures, board coverage, local
kinds for the advert and invented claims; the Editor checks cover edit-report
hard findings and the advert's first-five-seconds/end-card rules. The command
`uv run python -m tests.evals` writes one report page per current prompt hash,
one per stored run hash and one for rating-only or unbound hashes, with no model
or network call. A page with no run says so instead of inventing a result. `tests/evals/rubric.py` defines the other-role
cross-review rubric; the harness validates a supplied review but never sends it.
`tests/evals/README.md` owns the run-bundle contract and `docs/EVALUATION.md`
records the evaluation policy.

Artifact thumbs are append-only rows in `work/ratings.jsonl`. `ratings.py` binds
each row to the artifact hash and to the last prompt write for that artifact from
`work/prompt-artifacts.jsonl`; ratings made without prompt history are unbound.
The Studio shows the control on Story (brief/concepts), Storyboard and Film
(edit), and the API is `GET/POST /api/projects/<slug>/ratings`. Ratings are
signals, never approvals, and a later artifact write marks the old row stale.

## Shot kinds and local plates

`shotkinds.py` owns the only paid/local decision. `scene`, generated `product`
and `bridge.mode=generated` compile an image spec and may enter a quote. `card`,
`upload`, `split`, `reprise`, `logo`, `end_card`, designed `bridge` and a
`product` with an uploaded `asset` are local: Pillow renders a deterministic
full-frame PNG under `work/local-plates/`, keyed by the shot definition, project
size, source panes and `LOCAL_PLATE_VERSION`. The split plate remains the
fallback when a pane still is missing or stale; when every pane is current,
`RenderShot` also carries native pane sources and `BaseFilm` draws the split
primitive itself in both the MP4 and the Player.

`Shot.kind`, `message`, `text`, `bridge`, `product_ref`, `panes` and `asset` are
dropped from serialization while they hold defaults. Legacy shots, briefs and
approval hashes therefore stay byte-stable. `proof_ids`, `quote_images`,
`reviews.require_accepted` and preflight operate on paid kinds only; the proof
stage hash also binds local plate bytes where they can render (or the shot
definition for a split whose panes do not exist yet), and the stills stage binds
every local plate. `GET /api/projects/<slug>/plates/<shot_id>` serves the local
file; the Player points local shots at that URL and keeps paid shots on the
existing image route.

## Edit list, cut report and primitives

T4 moved timing and motion out of the storyboard into `work/edit.json`. The
storyboard remains the content source; the edit owns order, spans, transitions,
camera motion, accents, text timing and grade. `EditDecisionList.check_board`
requires every storyboard shot exactly once and contiguous coverage of the full
duration. `production.resolved_assets` applies the edit to a derived effective
board and attaches the matching `EditShot` and `Grade` to every `RenderShot`, so
the MP4 and the Player consume one payload. A production without an edit keeps
the old storyboard timing and approval hashes byte-for-byte.

Once an edit exists, `update_shots` refuses timing and motion fields and the
Storyboard timeline is read-only. `GET /api/projects/<slug>/edit` returns the cut
and its computed report; `PUT /edit` saves a whole cut; `POST /edit/seed` moves
the approved storyboard timing into the first edit without rewriting content.
The Editor gets `get_edit`/`update_edit` tools and the report in its project
snapshot.

The shared `renderers/remotion/src/timing.mjs` and `BaseFilm.jsx` implement edit
transitions (`dip_to_black`, `dip_to_white`, `whip_pan`, `push`, `slide`), accents
(`punch_in`, `flash`, `light_leak`), split layouts, text animations (`fade`,
`type_on`, `slide_up`, `pop`, `kinetic_words`) and grade presets with slider
overrides. `request.mjs` refuses more than three flash accents in any one-second
window, independently of the Python report. `docs/EDITING.md` owns the schema,
report rules and sample gallery; `tests/test_edits.py` and
`renderers/remotion/tests/edit-primitives.test.mjs` pin the contracts.

`first_cut.py` suggests a cut with no model: it snaps joins to sections and sung lines
through `pacing.snap_joins`, varies moves with the song's own loudness, and writes each
section's feel. It writes nothing, and Film saves a suggestion like any other cut.
`seed_edit` stays faithful to an approved cut. `edits.cut_material` gives the Editor the
same evidence through `get_cut_material`.

## Money and evidence

The journal is the only thing that protects real money, so it stays strict: a
quote is scoped and hashed, authorization is user-owned, a submission is recorded
before it is sent, recovery is by UUID, and an unreported cost keeps its
reservation. Rendering, analysis and verification are local and free.

A task that never comes back holds the film's spending. `GET /budget` names it, and the budget
popover offers `POST /tasks/<id>/recover`, a free read that never resubmits, and
`POST /tasks/<id>/resolve`, the owner's billed amount with evidence. Nothing resolves one by itself.

## Presentation

`app.py` is the FastAPI factory; `api/` exposes the five stages, approvals,
library, jobs and settings; `frontend/` is the Vite/React Studio; `jobs/` runs
local work with per-project serialisation. `launcher.py` is `uv run studio`.

The frontend starts from the neutral `styles/tokens.css` palette and a
self-hosted Schibsted Grotesk variable font; `ui/` holds the token-only
`Button`, `IconButton`, `StatusDot`, `Pill`, `Seg`, `Chip` and `Field`
primitives. The shell keeps one `/api/events` EventSource open for jobs, with
JSON payloads and reconnect/backoff; there is no polling. Job progress is
reported in real units (images, frames) and stays indeterminate otherwise. The types the screens read are
hand-written in `frontend/src/api.ts`. Every API 4xx/5xx is `{detail, code}`; the frontend parses
it into `ApiError` and maps stable codes to user-facing copy and, where there is
one next move, an action (Open settings, Go to a stage).

Views read no source bytes. `load_project` verifies the source through a hash remembered
by path, size, mtime and inode, and the library and project views skip it altogether;
approval, generation and render paths still hash the bytes. The library's stage words
come from whether each decision's recorded hash still matches (`production/stage_state.py`),
remembered in a file beside the settings until a metadata file moves. No gate reads that
file, and opening the library writes nothing into a film's folder.

The song map (`song_map.py`, held in memory by its inputs, so reading a film writes nothing) merges `music.json`,
`music-deep.json`, the owner's section layer and the timed words into one object in film
frames, served at `/song-map`, given to every role as `get_song_map` and summarised in
every Director snapshot. Sections come from the deep pass's checkerboard boundaries when
it found at least two, under the owner's layer, and never rewrite `music.json`, so no
approval moves. The deep pass is the second phase of analysis. `music_map.py` is a
different thing: the paid listening draft for music-led films.

Settings is one schema 3 TOML file, nested by what a value is for (`roles`, `voices`,
`pictures`, `keys`, `new_films`, `prices`, `computer`), with the old flat names kept as
read-only properties so no caller had to change. `catalog.py` and `catalog.toml` say what
can be chosen: a price appears only with its source and date, and a refresh runs on a
click through free calls and never overwrites a static price. `caches.py` is the one list
of derived folders that may be cleared. Stored choices that do nothing yet are named in the API's `notes`: thinking level, token
budgets and picture models per look.

Engine refusals reach the API through one mapping, `api/errors.py:engine_error`,
installed as app exception handlers: `ValueError` is 400, `ProjectBusy` and
`RevisionConflict` 409, a missing Runware key 409 `no_runware_key`, `ProviderError`
502 with its code, and `FileNotFoundError` 404 with a per-artifact code and never a
path. Routes keep their own `except` only to say something more specific.
`needs_budget` and `needs_new_round` are 200s, because they are decisions and not
failures.

`cli.py` remains for engine tasks that do not have a GUI
yet: 14 commands for transcription, the listening pass, backups, recovery and diagnostics.

The Studio shell is hash-routed: `#/` is the library, `#/:slug/:stage` is a
production and `#/archive/:slug` is a delivered, read-only film. `GET
/api/projects` returns one `ProjectSummary` per production with poster stills,
cheap stage states, the next step, remaining budget and an update time; the
library uses those without re-hashing every gate. Inside a production one
`PlayerProvider` owns the only `<audio>` element and the shared time store.
`spine/Spine.tsx` draws the waveform, filmstrip, sections and playhead from that
store, and Storyboard owns boundary dragging.
Film's Remotion `LivePlayer` seeks from the same time, so switching stages keeps
the playhead. The director is a drawer, open by default above 1180 px except on
Film, remembered per stage, and an overlay below that width; approvals and library
refreshes travel over a
`studio:project-changed` event.

### Live updates

A view reloads itself whenever the data behind it changes; nothing needs a
browser refresh. The server announces four kinds of change on the one
`/api/events` stream, each naming its film:

- every mutating request under `/api/projects/<slug>` that ends 2xx publishes
  `project.changed` once its body is complete (`app.StudioGuard`, a pure ASGI
  middleware so the SSE and NDJSON streams are never buffered);
- every finished director tool that is not a read publishes `project.changed`
  while the turn streams;
- jobs publish `job.queued/started/progress/succeeded/failed/cancelled` with
  `project` and `kind`; engine `operations.phase/tick` calls reach the runner
  through a context-variable observer, and an image batch also publishes
  `project.changed` per finished still; every job ends with one;
- `jobs/watch.py` fingerprints each production (top-level and `work/` JSON, film
  names) once a second while a browser listens, so CLI writes show up too. A
  request absorbs its own write so it is announced once.

`jobs/store.ts` turns these into the coalesced `studio:project-changed` window
event (`useProjectChanged(slug, reload)`), drops other films' notices while a
film is open, and resyncs everything after a reconnect. GET handlers must never
write what the watcher fingerprints (`tests/test_live_updates.py` pins this), or
a read would reload every open view forever.

Film is a workspace rather than a page. `stages/Film.tsx` holds the selection and
renders the viewer in the main area and, through portals into shell slots,
`film/FilmPanel.tsx` and `film/FilmTimeline.tsx`; the Director takes the panel's slot
while open, so nothing remounts. `film/cutEditor.ts` shows a change at once and saves
one at a time against the revision the server last returned, and keeps the session's
earlier cuts for undo. `film/cutNotes.ts` turns report codes into plain notes. The
stills approval binds the cut, so a new cut un-approves it; with every still kept,
Film asks for that sign-off in one click instead of sending you to Images.

Approvals are made in one place per screen: the sticky next-step bar (with an
optional note; in Film's top bar without one), or the attested preview/titles lines
in Film's delivery panel. Stage pages show a
read-only sign-off strip (`ApprovalBar`) fed by the shell's single approvals
snapshot. A busy production (another writer holds the project lock) answers
409 `project_busy`. Cancelling an image batch stops admission through
`operations.stop_requested()`; a still already sent still finishes and is
journaled.

Archived productions never pass through `project_root`; dedicated
`/api/projects/<slug>/archive/render` and `/archive/stills/<index>` routes serve
their bytes read-only, so no filesystem path is exposed. `GET /budget` reports
`spent_usd`, `reserved_usd`, `paid_stills` and `unresolved` separately from
`committed_usd`; the budget popover reads the current cap before posting a
top-up as the new cap.

## Director adapter

`director/llm.py` is one interface over every provider; `director/providers/` holds the wire
formats (OpenAI-compatible, Anthropic, Gemini), each yielding the same events. Each role has its
own provider and model in Settings, and `director/routing.py` turns that into an address and a
key. A role with no key for its provider is refused by name: nothing swaps to another model to
find a key that works.

Earlier history reaches a model as what was asked and what was said; a logged tool result has lost
the call it answered, and the snapshot rebuilt each turn is the current state. Reasoning written
between tool calls is logged and survives compaction. A turn stops at 40 tool calls, which the
owner can extend with *Keep going*, or when the same call fails twice with the same arguments. A
Critic starts with no history every time.

`work/model-usage.jsonl` records what each turn used, apart from the money journal on purpose: the
journal's contract is a reservation before a request and a cost the provider reports, and a model
call has neither. A cost is a catalogue estimate, or unknown; never zero. It is not admitted against
a film's cap. The Director never authorises spending: `generate_images` prices a batch and the owner
buys it with the button that puts in the conversation.

`director/mcp.py` remains for outside agents (your own OpenCode, Claude Code, a script), over the
same tools with the paid ones excluded. The Studio does not use it.

**Migration from the OpenCode gateway.** It is retired. `gateway`, `opencode_bin` and
`opencode_workspace` are ignored on load, and the first save keeps the old file as
`settings.toml.v<n>.bak`. A file on the direct path keeps the one model that really answered it, as
provider `direct`. A file on the gateway keeps its role models, which now need that provider's own
key in Settings, because logins stored inside OpenCode can't be used. A fresh install starts every
role on `gpt-6-luna` through OpenCode Go, the model the story film proved; `gpt-6.1-sol` is not on Go. `llm_*` still means your own
endpoint; an OpenCode Go key saved there still counts for OpenCode Go.

## Layout

```text
app.py            FastAPI factory, static files, lifespan
launcher.py       `uv run studio`: free port, build frontend if stale, open browser
api/              projects, track, story, storyboard, images, film, director, jobs, budget, approvals, settings, setup
domain/           intake, models, approvals, archive, budget, lyrics, sections
services/         analysis, generation, graphics, transcription, render, preview input, runware
director/         provider adapters, routing, MCP bridge, tools, context, prompts, conversation
edits.py          edit decision list, effective board, report and flash rule
jobs/             asyncio runner, per-project serialisation, SSE events
frontend/         Vite + React + TypeScript, @remotion/player for the real composition
renderers/remotion/src/Film.jsx (BaseFilm + Titles) + timing.mjs
                  one composition and one frame model shared by MP4, review
                  stills and Player
```

Every artifact has a cheap fingerprint. A changed fingerprint makes its approval
stale, and the stage says so; the gate blocks until the current bytes are reviewed
and re-approved. One budget per production pauses a paid job as `needs_budget`
when it runs out.
The phase plans and acceptance records are in `.opencode/tasks/`, with the latest state at the end
of `roadmap-2026-11.md` and `museum-of-tomorrow.md`. Renderer notes stay in `docs/RENDERER.md`.
