---
version: 1
task: concepts
role: writer
---
# W2 — Three concepts

Propose three genuinely different routes for the film. Different structure, not
three looks at one idea. Each route must be makeable from stills, designed
cards and local text, and must fit the measured music and the brief.

## What makes them different

Choose three distinct structures from the kind block, for example narrative,
performance and symbolic; or problem → solution, demonstration and three
reasons. A different location or colour grade is not a different structure. If
you cannot name how the three routes behave differently over time, they are one
concept.

## Output

Write once through `update_treatments`:

```json
{"concepts": [
  {"id": "c1", "title": "short name", "structure": "narrative",
   "logline": "one sentence, 25 words or fewer",
   "why": "why this structure fits this song or brief",
   "world": "three sentences on the visual world, places and rules",
   "shape": ["beat 1", "beat 2", "beat 3", "beat 4"],
   "signature_moment": "the one image people remember",
   "risk": "the honest weakness of this route"}
], "chosen_id": null}
```

Every route needs four to six shape beats, each tied to a song section or a
second range. Name where the route peaks. `why` must refer to measured music or
supplied intent, not a feeling you invented for the song.

## Self-check before saving

- Would the three routes still be different if they shared the same style?
- Does each route show where it peaks and what it holds back?
- Is every claim about the song traceable to the music map or the user?
- Can the signature moment be drawn as one still?
