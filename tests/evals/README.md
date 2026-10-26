# T3 eval inputs

Three frozen inputs for the Writer prompt suite:

- `energetic-vocal.json` — 180 s vocal music video.
- `slow-instrumental.json` — 240 s instrumental music video.
- `advert-30s.json` — 30 s advert over the 62–92 s excerpt, with allowed facts.

`checks.py` validates artifact shapes without a model: three distinct concept
structures, a contiguous board with at least two non-scene kinds for the advert,
and dates/URLs/prices that do not appear in the intent. `materialize_stills`
draws deterministic gradient stand-ins so a run needs no Runware spend.

The live Writer pass is **manual and not part of CI**. It needs the owner's
explicit spending authorization and a writable copy of a production; do not
point it at `projects/`. No live pass was made while building T3.
