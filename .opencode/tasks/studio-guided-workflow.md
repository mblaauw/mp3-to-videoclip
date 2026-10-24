# Guided Studio workflow and production archive

## Objective

Replace the eight-stage Studio workflow and four administrative menus with a
five-step guided creation path that matches how the user actually works:

1. Track: analyse locally; no user approval of measurements.
2. Story: agree concept, editable film style and storyboard, with durable revision
   notes for the agent; approve brief + storyboard as one human decision.
3. Style check: review a few representative stills; approve or send back feedback.
4. Images: review every selected still; approve or request a change per image.
5. Finish: prefill and edit factual credits, inspect composited samples, then render.

Keep only `forward-ever` and `stof-en-stilte` visible in the Studio. Move the other
six productions to a local archive without deleting them.

## Authority and boundaries

User approved implementation in the 2026-10-24 conversation. No paid provider call,
upload, production approval rewrite or new spending authority. Existing productions
without the guided policy keep their recorded v2 gates. The GUI cannot spend; paid
regeneration still needs a quote and a later human authorization/executor run.

## Implementation

- `flow.py` + `work/guided-flow.json`: guided policy outside every artifact hash.
  Guided brief excludes the signature; stills gate on `proof`, not `preview`;
  graphics still validates the full signature at Finish.
- `feedback.py` + `clip feedback`: durable revision requests with stage/scope/
  target/message/style, open/resolved status and agent replies. No provider call.
- Human actions: atomic `approve_story` (brief + storyboard with rollback),
  content-bound per-image `record_shot_review`, late-bound `save_credits` for guided
  projects, and a `work/credits-template.json` prefill for new productions.
- HTTP: read-only `/workflow`, `/story-review`, `/feedback`; capability-gated
  `/feedback`, `/review`, `/approve-story`, `/credits`. All writes stay same-origin,
  lock-guarded where they mutate approvals/specs, and outside `/api/create`.
- Studio: five steps and one Project menu; compact concept/style/storyboard;
  per-image review cards; preview inside Images for recorded v2 only; Finish credits
  editor for guided and explicit legacy notice for v2; revision notes and one Project
  panel for budget/quotes/decisions/activity.
- Archive: six productions moved to `archive/projects-2026-10-24/` (ignored).

## Acceptance and evidence

- `uv run pytest -q`: **929 passed, 2 skipped** (3 existing librosa warnings on
  short/silent fixtures).
- `uv run --with playwright pytest tests/test_studio_browser.py -q`: **33 passed**
  after the guided rewrite; includes old human capability/quote/security cases and
  new five-step, feedback, per-image review, guided credits, preview-target,
  v2-separate-story and responsive cases.
- `uv run ruff check .`: clean. `uv run ruff format --check .`: 127 files formatted.
- `uv run clip eval`: all six structural invariants pass.
- Actual 1440×1000 desktop pages inspected for library, Story, Style check, Images,
  Finish and Project; no page errors and no literal markup in the read-only banner.
  Phone/tablet layout is covered by Chromium viewport tests at 390/900/1280.
- No production approvals, budgets, media or provider state changed by the tests;
  they use temporary projects. The archive move changed only local ignored paths.

## Independent review and fixes

One read-only review of the uncommitted diff was run before publication. Confirmed
findings and resolutions:

1. **Custom style prefill could make a new project unapprovable.** A sibling's
   custom look was inherited while the project still claimed the default preset.
   Fixed: an inherited look that is not default-compatible records
   `style_preset=custom`; the default-compatible path keeps the default preset. The
   regression test now approves the prefilled brief instead of only reading it.
2. **A stray guided marker could flip a recorded v2 project.** The marker now
   carries the production's source hash and slug; copied markers are ignored, and
   `flow.mark` refuses a production with recorded decisions. Adding a matching
   marker to an old film is an explicit migration, not a side effect.
3. **Recorded v2 Story showed the combined guided approval form.** The combined
   form and `/approve-story` now refuse non-guided productions; v2 uses its
   separate brief/storyboard decisions.
4. **Empty credit blocks could be confirmed.** `save_credits` now requires at least
   one factual role/name pair.
5. **Malformed approvals could escape the JSON error path.** `approve_story` now
   validates the approvals shape and returns a typed 409 instead of a raw
   `TypeError`.
6. **Stale snapshot hashes could produce a confusing 409.** Approve buttons now
   fetch the exact current stage hash immediately before the decision; the server
   still rechecks it under lock.
7. **Concurrent feedback submissions could lose a request.** The HTTP feedback
   route now holds the project lock around its read-modify-write.
8. **The atomicity test did not exercise the stale-hash branch.** The test now
   submits the pre-mutation combined hash and asserts 409 with unchanged bytes,
   then separately proves rollback after a valid hash reaches a failing second gate.

## Decisions

- Guided policy is a source-bound marker, not `workflow_version: 3`, so existing
  v2 hashes and approvals are unchanged. The marker is ignored unless its source
  hash and slug match the production.
- Guided brief approval does not require prior analysis/lyrics/events/brand
  approvals; those artifact bytes still bind into the brief hash, so later changes
  make the brief stale. Recorded v2 keeps the full upstream approval chain.
- Credits are late-bound only for guided projects. Recorded v2 credits remain inside
  the brief hash; the UI refuses to silently rewrite them.
- New productions prefill film style from the newest approved sibling brief and
  credits from the newest explicit template, falling back to a sibling graphics
  spec. Both remain editable and unconfirmed until the user acts.
- Feedback is a request, not an approval or a generation trigger. The agent applies
  it and resolves it with a reply.

## Open questions / limits

- The GUI cannot start an LLM turn by itself. It records a durable instruction and
  the agent applies it in the workspace. This is the honest agent-operated boundary.
- Final render remains a local agent action; the GUI shows the command/status and
  records a render request, but does not execute ffmpeg from the server.
- The two existing productions are recorded v2; their credits are not editable at
  Finish and their preview gate remains mandatory. They were not migrated.
- Legacy hidden routes (`approvals`, `runs`, `quotes`, `stills`, `board`) remain for
  bookmarks/tests but are not in the five-step menu.
- Archive location is local and ignored; no remote backup was created by this task.

## Publication

Merged to `main` as `1646ddd` (PR #5, branch `guided-studio-flow`) after the CI
`check` job passed. The merge contains the five-step Studio, guided policy,
feedback store, per-image review, late credits, archive documentation and tests.
