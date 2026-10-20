# MP3 to videoclip — staged MVP

An **agent-operated** workflow, not a web app or one-click autonomous generator.
The agent writes creative artifacts; scripts measure music, enforce review gates,
track paid requests and render the film locally. New productions use **Remotion**
as the primary visual renderer (deliberate movement, keyframes, transitions and
effects chosen per shot purpose) with **FFmpeg** retained for encoding, audio mux,
probing and legacy compatibility — no AI character animation and no paid call in
post. See [PLAN.md](PLAN.md) for the agreed scope.

## Setup

Prerequisites: Python 3.12/3.13, uv, git, ffmpeg and ffprobe.

```sh
uv sync --locked
uv run python scripts/bootstrap_production.py
uv run clip doctor
```

The bootstrap command validates the local bundle (seven inline production agents,
the ten `clip-*` skills, `LOOP.md`) before changing anything. `--check` is
read-only: no clone, checkout, install, archive or network. A normal run reuses
the cached checkout, installs the five selected pinned recipes, and archives the
deselected motion recipes byte-for-byte under `backups/unused-motion-skills/`
(ignored, never edited). Re-running changes nothing.

OpenCode loads `LOOP.md` as project instructions and this project defaults to the
`film-director` agent — the single canonical state and only paid coordinator —
with six non-nesting specialists (`music-editor`, `short-film-writer`,
`visual-director`, `visual-critic`, `post-editor`, `film-finisher`). Two bounded
feedback lanes run before the user gates: the writer revises the story once after
the critic's narrative findings and the music-editor's music-binding findings, and
the visual-director revises the board once after the critic's visual-story/
continuity findings and the post-editor's render-feasibility findings — the
director only accepts, blocks or integrates. See [LOOP.md](LOOP.md) and
[docs/PRODUCTION_CREW_PLAN.md](docs/PRODUCTION_CREW_PLAN.md). `default_agent` and
the inline agent permissions apply to fresh, unselected sessions; reload the
project after changing configuration. A config edit is not runtime proof that a
denial or routing change took effect — confirm it in a fresh session rather than
asserting the fix from the file alone.

Runware MCP is project-scoped in `opencode.json`. Use OpenCode's `/mcps` to inspect
the connection and sign in if needed. Hosted OAuth asks for your Runware key on
`mcp.runware.ai`, not in project configuration. The controlled batch executor
uses `PROJECT_VEIL_RUNWARE_API` from the shell for both images and default cloud
transcription. No OpenAI key is needed for the Runware route. The optional legacy
OpenAI adapter still requires `OPENAI_API_KEY`; provider OAuth is not an API key.
Never put credentials into project JSON or tracked files.
By explicit user choice, this project shares the existing **project-veil** key.
The CLI requires `PROJECT_VEIL_RUNWARE_API` and ignores generic `RUNWARE_API_KEY`
and the previously proposed `MP3_TO_VIDEOCLIP_RUNWARE_API_KEY`. The existing
shell secrets setup already exports the selected variable; no key copying or
secret-file edits are needed. Other projects' credentials and MCP login stay
unchanged. Verify availability without displaying any credential:

```sh
uv run clip doctor
```

The example file is documentation only; the CLI does not automatically load `.env`.

Official Runware recipes are installed from a pinned external checkout into
ignored `.opencode/skills/`. Five still-production recipes are enabled, with their
references; the two motion recipes are archived out of active discovery under
`backups/unused-motion-skills/` instead of installed. `scripts/bootstrap_production.py`
(and `--check` for validation only) is the one bootstrap command; do not
redistribute the upstream recipes without resolving licensing. See
[.opencode/SOURCES.md](.opencode/SOURCES.md). Reload the project session if new
skills are not yet visible. Upstream model defaults never override our approval
and spending rules. MCP catalog queries are useful; paid MCP `run` calls require
approval and do **not** automatically populate our local batch journal. Use the
CLI batch executor for tracked generation. Do not call MCP generation without
first adding equivalent durable tracking (interactive result import is not yet
implemented).

### Studio shell: spine, actions, inspector, intake

```sh
uv run clip studio                       # cross-project index with "what needs you" actions
uv run clip spine status                 # durable run journal (SQLite, rebuildable)
uv run clip spine runs --limit 10        # recent runs, steps and open human waits
uv run clip spine events --run RUN_ID    # append-only event stream for a live view
uv run clip inspect PROJECT --shot s028  # per-shot page: versions, verdicts, edit commands
uv run clip inspect PROJECT              # index of every shot, with build commands
uv run clip intake                       # static wizard that emits init + budget commands
```

`clip spine` is the durable substrate for the app: one run per intent, one step per tool
call, an idempotency key so a replay never repeats work or a charge, a lease per run so a
crashed owner is reported instead of silently retried, and durable human waits that never
expire into consent. It is a **rebuildable journal** — artifacts stay canonical, and
deleting the database loses no work.

`clip studio` now carries per-production action objects: the next gate, a missing cap, a
rejected still, an interrupted run. Every action is either a link to an artifact or a
command template (`--note '<your decision>'`) with a copy button; nothing is approved,
selected or spent from the page.

`clip inspect` renders one static page per shot: version filmstrip with verdicts, the shot
contract and compiled prompt, and controls that compose `clip shot-edit`, `clip adopt` and
`clip review` commands — plus an explicit statement of which approvals an edit invalidates.

The **live layer** is deliberately the smallest possible: a loopback server with no
write endpoints.

```sh
uv run clip spine sync                    # index existing work/operations receipts as runs
uv run clip serve --port 8765             # read-only SSE studio; prints a tokenised URL
```

`clip serve` binds `127.0.0.1`, requires a per-session token, exposes `GET` only
(`/api/health`, `/api/status`, `/api/runs`, `/api/events`, `/api/stream`, `/api/studio`)
and answers every write verb with `405`. The page it serves tails the journal live; it
cannot approve, select, spend or edit, because those remain CLI commands under the
project lock.

### MCP surface

```sh
uv run clip mcp --projects-dir projects     # stdio JSON-RPC
```

`clip mcp` exposes **read/derive tools only** — `status`, `costs`, `studio`,
`plan_build`, `preflight`, `dashboard`, `inspect`. Everything that edits canon, spends or
decides (`approve`, `authorize`, `generate`, `shot-edit`, `resolve-task`) is absent from
`tools/list`, not merely discouraged. Project arguments resolve inside `projects/`, and
generated pages are returned as `text/html;profile=mcp-app` resources so a host can render
them in a sandboxed iframe; `resources/read` refuses any path outside a dashboard folder.

### Plans: the agent's unit of work

```sh
uv run clip plan build PROJECT --intent 'advance to delivery'
uv run clip plan list PROJECT
uv run clip plan show PROJECT --id plan-...
uv run clip plan run  PROJECT --id plan-... [--allow-edit]
```

A plan is data: ordered steps, the command each would run, whether it needs a human
decision or a placeholder it cannot fill, and which approvals it invalidates. Building a
plan changes nothing. Running one executes only concrete local steps through the spine and
**stops** at the first human decision, placeholder or missing capability — opening a
durable wait rather than guessing. `--allow-edit` is required before a run may change
canonical artifacts; `approve`, `authorize` and `resolve-task` never run unattended.

### Capability registry

`src/mp3_to_videoclip/tools.py` classifies every command once as `read`, `derive`, `edit`,
`spend` or `human`. A test fails if a command is added without a scope, so the registry
cannot drift from the parser. Default agent capability is `read + derive`; `edit` requires
explicit delegation; `approve`, `authorize` and `resolve-task` are **human-only** and
cannot be granted to an agent at all.

`clip intake` validates a new production before anything exists and emits only the
commands the kernel would accept: title/slug, source path, aspect, fps, music mode,
factual credits, cap and correction limit. Portrait plans warn about the 16:9-only
signature; missing credits or a non-positive cap block the command.

## Production layout

```text
projects/<slug>/
  project.json                  # Source hash, aspect, output dimensions/FPS
  brief.json                    # Selected treatment, direction, visual rules
  media/song.mp3                # Private local copy; original untouched
  media/references/             # Optional authorized protagonist photos
  work/music.json               # Local beat, energy and section estimates
  work/lyrics.json               # Timestamped words/segments for review
  work/storyboard.json           # Canonical, integer-frame shot timeline
  work/approvals.json            # User decisions bound to content hashes
  work/quotes/, authorizations.json, tasks.json, assets.json
  assets/<shot>/vNNN-<task>.jpg   # Immutable generated stills
  work/plates/                  # Content-keyed FFmpeg shot cache
  renders/stills-vNNN.mp4        # Versioned H264 + AAC output and JSON report
```

Everything under `projects/` is ignored, including audio, faces, temporary
provider URLs and prompts. Back up private production folders yourself; Git
does not preserve them.

## Workflow

**New default:** the versioned `photographic-painted-v2` on Nano Banana
2.1. Restore the supplied Ross / Dell'Otto photographic-painted language and put
it first. The user has approved the rooftop control's rendering as the visual
benchmark (`profiles.STYLE_BENCHMARK`); its subject, scene, lettering and layout
are not defaults. The core cannot be shortened in a default-preset brief; append
film-specific palette/light after a blank line. New story proofs still need
actual style comparison, not automatic acceptance or another paid calibration.
Music-appropriate coverage replaces a universal 4–12-second rule: energetic mixes
can use 4–6-second holds and short inserts, with deliberate longer holds where earned.
Keep one correction after an original, not an automatic retry cycle. Read
[Still-film workflow](docs/STILL_FILM_WORKFLOW.md) for the nine focused stage
skills, stronger story/storyboard contracts and exact CLI configuration.

### Film name, signature and style calibration

Choose the film title first; keep the source filename only as provenance:

```sh
uv run clip init projects/the-last-light --title 'The Last Light' --mp3 /path/to/source.mp3
```

The folder slug is derived from `--title`; `--slug` remains an explicit override
for deliberate versioned IDs. Existing projects are never renamed or migrated.
New projects get a draft `work/graphics-spec.json`: fill its factual credit cards
and set `credit_roles_confirmed: true` only after confirmation, before approving
the brief. The required signature uses the existing graphics pipeline, shared
MAHA KALA × VJDJ69 identity, 25-second opening and final 40-second credits inside
the original audio. No randomized demo roles or appended tail. That compositor is
16:9-only; portrait signature plans must be resolved before brief approval/spend.

After accepted stills:

```sh
uv run clip render projects/the-last-light --base-only
# Inspect the generated composited samples listed in work/graphics-review.json.
uv run clip approve projects/the-last-light graphics --inspected --note 'Actual inspection and decision'
uv run clip render projects/the-last-light
```

The first output is explicitly **not final**. Normal rendering requires current
graphics approval and composites the intro/credits; changed board/stills/spec/base
or sample bytes invalidate the relevant gate. Existing films retain their legacy
render and approval behaviour.

The separate style-control route creates no fake movie/audio approvals. The
current approved control is already retained; only a separately authorized style
change needs another job. Example for such a **new** scope:

```sh
uv run clip style-test quote style-tests/new-style-control --reserve 0.10
# Only with explicit authority for this exact one-image scope:
uv run clip style-test run style-tests/new-style-control --quote QUOTE_ID --cap 0.10 --note 'Authority for one exact rooftop control; no retries'
uv run clip style-test recover style-tests/new-style-control --task TASK_UUID
# Only after the user's actual visual decision, never automatic agent approval:
uv run clip style-test approve style-tests/new-style-control --task TASK_UUID --note 'Actual user decision'
```

It retains the exact supplied prompt (including its deliberate test lettering),
schema, settings, UUID, reservation, result, cost and hash. One image per workspace;
no reference upload, automatic retry or automatic fingerprint acceptance.
`style-tests/` is private and ignored like `projects/`.

New CLI projects default to **workflow 2**: explicit character states, immutable
reference imports, version-bound image reviews, cumulative spending/retry limits,
timeline-aware graphics preflight and per-element caching. Existing productions
are unchanged. Start with [Workflow 2](docs/PRODUCTION_WORKFLOW_V2.md) before the
individual stage examples below; set `clip budget` before authorizing paid work.

For DJ mixes, sparse chants and music-driven protagonist films, see
[Music-led workflow](docs/MUSIC_LED.md). Use `--music-mode music-led`,
`quote-music` / `listen` / `music-map`, and review sound structure rather than
making lyric transcription the narrative's prerequisite. The project-specific
`clip-music-director` skill supplies directing/review guidance. Integrated
5–10 s local branded openings and explicit reuse of stills for editorial crops
are supported; legacy projects retain their existing behaviour.

**New productions now use the creative workflow:** shot-first prompts, explicit
proof shots, an editable musical event map and a reviewed local animatic before
the full image batch. See [Creative workflow](docs/CREATIVE_WORKFLOW.md) for the
complete sequence, instrumental mode, framing and references. Existing
productions without `brief.creative` retain the legacy behaviour below; no
approved images or hashes are automatically migrated.

These are **individual stages**. Approval/authorization examples are commands
to execute only after an actual user decision, never as an unattended script.

### Studio index and validated re-edit

```sh
uv run clip studio                       # one static page for every project on disk
uv run clip shot-edit PROJECT --shot s005 --camera hold --effect contrast=1.05 --note 'calmer'
uv run clip shot-edit PROJECT --shot s025 --transition fade --dissolve 8 --note 'soften arrival'
```

`clip studio` writes `studio/studio-vNNN.html`: cards for every production with stage
pills, spend against cap, blockers, last activity, next gate, and links to the project's
dashboard, preview and newest export. It reads **small JSON artifacts only** — never
image bytes — so a catalogue over many gigabytes stays instant, and it records no state.
Image/movie stages show as `recorded` rather than claiming a fresh hash; the per-project
dashboard verifies those exactly.

`clip shot-edit` changes presentation only: transition, dissolve handle, simple camera
move and bounded grade. The whole storyboard is re-validated (contiguity, neighbour
handles, effect bounds), the previous board is archived, and the command reports which
approvals it invalidated. Timing, other shots, images and the recording are untouched.

### Review surfaces: dashboard, monitoring, local derivatives

```sh
uv run clip dashboard projects/forward-ever --stage board    # beatmap + shot list page
uv run clip dashboard projects/forward-ever --stage stills   # + thumbnails and verdicts
uv run clip progress projects/forward-ever                   # background operation receipts
uv run clip adopt projects/forward-ever --shot s018 --source work/drafts/crop.png \
  --operation 'native crop 0,90,984,732' --note 'remove bottom matte' --permission-confirmed
```

`clip dashboard` writes one versioned, self-contained HTML page and a sidecar of input
hashes; it never overwrites, never fetches anything and never records an approval. It
renders the section bands, shot timeline, measured activity, local graphics windows and
the per-shot contract, then prints the exact `clip approve` command with each stage's
current hash. **No meter, bar grid or downbeat is shown unless an explicitly approved
`work/music-grid.json` exists**; estimated events are drawn distinctly, and an invalid
grid fails closed with the reason.

`clip progress` reads durable `work/operations/` receipts without the project lock, so
it works during a long render. Quiet is not failure, completion is not approval, and
reconciliation only marks receipts whose owning process is provably gone.

`clip adopt` registers an inspected local derivative as a new immutable version with a
provenance receipt. It does not select it, review it or approve it; the new bytes still
need their own `clip review` verdict.

### 1. Import, analyze and review

```sh
uv run clip init projects/kortjakje --slug kortjakje \
  --mp3 '/Users/mich/Downloads/Suno Downloads/STYLES/kortjakje-02 (1).mp3'
uv run clip analyze projects/kortjakje
uv run clip status projects/kortjakje
# After review:
uv run clip approve projects/kortjakje analysis --note 'User approved analysis'
```

Select `--aspect 9:16` at initialization for portrait; default 16:9/1080p/24fps.
Changing formats later invalidates approvals. Create a separate production for
another format. Measurements do not infer lyrics, mood, language or genre;
no four-beat-bar assumption is made. Section boundaries and tempo need review.

### 2. Estimate transcription, obtain approval, then upload

```sh
uv run clip quote-transcription projects/kortjakje --reserve 0.05
# Use the returned quote ID, after reviewing its upload scope and cost:
uv run clip authorize projects/kortjakje --quote QUOTE_ID --cap 0.05 \
  --note 'User approved this Runware audio upload, Gemini model and allowance'
uv run clip transcribe projects/kortjakje --quote QUOTE_ID
```

The default is **Gemini 3.1 Flash Lite via Runware**, using the existing Runware
project-specific key. The quote fetches its live schema and pricing before any upload, and binds
the model, output-token limit, JSON contract and full-song source hash to your
authorization. Published audio-input/output rates are shown in the quote;
audio token counts are not inferred from seconds. The $0.05 example is a
reservation, **not an exact estimate or provider-enforced cap**. A new upload
reserves $0.01 of that scope because mediaStorage does not report cost; its
unknown cost remains explicitly reserved rather than recorded as zero.

The MP3 is uploaded via Runware mediaStorage and the returned media UUID goes to
an asynchronous `textInference` task. Each step is journaled before submission.
If the CLI returns `transcription_pending`, use
`clip recover PROJECT --task RETURNED_UUID` to retrieve the result without
resubmission. For `upload_pending`, recover that upload UUID, then rerun
`transcribe` with the **same quote** to continue. Completed uploads are reused.
Upload response metadata is checkpointed before validation, since a live
mediaStorage upload was not retrievable through task-details lookup. Recovery
is not guaranteed when no usable response/handle was captured; never blindly
re-upload in that case. Check the provider's stored media/status with the user.
Runware's storage retention/fees are undocumented: assume no automatic deletion;
this MVP records the media UUID but does not automate deletion. Runware sends
the recording to its Gemini provider as part of the authorized processing.

All sung text and **approximate segment timestamps** are flagged for review.
These are model estimates, not word-level forced alignment. Unclear passages
use `[unintelligible]` rather than reconstructed lyrics. Truncated, malformed,
overlapping or out-of-range results are rejected after the billed raw result,
actual cost and usage have been saved in `work/transcriptions/` and `tasks.json`.
Optional `work/audio-notes.json` contains unreviewed subjective observations,
separate from local beat/energy measurements. Correct text/times, then approve:

```sh
uv run clip approve projects/kortjakje lyrics --ack-uncertain \
  --note 'User corrected/reviewed these lyrics and timestamps'
```

Alternatively import a supplied artifact with `clip import-lyrics PROJECT FILE`.
Use `clip schema lyrics` for its contract. Imports archive the prior lyrics.
No automatic retry exists after an ambiguous upload/inference. The local MP3
safety limit remains 25 MB (not a claimed Runware server limit); larger inputs
require a separately designed chunking workflow.

The existing Whisper adapter remains available only with
`quote-transcription PROJECT --provider openai`. Old quotes without a provider
retain that original OpenAI scope; they are never silently switched to Runware.

### 3. Agent proposes treatments and writes the chosen storyboard

After analysis/lyrics approval, ask the agent for **2–3 treatments**, with visual
style, narrative arc and trade-offs. Save proposals locally (e.g. treatments.md).
Choose one, complete `brief.json`, and approve it. Additional direction belongs
in `direction`, `visual_rules` and `avoid`.

```sh
uv run clip approve projects/kortjakje brief --note 'User selected treatment …'
uv run clip skeleton projects/kortjakje
uv run clip schema storyboard
```

The skeleton provides approximate ten-second beat-snapped slots, **not creative
content**. The agent must replace every TODO with a real story purpose and image
prompt. Each shot has a stable `id`, `start_frame`, `duration_frames`, lyrical/
musical context, `image_prompt`, optional `character_ids`, camera choice and
future `motion_prompt`. Shots cover `ceil(audio_duration * fps)` exactly.

Camera: `hold`, `zoom_in`, `zoom_out`, `pan_left`, `pan_right`. Optional
`dissolve_frames` adds outgoing handles; overlaps do not shorten the film.
The last shot cannot dissolve, and dissolves must be shorter than both shots.

```sh
uv run clip approve projects/kortjakje storyboard --note 'User approved all shots'
```

### 4. Three-shot proof, then the remaining images

```sh
uv run clip quote projects/kortjakje --scope proof --reserve 0.01
# Review model, prompts, references, dimensions, published examples and reservation:
uv run clip authorize projects/kortjakje --quote QUOTE_ID --cap 0.03 \
  --note 'User approved this three-shot proof'
uv run clip generate projects/kortjakje --quote QUOTE_ID
uv run clip sheet projects/kortjakje --scope proof
# After visually reviewing the proof:
uv run clip approve projects/kortjakje proof --note 'User approved proof images'
uv run clip quote projects/kortjakje --scope stills --reserve 0.01
```

New productions persist Nano Banana 2.1 at 1376×768 (landscape) or 768×1376
(portrait), then crop/pan/zoom/upscale to the export. Export resolution is not a
claim of native 1080p detail. Old productions without a stored model retain their
historical FLUX fallback and dimensions. The older cheap-price/reservation
examples are **not Nano Banana quotes**: review current pricing and reserve the
actual approved scope. `--model` explicitly overrides a quote's schema slug;
never switch models because an upstream recipe recommends one.

Authorize and generate the full scope separately. Already generated current
shots are reused. An unresolved task blocks fresh submission for that shot.

### 5. Review, select versions, render

```sh
uv run clip sheet projects/kortjakje --scope stills
uv run clip approve projects/kortjakje stills --note 'User approved selected stills'
uv run clip render projects/kortjakje
uv run clip costs projects/kortjakje
```

Local review aids (no upload or generation):

```sh
uv run clip prompts projects/kortjakje --shots s014,s018
uv run clip preview projects/kortjakje --scope available
uv run clip backup projects/kortjakje
```

Previews are versioned in `previews/`, marked **PREVIEW / NOT FINAL**, and keep
the full original audio/timeline. A preview is judged on its actual continuous
playback with audio: sampled frames, contact sheets and signal checks are measured
evidence, not watching, and a delegated proxy export is declared **unwatched** and
never a pass. Backups are private mode-0600 archives under
ignored `backups/`, including source media, generated images, state and exports;
rebuildable plate caches and `.env` files are excluded. Backups are local only:
copy them to your own secure backup storage separately. Do not commit archives
or production folders. This repository's source still needs an intentional Git
commit; no Git staging/commit or remote publication happens automatically.

Render preserves musical timing and the complete music, encoding MP3 audio to
AAC for MP4 compatibility. No lyric captions, extra sounds, audio fades or
normalization. An explicitly approved brand package can add a local visual
opening overlay and its fade without changing the music.
Validate with ffprobe and visually inspect the result; scripted integrity tests
cannot judge the artistic outcome.

## Revisions and recovery

- Edit a shot's prompt/timing/character/motion directly in storyboard.json.
  Approvals become stale by content; no paid regeneration happens automatically.
- Image dependencies exclude timing/camera/motion, so changing editing does not
  invalidate unrelated stills. A global brief change may invalidate many images.
- Generate alternatives with `quote ... --shots s005 --regenerate`. Prior
  selection stays selected; explicitly `select PROJECT --shot s005 --version 2`.
- New images are not automatically approved. Reapprove affected creative stages
  and selected still set after review. Every export gets a new filename.
- Task UUID and reservation are saved **before** sending. A lost/slow response
  stops the batch. Use `recover PROJECT --task UUID`, then rerun the same quote
  to continue. Recovery uses lookup/download only, never paid resubmission.
- Provider result/cost is saved before downloading. A failed download can resume
  without generation; expiring URLs/provider history still impose limits.
- Recovery checks even "ready" assets: missing originals are downloaded again;
  changed/corrupt files are preserved in `work/quarantine/` before restoration.
  Default quotes refuse to rebill a lost recoverable asset.
- If a request was rejected or remains ambiguous and provider lookup cannot
  settle it, verify task status and billing with the provider. Only after the
  user confirms that evidence, record it with
  `clip resolve-task PROJECT --task UUID --cost USD --note 'verified evidence'`.
  Zero means the user verified no charge, not a presumed refund. The old task
  remains in the ledger; any retry needs a **new quote and authorization**.
  Never reconcile an actually running task just to bypass the recovery guard.
- A project lock prevents concurrent CLI writers; JSON writes are atomic.

Reservations and scoped authorization prevent unapproved submissions and stop
after an overrun. They are **not a provider-enforced hard billing cap** for
compute-priced tasks. Unknown results retain their reservations. Quotes cannot
silently mutate after authorization. Cost reports distinguish provider-reported
image cost from duration-rate transcription estimates, not invoices.

## Optional protagonist

Import authorized reference images (normally 2–4 useful ones; see docs/STILL_FILM_WORKFLOW.md) into `media/references/`. In brief.json add a character:

```json
{"id":"hero","description":"Stable appearance/wardrobe description",
 "references":["media/references/front.jpg"],"permission_confirmed":true}
```

Use `character_ids:["hero"]` only for shots that feature them. References remain
local until an authorized generation uploads them as data URIs. The chosen model
must support the reference count. Approve likeness manually; this is reference-
guided consistency, **not an exact identity lock**. The pilot has no protagonist.

## Renderer and future motion / limits

New productions render with **Remotion** as the primary visual engine and keep
**FFmpeg** for encoding, muxing, probing and legacy compatibility. Remotion is a
project-local Node dependency in [renderers/remotion](renderers/remotion), **not**
a new MCP server or skill. The canonical storyboard remains the only timeline.
See [renderer contracts](docs/RENDERER.md) and [repository layout/retention](docs/REPOSITORY_LAYOUT.md).

### Remotion render CLI

Install and validate the locked local renderer; use `clip` for production gates:

```sh
npm ci --prefix renderers/remotion --ignore-scripts --no-audit --no-fund
npm --prefix renderers/remotion test     # pure frame/timing contract tests
npm --prefix renderers/remotion run smoke  # one real 160x90 base render
```

The adapter produces exact-frame silent visuals and transparent alpha graphics,
using existing local Chrome and source-hashed caches. FFmpeg retains audio muxing,
output verification and base-AAC packet copying into the final. No implicit
browser download or overwrite. Actual Remotion overlay frames feed preflight.

Existing projects stay on their legacy FFmpeg
render and migrate only by explicit opt-in — nothing is rewritten automatically.
No AI character animation and no paid call in post. Generated video motion beyond
a local composition, lip-sync, video references, character training, UI and Resolve
integration are not implemented. Future motion assets must use the same IDs and
timeline, validate model-specific duration/format limits and cover transition
handles. A longer edit may require multiple generations; never silently stretch
clips or assume every model supports ten seconds. Preserve the original music
and mute generated model audio by default. The two upstream motion recipes are
archived under `backups/unused-motion-skills/` for a future, separately approved
decision; their presence there is not permission to execute them.

```sh
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

Provider tests are mocked; renderer tests use real small FFmpeg exports, including
JPEG-to-limited-range color normalization. Asset downloads reject redirects,
credential-bearing URLs and private/legacy IP literals. They trust hostnames
returned by Runware and do not provide DNS-rebinding protection; this is a local
trusted-provider workflow, not an arbitrary-URL ingestion service.
No paid generation/transcription is performed by tests.
