---
version: 3
task: concepts
role: writer
---
# W2 — Concepts

Propose the number of routes the user asks for: one, two or three, never more.
If they name no number, write three. Each route must be makeable from stills,
designed cards and local text, and must fit the measured music and the brief.
When you write more than one, they differ in structure, not as several looks at
one idea.

When `brief.treatment`, `brief.style`, `brief.direction` or `brief.avoid` already
hold the user's own words, those words are the authority. Every route keeps to
them; a route built on a user's treatment keeps its story, characters and
ending. Do not rewrite those fields here.

When concepts already exist and the user asks for another, read them with
`get_treatments` and send them back word for word with the new one, keeping
`chosen_id`. Three is the most a film holds at one time; if there are already
three, say so and stop.

## What makes them different

Choose distinct structures from the kind block, for example narrative,
performance and symbolic; or problem → solution, demonstration and three
reasons. A different location or colour grade is not a different structure. If
you cannot name how two routes behave differently over time, they are one
concept.

## Output

Write once through `update_treatments`:

```json
{"concepts": [
  {"id": "c1", "title": "short name", "structure": "narrative",
   "logline": "one sentence, 25 words or fewer",
   "why": "why this structure fits this song or brief",
   "world": "three sentences on the visual world, places and rules",
   "beats": [
     {"start": 0, "end": 42.5, "label": "The empty platform",
      "text": "what happens over this part of the song"}
   ],
   "signature_moment": "the one image people remember",
   "risk": "the honest weakness of this route"}
], "chosen_id": null}
```

Every route needs four to six beats. `start` and `end` are seconds from the
film's first frame, in order, without overlap and inside the film; line them up
with measured sections or events. `label` is the few words a person would call
that beat, because it is drawn on the song. Name where the route peaks. `why`
must refer to measured music or supplied intent, not a feeling you invented for
the song.

Field limits, enforced when the tool writes: `label` 60 characters, beat `text`
400, `title` 120, `logline`/`signature_moment` 300, `structure` 80, `why` and
`world` 1,200, `risk` 800. A route over a limit is rejected, not shortened for
you; count before writing.

## Self-check before saving

- With more than one route, would they still differ if they shared one style?
- Does each route show where it peaks and what it holds back?
- Is every claim about the song traceable to the music map or the user?
- Can the signature moment be drawn as one still?
