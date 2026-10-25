# Audit hardening — task record

**Objective:** close the concrete defects and documentation drift found in the
post-rework audit without touching any production folder. Keep the Studio
runnable, keep every approval content-bound, and leave the frozen films alone.

**Authority:** owner asked for a scan of bugs, stale code, bloat and incorrect
docs after `7d9203b`, with safe fixes. No paid provider call was authorized.

**Constraints:** never write `projects/`, `backups/` or `archive/`; source audio
and generated stills stay immutable; one PR for this slice; `pytest`, `ruff`,
`ruff format --check`, the frontend build and the renderer tests must be green.

## Findings and disposition

| # | Finding | Disposition |
| --- | --- | --- |
| 1 | Story's Save can PATCH an empty brief before the GET resolves, destroying direction/style/treatment/look. | Disable Save until the current brief loads, reset on project change, add retry. |
| 2 | Switching projects reuses stage and Director state, so A's text can be saved into B. | Key `StageView` and `Director` by project and reset Story fields. |
| 3 | Concurrent same-title uploads both pick one slug; the loser `rmtree`s the winner. | Reserve the folder atomically, allow `init_project` an empty reserved root, clean up only that root. |
| 4 | Studio "Render final" renders a base and never asks for graphics review/compose. | Split base and final: base prepares the review; final requires graphics and composes. Expose review samples in Film. |
| 5 | Migration drops `signature_required`; `zero-bars` therefore lost the graphics gate even though it kept its spec. | Preserve the flag in migration and infer from a schema-3 graphics spec when the flag is missing. No production write. |
| 6 | Alias shots break version selection, Select all and quoting. | Use the asset owner for selection/generation, accept either ID in `select_asset`, normalize estimate IDs. |
| 7 | The library silently drops unreadable productions. | Return an explicit unreadable row; disable it in the rail. |
| 8 | Studio LRC save overwrites lyrics; CLI archives the previous copy. | One `save_lyrics` path archives history for both. |
| 9 | Settings Runware key is saved but `providers.runware_api_key` reads only the environment. | Read `effective_settings()`; isolate tests from the real user settings file. |
| 10 | CI runs deleted `tests/test_studio_browser.py`. | Remove the dead browser step; keep the real Python suite. |
| 11 | `domain/staleness.py`, `markup.py`, `storage.write_versioned_page` and `execute` approve/authorize branches are orphaned. | Remove them and their tests; keep the parser's Studio guidance. |
| 12 | README/AGENTS/architecture/task record contain stale claims. | Correct upload locality, attestations, setup card, D1–D8 location and zero-bars gate state. |
| 13 | A test fixture lives under `.opencode/skills`, which AGENTS says will be deleted. | Copy the fixture to `tests/fixtures` and point the test there. |

## Acceptance

- A brief cannot be saved before its current content loads; a project switch
  cannot carry one project's stage or director text into another.
- Two concurrent same-title uploads produce two intact productions.
- A signature film cannot produce a delivery render without a current graphics
  review and approval; a base render prepares review samples the Studio shows.
- `zero-bars` reports the graphics gate as open, not silently passed, without
  modifying its folder.
- Alias shots select the shared owner version and quote only real owners.
- Unreadable library entries remain visible as unreadable.
- Both Studio and CLI lyric saves keep the previous artifact in history.
- The Studio settings Runware key is the key the provider uses.
- CI, `pytest`, `ruff`, the frontend build and renderer tests are green.
- Documentation matches the code and the live production state.

## Evidence

- `uv run pytest -q`: 813 passed, 1 skipped.
- `uv run ruff check .` and `uv run ruff format --check .`: clean.
- `npm --prefix frontend run build`: clean.
- `npm test --prefix renderers/remotion`: 15 passed.
- Browser (real Studio at 8799, `projects/`): library lists Forward Ever, Stof
  en Stilte and Zero Bars; Zero Bars Film shows the base/final controls and the
  graphics gate as open; no console errors.
- Browser (two-project temp library): Story Save is disabled while a delayed
  brief loads; switching Alpha → Beta shows Beta's fields and clears unsaved
  Director text; no PATCH request was sent.
- No file under `projects/`, `backups/` or `archive/` was written. `zero-bars`
  was read only; its missing `signature_required` is handled in code.

## Status

Complete on `audit/hardening`; merged as PR #17 (merge `361136e`, 25 Oct 2026).
