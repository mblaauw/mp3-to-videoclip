# Finish the blocked-state layer — plan

**Proposed** 1 Nov 2026 for owner approval; base `main` at `c1414a3`.

**Objective:** make every refusal in the Studio name the fix. Phase A of the 31 Oct 2026
assessment (`docs/design/studio-assessment-2026-10-31.md`, "Phase A"): one error
contract on the server, one copy map in the browser, a next-step bar that never sends you
to the page you are on, a Film stage that copes with a film that has no storyboard, human
words where the engine's placeholders and report codes show through today, and the three
phone overlaps. It ends with a handful of browser tests over exactly these states, because
they are where regressions hide and where no test looks today. No money, timing, hash or
approval rule changes.

## What the code showed

- **There is no shared error helper.** `api/_helpers.py` holds only `valid_slug` and
  `project_root` (lines 13-32). `api/errors.py:34-51` already has `ApiError` with a stable
  `code`, `error_payload` and `error_response`, and `app.py:279-281` maps `ProjectBusy` to a
  409 `project_busy`. Every router repeats `except ValueError: raise HTTPException(400,
  str(exc))` by hand (`api/story.py:33-34`, `api/storyboard.py:37-38`, `api/film.py:142-143`,
  `155-156`, `168-169`, `181-182`, `211-212`, `224-225`, `api/images.py:143`,
  `api/ratings.py:21`). `ProjectBusy` is itself a `ValueError` (`storage.py:195`).
- **Nine HTTP 200 error bodies.** `api/images.py:152, 162, 164, 177, 181, 186, 189, 198, 220`
  return `{"error": "..."}` with status 200; `api/track.py:264, 268, 273` do the same for
  lyrics. The browser types them (`api.ts:708-713`, `error?: string`) and shows the raw string
  in red (`images/paid.ts:60, 95-97`, `Images.tsx:591-592`).
- **`FileNotFoundError` text reaches the screen.** `api/images.py:85-86` forwards `str(exc)`
  of a `FileNotFoundError` as a 404 detail and `api/images.py:180-181` returns it in a 200
  body. `api/film.py:142-143` catches `OSError`, which includes `FileNotFoundError`, on
  `GET /edit` and answers 400 with the `[Errno 2] ... storyboard.json` text, because
  `edits.summary` (`edits.py:976-983`) calls `report(root)` even when no edit exists and the
  report reads the storyboard. `GET /edit/summary` (`api/film.py:168-169`) and
  `GET /film/checklist` (`155-156`) do the same.
- **Two engine errors become 500s.** `api/storyboard.py:44-58` `create_skeleton` calls
  `P.skeleton` with no `try`; the engine raises `ValueError` for an existing board or a bad
  timing word (`production/board.py:180, 186`) and `require_approval` raises when the brief
  is not approved. `api/story.py:17-22` `get_brief` calls `load_brief`, which is `read_json`
  (`production/brief.py:32-33`, `storage.py:120-121`) and raises `FileNotFoundError` on a film
  with no brief yet.
- **The copy map is thin.** `api/errors.ts:8-24` knows fifteen codes, mostly the Director's;
  everything else falls through to the raw `detail` (`errors.ts:52`). `api.ts:726-730` toasts
  `error.message` on every non-2xx response. The toast channel supports an action
  (`toast.ts:10-15`) but no error ever carries one; `no_llm_key` says "Open Settings" as words
  only (`errors.ts:9`). The toast tray is `role="status"` for every tone
  (`ToastTray.tsx:66`); `ErrorState` is already `role="alert"` (`ui/State.tsx:64`).
- **Provider failures are bare tokens.** `ProviderError` is a `ValueError` whose message is
  its code (`providers.py:74-80`), for example `network_error` at `providers.py:227`. A
  missing Runware key raises a plain `ValueError` naming the environment variable
  (`providers.py:183-191`). A failed job stores `str(exc)` (`jobs/runner.py:408-411`) and the
  browser toasts `payload.error` as is (`jobs/store.ts:181`).
- **Next-step dead ends, all in `shell/nextStep.ts`.** `193-198`: "The story is not ready
  yet" with *Go to Story* while on Story. The unconfirmed permission arrives as
  `state: "unavailable"` with `error: str(exc)` and no `blocking_stage`
  (`api/approvals.py:96-102`); the text is "permission to upload/depict <id> is not
  confirmed..." (`production/image_specs.py:38-42`), and the card that confirms it is
  `CharactersCard` on the World part (`stages/Story.tsx:22, 149`, `story/WorldPart.tsx:34`).
  `246-254`: "Build the cast, places and rules" with *Open Story*, on Story, from
  `profile_version` (`FilmShell.tsx:475`); nothing in `ProjectFacts` (`35-51`) says whether a
  model key exists, although `GET /api/settings` reports `has_llm_api_key`
  (`api/settings.py:23`). `309-314`: "Read the storyboard and approve it" with no placeholder
  check; `GET /storyboard` (`api/storyboard.py:14-24`) exposes no placeholder count and the
  only rule lives in `production/assets.py:85-97`. `filmStep` (`464-488`) never asks whether a
  storyboard exists and its first "needs you" branch sends to Images (`481-487`). The compact
  bar puts `step.detail` in a `title` tooltip (`NextStepBar.tsx:81, 91`); Film, Story and Track
  use the compact bar (`FilmShell.tsx:599-601`).
- **Film without a storyboard.** `film/useFilmData.ts:78-94` fires six requests at once,
  including `api.editSummary`, and `setError(String(failure.reason))` (`96-97`), so the
  `[Errno 2]` text shows three times: the toast from `api.ts:729`, the `ErrorState` at
  `stages/Film.tsx:258-259`, and the viewer body at `film/LiveViewer.tsx:125`.
- **The renderer setup card.** `stages/Film.tsx:261` mounts `RendererSetup` as the first
  child of `.film-work`, a flex column (`film/film.css:410-415`). The card renders only when
  `/api/setup` reports `renderer: false` (`RendererSetup.tsx:37`, `setup.py:46`) and its
  markup is `.card.setup` (`RendererSetup.tsx:56`), for which `film.css` has no rule. The
  assessment saw the placeholder plate instead of the card; the cause is not proven in code
  and task 5 proves it before fixing it.
- **Skeleton placeholders are shown as text.** `production/board.py:225-226` and `276-277`
  write `TODO: approved story purpose` and `TODO: compose this shot`. `stages/Storyboard.tsx:329`
  and `423` print `shot.purpose` raw, `storyboard/ShotInspector.tsx:338` puts it in the
  textarea, and `storyboard/ShotThumb.tsx:38` prints "framing to set", uppercased by
  `storyboard.css:223, 260`. Approval refuses with "finish storyboard placeholders before
  approval" (`production/approvals.py:351-352`) and the bar never counts them.
- **Header and rating.** `stages/Storyboard.tsx:200-201` still reads "Integer-frame timeline,
  stable shot IDs". `ArtifactRating.tsx:53-73` fetches on `[slug, artifact]` only, so after
  *Create timing skeleton* it keeps showing the engine's "storyboard does not exist yet"
  (`ratings.py:59`) raw (`ArtifactRating.tsx:110, 193`).
- **Cut and titles notes.** `film/cutNotes.ts:32-72` has no case for `travel_repetition`
  (`edits.py:618-624`), `long_static_shot` (`636-638`), `crop_soft` (`646`) or
  `section_no_feel` (`658-660`), and the `motion_repetition` case keeps the raw `push_in`
  token (`cutNotes.ts:52`). The titles message is built at `services/preview.py:178` as
  "The titles cannot be laid out yet: {exc}" with the `ComposeError` text appended.
- **Phone.** `film/film.css:1115` opens the 700 px query in which `.shell.on-film` scrolls;
  `.film-line-head` (`786-791`, wrapping from 1180 px at `1090-1093`) is rendered by
  `film/FilmTimeline.tsx:202` and the tab row by `stages/Film.tsx:231`. The same query hides
  the compact next-step bar outright (`film.css:1139-1141`), so Film has no next step on a
  phone. Transport width: `shell/shell.css:1212-1214` sets `.spine` to a 64 px first column
  at 700 px, but `styles/polish.css:705` sets the same property from
  `--spine-transport-w`, which `polish.css:884-886` makes 168 px below 900 px, and
  `polish.css` loads last (`main.tsx:8, 16`), so the 64 px rule is dead and the waveform gets
  about 220 px at 390 px. Stepper: `shell.css:1153-1156` hides `.step-state` from 1180 px and
  the 700 px rules (`1198-1205`) make the stepper a 48 px scroll strip; the assessment saw
  colour-only dots.
- **Browser tests.** `.opencode/tasks/studio-redesign.md:41-43` decided "do not add
  Playwright. Use the OpenCode browser tool for the phase sweeps... If committed browser
  tests are wanted later, that is a separate dependency decision." CI now exists
  (`.github/workflows/check.yml`: Python tests, frontend `npm test` and build, renderer
  tests), the frontend has 16 pure-logic test files under `frontend/tests/` run with
  `node --test`, and the launcher takes `--projects-dir` (`launcher.py:72, 80`), so a
  throwaway app is one command away. This plan asks for that separate decision (D1).

## Decisions for the owner

| # | Question | Recommendation |
| --- | --- | --- |
| D1 | Add Playwright now, and in which runner? | Yes, as `pytest-playwright` in the dev group with Chromium only, tests under `tests/e2e/` marked `e2e`, run in CI after the unit tests. The fixtures that make a synthetic film with no key already live in `tests/api_support.py`, so one runner and no second Node toolchain. This revisits the redesign decision as it said it would be revisited; the browser-tool sweeps stay for phase acceptance. |
| D2 | What does the server answer for an artifact that does not exist yet? | 404 with a stable per-artifact code (`storyboard_missing`, `brief_missing`, `edit_missing`, `analysis_missing`, else `artifact_missing`) and a plain detail ("The storyboard has not been made yet."). Never the path. `GET /storyboard` keeps its `{available: false}` shape since the Studio relies on it. |
| D3 | Where does "N shots still need a job and a prompt" count come from? | The API: `GET /storyboard` adds `placeholder_shot_ids`, computed with the engine's own `has_placeholders`, so the bar, the approval refusal and the cards agree on one rule. No regex copy in the browser. |
| D4 | How are placeholders shown and saved? | Cards and inspector treat the `TODO:` marker as empty ("Needs a job", "Needs a prompt", empty field with a hint). Saving an empty field writes the marker back, so the engine's approval gate is unchanged and nothing is approved by accident. |
| D5 | Should error toasts interrupt a screen reader? | Yes: `role="alert"` for the error tone only; done and info toasts stay `status`. |

## Tasks (one commit each, one PR)

1. **One error contract on the server.** (0.5 d) `api/_helpers.py` gains `engine_error(exc)
   -> ApiError` mapping `ValueError` to 400 `bad_request`, `ProjectBusy` to 409
   `project_busy`, `ProviderError` to 502 with `code = exc.code`, a new
   `MissingProviderKey(ValueError)` raised by `providers.py:183-191` to 409 `no_runware_key`,
   and `FileNotFoundError` to 404 per D2, deriving the artifact from the file name and never
   forwarding the path. A FastAPI dependency cannot catch what a handler raises, so it is
   installed as app exception handlers next to `ProjectBusy` (`app.py:279-281`); handlers keep
   an explicit `except` only where they add a more specific code. Remove the hand-written
   `except ValueError` blocks that only repeat the mapping. Turn the twelve HTTP 200 error
   bodies in `api/images.py` and `api/track.py` into 400s with codes (`needs_budget` stays a
   200 since it is a decision, not a failure). Wrap `create_skeleton` and `get_brief` by the
   same route. `jobs/runner.py:408` also records `code` when the exception has one.
   Tests in `tests/test_api_errors.py` for every mapping and for "no path in any detail".
2. **Every API error through the copy map.** (0.5 d) `api/errors.ts`: COPY for
   `bad_request` (use detail), `approval_invalid`, `project_busy`, `conflict`, `network_error`,
   `no_runware_key`, `invalidApiKey`, `http_error`, the `*_missing` codes, and a `prefix`
   table for provider codes. `ApiError` gains an optional `action`; `no_llm_key`,
   `no_runware_key` and `invalidApiKey` carry *Open settings*, dispatched as a
   `studio-open-settings` window event that `App.tsx` (`openSettings`, line 65) listens to;
   `*_missing` carry *Go to <stage>*. `api.ts:726-730` passes the action to the toast.
   Drop `error?: string` from the 200 types (`api.ts:708-713`); `images/paid.ts:60, 95` and the
   lyrics save handle `ApiError` instead. Job-failure toasts (`jobs/store.ts:181`) map
   `payload.code` through the same table. Pure tests in `frontend/tests/errors.test.ts`.
3. **No dead end in the next-step bar.** (0.5 d) `nextStep.ts` facts grow
   `has_model_key`, `has_storyboard`, `placeholder_shot_ids`, `permission_pending`
   (character names from `brief.creative`), all supplied by `FilmShell`, which already loads
   the brief and the settings. Rules: permission pending gives "Confirm permission for
   <name>" with *Go to World* (target `world`, which navigates to Story and selects the World
   part); missing profile gives "Ask the Writer to build the cast and places" with *Open the
   Director*, or "The director needs a model key" with *Open settings* when there is no key;
   placeholders give "N shots still need a job and a prompt" with *Show them* (target
   `placeholders`, which filters the board to those shots); `filmStep` checks
   `has_storyboard` before anything else and sends to Storyboard. One guard in `nextStep()`
   converts any `to === stage` into an in-page target, with a test over every stage and
   state combination that asserts no step links to its own stage. New targets are handled in
   `FilmShell.tsx:530-580`.
4. **Detail in the compact bar.** (0.25 d) `NextStepBar.tsx:81, 91`: the compact bar shows
   `step.detail` as a second, smaller line instead of a tooltip; `shell.css` sizes it so the
   Film top bar stays one row at 1440 px and wraps below 1180 px.
5. **Film without a storyboard, and the setup card.** (0.5 d) `useFilmData.ts` reads the
   storyboard first; without one it skips `editSummary`, `checklist`, `preview` and
   `graphicsReview` and shows a single card "This film has no storyboard yet" with *Go to
   Storyboard*; the viewer shows the same sentence (`LiveViewer.tsx:125`). With D2 the
   server would answer 404 `storyboard_missing` anyway, so no raw text can appear.
   Reproduce the missing setup card on a throwaway with the renderer folder absent, record
   the cause, give `.card.setup` a `flex: none` row above the viewer in `film.css`, and add a
   check in the e2e test of task 8.
6. **Human words for placeholders, the header, the rating and the notes.** (0.75 d) A
   `storyboard/placeholders.ts` (`isPlaceholder`, same rule as `production/assets.py:85-97`,
   tested) used by `Storyboard.tsx:329, 423`, `ShotInspector.tsx:338` and `ShotThumb.tsx:38`
   per D4, with "Needs a job" and "Needs a prompt" pills and the *Show them* filter from task
   3. Replace the `Storyboard.tsx:200-201` sentence with "Choose each shot's kind, job and
   picture. Only scene and generated shots cost money." `ArtifactRating.tsx:53-73` refetches
   on `studio:project-changed` for its slug and shows "Rate it once the storyboard exists"
   instead of the engine text. `cutNotes.ts`: cases for the four missing codes, a move-name
   table (`push_in` to "push-in"), and tests in `frontend/tests/cutNotes.test.ts`. The titles
   note: `services/preview.py:178` keeps its string; a new `film/titleNotes.ts` turns the
   three known `ComposeError` sentences into "The titles are not ready yet" plus a plain
   reason, and the panel shows the engine text only under *Details*.
7. **Phone.** (0.5 d) At 700 px: the tab row gets its own row above `.film-line-head`
   (`film.css:1115` query) and is measured clickable at 390×844; the compact next-step bar
   returns as one line under the top bar (`film.css:1139-1141`); delete the dead 64 px rule
   (`shell.css:1212-1214`) and add a real 64 px transport in `polish.css` (play and the clock,
   no time field) so the waveform gets about 300 px; the current step shows its label and
   state word beside the dot (`shell.css:1153-1156, 1198-1205`). Error toasts become
   `role="alert"` per D5 (`ToastTray.tsx:66-68`).
8. **Browser smoke tests and the frontend build.** (1 d) Per D1: `pytest-playwright` in the
   dev group, `tests/e2e/conftest.py` starting `create_app(tmp_path)` under uvicorn on a free
   loopback port with a synthetic 40 s MP3 and a settings file with no keys (the same way
   `tests/api_support.py` builds a project). Four tests: Film without a storyboard shows the
   one card and the page text contains no `[Errno`; Story with an unconfirmed character shows
   "Confirm permission for" and its button lands on the World part; Storyboard after the
   skeleton shows "shots still need a job and a prompt", *Show them* filters, and no card says
   `TODO`; Images with no Runware key shows a sentence containing "key" and *Open settings*
   opens the dialog, with the network recorded to prove no call left the loopback. CI runs
   `uv run playwright install chromium` and the `e2e` marker after the unit tests; locally the
   tests skip when the browser is absent. Rebuild `frontend/dist` (CI checks it is current)
   and update `docs/ARCHITECTURE.md` on the error contract.

About 4.5 days in one PR. The assessment's "one to two days" covered items 1 to 7 without
the tests, the phone work and the setup-card investigation.

## Not changing

Timing, money, approval hashes and the approval rules, the paid-task journal, the golden
contract (`tests/test_contract_golden.py`), the edit schema, the engine's placeholder marker
and the engine's note wording in `edits.py` and `services/preview.py`. Production folders are
only read. No prompt, model or provider change. The `ProjectBusy` handler keeps its code.

## Acceptance

- `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, frontend `tsc`,
  `npm test` and `npm run build`, renderer tests, and the new `e2e` marker all pass in CI.
- `tests/test_api_errors.py` proves every 4xx and 5xx body is `{detail, code}`, that no
  `detail` contains a path separator followed by `.json`, and that the twelve former HTTP
  200 error bodies now answer 400 with a code.
- Pure tests: no next step links to its own stage for any stage and state; the four new
  note codes read as sentences; `isPlaceholder` matches the engine rule on the same cases.
- On a **throwaway projects folder** with a synthetic song, no key and $0 spent, in the
  browser at 1440×900 and 390×844:
  - a new film opened on Film shows one card and one sentence, no toast, no `[Errno`;
  - Story with a character whose permission is unconfirmed names the character and *Go to
    World* lands on the card; with no model key the bar says the director needs a key and
    *Open settings* opens the dialog;
  - after *Create timing skeleton* the bar says how many shots still need a job and a
    prompt, *Show them* filters the board, no card or field shows `TODO`, and the rating
    control offers to rate;
  - on Images, the priced button with no key gives a sentence and *Open settings*;
  - with the renderer folder renamed away, Film shows the setup card above the viewer;
  - at 390 px the Film tab row is clickable, the next step is visible, the waveform is at
    least 290 px wide, and the current stage word is readable beside its dot.
- Every existing function stays reachable: approvals from the bar with a note, paid
  batches, lyrics save, the Director, rendered files and archived films.

## Risks

- **Changing 200 bodies to 400 is an API change.** Only the Studio consumes these routes,
  but `tests/test_api_images.py`, `test_api_local_kinds.py`, `test_api_kind_upstream.py`
  and `test_api_approvals.py` read `["error"]` from 200 bodies and are updated in the same
  commit.
- **App-level handlers hide where an error came from.** The log line keeps the route and
  the exception class; a `ValueError` from a bug, not a refusal, will read as 400. The
  tests for `create_skeleton` and `get_brief` pin the intended ones.
- **Playwright in CI costs time and a browser download.** Chromium is about 150 MB,
  cached by the runner; four tests add about a minute. If the owner declines D1, task 8
  shrinks to the browser-tool sweep recorded in this file.
- **Phone CSS has two override layers.** `polish.css` wins over `shell.css`, so a fix in
  the wrong file does nothing; task 7 moves the phone transport rules into one place and
  deletes the dead one.

## Out of scope

`StoryChanges.tsx` raw JSON, the advert brief URL, the budget history wording, the
Director's suggestions, the eight duplicated shell requests (Phase G4), the library mtime
heuristics (Phase D6), published pricing for reservations (Phase G5), and any change to the
settings dialog (Phase H).
