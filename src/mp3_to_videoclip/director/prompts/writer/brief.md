---
version: 2
task: brief
role: writer
---
# W1 — Creative brief

Turn the Story intake and the measured music summary into the one-page intent
block. You are not writing the treatment yet; you are making the job unambiguous.

## Input

- `intent` already holds the user's facts. Treat every reason, date, price, offer,
  URL and legal line as fixed. Never invent or "improve" one.
- The kind block tells you what this production is for.
- The music summary gives sections and energy; use it only to judge where the
  film can breathe.

## Output

Patch the brief through `update_brief`:

```json
{"intent": {
  "kind": "advert",
  "objective": "one sentence, active verb",
  "audience": "a specific group, not everyone",
  "message": "the one thing a stranger should repeat",
  "reasons": ["user-supplied fact", "user-supplied fact"],
  "tone": ["three", "plain", "words"],
  "mandatories": ["only what the user requires"],
  "avoid": ["only what the user rejects"],
  "cta": {"text": "verb + where", "url": "supplied URL"},
  "length_seconds": 30,
  "audio_window": {"start": 62.0, "end": 92.0, "fade_in": 0.0, "fade_out": 1.5}
}}
```

Keep `length_seconds` and `audio_window` consistent with the window the user
chose. For a music video, fill `about` (the song in the artist's words) and
`performance` (true/false), and leave sales fields empty.

## Self-check before saving

- Can a stranger state the message after one reading?
- Is the audience specific enough to picture one person?
- Is every reason, date, price and offer present in the user's input?
- Are the tone words three, and do they describe sound or feeling rather than
  visual style?
- Does the CTA say the verb and where the action happens?
