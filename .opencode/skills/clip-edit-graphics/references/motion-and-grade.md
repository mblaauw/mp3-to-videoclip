# Motion, transitions and grade

Detail for the `post-editor` and the `film-finisher`. The one-page rules stay in
`SKILL.md`; this file is the reasoning and the numbers.

## Why this exists

A still film is judged on movement as much as on images. The first production of
this pipeline shipped 51 shots of which **37 were pure holds**, only **one** had a
dissolve (12 frames) and **nine** had `camera_path` pairs whose start and end zoom
were identical — a path that renders as a freeze. The renderer already supported
per-shot `dissolve_frames` compiled to `xfade` and start/end `camera_path`
interpolation. The capability was there and unused.

So: check what the board is actually doing before adding any new mechanism.

**A deliberate hold is not the defect.** The failure above was a move declared and
not delivered (identical start/end zoom), not a count of holds. Movement is chosen
per shot purpose, and holding a strong still on a musical phrase stays valid. The
blanket "nearly every shot is a hold, therefore slideshow" reading is retired; the
`remotion-motion.md` model replaces it. Remotion is the primary renderer for new
productions; the scales and evidence rules below still apply.

## Camera travel

- One motion per shot. A slow push-in builds attention; a pull-back releases it.
- Keep travel modest — roughly **1.00 → 1.05 … 1.10** on a normal shot. Larger
  ratios are for deliberate detail crops that were framed for it.
- Use `smoothstep` easing for anything with a couple of seconds to run; linear
  reads mechanical. Very short inserts are the exception.
- `camera_path` fully determines the rendered motion when it is present, and
  ``camera`` is then descriptive metadata — keep the label consistent with the
  direction anyway so the board does not lie.
- **Never retune a reviewed crop.** A contained defect-repair crop (one whose zoom
  exists to exclude something) and an accepted reprise crop keep their accepted
  bytes. Changing the zoom, even upward, invalidates a review that was made on
  actual rendered samples, and buys almost nothing on a 1.5–5 s reprise. Freeze
  them and record why.

## Dissolves

- Put them where the film *joins*: a section boundary, a time or place shift, an
  emotional drop, a handover.
- `dissolve_frames` is declared on the **outgoing** shot and must be shorter than
  **both** adjacent shots, or the board is rejected.
- Useful scale: 12 frames (0.5 s) for a light join, 18 (0.75 s) for a section
  boundary, 24 (1.0 s) for a real emotional transition.
- The renderer carries the dissolve as *handle* frames and consumes them, so the
  delivered film still covers the exact frame count. A dissolve never shortens
  the timeline and never shifts a later cut.
- Do not dissolve inside one continuous action; that is what a hard cut is for.

## Movement and the beat

There is no beat-synchronous motion primitive. You cannot pulse a shot per beat
without adding one, so do not claim it:

- Use the measured pulse to choose dissolve *scale* and to decide which joins
  dissolve at all.
- Never retime a cut to a beat, and never assert a meter.
- A pulse estimate carries a half/double ambiguity that must stay visible. On one
  real track, two independent local methods agreed on 161.5 BPM while the rival
  octave reached 0.98 of the primary peak, and the supplied style intent claimed
  90 BPM — matching neither. Measurement and intent are different evidence
  classes, and the metrical level stayed unresolved rather than guessed.
- Cut boundaries that already sit on measured spectral changes will feel musical
  without any beat logic.

## Judge motion on pixels, not prose

A transition is real only when decoded frames change. Practical evidence:

- Sample several frames **inside** one shot and compute the mean absolute frame
  difference. A travelling shot should differ clearly; a frozen one should be
  ~0.00. Comparing against a previous static render makes the claim falsifiable.
- Sample **across** a boundary: a dissolve's mid-frame differs from *both*
  neighbours; a hard cut jumps. A control cut elsewhere in the film gives the
  scale to compare against.
- A contact sheet, a still, or a clean `ffprobe` report **cannot** show that
  motion exists. Only frame comparison can.

## Grade

- Opt-in, local, versioned, and never automatic.
- Never normalise, re-encode, stretch or replace the original audio.
- Never present a look change as a technical fix, and never let a grade hide a
  compositing defect.
- A grade is a new reviewed version, not an edit to an approved render.

## Division of labour

`post-editor` designs movement and drafts the plan; `film-finisher` executes it
and verifies the measured result; `film-director` integrates it into canonical
state and owns approvals. The planner never renders the delivery, and the executor
never invents a transition language.
