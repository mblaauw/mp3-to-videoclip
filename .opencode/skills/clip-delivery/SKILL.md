---
name: clip-delivery
description: Stage 9 of an MP3-to-videoclip production. Render and verify the approved film, confirm byte-bound approvals and intact audio, archive the production, and report what was measured, inspected, verified and still uncertain. Use for final export, ffprobe verification, backup and delivery reports.
---

# Stage 9 — Delivery

**Job:** hand over a versioned, verified film plus an honest report.
**Position:** last stage, only after every upstream gate. Links:
`../clip-music-director/SKILL.md`,
`../clip-music-director/references/production-gates.md`,
`../../../docs/PRODUCTION_WORKFLOW_V2.md`. Code: `render.py` (ffprobe),
`preview.py`, `backup.py`, `branding.py`, `production.py` (`status`).

## Inputs

- Approved still set and edit; approved preview (pacing on the real music);
  `clip review` records for every selected version; `clip costs` reconciled.

## Do

1. Confirm the gate chain before rendering:
   - brief, storyboard, proof and stills approvals exist and are **content-bound**
     to the bytes actually used;
   - every selected version has an inspected `clip review` verdict;
   - no changed artifact silently invalidated a later approval.
2. Render the approved full still set to a versioned MP4 (`clip render`). Never
   overwrite a prior export.
3. Deliver the **composited final**, never the bare base render: the 25 s opening
   overlay and the 40 s credit package must be present inside the music with the
   factual roles supplied at intake (`clip-edit-graphics`). Record the hash of the
   **base** and of the **final composite separately**, plus the hashes of the
   actual sample frames inspected — base and final are different artifacts.
4. **Verify with ffprobe:** frame count, fps, duration, dimensions, streams and
   audio integrity. Confirm the original audio is present packet-for-packet (no
   delay, truncation, stretch, added sting or normalisation). Inspect sample
   frames and the contact sheet. A clean ffprobe report is **technical**
   verification, not creative acceptance, and a container audio transcode (for
   example AAC) is **not** proof of MP3 packet identity — state which was actually
   compared.
5. `clip backup` — private local archive excluding rebuildable caches.
6. `clip status` — record the final state and any remaining uncertainty.

## Report (separate the evidence classes)

State plainly:

- what local tooling **measured**;
- what a provider model **reported** (billed/evidenced, unreviewed);
- what a human or bounded session **actually inspected** (with coverage);
- whether the timed preview and the final film were actually **watched/heard**,
  or a delegated proxy reporting its explicit limits — never claim a watch or
  listen that did not happen;
- what was **technically verified** (ffprobe, graphics preflight, base vs final
  composite and sample-frame hashes);
- what remains **uncertain**;
- what **awaits the user's decision** (e.g. credits roles, distribution).

## Boundaries

- A valid FFmpeg report does not certify professional artistry — never present it
  as artistic approval.
- Never claim mocked tests or a green render prove real image quality, likeness
  or provider behaviour.
- Preserve the entire original audio; long overlays must fit inside it. Record
  the production is an unaffiliated homage when an artist-inspired style was used.
- No new paid work (upscale, alternatives, AI lettering, motion) happens here
  without its own explicit authorized scope.
