# Approved MVP plan

## Design review status (2026-10-24)

The independent review of commit `457eb2e` (20 Oct 2026) reproduced ten defects and
named seven design problems. This section records what is true at `02afceb` on
`chore/retire-legacy-init`, what remains, and the order it should be taken in. It is
a status record, not a new approval: nothing here authorises spending, uploads,
production approvals or publication.

Measured at this revision: 46 modules / 19,709 lines of `src/`, 46 CLI commands,
~2,200 lines of Remotion source, 892 tests, and ~8,700 words across `AGENTS.md`,
`LOOP.md`, `README.md` and the inline agent prompts. `uv run pytest` gives 892
passed, 1 skipped; `uv run ruff check .` and `uv run ruff format --check .` are
clean (120 files) on macOS. Linux CI is green on `main` at `6d243e8` (run
`39842506833`, 5m13s); the commits above it are unpushed, so they have no CI
evidence yet.

### Fixed and verified

| # | Review finding | Evidence at this revision |
| --- | --- | --- |
| 1 | `clip plan run` always crashed | `spine` is imported at module top (`cli.py:14`); CLI-level build/list/show/run tests (`tests/test_plans.py:191`, `:280`); commit `5251ba2` |
| 2 | The journal never re-ran a command | Replay is opt-in and keyed on the new run id, not `argv` alone (`spine.py:310-345`) |
| 3 | A stored plan could run any command | `plans.py` re-derives the tool from argv, requires `argv[:3] == ["uv","run","clip"]`, rejects human capability and re-runs `problems()` on load (`plans.py:242-254`) |
| 4 | Tests only passed on this Mac | Inter (OFL) bundled in `src/mp3_to_videoclip/fonts/` and used as the fallback face (`graphics.py:356`); Linux `check.yml` runs ruff, pytest and the 19 browser tests (23 cases) in `tests/test_studio_browser.py`; the vendor-recipe test skips without the ignored checkout (`tests/test_stage_skills.py:195`) |
| 5 | Length came from container metadata | `init` stores decoded PCM seconds via `audio_seconds()`; commit `04d7c37` |
| 7 | The "read-only" server wrote | Only `POST /api/create` exists and it routes through the kernel; `PUT`/`PATCH`/`DELETE` return 405 (`serve.py:390-467`) |
| 8 | Review pages failed during a render | `dashboard`, `inspect`, `context`, `studio`, `sheet`, `progress`, `locate`, `preflight`, `prompts` are in `READ_ONLY_COMMANDS` (`cli.py:456-469`) |
| 9 | Docs linked into an untracked archive | The four plan docs and `experiments/README.md` now state the archive is untracked; `REPOSITORY_LAYOUT.md` labels `brand/releases/` generated output rather than active source |
| 10 | The README's own checks failed | `ruff check` and `ruff format --check` clean; type checking was dropped rather than adopted, so the review's 71 `pyright` errors are not gated |

### Still open

**Bug 6 — a Chrome update revokes approvals.** `remotion.implementation_hash()`
still hashes the desktop Chrome binary, and `REMOTION_CHROME` still defaults to
`/Applications/Google Chrome.app` (`remotion.py:20-35`, `:81`). Preview and graphics
approvals bind to that revision (`production.py:608-612`, `graphics.py:525-527`), so a
browser update invalidates reviewed previews and a machine without desktop Chrome
cannot satisfy the gate at all.

Design problems, in the review's numbering:

1. **Complexity out of proportion.** Partial. `workflow_version` accepts only `2`
   (plus `None` for legacy artifacts), the legacy creation switches are gone
   (`3696359`) and new productions are always Remotion (`production.py:108`), but the
   CLI still exposes 46 commands and the compatibility branches remain for four
   finished films.
2. **Two (or three) of everything.** Open. The FFmpeg plate path is still reachable
   for productions without `renderer_backend: remotion` (`render.py:626`); Pillow
   titles and credits (`graphics.py`, 2,572 lines) and `branding.py` (555) coexist
   with the Remotion equivalents; four analysis modules (1,996 lines) remain;
   `graphics.py` keeps private `_probe`/`_digest` copies; nothing tests that the
   Python timing constants and `renderers/remotion/src/timing.mjs` agree.
3. **Approval hashing is expensive and fragile.** Open. `stage_hash` hashes
   `model_dump()`-derived values, walks the upstream chain on every call and
   re-hashes the source MP3; the `Project` serializer still strips `None` fields to
   keep old hashes stable (`models.py:92-106`).
4. **Policy lives in prose and is bypassable.** Partial. `clip approve` and
   `clip authorize` redirect to Studio, and a human decision now needs a review note
   and the reviewed content hash (`human_actions.py`), but approvals remain plain
   JSON that any agent with `edit`/`shell` can write, and the rules are still
   restated in README, AGENTS.md, LOOP.md, the inline prompts and the skills.
5. **Personal setup is hardcoded.** Open: `PROJECT_VEIL_RUNWARE_API`
   (`providers.py:38`), `MAHA KALA × VJDJ69` (`signature.py:7-9`), the Chrome path,
   `~/Downloads/Suno Downloads` (`serve.py:953`) and `/Users/mich`
   (`intake.py:127`).
6. **A web app without a decision.** Half-decided in practice. Since PR #3 Studio is
   the only human decision channel, which answers the review's open question in
   favour of the UI; but `README.md:3` still opens with "not a web app" and the UI is
   still Python string literals rather than a frontend.
7. **A second agent runtime.** Open. `spine.py` (635), `plans.py` (310),
   `context.py` (140), `evals.py` (151), `mcp.py` (249) and `tools.py` (154) remain.
   They work now (bugs 1–3 are fixed) and no production workflow needs them.

### Remaining work, in order

Each phase is local engineering with no paid call, no upload and no production
approval; a phase that changes a renderer or an analysis dependency still needs the
user's explicit scope before it starts.

- **A. Portability and approval integrity.** Pin Remotion's own headless shell,
  stop hashing the browser, and bind preview/graphics approvals to the rendered
  output bytes. Move the Runware key name, Chrome path, Suno folder and signature
  constants into a user config with per-project overrides. Add `ruff format --check`
  and a type checker to CI, and add the Python↔`timing.mjs` parity test. Reword the
  README opening to describe the local review UI honestly. Done when a Chrome update
  changes no approval, a clean Linux runner passes the same commands the README
  documents, and no personal path or key name remains in `src/`.
- **B. One renderer, one graphics engine.** Record which commit re-renders each
  finished film, then delete the FFmpeg plate path, Pillow titles/credits, the
  unused brand marks, the duplicated hash/probe helpers and the compatibility
  branches. Merge the analysis modules. Done when Remotion is the only renderer and
  the CLI is near 20 commands.
- **C. Approvals as stored bytes.** Give each artifact an explicit `schema_version`
  with a migration, hash the canonical bytes of the stored file, record explicit
  parent hashes, and memoise file hashes per process. Then decide the
  `spine`/`plans`/`context`/`evals`/`mcp` layer: delete it per the review, or keep it
  only if Studio needs durable run history. Done when approving a 40-still set no
  longer re-hashes the song hundreds of times.
- **D. Better ears.** Add a pretrained beat/downbeat tracker and align the supplied
  Suno lyrics locally instead of paying to transcribe them, keeping the existing
  "unreviewed measurement" label. Then trim the guidance that only exists to guard
  weak estimates and reduce the crew to director plus critic. This phase needs a
  separately approved scope before any new model dependency is installed.

### Publication state

`chore/retire-legacy-init` is three commits ahead of `origin/main` (`6d243e8`) and is
the branch to publish: the two implementation commits plus this record. `feat/studio-ux-improvements` is superseded: its
implementation was squash-merged as PR #2 (`75f8c95`) and its tip only records that
handoff. `chore/sustained-delivery` is pushed but unmerged and carries a second CI
workflow (`.github/workflows/ci.yml`) beside `check.yml`; decide which one survives
before merging it. Push, PR, merge and deploy stay user-operated — agent publication
is blocked by configuration policy.

## Implemented engineering milestone: Human Studio decisions (2026-10-21)

The user selected UI approvals before legacy removal after PR #2 merged.
The record is `.opencode/tasks/studio-human-approvals.md` under the updated global
workflow. Local acceptance is complete; the reviewed branch awaits user-operated
publication/CI/merge. The record includes checks and independent-runtime limits.

## Completed engineering milestone: Studio usability (2026-10-21)

User approved implementation of the GUI review's P1–P3 improvements. Scope:
truthful stage state, decision support, navigation/create recovery, freshness,
keyboard/accessibility, responsive typography, searchable intake, honest errors
and copy feedback, and refused write aliases/security headers. Preserve the
vanilla templates, dark palette, CLI decision gates and existing productions.
No paid calls, uploads, new approval endpoints, legacy deletions or stack swap.

- Authority: local implementation/tests; feature branch and reviewed PR only;
  manual merge. No production approvals or spending changes.
- Branch/base: `feat/studio-ux-improvements` / `6d26a1b`.
- Started: 2026-10-21 16:59 UTC; checkpoint by 18:29 UTC (90-minute ceiling).
- Ready order: P1 state contract/navigation → P2 decisions/freshness → P3
  accessibility/polish/headers → independent review + verification.
- Acceptance: list/detail/approval state agree when verified; recorded media
  never imply freshness/delivery; URL reload/back preserve project/tab; create
  opens returned slug; failures offer recovery; keyboard navigation works;
  approval rationale visible; responsive review works at 390/900/1280px;
  unsupported write verbs return 405; tests/lint and browser checks pass.
- Spend cap: zero. Existing media/approval/budget files remain untouched.
- Status: P1–P3 implemented on the feature branch. Initial frozen revision passed
  847 tests including Chromium; source review found five defects, now corrected:
  kernel gate checks beyond hashes, source-search submission, setup-note
  validation, run-log recovery and the static copy fallback. Also tightened
  mobile approval notes, async route guards and reconnect feedback.
- Evidence: initial review session `ses_ea08ae2e8ffeCANExvVBuduYw1` returned
  source findings (shell unavailable); verifier dispatch was provider-blocked.
  Focused correction checks: 57 tests passed. New regressions use temporary
  projects only; no existing production/budget/review artifacts changed.
- Also verified image URLs/commands use the served project directory identity,
  not a potentially different imported config slug; added a real thumbnail and
  board-to-shot browser test.
- Final local acceptance: 859 tests passed with Chromium enabled; lint,
  formatting and all six eval invariants passed. Reviewed staged implementation
  identity: `6b3639b6ec93c7d720954e31aac68d9e299ae3227ba1ef4b55d40d47f4630661`.
  Focused independent source re-review resolved the five findings and two
  optional issues, with no remaining P1/P2 in scope; its sandbox could not
  recompute the diff hash or run browser tests. Parent verified unchanged bytes
  and ran runtime checks. Screens inspected locally at desktop and phone widths.
- Acceptance complete at implementation commit `a7020c4`: Linux CI run
  `39644165429` passed, including all 16 Chromium regressions. PR #2:
  https://github.com/mblaauw/mp3-to-videoclip/pull/2 — manually merged at `75f8c95`.
  Updated local server runs the branch at port 8800. All ready scope is complete;
  no default-branch push, spending or production-state change performed.

> **Historical record.** This document captures a point-in-time decision.
> Current behaviour is defined by `docs/STILL_FILM_WORKFLOW.md`,
> `docs/PRODUCTION_WORKFLOW_V2.md` and the code; counts and defaults here
> are not maintained.

Agent-operated MP3 -> reviewed music/lyrics analysis -> 2–3 treatments -> approved
brief/storyboard -> three-shot visual proof -> approved generated stills ->
full-song animated-stills MP4. Cloud uploads and paid generation require explicit
approval. Full AI motion is phase two, using the same shot IDs and timeline.

Pilot: `/Users/mich/Downloads/Suno Downloads/STYLES/kortjakje-02 (1).mp3`,
289.400167 seconds. No protagonist for this pilot. Approximately 29 shots,
music-aware rather than rigid ten-second edits. Style chosen after analysis.
Restrained motion; original musical timing; no captions or added audio.

Defaults: upfront aspect selection (16:9 or 9:16), 16:9 default, 1080p/24fps/H.264.
Optional photo-based protagonist with reviewed reference-guided likeness, not
guaranteed identity. Review/correct uncertain sung lyrics. Music sections and
beats are estimates; do not assume four beats per bar or label verse/chorus from
energy alone.

Bootstrap project-local Runware MCP with OAuth and selected upstream skills.
Pin their revision, retain auxiliary examples, avoid global skill collisions.
Keep the upstream checkout ignored: no license grant was found in the repository.
Project instructions override upstream automatic generation/model recommendations.

Use Python/uv, reviewed JSON artifacts, durable local task/expense tracking,
librosa analysis and FFmpeg rendering. Reuse relevant local media-production
patterns, not the neighboring project's Resolve dependency or effects grammar.
MCP handles interactive discovery/generation; retain a controlled HTTP executor
for batches requiring durable pre-submit tracking and recovery. Do not assume
MCP supplies enforcement of project budgets. Pricing estimates are not guarantees
for compute-billed tasks; reserve an explicit per-task allowance, stop after an
overrun, and carry unresolved task reservations without blind resubmission.

Invariants: sources untouched, immutable generated versions, approvals bound to
artifact content, no paid regeneration on edits, no gaps/transition-shortening,
complete music retained within one output frame, and recovery never blindly
resubmits an ambiguous paid task. Future motion must validate provider duration
limits and coverage. Do not implement lip-sync, video-reference ingestion,
character training, a web UI, or Resolve integration in the MVP.

Validation: focused unit/provider-mock tests; real small FFmpeg fixtures with
pan/zoom and dissolves; no paid tests; local analysis of the pilot; visually
inspect framing/contact sheets and verify duration, codecs and audio stream.
Stop before transcription upload and image generation for user approval.

## Approved Runware transcription change (2026-10-13)

Make Runware/Gemini 3.1 Flash Lite the default cloud transcription provider, using
the dedicated project Runware credential; retain the already-implemented OpenAI adapter only
as an explicitly selected legacy alternative. OpenCode OAuth continues to serve
creative reasoning, not raw-audio attachment transport.

Quote against the live public model schema/pricing. Do not infer input-token
counts from duration; show rates and a user-authorized reservation. Journal the
mediaStorage upload and async textInference separately before sending, retain
the audio handle for reuse, and recover via task lookup without resubmission.
Record actual text-inference cost before parsing; mediaStorage reports no cost,
so retain its explicit reservation rather than fabricate zero. Upload retention
is undocumented; do not assume automatic deletion. No audio upload/paid call is
authorized by this implementation approval.

Parse structured lyric segments into the existing Lyrics format, flag all sung
text and approximate timestamps for review, reject truncated/malformed/invalid
timing output, and keep raw billed evidence and token usage. Optional musical
notes are subjective model suggestions, not replacements for local beat/energy
measurements. Existing legacy quotes retain their original provider/scope.
Validate with mocked provider/ledger tests and live public schema GETs only.

Credential selection: the shared RUNWARE_API_KEY was found to belong to
project-veil. The user explicitly chose to share that existing key rather than
configure the dedicated key. The executor requires PROJECT_VEIL_RUNWARE_API
directly, with no generic-key fallback or secret-file edits. Keep other projects'
environment credentials and MCP login unchanged.

## Runware transcription: live fixes and first successful run (2026-10-13)

The first live upload failed client-side before response checkpointing existed. The
mediaStorage task never completed server-side (raw API and MCP getTaskDetails both
return taskNotFound); it was reconciled to $0 after the user reviewed the evidence.
Three fixes preceded the successful re-run:

- Checkpoint the mediaStorage response before validating it (landed first).
- Surface recognised public error codes from HTTP 4xx bodies (taskNotFound instead
  of a generic http_error).
- Accept the live mediaStorage result shape, which omits `operation` (the published
  example includes it); a contradictory operation is still rejected.

Live validation: the second upload (b18fa4c5) was recovered from its checkpointed
response with no re-upload, Gemini 3.1 Flash Lite returned a 42-segment Dutch lyric
draft, and provider-reported inference cost was $0.007657 against the $0.05
reservation. The $0.01 mediaStorage reservation is retained because mediaStorage
reports no cost. Lyric text, model-estimated timestamps and music notes remain
unreviewed drafts, not approvals.

Credential rule unchanged for now: the executor still requires
PROJECT_VEIL_RUNWARE_API; a dedicated mp3-to-videoclip key exists but remains unused
pending the user's decision.

## Approved still-video quality workflow (2026-10-14)

Implement the assessment's five priorities without paid generation or changing
the approved Kortjakje baseline. Existing artifacts use legacy prompt/proof/hash
behaviour; new productions use an explicit creative profile. Preserve hashes of
legacy inputs and all existing approvals, media and exports.

1. Separate shot content, scene continuity and global appearance. Add explicit
   proof IDs, framing and required-visible details. Approvals stay content-bound;
   only actual generation inputs invalidate images in the new profile.
2. Local low-resolution animatic with original full audio, real available stills
   and conspicuously labelled missing-shot placeholders. Version every preview;
   bind review to storyboard/proof inputs and movie bytes. New-profile full image
   batches require preview approval. Preview is not a final export or paid asset.
3. Explicit vocal/instrumental mode; no fabricated lyrics for instrumental work.
   Editable, frame-based musical events with source identity and user review.
   Offer event/beat/free timing, never infer meter, genre or meanings from MP3.
4. Optional start/end normalized crop framing, zoom and linear/smoothstep motion,
   while legacy camera behaviour and cached plates remain unchanged.
5. Permission-gated style/location/prop reference slots and shot/scene bindings;
   quote all referenced bytes and selected model schema before any upload.

Keep integer-frame timing, unshortened dissolves, preserved versions, explicit
upload/spending gates and original audio. No UI, Resolve or generated motion.
Test legacy compatibility, scene/shot isolation, dependency invalidation,
instrumental gates, proof/preview gates, reference limits/permissions and actual
FFmpeg previews/framing including portrait. Create no new approvals on behalf
of the user. Provide a local baseline preview for inspection, not regeneration.
Add a private local backup command (no media in Git); document source versioning.

## Approved music-led DJ production (2026-10-15)

New input: `/Users/mich/Downloads/Suno Downloads/master-versions/yasuke-style-vocal-v2-master.mp3`
(250.919979 s, stereo 48 kHz). Working production: `the-signal`, 16:9/24fps.
User selected The Signal: a fictional attractive dark-haired adult woman around
23 follows a recurring cue through one underground night, ending in connection
and collective release. User supplied style/chant blocks are intended context,
not verified structure, lyrics, tempo, key or sound. Brand direction is still a
proposal (Open Frame, Cutline, Monogram); no final identity approval exists.

User approved full-song Runware/Gemini 3.1 Flash Lite audio analysis with $0.50
allowance, including upload and timecoded sound/groove/tension/hook descriptions.
This is NOT image/character/video generation authority. Record exact quote,
source identity, task UUIDs and actual reported costs; reuse the existing tracked
Runware primitives. No blind retries and no more expensive model substitution.
Keep unknown upload cost reserved; $0.50 is not a provider-enforced billing cap.

Implement: richer local measured envelopes/window descriptors and candidate
changes/pulse ambiguity; separate structured audio-listening drafts with confidence
and provenance; music-led mode that does not make sparse chants the story's
mandatory parent; source-bound events with level/confidence/evidence. Stop for
user review of the resulting map before locking the artistic brief/storyboard.

Add an opt-in, versioned local brand package for a 5–10 s opening over the first
song seconds, without pre-roll, added sounds, delay, cropping or truncating audio.
Typeset/composite mark/title locally, include in the real preview and bind its
content hash into review/render dependencies. Brand changes do not regenerate
images. Preserve old brandless productions/approvals byte-for-byte.

Allow explicitly bound editorial shots to reuse an existing source shot's image
with their own stable IDs/camera/timing, without additional paid generation.
Validate targets and disallow cycles/chains. Preserve full integer-frame coverage.
Add an original project directing skill (not edits to pinned Runware recipes)
covering music-led direction, approved identity, scene continuity, intentional
coverage/match-cuts, labelled animatics, safe effects and all approval boundaries.
No paid image A/B tests or protagonist images until a separately approved quote.

Live execution note: user separately approved one Gemini 3.1 Pro pass within the
same remaining $0.50 allowance after Flash Lite proved too coarse. No additional
upload was made. Three inference results are durably priced ($0.049034 total);
the one upload retains its unknown-cost $0.01 reservation. The first Flash Lite
macro draft remains unreviewed; both detailed passes were rejected for exceeding
the requested 20 s passage limit, with raw responses retained. No music-map,
brand, protagonist, artistic brief or storyboard approval was manufactured.
The map is explicitly a review aid, not a verified musical interpretation.

Implementation validation: 298 tests pass; `uv run ruff check .` clean. Synthetic
FFmpeg tests cover the real opening overlay in both aspects, its disappearance,
full audio/frame coverage and unchanged legacy plate reuse. Pilot approvals and
all 32 selected image hashes were checked locally; new original/copied MP3 hashes
match. The Signal has no creative approvals or paid image tasks. A private backup
was created. Next gates: user review/correction of musical interpretation and
timings, identity selection/wording, creative brief/storyboard, then a separately
authorized character/proof image scope. Do not treat passing tests as approval
of musical semantics, photographic likeness or artistic quality.
