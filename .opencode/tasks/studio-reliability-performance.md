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
- Interrupted between 2026-10-27T20:28Z and the owner's explicit resume request.
  Resumed: 2026-10-28T02:31:09Z; new bounded cycle deadline 04:01:09Z.
  No work is claimed for the interruption. No test/render process is active.
- Further harness/user interruptions occurred; the owner explicitly requested
  continue again at the 2026-10-28T08:23:00Z status check. This bounded cycle ends
  by 09:53:00Z; elapsed idle interruption time is not engineering evidence.
- Spending cap: $0 new provider spend.
- Initial revision: `b6c3e4fc3d894995483b4cf070836e8a54b82324`; initially clean.
- Studio processes are running; no active render/pytest process was observed.
  Do not stop/restart the owner's app. Use fixture-only acceptance servers.

## Ordered tasks and dependencies

| Phase | Tasks | State |
| --- | --- | --- |
| 1: correctness | T1 complete/consistent snapshots; T2 coordinated mutations/budget/recovery; T3 worker ownership/lifecycle receipts | merged PR #38 at `2afc1cc` |
| 2: responsiveness | T4 read snapshots/indexes/hash reuse; T5 shared frontend resources/selective invalidation | merged PR #39 at `3375eb1` |
| 3: delivery clarity | T6 truthful output classification; T7 visible intro/credits/review/composite workflow | implemented; final checks/publication active |
| 4: render performance | T8 diagnostics/benchmark; T9 measured acceleration; T10 precise cache dependencies | pending phase 3 |

## Acceptance

All phases: pytest, ruff check/format, affected frontend/renderer checks, runnable
app, fresh revision-bound review and no production mutations. Add deterministic
race/restart/backup/request-count/hash-count tests. Preserve approval and golden
contracts unless an intended change is explained. Phase 4 additionally requires
local performance and quality evidence, not just encoder flags.

## Checkpoint

- Branch: `reliability/phase-3`; base `3375eb1`; T1 `d8d5d89`, T2 `285e0cb`,
  T3 `44f6a36`. Phase 1 GitHub CI passed before merge.
- T1 accepted: 45 snapshot tests passed, including JSONL restore, mutation
  detection, secret exclusions and exclusive publication. Fresh review found
  secret-root/output-symlink gaps; both were corrected and checks rerun. Capture
  is explicitly optimistic, not a filesystem transactional snapshot.
- T2 implemented: reentrant cross-process state locks separate from operation
  leases, atomic admission/reservation, coordinated manifest/review/document and
  journal writes, canonical schema-3 budget, offline ready-task index recovery,
  and optional HTTP ETag/If-Match conflicts for brief/board/edit. Frontend
  conditional-write wiring belongs with shared request resources in T5.
- Fresh T2 review found missing full-set gate revalidation, OpenAI publication
  conflict and matching-dual-budget top-up hazards. All corrected; 23 targeted
  coordination tests pass. Full suite: 1062 passed, 1 skipped (before final T3
  cancellation-race correction). Golden contracts unchanged.
- T3 implemented: explicit blocking job mode wired at all five worker callers,
  cooperative stopping/drain ownership, pure async cancellation compatibility,
  per-project monitoring receipts and read-only interrupted restart history.
  Frontend treats stopping as active, never as completed. Fresh review caught a
  simultaneous cancellation/failure error-loss race; regression reproduced then
  fixed. Focused runner/receipt/API/director integration: 37 passed.
- Frontend tests: 47 passed; API types regenerated; TypeScript/build clean.
  Ruff check and format clean. No production files or owner processes changed.
- T4 implemented: per-operation coherent reads, indexed reviews, unique dependency
  hashing and threadpool GET handlers. Review found/fixed captured-context cache
  lifetime, nested-root retirement and plate publication races. Focused suites:
  159 passed, 1 skipped; 79-shot fixture hashes source/79 images/shared ref once.
- T5 implemented: shared GET resources, selective invalidation, epoch guards and
  object-bound conditional writes. Review found track/edit-summary invalidation
  and inspector late-save/self-conflict gaps. Latest correction wrote helper/tests
  before its session response timed out; parent verification is required.
- Phase 2 full background suite completed: 1076 passed, 1 skipped in 152.61 s
  (`.opencode/scratch/phase2-pytest.log`). Earlier foreground timeouts stopped at
  different positions with no failure trace; no deterministic hang reproduced.
  Focused read-snapshot suite: 13 passed. Frontend: 64 passed, including selection
  ownership, pending saves, revision handoff and track/edit-summary invalidation.
  TypeScript and rebuilt shipped frontend passed; ruff/diff checks clean.
- Copy-only 79-shot zero-bars HTTP measurements, warm: Images 58.7 ms /38.1 MB
  binary reads; approvals 63.7 ms /38.1 MB; checklist 84.0 ms /38.1 MB; Player
  42.1 ms /5.29 MB. These include HTTP, unlike initial direct-function probes;
  no precise end-to-end speedup or physical disk IO claim. All copy files removed
  by temporary-directory cleanup; original production untouched.
- Next: commit T4/T5 separately, publish/check Phase 2; then T6/T7 delivery clarity.
- T4 `80e658d`, T5 `8f63345`, PR #39. Frozen review caught inspector navigation
  discarding newer typing during an outstanding save. Corrected with an explicit
  acknowledged-save navigation boundary; failed/pending/surviving drafts keep
  selection. Frontend now 67 passed and shipped build regenerated. Backend
  remains the exact 1076-pass snapshot. CI must pass the corrected PR head.
- Phase 2 correction `7b299da` passed GitHub CI and fresh navigation review;
  merged PR #39. No bypass/stale checks used. Phase 3 was prepared on its tested
  head while CI ran, then fast-forwarded to the integrated merge before commit.
- T6 implemented: report-backed base/preview/final/unknown exports, current-byte
  and graphics checks, immutable pre-render provenance and stable file selection.
  Budget changes do not make output metadata stale; root brand is tracked.
  Concurrent edits during render preserve the output but make it unready.
  Focused route/export/adapter/preview checks: 60 passed; frontend 69 passed,
  TypeScript and shipped build green. No existing production report rewritten.
- T6 commit `00586c2`; independent frozen review found two delivery-safety
  defects. Corrected: certify the compositor's actual versioned output, never
  overwrite the occupied destination's report; require nonempty graphics
  provenance for signature-required finals. Regressions cover missing/empty/
  whitespace provenance and preserved old movie/report bytes.
- T7 implemented: persisted render purpose, stage/part/frame progress with
  boundary resets, persistent workflow and explicit manual intro/credits review.
  No pixel/timing/encoding changes. Independent progress review found approved
  titles could request impossible reapproval while another gate was outstanding;
  corrected and regression added. Frontend 74 passed; renderer Node 24 passed;
  build, Ruff lint/format passed. Focused backend 79 passed.
- Fixture-only browser acceptance passed at 1440/390 px, including stage flow,
  review sample keyboard controls, explicit approval, approved-but-blocked gates,
  verification, Cancel → stopping, failure, file labels/download targets and
  reload persistence. No console errors/document overflow; own port 18973 closed.
  Evidence `.opencode/scratch/phase3-acceptance-report.md`, current complete
  fingerprint `eee5763da9b5cf0dedd2d9631d396ada3fcb27142a4b0127892025214ea0b9e2`.
  UI state evidence is stubbed; no engine, production approval or pixel claim.
- Initial full phase check: 1096 passed, 1 skipped, 1 failure: old strict SSE
  assertion omitted the intentionally additive nullable render purpose field.
  Updated that assertion; full same-code suite passed: 1097 passed, 1 skipped
  in 105.82 s (`.opencode/scratch/phase3-pytest.log`).
- Phase 3 code frozen at `c58fa0b`; T6 safety correction `bc91768` separately
  committed. Fresh revision-bound correction reviews accepted both provenance
  blockers and the workflow correction. Frontend API regeneration is clean.
  PR #40 opened; current-head CI/merge pending. Next: integrate after green,
  then T8 reproducible render diagnostics and bounded local benchmarks.
- Phase 1 final code revision `414fc92`: 1063 pytest passed, 1 skipped; ruff
  check/format clean; frontend 47 passed, TypeScript/build/API types clean.
  Isolated app startup root/projects/jobs all HTTP 200 using the required
  localhost host (initial testserver-host probe was correctly rejected 403).
  T3 fresh-review cancellation-race correction passed its deterministic test.
  No golden regeneration, provider call, production rewrite or app restart.
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
