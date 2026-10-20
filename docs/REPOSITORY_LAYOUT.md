# Active source versus production history

## Active

- `src/mp3_to_videoclip/`: production contracts, gates, durable provider records,
  analysis, image production, preview, verification and renderer adapter.
- `renderers/remotion/`: one pinned project-local visual renderer; Python derives
  its props from the canonical project/storyboard and graphics spec.
- `tests/`, `scripts/`: engineering checks and bounded maintenance entrypoints.
- `brand/releases/`: versioned vector masters/exports and manifests. Prior releases
  remain legitimate historical artwork, not accidental duplicates to remove.
- `AGENTS.md` → `LOOP.md` → focused stage skill → `PRODUCTION_WORKFLOW_V2.md` is the
  production read order. `RENDERER.md` documents implementation contracts, not
  another approval state. `PLAN.md` and implementation plans are historical.

## Private / generated

`projects/` holds original media, selected/unselected versions, paid task journals,
approvals, real review material and final films. `backups/` holds verified archives.
These are intentionally excluded from git; neither folder is disposable.

The 18 October 2026 inventory measured approximately4.5GiB of project material and
4.5GiB of backups, versus ~1.4MiB source,2.3MiB tests and84KiB docs. The initial
renderer pilot additionally used383MiB node_modules,33MiB bundle and616MiB output.
Disk consumption is not evidence that the40-module engine is redundant.

## Archive-first policy

Superseded implementation plans, design presentations and the first renderer pilot
can move to named archives **after** their replacement passes validation. Every
move is recorded with old/new relative paths and SHA256. Historical entrypoints
are kept as small pointers where links need compatibility. No blanket `git clean`,
backup pruning, source-media deletion or selected-version deduplication.

Rebuildable Node/Python caches are identified separately. Archiving within this
repository reorganizes source; it does **not** claim reclaimed disk space. A zip
beside a brand directory is a convenient handoff package, not automatically waste.

At migration start git tracked zero files. A private source/config snapshot was
verified member-by-member before implementation. This is not a git commit and
does not authorize publishing the repository or private production artifacts.
