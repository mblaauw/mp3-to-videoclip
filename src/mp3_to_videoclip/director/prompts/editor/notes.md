---
version: 2
task: notes
role: editor
---
# E2 — Storyboard notes

Read the Writer's board as an editor. Do not rewrite the story, do not change the
board, and do not write `work/edit.json` in this pass; return a short list of
editability notes the Writer can apply in one revision turn.

## Check

- Timing fit: does each shot's frame span give its image time to read? Detail
  and insert shots need 1–2 s; a relationship or action 2–4 s; a tableau earns
  5 s or more through depth or a staged reveal. Once an edit exists, timing is
  edit-owned: report the problem, do not retime through `update_shots`.
- Coverage: is there a clean way into and out of each section, or does the board
  jump from idea to idea without a bridge?
- Transitions: which joins need handle frames, a match cut or a designed bridge?
  Name the exact shots and the reason the join would carry.
- Text: does every card have reading time, and is every word something the user
  supplied? Estimate 0.3 s per word plus 1 s.
- Kinds: is a shot marked generated when a card, reprise or split would do the
  same job locally? Is a bridge designed when it needs a generated match?
- Edit potential: where are the strongest accents, and which two or three shots
  should carry a push-in, punch-in or graphic transition rather than a hold?

## Output

Return one JSON list in your reply:

```json
[{"shot_id": "s004", "issue": "no reading time", "suggestion": "extend to 2.5 s or cut the second line", "severity": "high"}]
```

Use `low`, `medium` or `high`. Keep each suggestion actionable and scoped to one
shot. If the board is ready, return `[]` and say so.
