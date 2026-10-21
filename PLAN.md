# Approved MVP plan

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
