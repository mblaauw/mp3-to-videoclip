# Studio reliability, responsiveness and render clarity

## Contract

Approved by the owner on 2026-10-27: execute the implementation plan at
`~/.opencode/plan/2026-10-27-studio-reliability-performance.md`.

Keep portable project folders and file formats. No paid calls/live quotes,
production approvals, creative restaging, media cleanup, SQLite migration or
renderer replacement. Preserve unrelated work and all existing productions.
One commit per numbered task; one PR per phase, with same-revision verification.
Publication authority follows the approved phase plan and repository policy.

## Session budget

- Started: 2026-10-27T19:38:25Z; deadline: 2026-10-27T21:08:25Z (up to 90 min).
- Spending cap: $0 new provider spend.
- Initial revision: `b6c3e4fc3d894995483b4cf070836e8a54b82324`; initially clean.
- Studio processes are running; no active render/pytest process was observed.
  Do not stop/restart the owner's app. Use fixture-only acceptance servers.

## Ordered tasks and dependencies

| Phase | Tasks | State |
| --- | --- | --- |
| 1: correctness | T1 complete/consistent snapshots; T2 coordinated mutations/budget/recovery; T3 worker ownership/lifecycle receipts | active |
| 2: responsiveness | T4 read snapshots/indexes/hash reuse; T5 shared frontend resources/selective invalidation | pending phase 1 |
| 3: delivery clarity | T6 truthful output classification; T7 visible intro/credits/review/composite workflow | pending phase 2 |
| 4: render performance | T8 diagnostics/benchmark; T9 measured acceleration; T10 precise cache dependencies | pending phase 3 |

## Acceptance

All phases: pytest, ruff check/format, affected frontend/renderer checks, runnable
app, fresh revision-bound review and no production mutations. Add deterministic
race/restart/backup/request-count/hash-count tests. Preserve approval and golden
contracts unless an intended change is explained. Phase 4 additionally requires
local performance and quality evidence, not just encoder flags.

## Checkpoint

- Branch: `reliability/phase-1`; HEAD `b6c3e4f`.
- T1 accepted: 45 snapshot tests passed, including JSONL restore, mutation
  detection, secret exclusions and exclusive publication. Fresh review found
  secret-root/output-symlink gaps; both were corrected and checks rerun. Capture
  is explicitly optimistic, not a filesystem transactional snapshot.
- Current task: T2. Next: coordinated mutations and financial admission tests.
- T1 files: script SHA256 `129c7c271e4b651589080ac00390aaa6d4e76dcbd9968d5b2d121ac1180171b8`,
  tests `037c93b60ab05d5f7510e32cee2f5ed5bb3e17b5e760dd2cf4014489ca734a52`.
  No new provider spend. Full phase checks pending.
- Task record is the only milestone checkpoint; the completed GUI-rework record
  remains unchanged.

## Open limitations / follow-ups

- Broader model consolidation, creative-profile enforcement bypass and Undo
  traversal are deferred by the approved scope.
- No render speedup has been established yet. Baseline latest-production visual
  render: 5,749 1080p frames, 668.803 s, software H.264 and PNG capture.
