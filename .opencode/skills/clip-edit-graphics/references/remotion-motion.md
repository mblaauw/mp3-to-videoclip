# Remotion movement model (new productions)

Detail for the `post-editor`. The renderer split stays one-line in `SKILL.md`;
this file is what movement is, who designs it and what is forbidden.

## Renderer split

- **Remotion** is the primary visual renderer for v004 and new productions: it
  composes the frame stream, keyframes, transitions and effects locally.
- **FFmpeg** remains the encoder, audio muxer, prober and the legacy renderer for
  existing productions. Older projects migrate only by explicit opt-in; nothing
  is rewritten automatically.
- Remotion is a **project-local Node dependency**, not a new MCP server and not a
  new skill. The renderer installation and the Python render adapter are owned by
  the renderer work, not by the crew skills.

## Movement is chosen per purpose

Movement exists to serve a shot's job, so design it shot by shot:

- a slow push or pull for attention, a pull-back to release it, a lateral travel
  for a reveal, a hold when the still and the music already carry the shot;
- one movement per shot, smoothstep-eased, modest scale (~1.00 → 1.05–1.10)
  unless a detail crop was framed for more;
- transitions where the film **joins** — section boundary, time/place shift,
  emotional drop — and a hard cut inside continuous action.

**A deliberate hold is a valid, valuable choice.** There is no rule that a board of
holds is a slideshow: the historical defect was a `camera_path` whose start and end
zoom were identical, which renders as a frozen frame while claiming a move. Fix
that mismatch; do not fill every shot with motion for its own sake.

## Forbidden by default

- No automatic glitches, flashes, strobes or per-beat cuts.
- No effects for their own sake, and no effect that hides a compositing defect.
- No AI character animation, no generated motion of people/animals, no paid call.
- Never retime a cut to a beat and never assert a meter.

## Evidence and handover

Transitions consume handle frames, so the delivered film still covers the exact
frame count. Judge movement on **decoded frames** — several samples inside a shot
and across a boundary — not on prose or a still. The `post-editor` drafts the plan,
the `film-finisher` executes and verifies it, and the `film-director` integrates
it into canonical state and owns approval.
