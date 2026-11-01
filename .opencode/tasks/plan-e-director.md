# Phase E: make the Director a director — plan

**Proposed** 1 Nov 2026 for owner approval; base `main` at `c1414a3`.

**Objective:** turn the Writer and Editor from safe clerks into a director you can
trust with the film and with the money. One direct adapter talks to any provider
and names its model and its cost on every turn. The Writer gets a craft layer and
examples that do not all live in the same neon city. The look can change by
section. Stills keep their people and places through generated sheets, edit-mode
redos and per-shot seeds. Tools are typed, every write says what changed and why,
and a first draft of a whole film exists minutes after the drop under one owner
authorisation with a ceiling. Section 8 and Phase E of the assessment
(`docs/design/studio-assessment-2026-10-31.md`); the owner's decisions 4, 5 and 6
are taken as read. Depends on Phase H (catalogue, per-role settings) and Phase B
(song map in the context); where either has not landed, the task says what E does
on its own.

## What the code showed

- **One model for both roles on the default path.** `api/director.py:262-267`
  builds `DirectorLLM(base_url=settings.llm_base_url, api_key=settings.llm_api_key,
  model=settings.llm_model)` whatever `role` is; `role` only picks the prompt suite
  and the thread tag. `config.py:27-32` keeps `writer_model` and `editor_model` for
  the gateway and `llm_model` for the direct path. `Director.tsx:389-393` puts
  `writer_model` and `editor_model` in the header even on the direct path, so the
  header names a model the direct path never calls.
- **One provider.** `llm.py:108-117` is a single `AsyncOpenAI` client; images reach
  it as `image_url` parts built in `loop.py:169-184`. There is no Anthropic or
  Gemini path, and no tool-schema translation.
- **Tokens are produced and dropped.** `llm.py:208` yields `Usage`; `llm.py:171-173`
  only reads it from a chunk with no choices, and `llm.py:151-158` never asks for
  `stream_options.include_usage`, so most OpenAI-compatible endpoints send none.
  `loop.py:81-91` handles `TextDelta`, `Progress`, `ToolCall` and `TurnResult` and
  lets `Usage` fall through. The gateway relay has no `session.usage.updated` case
  (`opencode.py:580-686`). No price table exists anywhere.
- **The bound is 25 calls and then a dead end.** `loop.py:33` `MAX_TOOL_CALLS = 25`;
  `loop.py:186` ends with "Stopped after the tool-call limit." The Story room
  record saw 18 failed calls in one turn; a profile plus skeleton plus a dozen
  `update_shots` plus `get_images` is a normal board pass.
- **Reasoning between tool calls is never kept.** `loop.py:122-135` appends the
  assistant text that accompanies tool calls to the in-memory `messages` only;
  `append_message` is called for the final answer (`loop.py:118`) and for tool
  results (`loop.py:160-164`). `conversation.py:108-124` compacts from user
  snippets and tool names only, so after sixty messages the model remembers what
  it was asked and which tools it used, not why it did anything.
- **Roles cannot read each other.** `conversation.py:37-57` `_for_role` keeps one
  role's rows plus rows from before the split; `api/director.py:162-168` serves
  one role at a time. Nothing hands the Writer's decisions to the Editor.
- **The Director authorises spend itself.** `tools.py:651-655` calls
  `services.generation.authorize(root, quote_id, note="confirmed in director chat")`
  whenever `budget.check` says the cap has room; `services/generation.py:80-88`
  records that as `via="studio", review_confirmed=True`, the same mark an owner's
  click leaves. `tests/test_director_tools.py:75` pins this behaviour. The MCP path
  only avoided it by excluding the tool (`mcp.py:29-34`).
- **Untyped write items.** `tools.py:66-69` (`update_edit_shots.shots`),
  `tools.py:76` (`update_edit.edit`) and `tools.py:302` (`update_shots.changes`)
  are `{"type": "object"}`. The engine refuses unknown fields
  (`production/board.py:149-151`, `edits.py:1049-1051`), so a wrong key costs a
  round trip and one of the 25 calls. Writes return the whole artifact
  (`tools.py:492`, `tools.py:509`); `Director.tsx:138-192` derives "N shots
  changed" from `changed` IDs; Undo is `history.restore`
  (`domain/history.py:104-125`), the newest different snapshot of the whole file.
- **The prompt budget has little room.** `tests/test_director_prompts.py:102`
  asserts 2,000 words per Writer task over three kinds and two styles. Measured on
  `c1414a3` over all four styles: storyboard 1,830, profile 1,775, concepts 1,585,
  prompts 1,463, script_ad 1,450, script_mv 1,388 (worst case each, always with
  `photographic-painted-v2`, 271 words). A 400-word `craft.md` in every Writer task
  puts storyboard at 2,230. The craft layer has to be placed per task.
- **One idiom.** `examples/concepts.md:7-16` (courier, record, sleeping city,
  street lamp), `examples/script_mv.md:7-9` (the same courier), `examples/script_ad.md`
  and `examples/storyboard.md` (one turntable advert), `examples/prompts.md` (needle
  on vinyl, night street reflections) and `examples/brief.md` (the same "Forward
  Ever" release). The eval fixture `tests/evals/fixtures/energetic-vocal.json`
  sets the intent "A night courier carries a record across a city that will not
  sleep", so the harness itself rewards the idiom.
- **The context is thin.** `context.py:102-105` gives tempo and at most twelve
  section labels; `context.py:212` clips the treatment at 420 characters;
  references are counted, never shown (`context.py:216-221`); stills reach the
  model only through `get_images` (`tools.py:576-620`, eight at 512 px).
- **The compiler puts the look first and knows one seed.** `image_specs.py:268-285`
  orders look, shot text, framing, must-show, scene, references, characters, image
  rules, then `"Avoid: ..."` as prose (`image_specs.py:282`). `prompt_look_first`
  (`production/project.py:80-82`) is already a per-project switch keyed on
  `prompt_version == 2` or schema 3. The seed is `project.image_seed`
  (`models.py:115`), copied into every task (`generation.py:87-88`,
  `image_specs.py:322-333`). `negativePrompt` appears nowhere in `src/`. The live
  model schema is fetched per model (`providers.py:326-342`) and every request is
  validated against it (`generation.py:70`, `generation.py:229`).
- **A compile change marks everything stale.** `begin_task` refuses a task whose
  `input_hash` differs from the current compiled spec (`generation.py:396-404`),
  and proof and stills hashes bind the spec (`approvals.py:202-213`).
  `tests/test_contract_golden.py:216-226` pins the look's first line, scene text,
  state text and `"Avoid: text; logos"` inside `positivePrompt`, and the golden
  fixture is a `prompt_version` 2 film.
- **Every redo is from scratch.** `generation.py:201-223` always builds a fresh
  `imageInference` with `referenceImages`; a rejected still is never an input.
  References only enter through `references.import_reference`
  (`references.py:17-45`), which needs the owner's `permission_confirmed=True` and
  a note and writes `media/references/<sha>.png`. Nothing generates a reference.
- **No per-section look.** `CreativeProfile` (`models.py:275-286`) has look, rules,
  arc, scenes, references; `Scene` has a description. `creative_profile_version`
  (`image_specs.py:145-155`) hashes look, rules and avoid.
- **Everything needed for a first draft exists as a click.** Owner authorisation is
  `POST /images/estimate` then `POST /images/generate` with the quote
  (`api/images.py:172-211`); jobs are `runner.submit(kind, project, factory,
  blocking=True)` (`jobs/runner.py:178-186`) with a `needs_budget` status
  (`runner.py:38-39`); `preview.build_preview` (`preview.py:169-183`) renders a
  marked animatic with placeholders for shots that have no still, free;
  `first_cut.suggest` (`first_cut.py:65`) is model-free and `api/film.py:185-194`
  returns it without saving; `edits.seed_edit` (`edits.py:951-959`) seeds from the
  board. Approvals record `{hash, at, note, via, review_confirmed}`
  (`approvals.py:406-415`); `require_approval` treats `via == "studio"` as
  needing `review_confirmed` (`approvals.py:241-254`); the proof batch requires the
  storyboard approval (`generation.py:405`). `production/brief.py:85-103` lets only
  `owner=True` change `permission_confirmed`; `character_refs` refuses any
  unconfirmed character in a shot (`image_specs.py:53-54`).
- **Evaluation measures format.** `tests/evals/checks.py` checks schema, frame
  contiguity, local kinds and regex claims; `rubric.py:7-40` is four 1 to 5
  questions with no anchored descriptors; `runs/` is empty by design
  (`tests/evals/runs/README.md`); the runner never calls a model. Ratings bind to
  the artifact hash and the prompt write (`ratings.py`, `promptlog.py:34-55`).
- **The gateway to retire.** `opencode.py:39-40` pins 2.1.4 to 2.2.0;
  `opencode.py:528-538` makes a warm-up session; `opencode.py:547` re-sends the
  whole system prompt and snapshot as user text every turn; `api/settings.py:64-94`
  shells out to the CLI for the settings test; `app.py:27,83` closes gateways;
  `tests/test_director_opencode.py` (455 lines), `tests/test_api_director_gateway.py`
  (190), `scripts/probe_opencode.py` and `docs/ARCHITECTURE.md:323-384` belong to
  it. `director/mcp.py` is 174 lines over the same `tools.TOOLS` with an exclusion
  set and its own 80-line test; it does not depend on `opencode.py`.
- **Where money shows today.** `TopBar.tsx:54-126` draws spent, reserved, remaining,
  cap and the cap history from the images journal; `Director.tsx:79` marks only
  `generate_images` and `transcribe_lyrics` as money rows; the `ToolRow`
  (`Director.tsx:224-272`) shows a label, an argument summary and raw details.

## Decisions for the owner

The assessment already decided: retire the OpenCode server and keep OpenCode Go
as a provider URL (4); one-click first draft under a budget ceiling with draft
approvals (5); the Director never authorises spend (6). What follows is only what
those decisions leave open.

| # | Question | Recommendation |
| --- | --- | --- |
| D1 | Keep `director/mcp.py` after the gateway goes? | Keep it, as the one way an outside agent (your own OpenCode, Claude Code or a script) can read a film and make safe writes. It stays over the same `TOOLS`, keeps its paid-tool exclusion, loses nothing and gains nothing in E, and is documented as "for external agents". Drop it in G if nobody has used it by then. |
| D2 | Where is model spend written? | A separate append-only `work/model-usage.jsonl`, not `work/tasks.json`. The journal's contract is a reservation written before a request, a UUID that is never resubmitted and a provider-reported cost; a model call has none of those (its cost is a catalogue estimate after the fact). Model spend is shown beside picture spend everywhere, summed per turn and per film, but is not admitted against the production cap in E. The first-draft ceiling has its own model allowance. |
| D3 | How does a 400-word craft layer fit a 2,000-word budget with 170 words of headroom on the storyboard task? | `shared/craft.md` at most 380 words, loaded for concepts, script_mv, script_ad, prompts, review, revise and import. Storyboard and profile get a 120-word craft digest inside their own task files, with 60 words trimmed elsewhere in `storyboard.md` so it keeps 100 words of headroom. The budget stays at 2,000 and the test grows to all four styles. |
| D4 | Compiler changes and existing films. | One switch: new films get `prompt_version: 3` at intake. Version 3 means subject before look, `negativePrompt` from `brief.avoid` where the live schema has it, per-shot seeds and section looks. Existing films stay at 2 and keep every hash; the golden fixture stays at 2. An existing film can opt in from Story's Look card, which the screen says will mark every still stale. |
| D5 | How is a character sheet or scene plate made and bound? | From the World tab, per character or scene, priced like a still ($0.05 reserve) and journaled like a still. The result is shown first; "Use as reference" is the owner's click that imports it with permission and binds it to the character's `references` or the scene's `reference_ids`. The brief then needs approving again, as it should when its references change. |
| D6 | Default ceiling for a first draft? | $1.00, editable in the dialog: three proof stills at the $0.05 reserve, plus a model allowance of $0.80 for about eight Writer and Editor turns at current OpenCode Go prices. The dialog shows both parts. |
| D7 | What may a draft approval unlock? | Brief, storyboard and the proof batch, and nothing after: stills, titles and a final always need your own approval. Draft approvals are content-bound like every other, recorded as `via: "draft"` with the role, model, prompt hash and job, shown as "Drafted, not yours" with one button that makes them yours. |
| D8 | What does the other role see? | Not the whole thread. Each turn's system prompt gets a "From the Writer" or "From the Editor" block: that role's last three answers (clipped) and its reasons from `work/decisions.jsonl` for this stage. The drawer gets a read-only "Both" view, merged by time. The chat log stays as it is. |
| D9 | Which judge for the creative evaluation, and how much may it spend? | The strongest configured model from a provider other than the one that wrote the artifacts where you have two keys, otherwise the Writer's model. Judging the three fixtures for two prompt hashes costs about $3 on today's prices; please authorise up to $5 for the first run. The judge's spend is written to the run's `meta.json`, never into a film. |

## Tasks (one commit each, one PR)

Three PRs of about a week each. The task limit, compaction and spend fixes land
in E-1 because everything after builds on them.

### PR E-1: adapter, cost and per-role models

1. **Provider plugins behind the adapter.** `director/providers/` with `base.py`
   (a `Provider` that takes messages, tools, system, image parts and yields the
   same `TextDelta`, `Progress`, `ToolCall`, `Usage`, `TurnResult` events as
   today), `openai_compatible.py` (OpenAI and OpenCode Go; asks for
   `stream_options.include_usage`), `anthropic.py` (Messages API streaming,
   `input_schema` tools, `image` source parts, usage from `message_start` and
   `message_delta`) and `gemini.py` (`generateContent` streaming, function
   declarations, `inline_data` parts, `usageMetadata`). `DirectorLLM` keeps its
   name and interface (`stream(messages, tools, system)`), the idle limit, the
   stall and service-failed messages and the single retry; only the client inside
   changes. Image attachments work on every provider, with one test each from a
   recorded thumbnail. Tests use `httpx.MockTransport` fixtures per provider, with
   and without usage in the stream. Files: `director/llm.py`, `director/providers/*`,
   `tests/test_director_providers.py`. 2.5 days.
2. **Per-role provider and model.** `api/director.py` resolves `{provider,
   base_url, key, model}` per role from Phase H's role settings; if H has not
   landed, from `writer_model` and `editor_model` read as `provider/model` with
   `llm_base_url` as the OpenAI-compatible URL and one key per provider in
   `config.py`. The `gateway`, `opencode_bin` and `opencode_workspace` keys are
   accepted and ignored on load, with one log line, so an old settings file still
   boots; `gateway: "opencode"` maps to the `opencode-go` provider. `GET
   /api/settings` and `Director.tsx:389-393` show the model that will actually
   answer, per role, and the `director_model_unavailable` error comes from the
   provider's own refusal. Files: `api/director.py`, `config.py`, `api/settings.py`,
   `frontend/src/shell/Director.tsx`, `frontend/src/api.ts`. 1 day.
3. **Retire the gateway.** Delete `director/opencode.py`, `run_gateway_turn`,
   `GATEWAYS`, `close_gateways` and its call in `app.py`, `_test_opencode` in
   `api/settings.py`, `scripts/probe_opencode.py`,
   `tests/test_director_opencode.py` and `tests/test_api_director_gateway.py`.
   Keep `director/mcp.py` and `tests/test_director_mcp.py` (D1) and give the
   module a docstring that says who it is for. Rewrite `docs/ARCHITECTURE.md`
   "Director gateway" as "Director adapter" and fix the `_announce_tool` docstring
   (`api/director.py:87-92`) that still names the MCP process. Migration note in
   the commit and in `docs/ARCHITECTURE.md`: what the old keys meant and what
   replaces them. 0.5 day.
4. **Tokens and money.** `loop.py` collects every `Usage` of a turn (one per model
   call, several per turn) and sums it. New `director/pricing.py` prices a usage
   from the catalogue's per-million input and output prices (cached-input where
   the provider reports it), returning `cost_usd` and `cost_basis:
   "catalogue estimate"`, or `None` with `cost_basis: "unpriced"` when the stream
   carried no usage or the model has no price; never zero. New
   `director/usage.py` appends `{at, turn_id, role, provider, model,
   prompt_tokens, completion_tokens, cost_usd, cost_basis, prompt_hash}` to
   `work/model-usage.jsonl` (D2) and sums per film. The `done` event carries
   `usage` and `cost_usd`; the assistant row in `work/chat.jsonl` carries the same.
   `GET /api/projects/{slug}/costs` gains a `model` block beside the journal's
   pictures. Files: `director/loop.py`, `director/pricing.py`,
   `director/usage.py`, `api/director.py`, `api/projects.py` (costs route),
   `tests/test_director_usage.py`. 1.5 days.
5. **Show the money.** Under each answer in the Director: "1,932 in · 410 out ·
   about $0.004" (or "tokens not reported" when unpriced). In the header: the
   film's model total. In the budget popover (`TopBar.tsx`): a second row
   "Model · $x.xx" under pictures, and the film total as "Pictures $a · Model
   $b". Phase H's Costs section reads the same summary. Pure tests for the
   formatting in `frontend/tests/modelCost.test.ts`. Files:
   `frontend/src/shell/Director.tsx`, `frontend/src/shell/TopBar.tsx`,
   `frontend/src/api.ts`. 1 day.
6. **The loop can keep its thoughts and keep going.** The assistant text that
   accompanies tool calls is written to `work/chat.jsonl` as an assistant row with
   `with_tools: true`, so the log holds the reasoning the model gave between
   calls. `compact_messages` keeps the last eight such snippets (clipped to 200
   characters) in the summary. `MAX_TOOL_CALLS` becomes 40 per turn, plus a stop
   when the same tool fails twice with the same arguments ("The Writer is
   repeating a failed call") and a `continue` option on the chat request that
   resumes the same turn with the same system prompt when the limit was hit; the
   Director shows "Stopped after 40 steps" with *Keep going* and the step count
   while it runs. `generate_images` stops authorising: it returns the quote,
   its price and `needs_owner: true`, and the Director renders that as a priced
   button that calls the existing `POST /images/generate`; the tool's test is
   inverted to "never authorises". Files: `director/loop.py`,
   `director/conversation.py`, `director/tools.py`, `api/director.py`,
   `frontend/src/shell/Director.tsx`, `tests/test_director_loop.py`,
   `tests/test_director_tools.py`. 1 day.

### PR E-2: craft, context, consistency

7. **The craft layer.** New `shared/craft.md` (version 1, at most 380 words):
   a motif system (plant it in the first section, transform it in the middle,
   pay it off in the last chorus); section to structure mapping (a verse states,
   a chorus returns larger and the last chorus is the largest image, a bridge
   turns, an outro leaves one thing behind); a colour script per section (one
   palette and one light per section, written before any shot); lyric literalism
   (never draw the noun in the line; draw what the line does to the person); a
   performance rule for stills (a performer held between two actions, never
   mid-note); fifteen named clichés to refuse (rain on a window, a lone figure on
   a rooftop, neon reflections in a puddle, a hand on glass, a record spinning,
   a city at night from above, a road at dawn, a match struck in the dark, a
   slow-motion hair flick, a crowd with phones up, a mirror split, an hourglass,
   a bird taking off, a candle blown out, a page turned); 9:16 framing (subject
   in the centre third, headroom for text, no horizontal reveals) and the
   sound-off test. `prompts.assemble` loads it after `shared/truth.md` for
   concepts, script_mv, script_ad, prompts, review, revise and import (D3).
   `writer/storyboard.md` v3 and `writer/profile.md` v2 each gain a 120-word
   "Craft digest" (motif pay-off placement, colour script per section, shot
   variety) and `storyboard.md` loses 60 words of repeated coverage prose. The
   budget test covers every task, kind and all four styles. Files:
   `director/prompts/shared/craft.md`, `director/prompts.py`,
   `director/prompts/writer/storyboard.md`, `director/prompts/writer/profile.md`,
   `tests/test_director_prompts.py`. 1 day.
8. **Three new idioms in the examples.** `examples/concepts.md` v3: the good
   routes become an abstract route (colour and rhythm as the subject), a daytime
   pastoral narrative and one performance route; the counter-example stays "three
   grades of one city". `examples/script_mv.md` v2: a daytime pastoral (a field,
   a harvest, a last light) with the same "does the last image change the first"
   test. `examples/script_ad.md` v2 and `examples/storyboard.md` v2: one studio
   product advert (a ceramic bottle on seamless paper) told in both files so the
   pair stays coherent, with the same kinds (card, bridge, product, end card) the
   current pair teaches. `examples/prompts.md` v2 follows the product. Each file
   stays within twenty words of its current length (147, 95, 119, 137, 112).
   `brief.md` and `profile.md` stay. Every current prompt hash changes, so every
   eval page changes; task 17 regenerates the reference runs. Files: the five
   example files. 1 day.
9. **A context that hears the song and sees the references.** `context.py` reads
   Phase B's song map (energy per section, key, downbeats per section, first sung
   line, the twenty-point sparkline as text) for every task; if B has not landed,
   it adds energy and beats per section from `work/music.json` and
   `work/music-deep.json` directly. The treatment is no longer clipped at 420
   characters: the placed passages are listed in full for every Writer task, not
   only storyboard. The references, character sheets and scene plates are listed
   with their descriptions, and `get_images` accepts reference ids and sheet ids
   as well as shot ids, so the model can look at the cast before it writes a
   prompt. Files: `director/context.py`, `director/tools.py`,
   `tests/test_director_context.py`. 1 day.
10. **The evolving look.** `CreativeProfile.sections: list[LookSection]`
    (`id`, `start`, `end` in seconds, `palette`, `light`, `lens`), serialised only
    when set, validated for order and no overlap. `set_creative_profile` and its
    schema accept `sections`; `creative_profile_version` includes them only when
    set. `_creative_image_spec` finds the section that holds the shot's first
    frame and inserts "Section look: palette …; light …; lens …" after the scene
    description (version 3 only, D4; version 2 films never see it, so the golden
    and every existing hash hold). The World tab shows the sections as a strip on
    the Spine with the palette as swatches. Files: `models.py`,
    `production/brief.py`, `production/image_specs.py`, `director/tools.py`,
    `frontend/src/stages/story/*`, `tests/test_image_specs.py`. 1 day.
11. **Compiler version 3.** `production/project.py` gains
    `compile_order(project)` returning `"look-first"` for version 2 and
    `"subject-first"` for version 3 (`prompt_look_first` stays for the legacy
    branches). Version 3 compiles shot text, framing, must-show, section look,
    scene, references, characters, then the look and rules; `brief.avoid` goes
    to `negativePrompt` when the live schema for the model lists it, otherwise
    the prose line stays; the seed is `int(sha256(f"{image_seed}:{shot.id}")[:8],
    16)` per shot when `image_seed` is set, so a redo of one shot never changes
    its neighbours and a shot's seed is stable across versions. Intake writes
    `prompt_version: 3` for new films; the Story Look card offers the switch for
    an existing film with the warning from D4. A second golden-style fixture at
    version 3 pins the new order; `tests/golden/contract.json` is untouched.
    Files: `production/project.py`, `production/image_specs.py`,
    `production/intake.py`, `generation.py` (`image_controls` reads the per-task
    seed), `tests/test_image_specs_v3.py`. 1.5 days.
12. **Character sheets, scene plates and edit-mode redos.** A `sheet` scope in
    `generation.quote_images` builds one task from a synthetic spec (a four-view
    sheet for a character from its identity, a plate for a scene from its
    description, under the film's look) priced and journaled like a still, with
    the result stored under `work/sheets/<entry-id>/vNNN.jpg` and recorded in
    `work/assets.json` under `sheet:<entry-id>`. The World tab shows "Make a
    character sheet · $0.05" per entry, the result, and "Use as reference" (D5),
    which calls `references.import_reference` with the owner's permission and
    binds it; `VisualReference.kind` gains `"sheet"`. Edit mode: `quote_images`
    accepts `edit_from={shot_id: version}`; where the live schema for the model
    accepts a source image for editing (Nano Banana's multi-turn editing), the
    task carries the rejected still as the edit input and the redo note as the
    instruction, journaled as a new version with `edit_of`; where it does not,
    the quote says so and the redo is from scratch as today. The Images stage's
    Redo offers "Edit this one" when available. Files: `generation.py`,
    `services/generation.py`, `api/images.py`, `api/story.py`, `models.py`,
    `references.py`, `frontend/src/stages/story/World*.tsx`,
    `frontend/src/stages/Images.tsx`, `tests/test_sheets.py`,
    `tests/test_edit_mode.py`. 2 days.

### PR E-3: tools, rationale, first draft, evaluation

13. **Typed tools.** `update_shots.changes[]` items are built from
    `Shot.model_json_schema()` minus the edit-owned fields; `update_edit_shots.
    shots[]` from `EditShot` limited to `EDITABLE_SHOT_FIELDS`; `update_edit.edit`
    from `EditDecisionList`. The schemas are generated at import, trimmed of
    descriptions over 120 characters, and a test pins their size so tool
    definitions do not grow past about 6,000 tokens. Files: `director/tools.py`,
    `tests/test_director_tools.py`. 1 day.
14. **Reasons and diffs.** Every write tool takes a required `reason` (at most
    300 characters). A generic before and after diff of the artifact produces
    `changed_fields` (for example `shots.s004.image_prompt`,
    `creative.sections[1].palette`), returned by every write instead of the whole
    artifact (the full artifact stays one `get_` call away). Each write appends
    `{at, turn_id, role, tool, artifact, reason, changed_fields, prompt_hash}` to
    `work/decisions.jsonl`. The `ToolRow` shows the changed fields and the
    reason, and Details shows before and after for each field. `compact_messages`
    adds the last twelve reasons to the summary, and the other role's system
    prompt gets the handoff block (D8); the drawer gets the "Both" view. Files:
    `director/tools.py`, `director/decisions.py`, `director/conversation.py`,
    `director/context.py`, `frontend/src/shell/Director.tsx`,
    `tests/test_director_decisions.py`. 1.5 days.
15. **Five new tools.** `propose_alternatives` (two or three variants of one
    field on one shot or passage, written nowhere; the Director renders them as
    choose-one cards that call the write with the reason "owner chose option 2");
    `batch_update_prompts` (many shots' `image_prompt` with one reason, validated
    as a whole board); `describe_images` (captions per still from the role's
    vision model, cached in `work/captions/<sha>.json` keyed by still hash and
    model, usage journaled in `work/model-usage.jsonl`); `compare_versions` (two
    versions of one shot as thumbnails plus the diff of their input specs);
    `get_preview_frames` (frames from the latest preview at given seconds,
    extracted by FFmpeg from the preview file, as thumbnails, for the Editor).
    Each gets a fake-provider test. Files: `director/tools.py`,
    `director/captions.py`, `tests/test_director_tools.py`. 1.5 days.
16. **One-click first draft.** `services/first_draft.py` runs as a `first-draft`
    job: concepts (one) → script → profile → storyboard → prompts → proof batch →
    seed and suggest a cut → animatic preview. Each model step is one `run_turn`
    with the task named, the Writer told it is drafting (fictional cast only,
    no questions, propose and move on) and a per-step turn limit. Approvals the
    draft needs (brief, storyboard) are recorded as `via: "draft"` with
    `drafted_by: {role, model, prompt_hash, job_id}` (D7); `require_approval`
    accepts `via == "draft"` for brief, storyboard and proof and for nothing
    else. The owner's one authorisation is the dialog "Make a first draft · up to
    $1.00": it shows the ceiling's two parts (D6), the sentence "the cast will be
    invented; confirm them for me", and starts the job. That confirmation is the
    owner's act: the job sets `permission_confirmed` through the owner route only
    for characters the Writer created with an identity and no reference image;
    any character carrying a reference, or whose name matches the brand names,
    the credits or a name in the owner's paste, stops the job at the permission
    gate with "Confirm <name> on Story's Characters card". The proof batch is
    estimated and authorised by the job under the dialog's authorisation, at
    most three stills, never above the reserve part of the ceiling; the model
    allowance is checked before every turn from `work/model-usage.jsonl` and the
    job stops when it is spent. It also stops on a hard report finding that
    survives one retry, and on Stop. Progress appears in the jobs popover as
    steps; stages show "Drafted, not yours" with the one button that makes an
    approval yours. Files: `services/first_draft.py`, `api/projects.py`,
    `production/approvals.py`, `domain/approvals.py`, `jobs/runner.py`
    (kind), `frontend/src/shell/FirstDraftDialog.tsx`,
    `frontend/src/shell/TopBar.tsx`, `tests/test_first_draft.py`. 2 days.
17. **Creative evaluation.** `tests/evals/judge.py`: a rubric with anchored
    descriptors for originality, song-specificity, cliché density and shot
    variety (what a 1, a 3 and a 5 look like, in one sentence each), run only
    with `--judge <provider/model>` and an explicit `--allow-spend`, writing the
    judge's usage to the run's `meta.json`. `tests/evals/lexicon.py`: the fifteen
    clichés from `craft.md` plus about forty more as stems, counted per thousand
    words over treatments, shots and prompts, reported per run and failing
    `--strict` above a threshold set from the reference runs. Shot entropy: the
    Shannon entropy of framing, kind and scene over the board, with a floor.
    Blind pairwise: two runs on the same fixture, order shuffled, the judge sees
    neither hash, the report shows the preference and the judge's sentence.
    Committed synthetic reference runs: one per fixture under
    `tests/evals/runs/reference-<fixture>/`, produced by the scripted fake model
    from the probe tests, so every page has a baseline at $0 and the lexicon and
    entropy checks have numbers to compare against. A fourth fixture,
    `bright-pastoral-120s.json`, whose intent is not a night city. Thumbs export
    stays as it is. Files: `tests/evals/judge.py`, `tests/evals/lexicon.py`,
    `tests/evals/checks.py`, `tests/evals/runner.py`, `tests/evals/fixtures/*`,
    `tests/evals/runs/reference-*/`, `docs/EVALUATION.md`. 1.5 days.
18. **Docs, acceptance and the live tests.** `docs/ARCHITECTURE.md` (adapter,
    money, decisions file, first draft, compiler v3), `docs/EVALUATION.md`,
    `README.md` settings, the screenshot of the first-draft dialog, the live
    tests below and this file's record. 0.5 day.

## Not changing

The money journal and its admission rules; every existing film's approval hashes
(version 2 films compile exactly as today); integer-frame timing; the renderer and
the Player; `tests/golden/contract.json`; the five truth rules and the owner-only
permission gate; Phase H's settings screens (E wires into them); Phase B's song
map (E reads it); the MCP server's tool surface (D1). No new field is serialised
unless set.

## Acceptance

- `uv run pytest`, `uv run ruff check .`, `uv run ruff format --check .`, the
  frontend `tsc`, `node --test` and build, and the renderer `npm test` pass; the
  app starts from a fresh clone with an old settings file that still names
  `gateway = "opencode"`.
- `tests/test_director_prompts.py` proves every Writer task, for every kind and
  all four styles, assembles under 2,000 words with the craft layer in place,
  and that `craft.md` is present in the tasks D3 lists and absent elsewhere.
- `tests/test_contract_golden.py` passes with `tests/golden/contract.json`
  byte-identical; the version 3 fixture has its own pinned prompt.
- Fake-provider probes, no network, no paid call, in the manner of
  `tests/test_director_probe.py`: one scripted Writer and Editor turn per
  provider plugin, with usage present and absent, writing `work/model-usage.jsonl`
  rows whose `cost_basis` is never zero by accident; a scripted first draft on a
  throwaway project with a fake image service, ending in an animatic preview,
  draft approvals recorded as `via: "draft"`, and a real-person stop; a scripted
  turn that hits the step limit and is continued; `generate_images` returning
  `needs_owner` and never calling `authorize`; a reason on every write and a
  `changed_fields` list that matches a hand-made diff.
- `uv run python -m tests.evals` runs at $0, shows the reference runs on every
  page, and `--strict` fails a run whose cliché density or entropy is worse than
  the reference by the set margin.
- **Live tests, each needing the owner's explicit authorisation, on scratch copies
  only, listed with a maximum spend:**
  - E-1 adapter smoke: one Writer turn and one Editor turn on each provider the
    owner has a key for, with an image attached, cost shown per turn. At most
    $0.50 in model spend.
  - E-2 consistency: one character sheet, one scene plate and one edit-mode redo
    on a scratch copy of a real film. At most $0.50 in stills, journaled.
  - E-3 first draft: one draft from the 40 s synthetic song used in the
    assessment and one from a scratch copy of Tree of Love. At most $1.00 each,
    the ceiling itself.
  - E-3 evaluation: the judge over the four fixtures for the prompt hash before
    and after the craft layer, blind pairwise. At most $5.00 (D9).
  - Total across the phase at most $8.00. Spend is measured this time: every
    live turn's usage row is quoted in the acceptance record.

## Risks

- **Providers stream tool calls differently.** Anthropic sends partial JSON
  deltas and Gemini sends whole function calls; the stall logic was written for
  OpenAI chunks. The plugin tests use recorded streams from each, and a provider
  that misbehaves live is a finding, not a blocker: OpenCode Go stays the default.
- **Usage can be missing.** Some OpenAI-compatible endpoints ignore
  `stream_options`. Then the row says "unpriced" and the header says "tokens not
  reported"; nothing shows a zero.
- **Every prompt hash changes in E-2.** The craft layer and the new examples
  invalidate every eval page's history. The reference runs are regenerated in
  task 17 and the old pages stay as history, per T5's rule.
- **Per-shot seeds change the look between shots.** The project-wide seed gave
  the whole film one rendering mood for free; a per-shot seed gives each shot its
  own. The sheets and the look carry identity instead, and version 2 films are
  untouched. If the live test shows drift, the compiler can keep one seed per
  scene instead of per shot; the hash design already allows it.
- **Edit mode depends on the live schema.** Whether Nano Banana accepts a source
  image under the schema the app validates against is only known at quote time;
  the quote says which path it took.
- **A first draft can be mediocre and still cost $1.** That is the point of the
  ceiling and of the draft approvals: nothing it makes is yours until you say so,
  and the proof batch is the only paid step.
- **The judge has taste too.** Anchored descriptors and blind pairs reduce the
  bias; they do not remove it. The judge is a signal beside the owner's thumbs,
  never a gate, as T5 decided.
- **Forty steps is still a bound.** The repeat-failure stop and *Keep going*
  make it visible rather than make it disappear.
- **Phase H and B timing.** If H lands late, task 2 reads the old keys in
  `provider/model` form; if B lands late, task 9 reads the deep analysis
  directly. Either way the settings and context converge when they land.

## Out of scope

The Critic as a third role; generated video and depth (Phase C); the catalogue
and settings screens themselves (Phase H); the song map's computation (Phase B);
the narrative kind (Phase I); transcription through the Director; upscaling;
a shared or cloud chat store; the owner's own lip-sync or performance capture.
