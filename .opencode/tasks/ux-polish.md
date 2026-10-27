# UX polish integration

## Objective

Apply the external Studio UX handover (`studio-ux-handover.zip`) to this
repository without losing the two local commits that landed after its base.

## Base and commits

- Base: `origin/main` at `d5aabf1` (the handover's stated base).
- Handover commits: `e5425c0` (source) and `baa858b` (rebuilt frontend).
- Local commit preserved: `da85a3c` — absolute API project roots.
- Local commit preserved and ported: `cb774d1` — stale-proof remakes.

## Decisions

- The handover was applied on a fresh `ux-polish` branch from `origin/main`,
  never directly on `fix/absolute-project-root`, because its `app.py` predates
  the absolute-root fix and its `Images.tsx` predates the stale-proof offer.
- Stale proof shots now travel through the handover's single next-step bar as
  `proof_stale_ids`, not through a second button on the Images page. The bar
  combines missing and stale proof IDs into one priced `proof` batch and labels
  it **Remake**.
- The committed frontend was rebuilt after the port; the old local `dist`
  bundle from `cb774d1` was discarded.

## Acceptance

- `uv run pytest -q` — 977 passed, 1 skipped.
- `uv run ruff check .` and `uv run ruff format --check .` — clean.
- `cd frontend && npm test` — 45 passed.
- `cd frontend && npx tsc -b` — clean.
- `cd frontend && npm run build` — clean; `dist/index.html` references the new
  hashed bundle.
- Manual checks from `HANDOVER.md` §7 remain the owner's visual acceptance,
  including any paid batch.

## Open questions

- The UX handover's data-layer recommendations (short lock per journal write,
  persistent job receipts, corrupt-approvals fallback, chat rotation) are
  deliberately unchanged.
- The creative-profile phase (characters/scenes/look contract) remains queued
  behind this integration and will build on the new single-approval bar.
