# Engineering notes

This repository makes films with a local app. Read `README.md`,
`docs/ARCHITECTURE.md` and `.opencode/tasks/gui-rework.md` before changing
anything: the phase record owns its decisions and the rework is complete.

## Rules

- `projects/`, `backups/` and `archive/` are never deleted or rewritten in place.
  Productions are gitignored; the metadata snapshot is their rollback.
- Source audio and generated stills are immutable. A new image is a new version.
- No paid provider call in tests, and no live call without the owner's explicit
  authorization. Money logic lives in the task journal — keep it strict.
- One commit per numbered task, one PR per phase. Each phase ends with `pytest`
  and `ruff` green and an app that starts.
- Do not edit `.opencode/skills/`: it is craft input for the director prompts and
  is deleted once distilled.

## Checks

```sh
uv run pytest
uv run ruff check .
uv run ruff format --check .
```

`tests/test_contract_golden.py` pins the compiled prompt, integer-frame timing and
the Remotion request. Regenerate it only for an intended change and state the
reason in the commit. `tests/test_archive.py` proves the frozen films are only
ever read.

## Shape of the code

- `models.py` is the contract: integer frames, validated dissolves, no legacy
  fields in new artifacts.
- Timing changes go through `timeline.py` / `pacing.py`, never ad-hoc arithmetic
  in a handler.
- Generation cost and recovery go through `generation.py`; never call the
  provider directly from a new surface.
- Keep the engine importable without the web layer: the API, jobs and director
  are consumers, not owners, of timing, money and pixels.

## Rework state

Phases 0–6 are complete. `uv run studio` owns intake, the five stages, the
director, paid generation and rendering; the interim server and its tests are
gone. The Player imports the renderer's own `BaseFilm.jsx` and `timing.mjs`, and
renderer approvals no longer hash the browser binary. A fresh clone installs the
pinned renderer on first launch and serves the committed frontend. Remaining: the
legacy FFmpeg/Pillow branches kept for frozen films and the portable headless-shell
decision.
