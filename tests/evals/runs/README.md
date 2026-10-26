# Eval run bundles

Put live or historical eval runs here, one directory per run:

```text
<run-id>/
  meta.json
  treatments.json     # Writer run
  storyboard.json     # Writer and Editor runs
  edit.json           # Editor run
  cross_review.json   # optional; or inline in meta.json
  ratings.jsonl       # optional; or inline in meta.json
```

`meta.json`:

```json
{
  "fixture": "advert-30s",
  "role": "writer",
  "model": "openai/gpt-6.1-sol",
  "created_at": "2026-10-26T12:00:00Z",
  "prompt": {
    "hash": "the assembled prompt hash",
    "files": [{"path": "writer/storyboard.md", "version": 3}],
    "task": "storyboard",
    "role": "writer",
    "kind": "advert",
    "words": 1450
  },
  "artifacts": {
    "treatments": "treatments.json",
    "storyboard": "storyboard.json"
  },
  "cross_review": {
    "reviewer_role": "editor",
    "scores": {"routes": 4, "jobs": 4, "rhythm": 4, "truth": 5},
    "notes": "One short paragraph."
  },
  "ratings": [
    {"artifact": "storyboard", "rating": "up", "note": "Clearer routes.", "prompt_hash": "the assembled prompt hash"}
  ]
}
```

A run without the optional cross-review/ratings is still valid. Invalid
cross-review or a failing automatic check is reported, never concealed.

Do not put paid provider credentials or production folders here. Live runs are
manual and need explicit spend authorization; the report command itself never
calls a model.
