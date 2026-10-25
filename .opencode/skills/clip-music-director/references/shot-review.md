# Shot and sequence review

For each reviewed filename/shot ID, return text-only findings:

Include exact source owner, version, image SHA256, frame interval and planned
overlay IDs. Use `clip locate`/graphics preflight labels, not a remembered shot
number. Supply the approved identity reference in the same pack when judging
likeness. Current selection metadata is not proof of which version was encoded
in an older movie; check that movie's render report.

1. Purpose / required visible elements: delivered, partial, or missing?
2. Intended framing versus actual framing; is the focal point clear?
3. Character/wardrobe/prop identity against approved references.
4. Spatial/anatomical plausibility, accidental collage, lettering and artifacts.
5. Musical interval and narrative function: why this image here?
6. Planned crop: sufficient native detail and safe frame throughout the move?
7. Adjacent shots: useful contrast or accidental repetition? Screen direction,
   shape and light continuity? Does a repeated motif gain meaning?

For the timed edit, judge the real rendered opening, readable identity, first
musical entrance, sustained attention, breakdown/re-entry, visual peak and ending.
Watch the actual timing; a contact sheet alone cannot validate pacing or sync.
Record coverage and uncertainty. Do not report uninspected images as reviewed.
Follow the global image budget: inventory/deduplicate and at most 15 image
occurrences per fresh session INCLUDING identity refs, re-reads and crops —
practically 6–8 per pack — and fewer if the route's limit is lower. The ceiling
is cumulative over the session's whole history, so plan the count before the
first read and open a new session rather than adding a late round; a blocked
session is spent, not retryable in place. Coverage is complete, "unavailable" is
not a pass, and re-reads or per-frame divisions are never mandatory. Return
coverage text only, never forward images.

## Fixed dispositions (workflow 2)

- **reject:** obvious extra/fused limbs, wrong load-bearing content, wrong lead,
  materially broken identity or distracting unapproved text. Cite the visible
  evidence and smallest repair; do not order a whole-frame reroll by default.
- **uncertain:** cannot resolve at this scale or needs reference comparison.
  Ask for one targeted detail crop. This is not a disguised reject or acceptance.
- **accept:** satisfies the intended beat/identity. State tolerable stylistic
  simplification/occlusion or minor deviation explicitly in the review note.

Do not require visible paw pads, exact toe counts or readable fingers on distant
dancers unless the approved shot depends on that detail. Palette alone does not
prove continuity. Do not relabel uncertain art as reviewed to pass a gate.

Calibrate reviewers before the next paid production: pick a small explicit set
of existing accepted/rejected examples plus their identity reference; deduplicate
and split into fresh bounded packs. Apply this same rubric, compare disagreements
with the user/delegated director, and record reason/coverage. Do not regenerate
the calibration set. Agreement between repeated sessions on the same model is
not independent evidence. Do not launch a reviewer for every individual frame.

Record actual judgements with `clip review ... --verdict accept|reject|uncertain
--inspected --reviewer NAME --note REASON`. Software binds this claim to exact
version/input/image bytes; it cannot prove the reviewer saw them. Never approve
proof/stills until the corrected selected versions have been inspected.
