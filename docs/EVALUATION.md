# Evaluation: honest prompt-version evidence

T5 makes prompt changes measurable without a provider call in the harness. It
keeps three frozen fixtures, adds prompt-version reports, a cross-review rubric
and human thumbs stored with the prompt revision.

## What is measured

- **Writer:** schema-valid treatments and storyboard; exactly three distinct
  concept structures; contiguous board coverage; generated shots have prompts;
  the advert has at least two non-scene kinds; dates, URLs, prices and
  percentages trace to the fixture's supplied facts.
- **Editor:** schema-valid storyboard and edit list; full coverage; no edit-report
  hard findings; advert structure checks (brand/product/text in the first five
  seconds and an end card of at least three seconds). Mandatory wording remains
  a report warning because it may be phrased in the image rather than the JSON.
- **Cross-review:** the other role scores four questions 1–5 — distinct routes,
  every shot has a job, rhythm/technique, truth/claims. It is a signal, not a
  gate, and the harness never sends the prompt itself.
- **Human ratings:** thumbs up/down plus an optional note for the brief,
  concepts, storyboard and edit. Each rating binds the exact artifact hash and
  the last prompt write that produced it.

## Prompt-version reports

```sh
uv run python -m tests.evals
```

The command writes one Markdown page per current prompt hash used by the
fixtures (Writer storyboard and Editor edit, for music video and advert), plus a
page for every historical run hash and every rating-only or unbound hash. A page
with no run says "No run recorded"; it never fabricates a result. Each page lists
prompt files and versions, the automatic pass rate, cross-review averages, human
ratings and the rule of change.

Reports are generated into `tests/evals/reports/` (ignored by git) by default;
`--reports` writes elsewhere. `--strict` exits non-zero when an automatic check
fails. `--ratings` ingests an exported `work/ratings.jsonl`.

## Run bundles

A run is a local directory under `tests/evals/runs/<id>/`:

```text
meta.json
treatments.json     # Writer
storyboard.json     # Writer and Editor
edit.json           # Editor
cross_review.json   # optional
ratings.jsonl       # optional
```

`meta.json` carries the fixture, role, model and the assembled prompt metadata
(`hash`, `files`, `task`, `kind`, `words`) from the API turn. The exact contract
is in `tests/evals/runs/README.md`. Runs are deliberately not committed: a live
run can contain production material and is only evidence when the owner made it.

## Ratings in the Studio

`ratings.py` owns the append-only `work/ratings.jsonl` store. `promptlog.latest`
finds the last recorded prompt write for the artifact, so a rating made after a
later chat turn still points at the prompt that produced the bytes. The Studio
rating control appears on Story (brief and concepts), Storyboard and Film (edit).
The API is `GET/POST /api/projects/<slug>/ratings`.

Ratings are not approvals: they never change a stage hash or open a gate. A
later artifact write leaves the old rating visible but marks it stale.

## Boundaries

- No test or harness command calls a paid provider.
- Live Writer/Editor evaluation and live cross-review need explicit spend
  authorization and a writable production copy.
- A prompt edit ships only when it does not lower the fixture pass rate and the
  owner prefers the side-by-side output.
