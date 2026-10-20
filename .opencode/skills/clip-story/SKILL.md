---
name: clip-story
description: Stage 2 of an MP3-to-videoclip production. Propose 2-3 treatment directions and fill the causal story into the existing brief (treatment, creative.arc) for user approval. Use for treatments, narrative spine, central question, protagonist or process arcs, symbolic/abstract directions. Does not create new formal stages or schemas.
---

# Stage 2 — Story

**Job:** turn reviewed music plus intent into **2–3 treatment directions** (or the
user's requested count), then record the chosen sequence arc, causality if narrative, in the
existing brief. **Position:** after stage 1, before storyboard. Links:
`../clip-music-director/SKILL.md`, `../clip-music-director/references/production-gates.md`,
`../../../AGENTS.md`, `../../../docs/CREATIVE_WORKFLOW.md`. Template:
`references/treatment-template.md`. Code: `src/mp3_to_videoclip/models.py`
(`Brief.treatment`, `Brief.creative`), `production.py`.

## Inputs

- Approved music map/events from stage 1; the user's supplied style/lyric intent
  (as context, not evidence).
- Any explicit constraints (adults-only if requested, no real-person imitation,
  branding, delegation of creative decisions).
- Early music-editor/post-editor sequence input; shared contract:
  `../clip-music-director/references/music-first-direction.md`.

## Do

1. Read `references/treatment-template.md`; draft the requested concept directions.
   Match reviewed music, or label pre-review explorations provisional intent-only.
2. Review them with the user. Their selection is the treatment; never record your
   own preference as approved. Narrative is optional; never invent a hero or plot.
3. Write `brief.treatment` and `creative.arc` (reuse the existing fields) and put
   look/palette/light/texture in `creative.look` only.
4. Develop the look/continuity with `clip-art-direction`, then present the
   complete brief for explicit approval. Do not approve story and then silently
   change its art-direction inputs.
5. Put the sequence treatment in the existing brief: passage evidence, visual
   experience, scale/cuts/holds/panels/text, contrast and what is saved for later.

## The visual short story (narrative films)

For a narrative direction, the treatment is an actual **short story told in
pictures**, 250–400 words of visual prose — not a premise followed by a shot
list. It must show:

- a **goal** the film's movement is toward, and the **conflict** resisting it;
- **visible actions** rather than stated feelings or voiceover;
- a **choice** at the turning point and its **cost**;
- **escalation** — each beat raises pressure, information or stakes;
- an **earned ending** that the earlier beats make necessary, without a caption
  explaining it.

Write one central thread and critique its weakest causal link before any picture
is bought. When the user's intent is high-energy, open **active** (movement,
pressure or an event already underway) rather than with a slow establishing
inventory. Never invent genre, meter, tempo, language or emotional meaning; take
those only from reviewed evidence and the user's supplied intent. Symbolic,
process and abstract directions are equally valid and use evolving visual
relationships instead of a conventional protagonist.

A **beat sheet is not an edit list.** Beats are causal story units; a beat may
need several stills, one hold, or a reaction shot. Do not map one beat to one
image and do not derive the story from the shot count.

## The causal spine (required for a narrative direction)

State, in plain language:

- **Central question** — what the film asks (may be answered or left open).
- **Goal or process** — what the protagonist wants, or the process the film
  follows. A **process film is valid**; a protagonist is not mandatory.
- **Obstacle** — the specific resistance, pressure or friction.
- **Choice and cost** — the decision at the turning point and what it costs.
- **Turn** — the point where the direction of the film changes.
- **Payoff** — what the ending earns, honestly. No unearned resolution.

Keep it a **short-film spine**: one central thread, a small number of locations,
a visible change from first frame to last. Do not teleport to a new city/style
at every musical change.

## Feedback lane (one bounded revision)

Before acceptance, `visual-critic` reviews the chosen mode (causality only for
narrative) and `music-editor` reviews music binding, independently. Their
findings return to the **writer**, who makes **one** bounded revision and names
what changed; the director then accepts it or records an explicit blocker. A
text review is not a new gate and never replaces the user's brief approval. This
lane is two read-only checks, not a committee: see `references/story-feedback.md`.

## Boundaries

- **No new formal stages or schema.** Treatments live in the existing brief
  approval; `brief.treatment` is editable planning text, not a new artifact.
- **Not forced humans/genre/hero formula.** Symbolic and abstract directions are
  valid and should be offered where the music supports them. A narrative without
  a protagonist is valid. Do not invent lyrics, genre, language or emotional
  meaning to justify a direction.
- Approval is the user's; an agent may not approve on their behalf.
  Under explicit delegation, label it **agent-reviewed under delegation**.
- No paid work happens in this stage.
