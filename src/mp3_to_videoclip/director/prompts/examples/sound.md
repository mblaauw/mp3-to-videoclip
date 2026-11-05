---
version: 1
example: sound
---
## Worked example

A 2:00 story film: a curator in 2300 explains a house key. Five beats, one room.

```json
{"cues": [
  {"id": "bed", "kind": "music", "prompt": "Sparse instrumental score, felt piano and a low sustained string pad, slow, no drums, room for a voice, warm and a little wry.",
   "start": {"frame": 0}, "end": {"frame": -1}, "why": "A floor under 140 s of narration, so pauses are not silence."},
  {"id": "room-hall", "kind": "ambience", "prompt": "The hush of a large museum hall: distant footsteps on stone, a faint ventilation hum, no voices.",
   "start": {"line": "l001"}, "end": {"line": "l014"}, "why": "One room from the hook to the reveal; its air must not change."},
  {"id": "key-turn", "kind": "effect", "prompt": "An old metal key turning in a heavy lock, one clean click, close and dry.",
   "start": {"line": "l015"}, "end": {"line": "l015"}, "gain_db": -4, "why": "The reveal is the key; the sound is its full stop."}
]}
```

What the film sounds like: a hall and a felt piano, and one click. Least sure:
whether the click should come a beat before the line or on it.
