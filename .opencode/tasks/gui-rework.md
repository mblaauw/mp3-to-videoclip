# GUI-first rework — task record

**Objective:** turn mp3-to-videoclip into one local GUI app (`uv run studio`) that owns the
LLM director, the paid generation and the render. One PR per phase, kept runnable, no
OpenCode crew and no user-facing CLI.

**Authority:** implementation brief supplied 25 Oct 2026 (reviewed revision `4e3b299`).
Decisions D1–D8 are in that brief and are authoritative. Three answers given 25 Oct
override it where they disagree:

- **zero-bars migrates** to schema 3 (it is the one live production: 79 shots, 240 s,
  82 stills, 16 accepts / 2 rejects, no render). The two finished films stay frozen.
- **Remotion Player assumed workable.** If the 79-shot composition cannot play smoothly,
  stop and ask before choosing a proxy fallback.
- **One PR per phase**: commit, push, merge, then start the next phase.

## Constraints

- Never delete anything under `projects/`, `backups/` or `archive/`. `projects/` is
  gitignored: the metadata snapshot in `backups/` is its only rollback besides the
  `pre-gui-rework` tag on code.
- No live paid call in tests. Source audio and generated stills are immutable.
- One commit per numbered task in the brief.
- Every phase ends with `pytest` and `ruff` green and an app that starts.

## Deviation from the brief (recorded, reversible)

Phase 1's delete table removes the current Studio (`serve.py`, `studio_ui*`, `human_*`)
and the approval machinery before the replacement exists in Phase 4. That would leave no
working app — and no way to advance zero-bars — for the 2–3 weeks of Phases 2–3. So:

- Phase 1 deletes only what nothing else imports: the agent runtime, the second agent
  runtime (`spine/plans/context/evals/mcp/tools`), the static page generators and the
  dead one-off modules.
- `serve.py` and the approval paths stay, working, until the commit in Phase 4 that lands
  the new frontend. Phase 1's ≤ 11,000-line target is therefore measured after that
  replacement, not at Phase 1 merge.

## Status

| Phase | State |
| --- | --- |
| 0 · safety net | **done** — tag `pre-gui-rework`, metadata snapshot (610 files), golden contract test |
| 1 · delete and migrate | **functionally complete on `gui-rework/phase-1-delete-migrate`.** Done: crew config and loop removed; second agent runtime removed (106 tests); `.opencode/skills` kept for Phase 3; read-only archive reader; static page generators and one-off tools deleted (`dashboard`, `inspector`, `intake`, `calibration`, `edits`); docs replaced with README + `docs/ARCHITECTURE.md` + 60-line `AGENTS.md`; B13 skeleton defaults unified; `studio` launcher added; feedback queue removed. Remaining modules (`flow`, `operations`, `sources`, `human_*`, `studio`, `studio_ui*`, `reviews`, `appdata`, `backup`, `signature`) are imported by the interim Studio/CLI and cannot be deleted until their replacements land in Phases 2-4 (recorded deviation). Legacy model branches move with them. `src/` 21,124 -> 17,371. |
| 2 · backend skeleton | not started — owns the schema-3 models and therefore the zero-bars importer |
| 3 · director | not started |
| 4 · frontend | not started — deletes the interim Studio and the approval paths |
| 5 · render cleanup | not started |
| 6 · polish | not started |

## Acceptance per phase

- **0:** tag exists; snapshot restores metadata; golden passes. ✅
- **1:** no import of a deleted module; golden unchanged; archive lists both finished films;
  zero-bars imports to schema 3 and opens; suite < 3 min.
- **2:** every route tested; zero-bars opens < 150 ms; B4/B6/B7 regression tests.
- **3:** probe recorded; fake-provider session import → board → mocked batch → one
  regeneration; Stop < 1 s.
- **4:** every route zero console errors; 390/900/1280; keyboard-only path; Player spike.
- **5:** no Chrome read; preview + final on a clean runner; `timing.mjs` parity.
- **6:** fresh clone → `uv sync` → `uv run studio` → film, no terminal.

## Open questions

- Remotion Player at 79 shots: assumed acceptable; revisit only if measured.
- YouTube audio bitrate in the brief (384 kbps) to be checked against the live spec in
  Phase 5; harmless if generous.
