# Writer: start from an existing concept

## Objective

Let the owner paste a treatment they already wrote into Story, keep it as
`brief.treatment`, and open the Writer with an instruction to improve it
instead of replacing it. Fix the two failures that made the Writer feel broken:
the 8,000-character chat cap and concept field limits the Writer could not see.

## Constraints

- No paid provider call in tests or without the owner's word.
- The pasted text is the owner's creative work: preserve it, snapshot the
  previous brief in history, and never silently rewrite the Treatment.
- Keep the existing stage flow and prompt-suite versioning.
- Rebuild `frontend/dist`; no new runtime dependency.

## Decisions

- A pasted treatment is Story content, not a chat message. Story saves it with
  `PATCH /brief` first, then opens the Director prefilled. The Writer reads
  `brief.treatment` with `get_brief` and may improve it with `update_brief`.
- Chat bound is now 24,000 characters with a stable `message_too_long` code and
  copy that names the Story import panel.
- Concept limits: `why`/`world` 1,200 and `risk` 800 (was 500/700/300). The
  `update_treatments` schema advertises every limit; `writer/concepts.md` v2
  states them and says an existing treatment is the authority.
- Story reloads the brief on external project changes, but only when there is
  no unsaved treatment text, direction/style edit or save in flight.

## Acceptance

- A 24,000-character chat message is accepted; 24,001 is rejected as
  `message_too_long` before any model call.
- Concepts with 1,200-character `why`/`world` and 800-character `risk` save;
  the tool schema advertises the same limits as the model.
- Story shows "I already have a concept" when empty and in a collapsed details
  when concepts exist. Saving fills the Treatment, updates the textarea and
  opens the Writer with the improvement prompt, without sending.
- `pytest`, `ruff` and the frontend build/tests are green; Studio starts and
  serves the new bundle.

## Follow-up: the protected style core

The Writer followed the owner's master-style request by replacing the whole
`creative.look`, which is correct for a custom look but invalid while
`photographic-painted-v2` stayed selected. Approval then failed the protected
core check, and the Look card had no way to detach from the preset.

- `apply_intake(style_preset="")` now clears the preset and keeps the current
  look; selecting a named preset still replaces the look with that preset.
- Story → Look lists **Custom**; choosing it detaches without rewriting the look.
- The Writer prompt now states the protected-core rule and points at Custom. The
  `update_brief` tool refuses to blank `direction`, `style` or `treatment`, so a
  full-object patch cannot quietly make the brief unapprovable.
- Repaired `tree-of-love` through the API: preset cleared to custom, its 2,049
  character master look unchanged, and the missing one-line `style` restored
  from the owner's own sentence. A dry-run approval on a copy validates; the
  owner still makes the real approval decision.

## Follow-up: a null correction limit in a schema-3 budget

`schema_version: 3` keeps the cap history in `project.json`. A null
`max_corrections` there means "no explicit limit was recorded", but the budget
validator only defaulted a *missing* key and rejected null, so the first paid
style-check quote failed with `production budget artifact has invalid
max_corrections`.

- `_schema_budget` now maps a null correction limit to
  `DEFAULT_MAX_CORRECTIONS`; explicit integers, including 0, stay untouched.
- `tree-of-love` now reads `cap $5.00`, `max_corrections 1`.
- The proof estimate for s003/s006/s038 returns 3 stills at $0.15 with
  `needs_budget: false`. No provider call was made; the owner confirms the paid
  batch.

## Status

Complete. Live smoke check on a temporary copy of `tree-of-love`: imported a
short concept, confirmed `brief.json`, the Treatment textarea and the Director
composer prefill; no model call. Temporary project and server removed. The
owner's `projects/tree-of-love` data was not modified by that smoke check; the
later style and budget repairs were deliberate and recorded above.

## Evidence

- `uv run pytest -q`: 943 passed, 1 skipped.
- `uv run ruff check .` and `uv run ruff format --check .`: clean.
- `npm run build`, `npm test`: 39 tests passed.
- `GET /api/health` on `127.0.0.1:8799`: ok.
- `POST /chat` with 24,001 characters: `400 {"code": "message_too_long"}`.
