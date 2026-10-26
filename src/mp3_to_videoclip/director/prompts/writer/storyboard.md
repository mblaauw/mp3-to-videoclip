---
version: 1
task: storyboard
role: writer
---
# W4 — Storyboard

Turn the script and the measured music into shots. A shot is a job, a change and
a decisive image, not a duration to fill. Every shot owns an exact frame span.

## Per-shot contract

For each shot give: `id`, `start_frame`, `duration_frames`, `kind`, `purpose`
(the job), `message` (the one thing it communicates), `framing`, `must_show`,
and the change from the previous shot. Add `character_ids`, `scene_id`,
`reference_ids` and `event_ids` only when the shot truly uses them. Add `text`
only for words that appear on screen. Give the editor an intended feel in
`motion_prompt`.

Choose the kind from the table. Only `scene` and generated `product`/`bridge`
shots cost money; the rest are designed or reused locally:

| Kind | Use it for | Paid |
| --- | --- | --- |
| `scene` | story, place, performance | yes |
| `product` | product hero, packshot, in use | yes, or local when `asset` is supplied |
| `bridge` | a match cut or message carrying one idea into the next | only `bridge.mode: generated` |
| `card` | a statement, offer, chapter title or lyric hit | no |
| `split` | comparison or simultaneity in two or three panes | no |
| `reprise` | a new crop of an existing still | no |
| `upload` | a user-owned photo, venue or logo art | no |
| `logo`, `end_card` | lockup, CTA close, legal line | no |

A `bridge` carries `{"mode": "generated"|"designed", "match": {"type":
"shape"|"colour"|"position", "anchor": [0.5, 0.45], "note": "round lamp →
round label"}}`. Compose both neighbouring prompts so the matched shape sits at
that anchor. A `split` carries two or three `panes`, each a `shot_id` and crop.
An `upload` carries a project-relative `asset`. A `product` carries
`product_ref` (a reference ID or a project-relative product image) unless it
uses an uploaded `asset`.

## Timing and coverage

Grow shots from story beats, not from a target count. Cover every frame exactly
and keep IDs stable. Vary scale: a detail, a medium, a wide and a close-up should
each do different work. Give each music section its own visual idea. Reuse a
strong still as a `reprise` instead of buying another image. Text cards read at
about 0.3 s per word plus one second and stay at seven words or fewer. A split
or card is a shot in its own right, not a free overlay.

## Output

Use `update_shots` with one change per shot. It validates the whole board,
rejects unknown fields and writes atomically. Build from the timing skeleton if
one exists; never renumber existing IDs.

## Self-check before saving

- Does every shot change information, scale, place, time, light, relationship or
  meaning? Merge the ones that do not.
- Do neighbours avoid the same framing and subject unless the repetition is the
  point?
- Is there at least one designed or reused shot where the kind allows it, so the
  film is not wall-to-wall generated stills?
- Does every text card say only what the user supplied?
- If a proof shot became local, re-pick paid proof shots with `set_proof_shots`;
  a card or end card can never be an accepted-image proof.
