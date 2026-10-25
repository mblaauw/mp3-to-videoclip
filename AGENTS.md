# Engineering notes

This repository makes films with a local app. Read `README.md`,
`docs/ARCHITECTURE.md` and `.opencode/tasks/gui-rework.md` before changing
anything: the rework is in progress and the task record owns its decisions.

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

Phases 0–2 and the Phase 4 Studio are merged. `uv run studio` owns intake, the
five stages, the director, paid generation and rendering; the interim
`serve.py`/`studio_ui*`/`human_*` server and its tests were removed in the Phase 4
cleanup. `cli.py` remains only for engine tasks without a GUI yet. Remaining: the
director compaction/fake-provider probe (Phase 3), legacy model branches, Phase 5
render cleanup and the Phase 6 fresh-clone path.
