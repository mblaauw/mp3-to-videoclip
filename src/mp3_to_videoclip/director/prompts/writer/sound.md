---
version: 1
task: sound
role: writer
---
# W6 — Sound cues

Read the brief with `get_brief`, the shots with `get_storyboard` and, on a story
film, the lines with `get_narration`. Then call `write_sound_cues` with the whole
list: every cue the film needs and nothing it does not.

Three kinds. A `music` cue is a bed: one over the whole film, or one per act when
the feel turns. An `ambience` cue is the air of a place, from the first line or
frame there to the last: it never changes mid-scene. An `effect` is one sound on
one moment, a few seconds, on a reveal, a door, a hit. On a song film the song is
the music: write no bed unless the brief asks for one, and keep effects few.

A prompt describes a sound, never a picture: instrument, texture, tempo feel, room,
weather, distance. It names only what the brief, the script or a shot names. No
song titles, artists or lyrics. A bed says "no drums, room for a voice" when a
narrator speaks over it.

Anchor a cue to lines on a story film (`start: {"line": id}`) so it follows the
takes, and to frames otherwise (`start: {"frame": n}`; `{"frame": -1}` is the end).
Say `why` in one sentence each. Reply in two lines: what the film sounds like,
and the one cue you were least sure of.
