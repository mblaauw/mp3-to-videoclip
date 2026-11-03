# Project assessment, 3 November 2026

Reviewed: `main` at `78fbd26`, on the owner's Mac. Read: README, ARCHITECTURE, the
roadmap and its acceptance records, the Museum of Tomorrow and Cool Cat production
records, the engine (models, budget, generation, approvals, jobs, app), the Director
(loop, adapter, prompts, tools), the renderer (timing, BaseFilm, render.mjs), the
frontend tree and the tests. Run: `pytest -n auto`, `ruff check`, `ruff format
--check`, frontend tests, lint and build, renderer tests, a dist-currency check and a
complexity scan. No production folder was touched, no paid call was made. It stands
beside `studio-assessment-2026-10-31.md`, which graded the app before the November
roadmap; where a grade moved, this says why.

## Verdict

This is an unusually well-engineered local tool with a trust model most commercial
products lack, carried by a documentation and decision-record culture that is the
project's real moat. The engine, the money journal, the approval chain and the test
discipline are excellent and should be preserved as they are. Two weeks of roadmap
work closed almost every gap the October assessment named: blocked states, the song
map, provider adapters, per-role models, depth, clips, titles as a preset, narration,
delivery packages, vertical versions.

What holds it back now is not missing features. It is three things:

1. **The product has never been judged by its own standard.** Three real films exist
   (two Cool Cat films and the Museum story film), made by the tool for under $15 in
   total, and the records say plainly that nobody has watched or heard any of them in
   motion. Every "it looks right" in the record is a sampled frame or a Critic reading
   frames. The purpose of the tool is a finished film, and that last mile is unverified.
2. **Complexity has accumulated at the centre.** Six modules over 1,100 lines, 24
   functions above a McCabe complexity of 15, a 1,690-line hand-written API type file
   and 7,700 lines of CSS. None of it is wrong, all of it is where the next bug will hide.
3. **The money model has a hole the record admits:** model (LLM) spend is recorded in
   tokens and never priced, so a turn allowance, not a dollar cap, is the only limit on
   Director cost. The image journal is strict; the text model is on the honour system.

## Scorecard

| Dimension | Grade | Oct 31 | One line |
| --- | --- | --- | --- |
| Engine correctness and money | A | A | Pre-submit journal, UUID recovery, content-bound approvals, integer frames. Unchanged, still the best part. |
| Security of a local app | A | A | Loopback only, origin gate, secrets never returned, 0600 settings, paid tools excluded from the MCP bridge. |
| Tests and CI | A | A− | 1,916 + 166 + 94 + 23 e2e, 75 s locally, pixel goldens, dist currency check. Golden no longer pins the legacy path. |
| Documentation and decision records | A | – | ARCHITECTURE is current; every phase has a plan, an acceptance record and a "not proven" list. Rare. |
| Director architecture | B+ | C+ | One adapter, three wire formats, per-role models, prompt hash on every write, decisions log, 40-call cap. Cost unpriced. |
| Prompt craft | B+ | B | Honest-medium framing, five truth rules, nine styles, four kinds, four structures, craft digest. Still one house idiom in the examples. |
| Music understanding and the cut | B | C | Song map with deep pass, downbeat grid tiers, first cut snaps to sections and lines, ramps on downbeats. Beats reach the Editor now. |
| Visual quality of the film | B− | C+ | Depth, upscale, three faces, grain tile, clips, grades. Unverified by a human eye in motion; "may feel like a slideshow" is the record's own words. |
| Frontend architecture | B | B+ | Strict TS, SSE with no polling, shared resource store, ESLint now on. Large files, hand-written types, no component tests, 600 KB main chunk. |
| Render performance | B− | C+ | 3:37 for a 4-minute film at 4 browsers, 14 s for one changed shot, exit bug fixed. 16 GB Macs still stall at 4 browsers on long films. |
| Code complexity | B− | C | Legacy is down to 1,127 lines and reached by one `python -m`. But `edits.py` 1,754, `graphics.py` 1,699, `tools.py` 1,545, `models.py` 1,445. |
| Install and portability | B− | B− | `uv sync && uv run studio` is real. Still Node, FFmpeg, Chrome; lyric timing is Apple Silicon only; CPU timing refused for a download. |
| Product proof | C+ | – | Three real films made end to end through the Studio. None watched or heard by the owner. No sound design exists. |
| Repository hygiene | C+ | – | Seven local branches, three with unmerged commits; 25 remote branches; 42 GB of local productions, backups and caches; a stale test README. |
| Sustainability | C | – | One owner, 456 commits in 15 days, 231 co-authored with Claude. The docs carry the knowledge, which is the mitigation. |

## Fantastic: keep exactly as it is

- **The paid-task journal** (`generation.py:476-566`). Reservation and task UUID are
  durable before the request leaves; recovery is by UUID and never resubmits; a
  changed spec between quote and submission is refused; a task that never returns
  holds the film's spending until the owner settles it with evidence. The Museum run
  proved it live: a clip stuck for over an hour, nothing charged twice, nothing new
  spent. This is the heart of the trust model and it held under real failure.
- **Content-bound approvals** (`production/approvals.py:170-231`). Every stage hash
  binds the bytes it depends on: reference images, plate bytes, the cut, the brand,
  the renderer revision. Changing anything invalidates the approval rather than
  inheriting it. New fields are serialised only when set, so 208 recorded hashes
  across four films survived the whole November roadmap byte for byte.
- **One composition for every output.** `BaseFilm.jsx` and `timing.mjs` are pure
  frame functions shared by the MP4, the review stills and the live Player. The
  caption-overlap check now reads its geometry out of the renderer so the Python
  side cannot drift from it. This is the right shape and it is unusual.
- **Integer frames everywhere**, dissolves as handles that never shorten the film,
  a pacing planner with exact coverage, and a story film whose clock is the mixed
  narration so a longer take moves only the shots after it.
- **The honest record.** Every acceptance record ends with what was not done and
  what was not proven. The architecture doc says what stored settings do nothing
  yet. The README says screenshots came from fixtures with no paid call. This is
  the single most valuable engineering habit in the repository and it is what makes
  the AI-assisted velocity safe rather than reckless.
- **CI.** Lint, format, unit, slow compositor, frontend tests and lint, a check that
  the committed build matches the source, renderer tests, browser e2e, a render
  smoke and pixel goldens. Few projects of any size run that much on every push.
- **Security posture for a local app.** Loopback binding, an origin allow-list on
  this port and the Vite port, an empty CORS list, secrets replaced by presence
  flags on the way to the browser, settings written at 0600 through a temp file,
  archive bytes served without exposing a path, the MCP bridge with paid tools
  removed.

## Great, with a note

- **The Director.** One adapter over OpenAI-compatible, Anthropic and Gemini wire
  formats; each role has its own provider, model and key; a role with no key is
  refused by name rather than silently rerouted; every write needs a reason that
  lands in `work/decisions.jsonl`; the tool schema is pinned at 7,000 tokens. The
  turn loop stops at 40 calls, on a repeated identical failure, on a stall, and
  reports "Nothing was lost". Note: the fresh-install default routes every role to
  `gpt-6-luna` through OpenCode Go, a hosted provider whose model availability has
  already bitten once (`gpt-6.1-sol` answered 400). A default that depends on a
  third party's catalogue is a support burden waiting to happen.
- **The prompts.** The Writer system prompt's "The medium, honestly" paragraph and
  the five truth rules are the kind of writing that makes a model behave. Version
  front matter, a 2,000-word budget per task, a deterministic task chooser and a
  hash on every turn make bad output traceable. Note: the October finding that all
  worked examples share one idiom (courier, record, sleeping city, neon) is still
  true of the examples folder; a model anchors on what it is shown.
- **The job runner and live updates.** Per-project serialisation, durable receipts,
  `interrupted` on restart, a bounded event bus, a watcher that fingerprints while a
  browser listens, and a test that pins "GET handlers never write what the watcher
  reads". The frontend has no polling at all.
- **The evaluation harness.** Three frozen fixtures, automatic Writer and Editor
  checks, prompt-version report pages that say "No run recorded" instead of
  inventing a pass, ratings bound to artifact hash and prompt revision. Note: as the
  policy document itself says, it measures format, not quality. A cross-review
  rubric exists and is never sent. Nothing in the repository can tell you whether
  prompt version 3 makes better films than version 2.
- **The error contract.** One `engine_error` mapping to 400/404/409/502 with stable
  codes and never a path; the frontend maps codes to copy and, where there is one
  next move, an action. The October complaint about raw `[Errno 2]` paths is gone.
- **Settings and catalogue.** A nested schema 3 TOML with the old flat names kept as
  read-only properties; a catalogue where a price appears only with its source and
  date; a "what is missing to make a film" checklist. Note: the catalogue is also
  where a wrong voice id sat for a whole phase until a real call exposed it. Live
  probes (`scripts/probe_llm.py`) exist now; run them before each release.

## Needs improvement

### 1. The last mile is unverified

The Cool Cat promo, the advert and the Museum story film are all at a final render,
and the records state that nobody has watched or heard any of them. The Critic reads
frames; it cannot hear or see motion. There is no sound design at all: no ambience
generation, no signature, no music bed for a story film unless a file is supplied.
"Holds are many, so it may feel like a slideshow" is the record's own worry about the
Museum film. Until the owner sits through all three with sound, the visual-quality
and product grades above are estimates. This is the cheapest and most valuable thing
left to do, and it costs nothing.

### 2. Model spend is not money

`work/model-usage.jsonl` records tokens per turn and the architecture says a cost is
"a catalogue estimate, or unknown; never zero", which is correct and honest. But no
text model has a verified price, so the Director's allowance is 25 turns or 400,000
tokens, not dollars, and it is not admitted against the film's cap. The image journal
would refuse this looseness. Either verify one price per default model and admit an
estimated reservation, or show the token count beside every turn in the UI so the
owner at least sees it grow.

### 3. Complexity at the centre

| Hotspot | Measure |
| --- | --- |
| `edits.py` | 1,754 lines |
| `graphics.py` | 1,699 lines; kept because its source is in the renderer hash |
| `director/tools.py` | 1,545 lines, 62 top-level definitions |
| `models.py` | 1,445 lines, 60 classes |
| `remotion.py` | 1,391 lines |
| `generation.py` | 1,138 lines |
| `frontend/src/api.ts` | 1,690 lines of hand-written types |
| `film/FilmPanel.tsx`, `spine/Spine.tsx`, `storyboard/ShotInspector.tsx` | 867, 732, 660 lines |
| CSS | 7,771 lines across 12 stylesheets |
| Functions above McCabe 15 | 24; the worst are `set_creative_profile` 30, `build_context` 29, `run_turn` 28, `init_project` 28, `manifest` 27 |
| Broad `except Exception` in non-legacy source | 22 |

None of this is a defect today, and the tests make refactoring safe. But `run_turn`
and `build_context` are the two functions every Director bug will pass through, and
at 28 and 29 branches they are hard to reason about. The G phase chose, with
measurements, not to split some of these; that decision was sound for the frontend
store and should be revisited for the four Python functions above.

### 4. Frontend tests stop at pure logic

166 frontend tests are all pure functions in `frontend/tests/`. There is no
component test, so the seam click, shift-click, drag, lightbox keys, focus traps and
the Film workspace's portals are covered only by 23 Playwright tests that drive
blocked states, new film, settings, a director turn and the story film. The record
shows what that costs: "the Player's hold past a clip's end was not looked at", "the
Studio's package and vertical-version buttons were always refused" (found by making
a film, not by a test). One Playwright test per interaction the owner uses daily
would be worth more than another hundred unit cases.

### 5. Bundle and types

The main chunk is 600 KB (180 KB gzip) and over Vite's warning; the Player is
already lazy. Stages are not. `api.ts` hand-writes every type the screens read while
FastAPI already emits an OpenAPI document (`frontend/openapi.json` is gitignored, so
something generates it). Generating the types would remove a thousand lines and a
class of drift.

### 6. Portability and the machine

Lyric timing is Apple Silicon only because the word recogniser is MLX; the CPU path
was refused rather than tried because it needs a several-hundred-MB model download,
which is a fair call but leaves Linux and Intel owners on tap-along. Four render
browsers stalled on a 16 GB Mac and the memory guard's accounting is "unproved either
way"; the launch config pins one worker. Chrome is required and not pinned, by
design, so a Chrome update changes no approval but may change a frame. The pixel
goldens guard this in CI on Linux Chromium, which is a different browser from the one
on the Mac.

### 7. Hygiene

- `tests/README.md` names five test files that no longer exist
  (`test_graphics_cache`, `test_render`, `test_camera_path`, `test_preview`,
  `test_stage_skills`) and a `backups/pre-consolidation/` rule from an earlier era.
- Seven local branches; `feat/studio-workflow-redesign`, `fix/absolute-project-root`
  and `tmp/pr71-check` each hold commits not on `main`. 25 remote branches from
  merged or closed PRs.
- On disk: `projects/` 25 GB, `backups/` 8.3 GB, `archive/` 4 GB,
  `.opencode/scratch` 1.9 GB, `renderers/remotion/.cache` 2.5 GB. The record says an
  off-machine copy of the metadata snapshot "is still unchecked". Productions are
  gitignored and immutable by rule, which makes an unverified backup the single
  largest risk to the owner's own work.
- `legacy/` (1,127 lines) waits on the owner; 18 non-legacy modules still mention it
  by name, mostly in comments explaining what replaced it.
- Renderer `npm audit`: `zod` high and `fast-uri` moderate in Remotion's dev
  packages, reached only locally; fixing moves the lock and un-approves every
  film's renderer sign-off, so it waits for a chosen upgrade. Reasonable, but it
  should have a date.
- Six of the eight commits touching `pyproject.toml` since launch were dependabot;
  `openai` 3.x merged after one live probe. Fine. React 19.2, Vite 8 (rolldown),
  Remotion 4.0.539 exact, FastAPI 0.162, Python 3.12 only in CI though the project
  allows 3.13.

## Risks

- **Provider concentration.** Runware is the only paid media provider (stills,
  upscale, clips, speech) and OpenCode Go is the default text route. Both have
  already changed under the project (a voice id that never existed, a model that
  answered 400). There is no second media provider even scaffolded except an
  ElevenLabs adapter behind a key.
- **Approval hashes bind renderer source.** This is correct and is what makes a
  frozen film frozen. It also means every renderer improvement un-approves every
  film and forces one free re-render per film. As the library grows this becomes the
  tax on every visual change; the record already notes it for `graphics.py` and the
  `zod` fix.
- **Bus factor.** One owner, two weeks, 30 commits a day with an AI pair. The
  decision records are the reason this is a B rather than a D: a stranger can read
  why every choice was made. But no second person has run the app from the docs and
  said so.
- **The default experience for a stranger.** Fresh clone, `uv sync`, `uv run studio`,
  then Node, FFmpeg, Chrome, a Runware key and an OpenCode Go key before anything
  paid or written happens. The settings checklist tells you what is missing, which
  is good; it is still five prerequisites.

## What to do next, in order

1. **Watch and listen to the three films**, with sound, start to finish, and write
   the verdict into the production records. Costs nothing, settles the biggest
   unknown, and decides whether "slideshow" is a real problem or a worry.
2. **Verify an off-machine copy** of the newest metadata snapshot and of
   `projects/`. One command, one afternoon, removes the largest single risk.
3. **Price the text models** for the three default routes and admit an estimated
   reservation per turn, or at minimum show tokens beside each answer. Bring the
   Director under the same discipline as the stills.
4. **Split `run_turn`, `build_context`, `set_creative_profile` and `init_project`**
   under the existing tests; target under 15 branches each. No behaviour change.
5. **Add five Playwright tests** for the daily interactions: seam click and drag,
   lightbox Keep/Redo, Make a first cut, approve in the next-step bar, buy a batch
   with a fake provider.
6. **Generate `api.ts` from OpenAPI** and lazy-load the stages; the main chunk
   should drop under Vite's limit without hand work.
7. **Housekeeping day:** fix `tests/README.md`, delete merged branches, decide
   `legacy/`, date the renderer audit fix, run `scripts/clean_caches.py --yes`.
8. **Decide the default model route.** Either own the OpenCode Go dependency with a
   probe in CI that fails loudly, or default to a provider the owner holds a key for.

## Numbers behind this page

| Measure | Value |
| --- | --- |
| Python source | 145 files, 39,482 lines (1,127 legacy) |
| Frontend source | 31,300 lines of TS, TSX and CSS |
| Renderer | 6,025 lines |
| Tests | 33,354 lines; 1,916 pytest in 75 s, 166 frontend, 94 renderer, 23 e2e |
| API routes | 136 (61 GET, 60 POST, 13 PUT, 2 PATCH) |
| Commits | 456 since 20 Oct 2026; 231 co-authored with Claude |
| Real films | Cool Cat promo (final v006), Cool Cat advert (v002), Museum 001 (v004, $1.44) |
| Local data | 42 GB across productions, backups, archive, scratch and caches |
