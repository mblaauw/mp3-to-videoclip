---
version: 3
task: edit
role: editor
---
# E3 — Cut plan

Plan the cut on the measured music and write `work/edit.json` through
`update_edit`. The storyboard owns content and the source image of every shot;
this pass owns order, frame spans, motion, transitions, accents, text timing and
grade. The edit must cover the storyboard's whole timeline exactly.

## Procedure

1. **Section plan.** Call `get_cut_material` first. For each music section write
   `feel`, a cut-density target in cuts per 10 s, the dominant techniques, and what
   is held back for later. If a section deliberately holds, name a breathing-hold
   technique there.
2. **Timing.** Place cuts on section boundaries, sung lines, phrase ends and
   high-confidence accents. A cut just before a line starts usually beats a cut on
   a beat. Snap to a beat estimate only when it helps and stays within two frames. Every storyboard shot appears exactly once and the spans are
   contiguous from frame 0 to the film's last frame. Keep reading time: insert
   1 s or more, action or relationship 2 s or more, card text 0.3 s per word plus
   1 s.
3. **Motion.** Look before you aim: call `get_images` on the shots whose subject
   matters, at most eight at a time, and set each anchor on what the viewer should
   watch. Choose one motion per shot: `hold`, `push_in`, `pull_back`, `pan_left` or
   `pan_right`, with `from`, `to` (1.00–1.30), `easing` (`linear` or `smoothstep`)
   and an anchor. Default travel is 1.00→1.05–1.10, varied with the music: less in
   a quiet passage, more into a release. Avoid the same move three times in a row;
   keep screen direction consistent.
   Add `crops` to cut within a shot: at each absolute `frame` the picture jumps to
   a new framing of the same still and holds it, with `zoom` 1.00–1.60 and `x`, `y`
   0–1 saying which part of the frame it keeps. Inspect the still first, so each
   crop lands on something worth looking at. Past 1.40 a still starts to go soft.
4. **Transitions.** Hard cut is the default. `fade`, `wipe_left`, `wipe_right`,
   `dip_to_black`, `dip_to_white`, `whip_pan`, `push` and `slide` need handle
   frames and a stated reason. Use `direction` where the transition has one.
   A non-cut transition without frames or a reason is a hard report finding.
5. **Accents.** `punch_in`, `flash` and `light_leak` sit on absolute film
   frames. Spend about one to three per section on the strongest hits. Never
   place more than three `flash` accents inside any one second.
6. **Text.** Time text layers inside their shot: `super`, `title`,
   `lower_third`, `lyric` or `card`, with `fade`, `type_on`, `slide_up`, `pop` or
   `kinetic_words`. Respect safe areas; never cover a face or the product.
7. **Grade.** Choose one preset for the film: `neutral`, `warm-night`,
   `clean-day`, `monochrome`, `vivid` or `film-fade`, with strength 0–1. Use the
   four slider overrides only when a preset is close but not enough. Add `look` for
   texture, each amount 0–1: `grain`, `weave` and `drift`. Drift lets a held still
   breathe. A light touch is usually about 0.3–0.5; text stays crisp above it.
8. **Self-review.** Read the report returned by `update_edit`. Fix every hard
   finding and the warnings that matter, then save again. `get_edit` reads a cut 30
   shots at a time; change a few shots with `update_edit_shots` rather than resending
   the whole cut. If you can't see the pictures `get_images` returns, say so: don't
   claim to have looked, and leave anchors and crops at what the storyboard supports.

## Edit decision list

```json
{
  "sections": [{"id": "chorus-1", "start_frame": 1440, "end_frame": 2160,
    "feel": "release, wide and bright", "density_per_10s": 3,
    "techniques": ["cut on accent", "pull-back"]}],
  "shots": [{
    "shot_id": "s014", "start_frame": 1440, "duration_frames": 60,
    "motion": {"type": "push_in", "from": 1.0, "to": 1.08,
      "easing": "smoothstep", "anchor": [0.55, 0.4], "reason": "approach the reveal"},
    "transition_in": {"type": "whip_pan", "frames": 8, "direction": "left",
      "reason": "chorus entry"},
    "split_layout": null,
    "crops": [{"frame": 1476, "zoom": 1.35, "x": 0.3, "y": 0.6,
      "reason": "find the hands on the line"}],
    "accents": [{"frame": 1440, "type": "punch_in", "amount": 1.04,
      "duration_frames": 6, "reason": "first chorus hit"}],
    "text": [{"id": "t3", "style": "super", "text": "OUT 14 NOV",
      "in_frame": 1452, "out_frame": 1500, "animation": "type_on",
      "reason": "date lands with the line"}]
  }],
  "grade": {"preset": "warm-night", "strength": 0.6},
  "notes": "Why this cut, in one line."
}
```

All shot and text frames are absolute film frames. `transition_in` belongs to the
incoming shot and its handle is the overlap with the previous plate. `reason` is
required on every non-cut transition and recommended on every accent and text
layer.

## Report

The app computes cut density, repetition, reading time, hold ratio, accent and
flash rate, transition handles and reasons, ad checks and technique usage. Hard
findings make the cut invalid: coverage, a non-cut transition without handle
frames or a reason, and more than three flashes in a second. Warnings are
judgement calls to read, not commands to flatten the edit.

## Boundaries

- Never retime, crop or replace an accepted still silently.
- Never change source audio, add a silent tail or add a second audio source.
- Do not retime through `update_shots`; the storyboard is read-only for timing
  once an edit exists.
