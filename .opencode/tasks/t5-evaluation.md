# T5 — Evaluation harness, cross-review and artifact ratings

Authorized: 2026-10-26, owner said "continue and do the whole of T5".

Branch: `director/t5-evaluation` (squash-merged as PR #23, `bbfc646`, 26 Oct 2026)
Phase record: this file
Spec: `.opencode/scratch/t1/writer-editor-brief.md`, T5 and *Evaluation*

## Objective

Make prompt changes measurable without pretending a model ran when it did not:

1. Keep the three frozen fixtures and offline automatic checks.
2. Add a runner that produces one one-page report per prompt version.
3. Add the cross-review rubric and a validated contract for the other role's
   scores; it is a signal, not a gate.
4. Store thumbs up/down plus an optional note for every Writer/Editor artifact,
   bound to the artifact bytes and the prompt revision that produced them.
5. Show ratings in the GUI and aggregate them in the prompt-version report.

## Constraints

- No paid provider call in tests or implementation.
- `uv run python -m tests.evals` must work from a clean checkout and must not
  require a model, a production folder or a browser.
- Live evaluation and cross-review remain manual, explicitly authorized steps.
  The harness must be honest when no run exists.
- Reports are per prompt hash, not per filename; a prompt edit creates a new
  page rather than overwriting history.
- Existing approvals, artifacts and production folders are never rewritten.

## Decisions

- A run is a directory under `tests/evals/runs/<id>/` with `meta.json` and local
  artifact files. `meta.json` names the fixture, role, model, prompt metadata and
  optional cross-review/ratings.
- The default command writes current prompt-version pages for the three frozen
  fixtures (Writer storyboard and Editor edit) even when no run exists. Those
  pages say "not run" rather than inventing results.
- Historical run hashes not in the current prompt set still get a page.
  Rating-only and unbound prompt hashes get a page too; the unbound page is
  titled "Unbound ratings" and lists the thumbs without pretending they belong
  to a run.
- Artifact ratings live in `work/ratings.jsonl`. Each entry binds `artifact`,
  `artifact_hash`, `prompt_hash`, prompt files, rating and optional note. The
  latest matching prompt write comes from `work/prompt-artifacts.jsonl`; a
  rating made without prompt history is stored as unbound.
- Ratings are append-only; the latest entry is shown, history is retained.
- Cross-review scores use a four-question 1–5 rubric: routes, shot jobs,
  rhythm/technique, truth. The reviewer must be the other role. Invalid or
  missing reviews are reported, never silently averaged as zero.
- Automatic checks decide pass/fail. Cross-review and human ratings are signals,
  not gates.
- A damaged JSONL ratings line is skipped so one bad export row cannot hide the
  rest of the report. Malformed cross-review is reported as invalid, not fatal.
- The report command does not scan `projects/` by itself. An operator exports a
  production's `work/ratings.jsonl` and passes it with `--ratings`; this keeps the
  harness from reading production folders by default.

## Acceptance

- `uv run python -m tests.evals` writes one Markdown page per current prompt
  version and an index, with no network or model call.
- A stored Writer run is checked for schema, three distinct structures, board
  coverage, advert kinds and invented claims.
- A stored Editor run is checked for schema, coverage, edit-report hard findings
  and advert checks.
- Ratings round-trip through the API and appear in the prompt-version report.
- Cross-review validation rejects the wrong role or out-of-range scores.
- GUI shows rating controls for brief, treatments, storyboard and edit.
- `pytest`, `ruff`, frontend build and app start are green.

## Evidence

Verification run on `director/t5-evaluation` at `c966b6b`, 26 Oct 2026, against
the final working tree:

- `uv run pytest -q`: **904 passed, 1 skipped**, 4 pre-existing warnings in
  103.60 s.
- `uv run ruff check .`: clean. `uv run ruff format --check .`: 209 files already
  formatted.
- `npm run build --prefix frontend`: clean, 54 modules. The committed `dist`
  serves `index-B32yFqOc.js`, `LivePlayer-B9IC109d.js` and `index-gmShxNLr.css`.
- `uv run studio --projects-dir /tmp/opencode/t4-player --port 8923`:
  `/api/health` returned `{"ok":true,...}` and `/` served the build. In the
  browser, Story showed the Brief and Concepts rating controls, Storyboard showed
  its rating card, and Film showed the Edit rating. Submitting "Good" with the
  note "checked in the Studio UI" wrote
  `work/ratings.jsonl` and the API returned the same row; the browser reported no
  console errors. That throwaway project has no prompt history, so the live row
  is honestly shown as unbound; the prompt-bound case is covered by
  `tests/test_ratings.py`.
- `uv run python -m tests.evals`: **4 current prompt versions, 0 stored runs, 0
  failing**. It wrote four `prompt-<hash>.md` pages plus `index.md` under
  `tests/evals/reports/`. Adding
  `--ratings /tmp/opencode/t4-player/production/work/ratings.jsonl` also wrote
  `prompt-unbound.md` with both thumbs.
- `tests/test_eval_runner.py` covers stored Writer and Editor bundles, failing
  automatic checks, Editor text claims, cross-review wrong role/out-of-range/
  missing scores, rating aggregation, rating-only and unbound pages, damaged
  JSONL, and the clean-checkout module command.
- No paid provider call was made. No production under `projects/` was modified;
  the live app check used a throwaway copy under `/tmp/opencode/`.

## Limitations

- No live Writer/Editor evaluation or live cross-review was run. Both need the
  owner's explicit spend authorization and a writable production copy. The
  harness has no stored model run to report yet, so the current pages say
  "No run recorded" instead of claiming a result.
- The default report command does not read `projects/`; an operator must export
  `work/ratings.jsonl` and pass `--ratings` to include Studio thumbs.
- A prompt edit still ships on the owner's side-by-side judgement; the harness
  supplies the automatic pass rate, cross-review and thumbs, not a verdict.

## Status

Complete. PR #23 squash-merged into `main` as `bbfc646` on 26 Oct 2026; CI
(`check`) passed in 4m34s before the merge.
