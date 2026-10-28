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
- Last pre-handoff clock check was 09:21:49Z. After the bounded T9 child returned,
  the next observed clock was 10:58:57Z, beyond the cycle deadline. No engineering
  work is claimed for the unobserved gap. Implementation stopped; only final
  verification and this checkpoint followed. Resume requires a fresh owner cycle.
- Owner requested continue; resumed at 2026-10-28T11:08:18Z with a new bounded
  cycle deadline 12:38:18Z. Ready order: independent T8 cleanup/T10 cache review,
  finish bounded T9 evidence or explicitly defer unsupported adoption, verify
  frozen Phase4 checks/runtime, commit/publish/current-head CI/merge. Scope,
  publication authority and zero-provider-spend cap are unchanged.
- Spending cap: $0 new provider spend.
- Initial revision: `b6c3e4fc3d894995483b4cf070836e8a54b82324`; initially clean.
- Studio processes are running; no active render/pytest process was observed.
  Do not stop/restart the owner's app. Use fixture-only acceptance servers.

## Ordered tasks and dependencies

| Phase | Tasks | State |
| --- | --- | --- |
| 1: correctness | T1 complete/consistent snapshots; T2 coordinated mutations/budget/recovery; T3 worker ownership/lifecycle receipts | merged PR #38 at `2afc1cc` |
| 2: responsiveness | T4 read snapshots/indexes/hash reuse; T5 shared frontend resources/selective invalidation | merged PR #39 at `3375eb1` |
| 3: delivery clarity | T6 truthful output classification; T7 visible intro/credits/review/composite workflow | merged PR #40 at `7fe6f96` |
| 4: render performance | T8 diagnostics/benchmark; T9 measured acceleration; T10 precise cache dependencies | partial; T8 committed, T9/T10 uncommitted; review/publication pending |

## Acceptance

All phases: pytest, ruff check/format, affected frontend/renderer checks, runnable
app, fresh revision-bound review and no production mutations. Add deterministic
race/restart/backup/request-count/hash-count tests. Preserve approval and golden
contracts unless an intended change is explained. Phase 4 additionally requires
local performance and quality evidence, not just encoder flags.

## Checkpoint

- Branch: `reliability/phase-4`; base `7fe6f96`; T1 `d8d5d89`, T2 `285e0cb`,
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
- Phase 3 evidence head `ab23264` passed current-head CI; PR #40 merged at
  `7fe6f96`. Same-snapshot affected/golden/parity checks: 53 passed; real local
  renderer smoke passed. No production app restart or artifact mutation.
- T8 implemented observation-only renderer/adapter/compositor timing reports and
  opt-in isolated synthetic 1080p benchmark. No quality/encoder/concurrency change.
  Initial base run partial (2 cold/1 warm within 180s); alpha 2 cold/2 warm.
  Observed libx264 / prores_ks, PNG/image2pipe, parallel encoding, concurrency 2.
  Base subprocess overhead outside measured rendering remains unexplained.
  Targeted Python/golden 19 passed, Node 26 passed, real smoke and alpha extrema
  (0,255) passed. Next: freeze/repeat baseline, review T8, then benchmark T9
  candidates without changing master defaults; T10 selected-asset cache boundary.
- Phase 4 HEAD `ea98503` (T8). Final unchanged-renderer baseline completed two
  cold/warm pairs for both base and alpha. Base subprocess medians cold/warm
  47.49/47.10 s; renderMedia 20.83/20.80 s. Alpha subprocess 6.00/5.17 s;
  renderMedia 4.63/4.52 s. Dominant base observation is unexplained subprocess
  overhead, not isolated encoding. Evidence in approved temporary directory
  `t8-render-final/benchmark.json`, frozen renderer source hashes included.
- Independent T8 review accepted diagnostics/noninterference but blocked timeout
  cleanup: subprocess timeout killed Node without bounding detached Chrome.
  Uncommitted correction tracks owned PID/start identities, graceful termination,
  bounded escalation and survivor checks. Five local-process regression tests
  pass; correction still requires independent review. No benchmark/render/ffmpeg
  process remained in the final scoped process check; owner Studio was untouched.
- T9 uncommitted opt-in candidate harness and base-only VideoToolbox-20M profile.
  Completed software runs: c1 one replicate (18.46s), c2 one (48.60s), c3 two
  (median45.72s); all warm, exact 288 frames/1080p24/BT.709/silent and SSIM1.0.
  Interrupted second c2; hardware runs not reached. Raw CDP capability probe
  confirms the installed browser lacks Page.remotionCreateFramePool. No browser
  replacement, hardware/concurrency default adoption or speedup claim. T9 remains
  partial, not accepted. Evidence `t9-render-candidates-final/candidates.json`.
- T10 uncommitted visual-only cache identity and immutable selected-asset
  publications; budget-only reuse, selected/native-pane pixel dependencies,
  strict SHA/full-key receipts and historical creation timers distinguished.
  Adapter/golden tests43 passed; independent review and runtime/cache acceptance
  still pending. Code-only bundle separation deliberately not introduced.
- Final worktree verification: pytest1128 passed/1 skipped in120.04s; renderer
  Node26 passed; Ruff lint/format and diff checks passed. Frontend unchanged from
  accepted Phase3. Tested uncommitted seven-file fingerprint before checkpoint
  documentation-only updates:
  `84e4265d7fb69121f75c3ba3e248b8ffc545952a61aff31b57f19b8e3bee0444`.
  All Phase4 changes remain local; no Phase4 PR or merge. No golden regeneration,
  provider spend, production rewrite, approval, owner restart or cleanup.
- Next owner-authorized cycle: review T8 cleanup/T9 harness/T10 frozen diff,
  resolve findings and add acceptance evidence; finish or explicitly defer T9's
  missing hardware/quality measurements, commit tasks separately, run same-head
  full checks/startup, then publish Phase4 with current-head CI. Do not treat the
  passing tests or child 'complete' status as final milestone acceptance.
- Resumed-cycle progress: T8 cleanup review rejected ancestry polling's initial
  inspection, orphan and second-resolution identity gaps. Replaced with an
  inherited cryptographic run nonce, UID-scoped discovery, immediate nonce
  revalidation and independent Popen cleanup. Eleven local-process tests passed;
  fresh review accepted the supported environment-inheriting renderer scope.
  Correction committed `95709ec`; arbitrary environment-scrubbing programs are
  explicitly outside this opt-in runner's contract. Raw environments never logged.
- T10 review found same-key silent render creation unprotected across processes.
  Added per-visual-cache lock through strict receipt publication, never a long
  project-state lock; distinct final muxes run after release. Deterministic
  synchronized two-process contention test proves one invocation and two successful
  consumers. Independent correction review accepted adapter hash
  `55522e28389074c907ba3549933955017b5a1f11426064b3c64df4a01b6183ed`.
- T9 adds replicated software/all/hardware suites, warm-cache and actual encoder
  assertions, nonzero partial exits and opt-in profile tests. Source review found
  raw CDP probe could allow implicit browser acquisition with a malformed baseline;
  corrected with explicit existing local executable validation and a refusing
  download callback. Six candidate-script tests pass; correction review pending.
- Serial full T9 comparison running with a 660s budget in approved temporary
  `t9-resumed-comparison/`, shell job `sh_1823b11c3001zwAUxzBqhK5ifT`.
  No concurrent rendering/quality acceptance runs; Node sources remain frozen.
  Ready next: inspect completed evidence, runtime cache/alpha/audio acceptance,
  same-head full suite and phase publication. No master defaults changed.
- Full synthetic T9 series completed: two measured runs each c1/c2/c3/software
  and c2/VideoToolbox, all warm, exact frames/canvas/fps/colour/silent contracts.
  Median subprocess wall c1 18.64s, c2 46.82s, c3 47.21s, VT-c2 46.63s.
  Software decoded SSIM1.0; actual h264_videotoolbox20M SSIM0.999306. Hardware
  policy is not quality-equivalent and offers no material wall improvement here;
  master hardware adoption will be deferred. Source reports record exact hashes.
- T9 browser-preflight correction accepted by independent review; removed an
  ignored openBrowser option instead of claiming an unsupported API safeguard.
  Only the validated explicit existing executable prevents implicit acquisition.
- Per-cache creation correction and T10 visual/selected-assets boundary accepted
  by independent review. Focused cleanup/candidate/adapter/golden suite55 passed.
  Freezing cache implementation before runtime acceptance. No deletion or repair
  of old caches is part of this change; code-plus-selected-assets bundle remains.
- To qualify a base-only concurrency change, a second serial comparison now uses
  read-only, SHA-verified copies of selected tree-of-love images s003/s006/s038
  in a synthetic12s test cut. No production timeline changed. Baseline includes
  an opt-in external active-resource probe, not renderer/dependency patches.
  Evidence `t9-real-image-comparison/`, shell `sh_18243aa6d001lLzO5wa3pBW6HD`.
  Adoption still requires completed replicated measurements and visual/alpha/
  audio acceptance; no default has changed yet.
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
