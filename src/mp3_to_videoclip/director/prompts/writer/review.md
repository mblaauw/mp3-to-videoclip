---
version: 1
task: review
role: writer
---
# W6 — Still review

Review the selected images against the job each shot was written to do. Call
`get_images` with at most eight shot IDs, inspect the returned thumbnails, and
record a verdict for the exact version you saw. Never claim you inspected bytes
you did not receive.

## What to judge

- The shot's job and `message`: does the image do that job without a caption?
- Framing and `must_show`: are the load-bearing details actually visible?
- Identity and state: the same person, costume and props as the neighbouring
  shots; permission is already recorded, not assumed.
- The neighbours: does this image cut cleanly from the shot before and into the
  shot after, or does it repeat their framing?
- Honest craft: accept a stylised small detail when the whole frame works;
  reject a wrong face, a broken product, unreadable text or a missing must-show.

## Output

For each inspected shot, keep or redo:

```json
{"shot_id": "s004", "version": 2, "verdict": "accept|reject|uncertain",
 "note": "what you saw and why"}
```

A redo needs a concrete prompt change: name the field and the new wording. "Make
it better" is not a repair. Do not regenerate what is already right.

## Self-check before saving

- Did you inspect every version you judged?
- Does every redo have a changed prompt, not only a complaint?
- Are the accepted shots still consistent with their neighbours?
