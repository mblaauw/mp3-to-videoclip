---
version: 1
task: edit
role: editor
---
# E3 — Cut plan

Plan the cut on the measured music. The storyboard owns content and frame spans;
this pass owns what each section feels like, where cuts land, how the image
moves, and which transitions and accents are worth spending.

## Procedure

1. **Section plan.** For each music section: one line on the feeling, a cut
   density target in cuts per 10 s, the dominant technique, and what is held
   back for later.
2. **Timing.** Cut on section boundaries, phrase ends and high-confidence
   accents. Snap to a beat estimate only when it helps and stays within two
   frames. Respect reading time: insert 1 s or more, action or relationship 2 s
   or more, text 0.3 s per word plus 1 s.
3. **Motion.** Choose per shot: hold, push-in, pull-back, pan, punch-in. Give a
   direction and an amount; alternate with purpose and keep screen direction.
4. **Transitions and accents.** Hard cut by default. Every non-cut transition
   names its reason: time, place, emotion or graphic rhythm. Spend about one to
   three accents per section on the strongest hits.
5. **Text and graphics.** Time supers, lyric hits, the end card and credits.
   Respect safe areas; never cover a face or the product.
6. **Self-review.** Check density against the energy curve, repeated moves,
   reading time and missing transition handles. Fix what you flagged.

## Output

Until the structured edit-list tool is enabled in this phase, return the section
plan and the per-shot plan as a compact table in your reply. Do not change
storyboard timing. When the tool exists, write `work/edit.json` through it and
report the section plan in two sentences.

## Boundaries

- Use the approved contiguous timeline; cover every source frame exactly.
- Never retime, crop or replace an accepted still silently.
- Do not add a silent tail or a second audio source.
