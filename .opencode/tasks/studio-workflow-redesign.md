# Studio workflow redesign

## Objective and authority

User approved the conversation plan with “go” on 2026-10-24. Make the existing
Studio more professional, readable and aligned with the real creation workflow.
Implementation, local tests and normal repository publication are authorized.
No production-state changes, uploads, paid calls, new human decision authority,
framework replacement or automatic generation. Existing artifacts remain canonical.

## Execution

- Start: 2026-10-24 11:46 UTC; checkpoint/deadline: 13:16 UTC (90-minute ceiling).
- Branch: `feat/studio-workflow-redesign`; base: `cc83c7543bbe96ac6d281826149cef01584bbd2b`.
- Spend: zero.
- Owned surface: Studio shell/templates, read-only stage projections, human review
  presentation, focused tests and usage documentation.
- Ready order: shared styling/layout → workflow navigation and readable review
  screens → guided local setup → browser/accessibility/regression verification →
  independent diff review → corrections, commit and publication.

## Acceptance

- Compact searchable project navigation; current project work remains visible at
  phone/tablet widths rather than below the entire library.
- Workflow stages reflect real gate state; optional lyrics and reviewed rollout
  are explained, no invented completion percentage or automatic approvals.
- One prominent next requirement/action; technical commands/hashes secondary.
- Readable music/brief/board/stills/graphics/delivery review surfaces, with honest
  missing-media and read-only states. Human actions retain exact-content binding.
- Guided Track → Film settings → Budget/confirmation setup; valid back/next,
  inline recovery, no duplicate creation and no generation or spend on submit.
- Keyboard/focus, responsive 390/900/1280px, loading/empty/error/capability states
  tested; route reload/back/forward and existing decision-security tests preserved.
- `uv run pytest`, ruff check/format and browser regressions pass on the final
  revision; actual rendered desktop/phone samples inspected, limitations explicit.

## Status

Implemented: refined shared review styling, compact searchable library, responsive
project switcher, eight-step workflow rail, next-requirement overview, readable
music/brief/specification panels, scoped proof review, roomier storyboard, still
inspection, local preview/delivery guidance, readable human decision evidence and
budget/quote summaries. Native dialog implements the three-step local setup flow.
CLI now prints the main workspace link; the old journal URL still works.

The token-scoped workflow projection reads local JSON without locks or media reads.
Supporting lyrics/listening/brand decisions follow kernel dependencies. Graphics
specifications and actual composite-review evidence are kept separate. No new
decision endpoint, streaming endpoint, upload, spend or production mutation.

Verification in progress: initial full suite 912 passed / 1 skipped (Playwright is
run separately); 36 real Chromium cases pass, including old human/capability and
new workflow/setup/error/responsive checks. Final focused review/transport/browser
batch: 117 passed. Scoped read-only/transport tests pass.
Ruff check/format clean. Four actual desktop/phone screenshots inspected locally;
inspection led to putting the next action ahead of statistics on phones and widening
workflow cells to prevent text collision. Final re-verification and independent
source re-review completed below. Test-data-only correction: wait for the new route heading,
not a prior route's aria-busy=false; use Playwright's focus expectation API.

Independent source review at staged diff `1a3cc46cd2d54ca73901340f86e3cb9da6a9984d140813374791f343ed96e1be`
found three P2 defects and no P1: latest movie was not necessarily the review-bound
preview; character identities were read from the wrong brief field; and canonical
`estimated_tempo_bpm` was absent from readable measurement evidence. Corrected all
three with regressions for newer-unbound/missing previews, exact movie names in
human confirmation, canonical identities/wardrobe states, and canonical tempo.
The new preview projection reads metadata/stats only; exact validity remains the
existing gate's job. The human-character test initially lacked the fixture's
depiction permission; the gate correctly refused it, and test data was corrected.
Reviewer session: `ses_e922c9d1cffe5hatredhy1hWp5`; same reviewer verified all three
resolved at staged diff `f3a9ef3c540f6f02d66f14e90667c193871148114bf336c1a5b0b47eba28e307`,
with no new confirmed P1/P2. Independent verification used read-only Node/Python
checks, not an independent Chromium/full-suite or pixel pass. Parent retains
responsibility for all runtime/browser/pixel acceptance.

## Evidence / handoff

Pending final content identity, final checks, independent findings and publication.
Preview/composite playback remains local-player work; no playback or pixel review
of any production film is claimed. No production media or approval record changed.
