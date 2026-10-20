---
name: clip-visual-review
description: Stage 7 of an MP3-to-videoclip production. Inspect every generated image once, record version-bound accept/reject/uncertain verdicts, and contain repairs before whole-frame rolls. Use for proof/full-set review, severity calibration and coverage reporting. Never reports uninspected images as reviewed.
---

# Stage 7 — Visual review

**Job:** judge actual pixels, record durable verdicts, and keep repairs contained.
**Position:** after generation, before the full-set approval; the same read-only
role also runs **story** and **board** modes on those drafts. Links:
`references/critic-modes.md` (the three modes, report shape, honesty),
`../clip-music-director/SKILL.md`,
`../clip-music-director/references/production-gates.md`,
`../clip-music-director/references/shot-review.md` (the rubric), Code:
`reviews.py`, `timeline.py`, `budget.py` (`restage`), `references.py`.

## Inputs

- Generated image versions with hashes, the compiled prompt, and the relevant
  approved identity reference in the same review pack.
- The intact user-approved style benchmark from `default-style.md`, counted in
  the image budget. Compare rendering, not its rooftop/content/cover design.
- `clip sheet PROJECT --scope stills` contact sheet as a review aid (not an
  approval).

## Do — mandatory coverage

1. **One quick actual inspection of every image.** No sampling, no skipping, no
    claiming coverage you did not see. Record coverage per filename explicitly.
   Check photographic-painted fidelity against the approved benchmark: believable
   anatomy/volume and exposure, visible material/skin craft at the intended scale,
   brush-rendered detail, deep blacks and selective hard highlights. Flat outlined
   or softened generic-comic output fails the style even if cast and palette match.
   Do not excuse that failure as accepted small/distant-detail stylisation. Wide
   shots need not show close-up pores, and new subjects need not copy the rooftop.
2. Spend **deep review only** on an obvious or load-bearing issue (wrong lead,
   required content missing, identity/anatomy the shot depends on). Do not run
   cosmetic loops or relitigate accepted stylisation.
3. Calibrate severity on existing accepted/rejected examples. **Accept** stylised
   or occluded small details — distant simplified digits, a stylised paw pad —
   unless the approved shot genuinely needs them. Do not impose toe counts or
   readable distant fingers.
4. Bounded fresh sessions: **at most 15 image occurrences**, practically 6–8,
   including identity references, detail crops and re-reads, with headroom kept
   below the ceiling. Inventory and deduplicate first. Return **text-only**
   coverage — never forward images into the coordinating session. A failed or
   timed-out reviewer is unavailable evidence, not a PASS; no mandatory re-reads
   and no per-frame review divisions, but coverage stays complete.
5. Record the verdict, bound to exact bytes:

```sh
uv run clip select PROJECT --shot s003 --version 2
uv run clip review PROJECT --shot s003 --version 2 --verdict accept \
  --reviewer 'actual reviewer' --inspected \
  --note 'gap and identity hold; distant paw simplified, acceptable for this shot'
```

`accept` / `reject` / `uncertain` follow `shot-review.md`. Uncertain asks for one
targeted crop — it is not a disguised reject or acceptance.

## Repair discipline

- Keep the original plus **one** correction by default. Do not roll a second
  silent correction.
- After that, **diagnose and restage** explicitly:

```sh
uv run clip restage PROJECT --shots s003 \
  --note 'Diagnosis: interlocked hands fail; restage separated with a gap'
```

- Prefer containment: a crop/composite for a small isolated defect, a reprise of
  an accepted panel for a repeated composition, a restaged framing for a wrong
  composition. Never replace a good whole frame to fix one finger.
- **Repairs land before any whole-frame batch roll or export**, and no repair is
  assumed free/billed — a correction consumes the running count and any masked
  edit/alternative needs its own authorized quote.
- **A first generated or calibration image is a candidate, not the new golden
  reference**; earlier film/Takeover reference sets are history. Only the user's
  own inspection promotes a style candidate — never auto-accept the first result.
- **A style/quality failure is a stop, not a roll loop.** When output fails on
  style or quality rather than a small fixable defect, stop, state the failure
  and diagnose the cause instead of spending on repeated rolls.
- A delegated proxy (agent or bounded session) is labelled **agent-reviewed under
  delegation** and reports its explicit limits — what it did and did not see. It
  is never presented as the user's own inspection.

## Exit gate

Every selected version is inspected and recorded; uncertain/rejected versions do
not pass; the user approves proof/stills. Stop repeated confirmation with a
single model — it is not independent evidence.
