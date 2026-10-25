# T0 — director tool fixes

**Objective:** make the director's write tools safe and its per-turn context cheap
before adding the Writer/Editor roles. Four defects:

- **W1** `update_brief` shallow-merges, so a look-only patch deletes the creative
  world, scenes, references and proof selection.
- **W2** `update_shots` writes unchecked `setattr` values and never re-validates
  the whole board against the project and brief.
- **W3** the per-turn context runs every approval gate and re-hashes the source.
- **W4** the director cannot see an image, so it cannot review stills.

## Acceptance

- A look-only brief patch keeps every other creative field and snapshots the
  previous brief in `work/brief-history/`.
- Invalid shot edits return an error, change no file, and unknown fields/IDs are
  refused; a valid multi-shot timing edit is revalidated against the project and
  brief before writing.
- A context snapshot on the 79-shot production contains the brief, shot table,
  image statuses, recorded approvals, budget and stage without hashing the MP3
  or calling every gate.
- `get_images(shot_ids)` returns at most eight thumbnails (long edge ≤512 px) as
  image parts, never persisted as base64 in chat history.
- `pytest`, `ruff`, `ruff format --check` and the frontend build are green.

## Evidence

- `uv run pytest -q`: 824 passed, 1 skipped.
- `uv run ruff check .` / `uv run ruff format --check .`: clean.
- `build_context("zero-bars", stage="story")`: 0.04 s, 10.8 kB, 79
  current-input stills, brief, recorded approvals, budget and shot table; no
  source hash or gate pass.
- `get_images` on `zero-bars` returned two 512 px thumbnails as image parts with
  no errors; chat history stores only the bounded text result.
- No production folder was written.

## Status

Complete on `director/t0-tools`, based on `7b93068`.
