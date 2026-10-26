# Evaluation inputs and reports

Three frozen inputs live in `fixtures/`:

- `energetic-vocal.json` — 180 s vocal music video.
- `slow-instrumental.json` — 240 s instrumental music video.
- `advert-30s.json` — 30 s advert over the 62–92 s excerpt, with allowed facts.

`checks.py` validates artifact shapes without a model: three distinct concept
structures, a contiguous board, the advert's local kinds, invented dates/URLs/
prices and the Editor's edit report. `materialize_stills` draws deterministic
gradient stand-ins so a run needs no Runware spend.

## Run a report

```sh
uv run python -m tests.evals
```

The command makes no model or network call. It writes one Markdown page per
current Writer/Editor prompt version used by the fixtures, plus one page for
every stored run hash and every rating-only or unbound prompt hash, into
`reports/` (gitignored). `reports/index.md` links them. A page with no run says
so; it never invents a pass.

Useful options:

```sh
uv run python -m tests.evals --runs path/to/runs --reports path/to/reports
uv run python -m tests.evals --ratings projects/<slug>/work/ratings.jsonl
uv run python -m tests.evals --strict   # exit 1 if an automatic check fails
```

## Run bundles

A live or historical run is a directory under `runs/` with `meta.json` and local
artifacts. See `runs/README.md` for the full shape. The fixture, role, model,
prompt hash/files and artifact paths are required. `cross_review.json`,
`ratings.jsonl`, `ratings` and `cross_review` in `meta.json` are optional.

Automatic checks are the gate. Cross-review and human ratings are signals.
A run whose schema or automatic checks fail is shown as **FAIL** and listed in
`--strict` output; it is never silently dropped.

## Cross-review

The rubric is in `rubric.py`: distinct routes, every shot has a job, rhythm and
technique, and truth/claims, each scored 1–5 by the other role. The runner does
not call a model. Put the reviewer's JSON in `cross_review.json` or the run
meta, or use `rubric.prompt("editor", "writer")` to print a copyable prompt.

## Human ratings

The Studio stores thumbs up/down and an optional note in
`work/ratings.jsonl` for the brief, concepts, storyboard and edit. Each entry
binds the artifact bytes and the last prompt write that produced that artifact
(`work/prompt-artifacts.jsonl`); ratings without prompt history are marked
unbound. The report groups them by prompt hash. Ratings never invalidate an
approval.

## Live evaluation

The live Writer/Editor pass is manual and not part of CI. It needs the owner's
explicit spending authorization and a writable copy of a production; never point
it at `projects/`. No live pass was made while building T5.
