# T3 — Writer prompts and shot kinds

Status: complete (merged); live Writer eval pending owner authorization
Revision: merged as 253da6b (PR #21), from branch commit a4d141f
Authorized: 2026-10-26, owner said "continue and do the whole of T3".

## Objective

Replace the ad-hoc stage guides with the Writer/Editor prompt suite, teach the
engine which shots are generated and which are designed locally, and make the
paid image path queue only generated kinds.

## Acceptance

1. `writer/*.md`, `shared/truth.md`, `kinds/*.md` and `examples/` follow the
   brief's layout; assembly is role system + truth + kind + style (Writer only)
   + one task + examples. Every file carries a `version:` front matter.
2. Every assembled Writer task is ≤ 2,000 words excluding project data; the
   assembled hash and file versions are recorded on the chat turn and artifact
   write.
3. `Shot.kind`, `message`, `text[]`, `bridge.match`, `product_ref` and `panes[]`
   validate on the whole board. Generated `scene`, `product` and
   `bridge.mode=generated` compile an image spec. Local `card`, `split`, `logo`,
   `end_card`, designed `bridge`, `upload`, `reprise` and uploaded `product`
   render deterministic Pillow plates without a Runware task or budget use.
4. `proof_ids`, `quote_images`, `reviews.require_accepted` and preflight are
   paid-kind only. Stage hashes include deterministic local-plate bytes; legacy
   shot/brief hashes stay byte-stable when new fields hold defaults.
5. The Storyboard UI shows kind icons, edits interesting fields and changes a
   shot's kind. The Images UI shows local plates with no paid select/review
   controls.
6. The three eval fixtures exist with offline automatic checks; a live Writer
   run remains unauthorized until the owner says so.
7. `.opencode/skills/*` is deleted with an old-file → new-file mapping in the PR.
8. `pytest`, ruff check/format, frontend build and app start are green.

## Constraints

- Never write `projects/`, `backups/` or `archive/`.
- Source audio and generated stills are immutable; local plates are derived and
  keyed by content plus renderer version.
- No paid provider call in tests or during implementation.
- Legacy productions must keep their approval hashes: new `Shot` fields are
  dropped from serialization while default; an empty `image_prompt` is dropped.
- Local plates are not a new Remotion primitive: they are ordinary image files.

## Decisions

- `shotkinds.py` owns the paid/local predicate. `scene` and `product` are paid;
  `product` with an uploaded `asset` is local; `bridge` is paid only in
  `generated` mode; everything else is local.
- `asset_shot_id` remains the reprise alias. Legacy aliases keep working without
  a `kind` value.
- Local plates live in `work/local-plates/<shot>-<key>.png`; the Player gets a
  `GET /api/projects/{slug}/plates/{shot_id}` URL.
- `split` composes its pane shots at plate-render time; a pane that is still
  missing keeps a definition hash in the proof stage but blocks stills/Player
  until it exists.
- Treatment concepts get a validated `Treatments` model with exactly three
  concepts, unique structures and an optional chosen ID.
- Prompt task selection is deterministic: Story picks brief → concepts → script
  → revise from artifact state; Storyboard picks storyboard; Images picks
  prompts or review; Track/Film route to the Editor.
- The old `film.md` content moves to `editor/edit.md` + `editor/post.md`; the
  structured edit list and renderer primitives remain T4.

## Open questions

- Live Writer/Editor eval on the three fixtures requires explicit spend
  authorization. Offline checks can run now.
- `.opencode/skills` deletion is part of T3; the mapping table is generated from
  the actual files that existed at the branch point.

## Skill mapping (old file → new home)

| Old file | New home |
| --- | --- |
| `.opencode/skills/clip-music-director/SKILL.md` | `writer/system.md`, `editor/system.md`, `shared/truth.md` (routing, hand-offs, stage contract) |
| `.opencode/skills/clip-music-analysis/SKILL.md` | `editor/music.md` (measurement, candidate sections, uncertainty) |
| `.opencode/skills/clip-story/SKILL.md` | `writer/brief.md`, `writer/concepts.md`, `writer/script_mv.md`, `writer/script_ad.md`, `examples/brief.md`, `examples/concepts.md` |
| `.opencode/skills/clip-storyboard/SKILL.md` | `writer/storyboard.md`, `examples/storyboard.md` (shot contract, coverage, proof selection) |
| `.opencode/skills/clip-art-direction/SKILL.md` | `writer/system.md` (style block), `kinds/*.md`, `styles/*.md` |
| `.opencode/skills/clip-image-prompts/SKILL.md` | `writer/prompts.md`, `examples/prompts.md` |
| `.opencode/skills/clip-image-production/SKILL.md` | `writer/review.md`, `writer/revise.md`, `generation.py` (quote/budget/recovery unchanged) |
| `.opencode/skills/clip-visual-review/SKILL.md` | `writer/review.md`, `examples/review.md` |
| `.opencode/skills/clip-edit-graphics/SKILL.md` | `editor/edit.md`, `editor/post.md`, `editor/techniques.md` |
| `.opencode/skills/clip-delivery/SKILL.md` | `editor/post.md` (render, probe, delivery honesty) |
| `.opencode/skills/character-consistency/SKILL.md` | `writer/prompts.md`, `writer/review.md` (identity, references, no invented person) |
| `.opencode/skills/photoreal-stills/SKILL.md` | `writer/prompts.md`, `styles/clean-photographic.md`, `styles/photographic-painted.md` |
| `.opencode/skills/runware-models/SKILL.md` | engine: `profiles.py`, `styles/*.md` model settings (no Writer task) |
| `.opencode/skills/runware-prompting/SKILL.md` | `writer/prompts.md`, `writer/system.md` |
| `.opencode/skills/runware-run/SKILL.md` | engine: `generation.py`, `docs/ARCHITECTURE.md` (no Writer task) |

Every `references/*.md` under a deleted skill was distilled into the same new
file as its `SKILL.md`; no skill reference file remains a runtime prompt source.

## Implementation

- `director/prompts.py` assembles role system → truth → kind → style (Writer) →
  task → example, parses `version:` front matter, and returns the hash plus file
  versions. Story task selection walks brief → concepts → script → revise from
  the artifacts; Track and Film route to the Editor.
- `writer/*.md`, `editor/*.md`, `shared/truth.md`, `kinds/*.md` and
  `examples/*.md` replace the six stage guides. `promptlog.py` writes
  `work/prompt-current.json` and `work/prompt-artifacts.jsonl`;
  `api/director.py`, `loop.py` and `opencode.py` keep the metadata on the turn.
- `models.py` adds `Shot.kind/message/text/asset/product_ref/bridge/panes`, the
  `BridgeMatch`/`BridgePlan`/`Pane` contracts, script beats and `Treatments`.
  Default values are dropped from serialization; `image_prompt` is optional only
  for local kinds. `update_treatments` validates exactly three distinct
  structures and keeps history.
- `shotkinds.py` is the paid/local table. `production.py` compiles product and
  generated-bridge specs, renders local plates, serves them through
  `local_plate_path`, and keeps local bytes/definitions in the proof/stills
  hashes. `localplate.py` makes deterministic PNG plates from local type,
  brand colours, uploaded assets and split panes.
- `generation.py`, `services/generation.py`, `reviews.py`, `preflight.py`,
  `cli.py`, `derivations.py` and `services/preview.py` filter or skip local
  kinds. The Images API returns `kind/paid/local/plate`; the Player uses
  `/plates/<shot_id>`; Storyboard and Images expose the new fields.
- `tests/evals/` contains the three frozen inputs, deterministic still
  materialization and offline checks for distinct concepts, board coverage, the
  advert's local kinds and invented claims.

## Evidence

- `uv run pytest -q`: 884 passed, 1 skipped.
- `uv run ruff check .`: clean. `uv run ruff format --check .`: 195 files already
  formatted.
- `cd frontend && npm run build`: clean (53 modules).
- `uv run studio --port 8918`: `/api/health` ok and `/` returned 200.
- Assembled Writer prompt worst case: 1,532 words
  (`storyboard/advert/photographic-painted-v2`); every Writer task, kind and
  style combination is under 2,000.
- `tests/test_shot_kinds.py` proves legacy round-trips keep new fields out,
  local plates are deterministic and content-bound, split/upload/logo render,
  product and generated bridge compile their own specs, and reprise aliases keep
  working.
- `tests/test_api_local_kinds.py` proves Images exposes local plates, the Player
  uses the plate URL, estimates/reviews refuse local shots, and treatments
  require distinct structures.
- `tests/test_evals.py` proves the fixtures, concept distinctness, advert
  non-scene coverage and claim checking without a model call.

## Limitations

- No live Writer/Editor eval was run: that needs the owner's explicit spending
  authorization. The fixtures and offline checks are ready; the live
  "three structurally different concepts" and "advert storyboard" proof remains
  unmeasured.
- A split shot needs its pane stills before it can render; the proof stage binds
  the definition until then, and stills/Player report the missing plate.
- The Storyboard UI can change kind and text, but product references, uploaded
  assets, bridge mode/match and split panes for advanced cases still come from
  the Writer tools or JSON.
- The Editor's structured edit list and renderer primitives remain T4; the Film
  prompt says so and plans in the reply for now.

## Merge

PR #21 squash-merged as `253da6b`; the branch commit `a4d141f` and the merge
tree are identical (`b3bc0e0`). CI check passed in 4m31s. No paid provider call
was made. The branch was deleted after merge.
