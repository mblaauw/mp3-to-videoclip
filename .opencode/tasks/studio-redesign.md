# Studio redesign — phased implementation

Authorized: 2026-10-26, owner asked to implement the complete Studio redesign.
Source: `studio-redesign-handover.zip` (README, 01–05, tokens, prototype,
screenshots), with `05-update-42a33cf.md` overriding 01–04 where they differ.
Base: `main` at `42a33cf` (T0–T5 merged).
P0 branch: `studio-redesign/p0-correctness`, merged as PR #24 (`1a3800e`).
P1 branch: `studio-redesign/p1-foundations`, merged as PR #25 (`71406aa`).
P2 branch: `studio-redesign/p2-shell`, merged as PR #26 (`d437b37`).
P3 branch: `studio-redesign/p3-track-story`.

## Objective

Replace the old rail/tabs Studio with the handover design: the song as a shared
spine, one next step per stage, pictures at picture size, one-click approvals,
a role-aware director drawer, readable cut, inline ratings and a settings dialog.

One PR per phase. Every phase ends with:

```sh
uv run pytest
uv run ruff check .
uv run ruff format --check .
npm run build --prefix frontend
uv run studio   # app starts and the affected screens are checked
```

No paid provider call in any phase. Money, timing, rendering and approval-hash
logic stay authoritative in the existing engine modules.

## Decisions

- **Ratings:** keep all four T5 rating artifacts — brief, concepts, storyboard,
  edit — as compact inline controls. Do not collapse to the three spots named in
  the handover.
- **Credits:** add a credits confirmation card to Story before brief approval;
  the full `CreditsEditor` mentioned for Film remains a later P5 surface. The
  signature gate is not relaxed and no credit is invented.
- **Browser verification:** do not add Playwright. Use the OpenCode browser tool
  for the phase sweeps and record the evidence. If committed browser tests are
  wanted later, that is a separate dependency decision.
- **Design assets:** commit the handover docs, tokens and proposed screenshots
  under `docs/design/studio-redesign/`; do not commit the prototype's mock media.
- **API typing:** generate the OpenAPI schema, add response models for the routes
  the redesign touches, and keep explicit types for legacy untyped routes.
- **Job progress:** use SSE for status and an honest indeterminate bar until the
  backend can report real per-job progress. Do not invent progress or cost.
- **Plain lyrics:** extend `Lyrics` with untimed lines; never invent timestamps.
- **`Shot.change`:** dropped; `05-update-42a33cf.md` does not require it.

## Phases

| Phase | Scope | Status |
| --- | --- | --- |
| P0 | K13 vocal promo/advert brief approval; K2 real blocking stage | Complete (PR #24, `1a3800e`) |
| P1 | Tokens/font, UI primitives, SSE jobs, API types, error codes | Complete (PR #25, `71406aa`) |
| P2 | Shell, routes, library, top bar, next step, budget/jobs, spine, director drawer | Complete (PR #26, `d437b37`) |
| P3 | Track and Story, Brief card, excerpt band, lyrics, credits card, one-click approval | In review (`studio-redesign/p3-track-story`) |
| P4 | Storyboard cards/table/inspector, Images contact sheet/lightbox, priced actions | Not started |
| P5 | Film Cut tab, checklist, credits editor, settings, director tool cards, history | Not started |
| P6 | Empty/loading/error states, responsive and accessibility pass | Not started |

## P0 — correctness

### Scope

- K13: `production.effective_upstream` must return `analysis` for `brief` on a
  promo or advert, regardless of vocal/instrumental mode. A vocal advert has no
  lyrics artifact, and that must not block story approval.
- K2: `_approval` must name the stage that actually blocks an unavailable
  artifact (`blocking_stage`), instead of the generic
  "artifact has not been created" message.
- Add regression tests that create a vocal advert, write its brief and approve
  it, and that a music video without lyrics reports `lyrics` as the blocker.

### Constraints

- Do not change approval hashing, note requirements, budgets, timing or pixels.
- The existing guided-flow policy and the signature gate stay as they are.
- No provider or model call.

### Acceptance

- A vocal advert can be created through `POST /api/projects`, its brief patched
  and approved through `POST /approvals/brief`.
- A music video without `work/lyrics.json` returns an unavailable brief state
  with `blocking_stage: "lyrics"` and a message that names lyrics.
- `pytest`, `ruff`, format check and frontend build are green; the app starts.

## Evidence

P0 verified on `studio-redesign/p0-correctness` at the final working tree:

- `uv run pytest -q`: **907 passed, 1 skipped** (104.69 s). This includes three
  new regressions in `tests/test_api_kind_upstream.py`: a vocal advert can
  approve its brief; a vocal music video without lyrics reports
  `blocking_stage: "lyrics"`; a missing storyboard reports its own stage.
- `uv run ruff check .`: clean. `uv run ruff format --check .`: 210 files already
  formatted.
- `npm run build --prefix frontend`: clean, 54 modules.
- `uv run studio --projects-dir /tmp/opencode/t4-player --port 8924`:
  `/api/health` returned `{"ok":true,...}` and
  `/api/projects/production/approvals?stages=brief` returned a normal missing
  state, so the app still starts and serves approvals.
- No paid provider call was made; no production under `projects/` was modified.

P0 shipped in PR #24, squash-merged as `1a3800e` on 26 Oct 2026. CI (`check`)
passed in 4m46s before the merge.

## P1 — foundations

### Scope

- Copy the handover tokens to `frontend/src/styles/tokens.css`, self-host
  Schibsted Grotesk 5.3.0, and keep the old screen variables as aliases so no
  stage breaks while it is rebuilt.
- Add token-only `ui/` primitives and use them in the jobs tray.
- Replace the 3-second jobs polling with one `/api/events` EventSource, a jobs
  store with reconnect/backoff, and honest indeterminate progress.
- Generate `frontend/src/api/schema.d.ts` from the app's OpenAPI document with
  `npm run api:types`; add response models for the routes touched and alias
  those generated types in `api.ts`.
- K11: every 4xx/5xx is `{detail, code}`; the frontend throws a typed `ApiError`
  and maps stable codes to copy.

### Constraints

- No money, timing, rendering or approval-hash change.
- No paid provider call.
- No new dependency beyond `@fontsource-variable/schibsted-grotesk@5.3.0` and
  `openapi-typescript` 7.x.

### Acceptance

- Existing screens render with the new font and tokens.
- A queued job reaches the tray over SSE; polling is gone; no progress is
  invented.
- `npm run api:types` is reproducible and `npm run build` type-checks.
- Every tested API failure returns `{detail, code}`.

## P1 evidence

P1 verified on `studio-redesign/p1-foundations` at the final working tree:

- `uv run pytest -q`: **915 passed, 1 skipped** (102.84 s). New coverage:
  eight envelope cases in `tests/test_api_errors.py` (including a hidden 500)
  and a JSON `hello` parse in `tests/test_api_routes.py`.
- `uv run ruff check .`: clean. `uv run ruff format --check .`: 219 files already
  formatted.
- `npm run api:types`: regenerated from the app OpenAPI document; `JobOut`,
  `JobDetailOut`, `JobProgress`, `CancelOut`, `ApprovalStateOut`, `ApprovalsOut`
  and `ApprovalOut` are generated types now used by `api.ts`.
- `npm run build --prefix frontend`: clean, 67 modules; the two Schibsted
  Grotesk woff2 files are emitted into `dist`.
- Live Studio on port 8931 with `/tmp/opencode/t4-player`: the browser reported
  the Schibsted font loaded, the neutral `rgb(27, 28, 31)` surround, and no
  console errors. A local analysis upload produced a queued job that appeared in
  the tray as `analysis · Done` through SSE. The first live probe exposed that
  `sse-starlette` was sending Python dict reprs; the stream now emits JSON and
  the regression parses the `data:` line.
- Error envelope spot checks: `POST .../chat` with no body returned
  `{"detail":"message required","code":"bad_request"}`; missing projects, jobs,
  validation failures, stale/invalid approvals and the missing director key all
  returned their stable codes.
- No paid provider call was made; test uploads went to the `/tmp` fixture, not
  `projects/`.
- Browser evidence was collected before the browser tool was temporarily removed
  from the session catalog and again after it returned. No Playwright dependency
  was added.

P1 shipped in PR #25, squash-merged as `71406aa` on 26 Oct 2026. CI (`check`)
passed in 4m15s before the merge.

## P2 — shell, library, spine

### Scope

- Hash routes `#/` (library), `#/:slug/:stage` and `#/archive/:slug`; remove the
  left rail.
- `TopBar` with the mark, title/breadcrumb, stepper, budget chip/popover, jobs
  popover, director toggle and settings entry.
- `NextStepBar` backed by one pure `nextStep(stage, project, approvals, images,
  budget)` function with executable tests for every rule.
- Library with poster mosaics, cheap stage states, next-step copy, *New film*
  modal, MP3 drop target, *Delivered* section and a read-only archive player.
- `ProjectSummary` adds `poster_stills`, `stage_states`, `next_step`,
  `remaining_usd`, `updated_at`, `audio_url`, `shots`, `music_mode`,
  `has_analysis` and `has_lyrics`.
- One `PlayerProvider` (single `<audio>`, shared time) and a `Spine` with
  waveform, filmstrip, sections and playhead. Boundary dragging moved out of
  `Timeline.tsx`, which is deleted; Storyboard now owns cut editing.
- Film's Remotion `LivePlayer` follows the shared time and play state.
- Director drawer restyled; open by default above 1180 px, overlay below.
- K12: `GET /budget` reports `spent_usd`, `reserved_usd` and `paid_stills`
  alongside `committed_usd`.
- Read-only archive media routes so the library never exposes filesystem paths.

### Decisions

- Library summaries stay cheap: approval records plus artifact mtimes, never full
  gate hashes per card. Approval endpoints remain authoritative.
- Inside a production the top bar's stage states are derived from the loaded
  approval states, so the stepper and the next-step bar cannot disagree. The
  library keeps the cheap summary heuristic.
- Archive render and stills are addressed by `/archive/render` and
  `/archive/stills/<index>`; the render is served with byte-range support for the
  video player.
- `nextStep` is plain TypeScript under `frontend/src/shell/nextStep.ts`; its 28
  rules run under Node's native TypeScript stripping
  (`npm test --prefix frontend`), so no test dependency was added.
- `POST /budget` records a new absolute cap, as the engine already did. The
  popover therefore computes `current cap + amount` and labels the action *Add to
  budget*; it never lowers the cap by treating the amount as the total.
- No progress is invented: running jobs with no reported units keep an
  indeterminate bar and the copy says "working…".

### Acceptance

- At 1440, 900 and 390 px the library and every stage show the top bar,
  next-step bar (where applicable) and the spine, with no page-level horizontal
  overflow.
- Playing in Track and switching to Film preserves the shared time.
- Moving a boundary on the spine updates the Storyboard and its approval state.
- Every route renders without a console error or a request with status ≥ 400.
- Archive playback and stills work without exposing a path.

## P2 evidence

P2 verified on `studio-redesign/p2-shell` at the final working tree:

- `uv run pytest -q`: **919 passed, 1 skipped** (123.22 s). New coverage in
  `tests/test_api_library.py`: summary stage states/next step, poster image
  routes, K12 spend/reserve/paid-still split, archive summary and read-only
  render/still routes.
- `uv run ruff check .`: clean. `uv run ruff format --check .`: 220 files already
  formatted.
- `npm run build --prefix frontend`: clean, 80 modules. `npm test --prefix
  frontend`: **28 passed**.
- Live Studio on a `/tmp/opencode` fixture (a copy of `zero-bars`, with the two
  frozen films symlinked read-only) served the library and every stage. The
  direct OpenCode browser tab is 1000×700, so 1440×900 and 390×844 were measured
  through a same-origin iframe harness; there was no page-level horizontal
  overflow at any size, the spine sat at the viewport bottom, and the library
  grid was 3 / 2 / 1 columns at 1440 / 900 / 390.
- The director is a 380 px static column at 1440 and a full-height overlay at
  900 and 390 (`position: fixed`, 380 px and 390 px wide), with no overflow.
- Playback evidence: seeking the shared audio to 60.0 s moved the Remotion player
  to frame 1440 (24 fps); playing from Track and switching to Film kept the time
  and the player within two frames. Moving the first Storyboard boundary one
  frame right changed `a001` from 114 to 115 frames and `a002` to start at 115
  through the API, and the table and approval state followed.
- Budget evidence: the popover showed 82 paid stills, $2.88 spent, $0 reserved
  and $5.12 of $8.00 left; adding $1.00 produced a $9.00 cap, $6.12 remaining and
  a new history entry. No paid provider call was made.
- Route sweep (library, Track, Story, Storyboard, Images, Film, archive): no
  console errors and no requests with status ≥ 400. Archive render and stills
  returned 200/206; media `failed` entries were aborted range streams after the
  browser buffered enough, not HTTP errors.
- Fixture limitation: copying `zero-bars` without preserving mtimes made the
  cheap library heuristic call already-approved stages "changed"; the shell's
  authoritative approval states stayed "approved". This confirms why the
  library uses the cheap summary and the film shell uses the approval endpoints.
- No production under `projects/` was modified; all mutations happened in the
  `/tmp` fixture. No Playwright dependency was added.

P2 shipped in PR #26, squash-merged as `d437b37` on 26 Oct 2026. CI (`check`)
passed in 4m31s before the merge; the first two runs were killed by a slow apt
mirror while installing ffmpeg, so the job timeout was raised to 30 minutes.

## P3 — Track, Story and the excerpt band

### Scope

- **Track** facts row (length, estimated tempo, measured sections, Vocals /
  Instrumental), editable section names, lyrics view, plain-text or LRC paste,
  `Edit lyrics`, and *Transcribe instead* only while the lyrics are empty.
- **Story** Brief card for promo and advert, three concept cards and a chosen
  concept, treatment autosave, Direction and Style fields, Look card with the
  kind's allowed presets, Characters card, Credits card, one-click approval with
  an optional note, and the changed banner with a reason and *See what changed*.
- **Spine** excerpt band on Story: full-source peaks, gold start/end handles,
  live local draft, commit through `PUT /intake`, fades shown on the band.
- **New film** dialog: kind-specific fields, handover lengths, no 9:16, no style
  preset. Promo 30/60/90 s; advert 6/15/30/60 s.
- **Next step:** a vocal music video without words asks for lyrics before story
  approval; a promo/advert asks for its message and CTA; a stale brief carries
  its real reason and offers *See what changed*.
- **Director:** *Ask for three more* and *Ask the Writer…* prefill the composer;
  the director context and music tool read the human section names.

### Backend changes

- `Lyrics.lines`: untimed plain text is a real artifact. The serializer omits
  `lines` when empty, so existing files and hashes do not move.
- `PUT /lyrics` accepts `{text}`, detects LRC by timestamps, and refuses a mixed
  timed/untimed paste instead of silently dropping lines. It still accepts
  `{lrc}` and a full `Lyrics` model, and still refuses non-music-video kinds.
- `GET/PUT /music-notes` store `{sections: [{start, name}]}` in
  `work/music-notes.json`; `music.json` is never rewritten. `PUT /music-mode`
  records Vocals/Instrumental and refuses the change once a brief is approved.
- `PUT /graphics/credits` confirms factual late credits for guided productions;
  `GET /graphics` adds `guided` so the UI can keep older productions read-only.
  The optional *Use these roles for new films* writes `work/credits-template.json`.
- Approval and image-review notes are optional and stored as `null`, never as
  fabricated text. The explicit confirmation/inspection flags stay mandatory.
- Approval snapshots live in `work/approval-snapshots/` and only explain a stale
  decision; `GET /approvals/{stage}/changes` returns a short before/after diff.
  The approval hash and gates are unchanged.
- `ProjectSummary.has_lyrics` requires actual words (`segments` or `lines`), not
  just a `work/lyrics.json` file. `_stage_states` uses the same rule.
- `intake.create_from_upload` requires an advert's message and CTA only; the
  objective moved to Story. A promo/advert has no lyrics upstream (P0).
- Director context and `get_music_summary` use names from `music-notes.json`,
  falling back to `Section N` only when no name was saved.

### Decisions

- Section names are a separate naming layer. Renaming a section must never
  rewrite a measured sample or change the analysis bytes an approval binds.
- Plain text is stored as lines without positions. LRC is used only when every
  lyric line carries a timestamp; metadata lines (`[ar:…]`, `[ti:…]`) are ignored.
- The excerpt is editable only before a storyboard exists. Once a cut exists,
  Story shows the band read-only with the reason, and no failing request is sent.
- The player source changes only on a committed window. Dragging updates the
  readout and the gold band immediately, then commits on pointer release or a
  short keyboard debounce.
- Credits are late-bound for guided films because the signature is deliberately
  outside their brief hash. Older productions keep credits inside the brief and
  see a read-only explanation. The Story card is the only credits editor in this
  build; a fuller Film editor stays for P5.
- *Transcribe instead* explains that paid transcription is not enabled in this
  build. No route, quote or provider call was added.
- Story gained editable Direction and Style fields: a fresh advert otherwise
  cannot pass the existing brief gate, which requires both.
- FilmShell is keyed by slug so switching productions cannot reuse the previous
  board's shots or request its images under the new slug.
- The library's Track card distinguishes *Measure the song* (no analysis) from
  *Add the lyrics* (analysis done, vocal music video missing words).

### Acceptance

- A vocal production without lyrics shows *Add the lyrics first — the story is
  checked against them.* in the Story bar, not "artifact has not been created".
- Approving the story is one click; the stored note is `null` when none is typed.
- Editing the treatment shows *Saved* within the autosave window and there is no
  Save button.
- Moving a style-check star in Storyboard turns the Story step violet and the bar
  names the reason; *See what changed* shows the proof-list diff.
- The Credits card confirms the guided film's cards and refuses a non-guided film
  without pretending to edit it.
- The excerpt start/end handles commit a new window before a board exists and are
  absent with a plain reason after one exists.
- Track, Story, Storyboard, Images, Film and the library render without a console
  error or a request with status ≥ 400.
- At 1440, 900 and 390 px the shell, next-step bar and spine stay inside the
  viewport with no page-level horizontal overflow.

## P3 evidence

Verified on `studio-redesign/p3-track-story` (base `260cf9d`) at the final working
tree:

- `uv run pytest -q`: **931 passed, 1 skipped** (110.71 s). New coverage in
  `tests/test_api_p3_track_story.py` for plain text without invented times, LRC
  and metadata, a refused mixed paste, section names outside `music.json`, the
  music-mode lock, guided vs. recorded-v2 credits, treatment and star-change
  reasons, optional review notes, and the empty-lyrics library summary.
- `uv run ruff check .`: clean. `uv run ruff format --check .`: 223 files already
  formatted.
- `npm run build --prefix frontend`: clean, 84 modules. `npm test --prefix
  frontend`: **31 passed**. `npm run api:types --prefix frontend` regenerated the
  schema; no additional schema change was needed.
- Live Studio on port 8938 with fixtures under `/tmp/opencode/p3-projects`:
  `night-signal` (fresh advert, later a six-shot board), `fresh-advert` (advert
  with three concept cards), `stars` (guided copy of `zero-bars`), `no-lyrics`
  (vocal copy without words) and `legacy` (a copy without the guided marker).

Browser evidence:

- **Track on an advert:** 0:30 length, about 129 BPM, 2 measured sections, no
  lyrics requirement. The lyrics panel says the advert is built from its message
  and ending; no *Transcribe* action is offered for a non-music-video.
- **Track on a vocal film without words:** *Not added yet*, an empty paste box,
  and *Transcribe instead · $0.05*. Pasting three plain lines saved
  `lines: [3]` with `segments: []` and the warning that no timestamps were
  invented; the Transcribe action disappeared and the bar became *Track is
  ready.* The Story bar before this read *Add the lyrics first — the story is
  checked against them.*
- **Section names:** renaming the first section saved
  `work/music-notes.json` (`Opening`, then the measured starts) and showed
  *Saved*; the `music.json` hash stayed `59989aee…`. The Track API returns the
  names and the director summary reads them.
- **Brief card:** the collapsed sentence read *Advert · 30.0 s — Night Signal is
  out Friday — for an audience to name — ends on Pre-save now →
  https://example.com · Look: Clean photographic*. *Edit* revealed The point /
  Who and how / Ending; changing Audience and leaving the field saved through
  `PUT /intake` and showed *Saved*.
- **Concepts:** three cards rendered from `work/treatments.json`; choosing the
  second made it the only gold card and persisted `chosen_id: signal-room`.
  *Ask for three more* opened the Director with the revision prompt prefilled.
- **Treatment and fields:** typing a new treatment autosaved after 800 ms with
  *Saved* and no button; Direction and Style saved through the same debounce.
- **One-click approval:** the Story bar's *Approve story* posted the expected
  hash and produced `state: approved`, `note: null`, and *Story approved.*
  No note was required.
- **Changed banner:** editing the approved treatment produced
  `state: stale`, reason *The treatment changed.*, the bar *The story changed
  since you approved it.* and a before → after Treatment diff.
- **Style-check star move:** moving the selection to s001, s002 and s003 in
  Storyboard produced reason *The style-check shots moved to s001, s002 and
  s003.*, `state: stale`, the Story step class `changed` with
  `ui-dot--changed` (violet), and the same reason in the Story bar and diff panel.
- **Credits:** on guided `stars`, the Story card confirmed
  `[MUSIC, MAHA KALA]` and `[FILM DIRECTION, VJDJ69]`; the API returned
  `credit_roles_confirmed: true` and the same cards. On `legacy` (no guided
  marker) the card explained that credits live inside the story approval and
  offered no edit control.
- **Excerpt band:** a fresh advert showed the full 239.8 s source with a gold
  0–30 s band and both handles. Moving the end to 29.75 s committed
  `PUT /intake`; the summary read 29.8 s and the audio source became
  `?v=0-29.75-0-1.5`. Once a storyboard existed, the band stayed visible but the
  handles disappeared and the hint explained that the cut fixes the excerpt;
  no failing `PUT /intake` was sent.
- **New film:** the dialog offered no 9:16 and no style preset. Promo showed
  Title / One message / Length (30, 60, 90) / Budget; Advert showed the same plus
  Call to action and lengths 6, 15, 30, 60.
- **Route sweep:** 15 routes across the five fixture productions plus the
  library, 204 captured requests, 0 dropped, no console messages and no request
  with status ≥ 400. The earlier sweep found that FilmShell/Storyboard called
  `/edit` on a board-less project; the call is now made only after a board exists.
- **Responsive geometry** through a same-origin iframe at 1440 / 900 / 390 px:
  `scrollWidth == clientWidth` at every size. Story used two columns
  (536 + 397 px) at 1440 and one column at 900/390; the next bar was 69 / 69 /
  142 px tall; the spine was 132 / 132 / 96 px and ended exactly at the viewport
  bottom. No stage control was clipped at 390 px; the storyboard table scrolls
  inside its own container.
- **Library labels:** a vocal music video with analysis but no words reads *Add
  the lyrics*; a fresh advert without analysis reads *Measure the song*; an
  approved-but-changed story reads *Approve the story again*.

Limitations:

- Paid transcription is not wired. The *Transcribe instead* action is only a
  quiet explanation; no quote, upload or provider call exists in this build.
- Change reasons and diffs only exist for approvals recorded after P3. Older
  approvals show the generic reason and state that the change predates the log.
- The full credits editor mentioned for Film is not part of this build; Story is
  the only credits surface until P5.
- The browser tool can measure layout but its screenshot capture required a
  visible desktop window that was not available in this session, so responsive
  evidence is geometry and DOM state rather than images.
- All mutations happened in `/tmp/opencode/p3-projects`; no production under
  `projects/` was modified. No paid provider call was made and no Playwright
  dependency was added.

## Next

P4 — Storyboard and Images: picture cards grouped by Track section, table and
inspector, style-check stars, contact sheet and lightbox, priced actions.
