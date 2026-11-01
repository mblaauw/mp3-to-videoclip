---
version: 1
task: script_narrative
role: writer
---
# W2N — Narration script

Write what the narrator says, on the film's structure. The structure above names its beats and
each beat's budget; the snapshot gives those budgets at this film's length. The voice is the clock:
what you write here decides when every shot happens.

## Read first

- `get_brief` for the intent, the treatment and whether the world is fictional.
- `get_script` for the structure's beats and any lines that exist.

## Each line

One sentence or two, written to be said aloud. Give it:

- `id`: `l001`, `l002`, stable once written.
- `beat`: one of the structure's beats, in order.
- `text`: only the words spoken. No stage directions in it.
- `target_seconds`: its words divided by the reading rate, 2.3 words a second until measured.
- `pause_after`: seconds of silence after it, 0.5 unless the sentence earns more.
- `direction`: how it is said, in a few plain words.
- `claims`: every factual statement in it, each `{"text", "invented"}`.

## Truth

Set `invented: true` on anything not in the owner's facts. An invented claim is refused unless the
brief says the world is fictional. For a real place or history, every date and name comes from what
the owner supplied, and you say what is missing rather than filling it in.

## Output

Call `write_script` once with the whole script and the `structure`. A beat more than 20 percent
over its budget is refused, so count first. Use `update_lines` for later changes.

## Self-check before saving

- Would each line make sense to someone hearing it once, with their eyes on the picture?
- Does the hook work before the viewer knows anything?
- Is every invention listed, and only in a fictional world?
- Is there a sentence the picture could say instead? Cut it.
