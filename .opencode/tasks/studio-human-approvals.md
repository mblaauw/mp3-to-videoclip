# Human Studio decisions

## Objective and authority

User selected UI approvals before legacy removal after PR #2 merged at `75f8c95`.
Implement ordinary stage approvals and quote authorizations in an explicitly
terminal-enabled Studio session. Public CLI approve/authorize direct users there;
kernel APIs remain callable for internal integrations/tests. This is workflow
separation, not a sandbox against unrestricted same-OS processes.

Branch: `feat/studio-human-approvals`; base `75f8c95`. Started 2026-10-21 18:50 UTC;
checkpoint by 20:20 UTC (90-minute ceiling). Zero new spend. Updated global policy:
leave reviewed commits ready; the user publishes, opens PRs and merges.

## Scope and constraints

Two narrow action endpoints; reviewed stage/quote hashes under the existing lock
and complete kernel gates; independent session action capability; Origin/Host/JSON
checks; deliberate confirmation, notes and provenance; exact quote amount/scope
and upload consent without execution. No generic commands. Preserve vanilla UI.

No paid calls/uploads, real production decisions, style-test or individual pixel
verdict migration, legacy removal, global agent/MCP changes, releases or deployment.
No cap inflation; existing production artifacts remain untouched.

## Acceptance

- Stale, forged, foreign-origin and malformed confirmations cannot write.
- Verified decisions preserve kernel checks and exact content binding.
- Quote authority is the quoted admission amount, never a larger browser amount.
- Read-only sessions and normal CLI commands cannot decide.
- Explicit UI success/failure paths pass temporary-project unit/Chromium tests.
- Provider calls, generation and uploads are never triggered by decisions.
- Project checks, frozen independent review and verifier evidence recorded.

## Decisions and progress

- Architecture investigation: terminal-confirmed action capability, separate from
  the read token; fragment bootstrap into session storage and removal from URL.
  Same-OS/PTY/direct-module bypass limits documented, no human identity fabricated.
- Implemented: kernel expected-hash preconditions/provenance; typed service;
  HTTP guards; interactive serve mode; CLI redirects; stage and quote forms.
- Supporting lyrics/listening/brand decisions selectable; preview and graphics
  attestations explicit. Read-only legacy pages remain review aids.
- Initial frozen identity: `2b1bfd880c3dddc7fb5ce3725483f20e7d5b410662792f67d7b4fc3079a8ccf8`.
  Independent source review `ses_ea022e73bffeSpPdED7Eyr1FgB` found missing durable
  upload/playback attestations plus optional storage/error/coverage issues.
  Verifier `ses_ea022b517ffeweE1EjF8XoTdSm` was shell-blocked and could only
  inspect source; independent dynamic verification is not claimed.
- Initial full checks: 883 passed, one stale 120-line LOOP assertion failed;
  corrected it to use the existing approved `MAX_LOOP_LINES = 140` constant.
- Corrections: durable and kernel-checked review/upload/playback attestations;
  exact fractional-USD labels (0.0006 must not appear as 0.00); storage-blocked
  browser fallback; no absolute-path filesystem error; preserved corrupt/prior
  authority; provider/model clarity; no external-network route test; public CLI
  approve and authorize tests. Scratch artifacts now ignored.
- Second frozen identity: `0a703ab3e5dfe8240180c5258114e168787d9a2a873826f17b6521e486e213b5`.
  Full parent runtime checks: 892 passed, lint/format/eval green. Source re-review
  found no P1/P2; both lanes found the remaining action-POST filesystem path
  disclosure (now masked). Independent runtime remained shell-permission blocked.
- Advisor `ses_ea00648f5ffeqnf7UknhlDgF3z` reviewed attestation read semantics:
  fail closed on incomplete Studio-originated stage records, preserving legacy
  records. Implemented for review, preview-watch, graphics-inspection and flagged
  lyric acknowledgements; no existing production Studio records were present.
- Latest corrections also cover failed URL cleanup (discard capability and reload
  without fragment), blocked-storage decision submission, stale quote/upload
  browser failure, provider/model validation, incomplete-consent retry and
  legacy authority clarity. No production decision records were changed.
- Final decision-path snapshot `1d87e0927cd277faf579705639919efb76d9df3e379d471d90e59befb85872da`
  passed 901 full-suite tests, 23 Chromium cases included, lint/format/eval,
  JavaScript syntax and wheel/import smoke checks. Final source review found no
  P1/P2. Both independent lanes remained unable to execute or hash the index;
  runtime evidence and hash verification are parent-run, not independent passes.
- Last verifier residual: generated dashboard states were still hash-only and
  current generated commands still suggested the retired CLI decision path.
  Fixed by reusing the shared full-kernel approval-state projection, showing
  blocked reasons, and emitting `clip serve --actions` from current review aids.
  README now distinguishes default review-only mode from action sessions.
  Historical examples remain explicitly deprecated, not alternate authority.
- Latest affected checks: 115 passed (dashboard, studio, live, actions and
  Chromium); lint, format and eval passed. Added dashboard same-hash incomplete
  attestation regression and explicit legacy-preview compatibility coverage.
- Surface snapshot `2f279158793dfa26cc803c5b43d35d9cf6b0e10852620339bc40deb32695d21f`
  passed both scoped source closure reviews (runtime still blocked). Full suite
  then found a plan integration regression: 901 passed, approval action was not
  a blocker because `serve --actions` retained the command's read classification.
- Advisor `ses_e9ff56df2ffemoJC3KKQatQ7C5` diagnosed the wider stored-plan issue:
  human modes must be parsed from argv at proposal and again before execution,
  not inferred from a stored label or a literal option string. Added shared
  `tools.human_capability` using the actual CLI parser, including abbreviations;
  plan runner refuses action-mode startup and budget-cap authority even with
  forged nonhuman metadata. Normal read modes/help remain available.
- Plan correction focused evidence: 134 tests passed, lint/format/eval green.
  Includes generated approval blockers, never-spawn assertions for action/cap
  modes and abbreviations, parser errors and ordinary read/help preservation.
  Final re-freeze/review/checks follow. Ancillary signature/shot-edit hints still
  name retired CLI decisions; those redirect to Studio and cannot write.
- Snapshot `a296046691eafe838cc981b24b6c32f464bdaffde71c0151008ad6745938790b`
  passed 908 full-suite tests and source review. Static verifier identified a
  separator bypass candidate; parent confirmed the real parser accepts
  `clip -- serve --actions` / `clip -- budget ... --cap` while the helper skipped
  the tail. Advisor confirmed the one-line correction: gate on classified tool,
  then parse the complete unmodified tail including the leading separator.
  Added four never-spawn separator regressions and preserved separator read modes.
- Latest plan/live/studio checks: 64 passed, lint/format green. Last final freeze
  covers the separator fix; only result-record updates may follow verification.
- Final tested/reviewed snapshot:
  `a693155bd974ee9d4df99785c7f21bca4817698c0030aac8d206f0b9d9f844ca`
  (SHA-256 of the staged binary diff against `75f8c95`). Parent rechecked exact
  identity after completion; only this acceptance record and PLAN status change
  after the freeze. Implementation and tests remain byte-identical.

## Final evidence and acceptance (20:12 UTC)

- `uv run --with playwright pytest -q`: **912 passed**, 3 existing librosa
  warnings; includes **23 Chromium cases** on disposable productions.
- `uv run ruff check .`: passed.
- `uv run ruff format --check .`: passed, 120 files.
- `uv run clip eval`: all six structural invariants passed.
- `node --check`: integrated app, journal and changed dashboard scripts passed.
- `uv build --wheel --out-dir .opencode/scratch/human-wheel-ready`: passed;
  isolated wheel import/UI integration/parser smoke confirms both new modules
  are included and separator human modes stop while ordinary reads remain open.
- Review `ses_ea022e73bffeSpPdED7Eyr1FgB`: final scoped source closure complete,
  no P1/P2; all confirmed decision, display and plan-gate findings resolved.
- Verifier `ses_ea010e8d5ffe2Ngn4lxtXeVuxU`: confirmed final separator closure by
  source inspection. Independent runtime/hash verification remained blocked by
  shell permissions; this is not claimed as an independently executed pass.
- Acceptance: implementation and local runtime criteria met; independent source
  review complete, independent runtime unavailable. No production approvals,
  authorization records, uploads, provider calls, spend or deployment occurred.
- Status: complete locally, ready for user publication/CI/merge. Stop reason:
  authorized UI-decision scope completed. Legacy removal remains excluded.
- Next action (user-operated): publish this branch and run PR CI. In the user's
  own terminal, `uv run clip serve --actions` enables the reviewed decision UI;
  the agent must not enable or confirm real human actions.

## Known limitations / open questions

Internal Python APIs and another unrestricted same-UID process are not isolated.
Published provider prices/reservations are not enforceable provider-side caps.
No separate user accounts or identity claim. No outstanding product decision.
Independent dynamic verification could not run; local tests are parent-executed,
and Linux CI has not been run for this unpublished branch. A few ancillary
signature/shot-edit hints retain retired CLI syntax; those commands redirect to
Studio without recording a decision. Historical recipe migration is out of scope.
