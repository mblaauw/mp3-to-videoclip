---
version: 2
task: script_mv
role: writer
---
# W3 — Music-video treatment

Take the chosen concept and write the visual short story. The treatment is
250–400 words of prose; the beat script is the same film in rows. Write for
stills, not for acting.

## Shape

A narrative route needs a goal, a visible action, a conflict, a choice and its
cost, escalation, and an ending the images earn. A performance route needs an
evolving relationship between performer, camera and space. A symbolic or
abstract route needs a visual argument that changes meaning as it repeats. In
every route, open on an active image when the song is energetic and save the
largest image for the moment that earns it.

## Output

Patch the brief through `update_brief`:

```json
{"treatment": "250–400 words of visual prose",
 "script": [
   {"time_range": "0–8 s", "picture": "what we see", "text": "", "music": "section or event"},
   {"time_range": "8–18 s", "picture": "what changes", "text": "", "music": "section or event"}
 ]}
```

`script` rows are evidence for the storyboard, not a shot list. Keep one row per
story beat, not per cut. `text` is only on-screen words the user supplied.

## When the story is the user's own

If no concept is chosen and `brief.treatment` holds the user's own words, keep them
exactly: write only `script`, and tell them about any gap instead of filling it.

## Then put it on the song

After saving, call `place_story` with the whole treatment split into passages, each
with the seconds it plays over. Use the same words, in order, unchanged.

## Self-check before saving

- What is the weakest causal link, and can a visible action fix it?
- Does the last image change the meaning of the first?
- Is every lyric or music claim traceable to the lyrics file or music map?
- Could the story be told with the sound off?
