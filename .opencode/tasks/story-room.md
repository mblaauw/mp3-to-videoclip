# Story room — plan

**Approved by the owner, 30 Oct 2026,** with the recommended D1–D6 and D7 authorized: a
capped live Writer test on a scratch copy only. No image generation.

**Objective:** turn Story from a long form into a room with a clear start. You begin
either from your own idea or by asking for 1, 2 or 3 concepts from the music. Concepts
compare on the song, and the chosen story reads like a script against the music. As
tried in the prototype (`.opencode/scratch/story-room-prototype/`, 30 Oct 2026). Base:
`main` at `719ec3e`.

## What the code showed

- **Three is hard-coded in five places:** `Treatments` (`min_length=3, max_length=3`),
  `director/prompts.py` (`len(concepts) < 3` routes back to concepts),
  `writer/concepts.md` and its example, `tests/evals/checks.py` and the rubric.
- **Today's import does the opposite of what's wanted.** "I already have a concept" is
  collapsed, saves everything as the treatment, then prefills the Writer with "improve
  only what is weak… then propose three structurally different concepts."
- **`select_task` needs a chosen concept** before it moves on to the script, so an idea
  with no concepts has no route today.
- **Concept beats are prose.** `shape` is 4–6 free strings with timing inside the text
  ("0–49.6 s (0.25, 0.24): …"); the prototype reads them with a regex.
- **`work/treatments.json` isn't in any approval hash,** and has history. Timing and
  concepts can change without un-approving anything; `brief.json` can't.
- **The brief already has the fields to sort into:** `treatment`, `direction`, `style`,
  `visual_rules`, `avoid`.
- **The Writer runs only as a chat turn,** prefilled by `studio:ask-director` and sent by
  hand. The buttons here need it to send on your click.
- **The Spine already serves Story,** including promo/advert excerpt handles, so Story
  keeps it rather than getting a new timeline.

## Decisions for the owner

| # | Question | Recommendation |
| --- | --- | --- |
| D1 | How strict is "your words stay yours"? | Strict. Your paste is kept untouched in an append-only `work/idea.jsonl`. Sorting may only assign your sentences to Story, Style or Rules: the server refuses any sorted text that isn't verbatim from the paste. Changes to wording are separate proposals you accept. |
| D2 | Where does sorted text go? | Story to `brief.treatment`, Style to `brief.style`, Rules to `brief.direction` (`avoid` when it's a "no…" rule). No new brief fields, so hashes keep their meaning. |
| D3 | Where do story timings live? | A new `work/story-beats.json`, outside the brief, so placing or retiming beats never un-approves the story. |
| D4 | When does the Start screen show? | On a new film with no story, as the opening view. On a film with a story, Story opens on the script and Start stays one click away. Starting over there first says what gets un-approved. |
| D5 | Promo and advert films? | Keep their brief card (objective, message, call to action) above the Start choice this phase. The prototype never covered them, so please look at them in review. |
| D6 | Do World and Credits get redesigned now? | No. Their current cards move into those tabs unchanged. The picture-based world bible, cost warnings and in-place rewriting are later work. |
| D7 | Are real Writer calls allowed in acceptance? | Please authorize a capped test on a scratch copy (real model calls, roughly a few cents each going by earlier probes). Automated tests use a fake model, and the rules forbid live calls without your word. Without it, sorting and timing quality stay unproven. |

## Tasks (one commit each, one PR)

1. **Split the screen, no behaviour change.** `stages/Story.tsx` (600 lines) becomes a data
   hook plus parts, in the tabs Concept, Story, World and Credits, with the next action in
   the top bar as on Film.
2. **1–3 concepts.** `Treatments` accepts 1–3; structures must differ only when there's more
   than one. `Concept` gains optional structured `beats` (start, end, label, text); `shape`
   stays readable for existing films. Update routing, `writer/concepts.md` (v3: writes the
   requested number, with beats), its example, the tool schema, eval checks and rubric, so
   each prompt version gets its own eval page. No change to approval hashes.
3. **Your idea, sorted.** Append-only `work/idea.jsonl`, a `writer/import.md` task and a
   `sort_idea` tool that enforces D1. Routing treats a brief with a treatment and no concepts
   as ready for the script. If the Writer is unavailable or fails, the paste is saved whole as
   the treatment, nothing is lost, and the screen says so.
4. **The Start screen.** The two choices from the prototype: the idea box, what was measured,
   and 1, 2 or 3 (default 2). The click sends the Writer turn with the Director open, so you
   see the work. A paste with no story offers "write 1, 2 or 3 within this", and the Writer is
   told to keep to your style and rules.
5. **The concept room.** The song, one row of beats per concept, playing a beat with sound, and
   the signature moment, why, world and risk. "Build on this" chooses; "Also suggest a concept"
   or "Ask for another" stops at three. Old concepts fall back to parsing `shape`, then to
   untimed text.
6. **The story on the song.** A `place_story` tool and `work/story-beats.json`, validated:
   whole words unchanged, in order, inside the film. The script view lights the passage as the
   song plays, with the still at that moment once one exists, and bands on the Spine. Each
   passage edits in place through the existing brief save. Passages with no placement or edited
   since read as "not on the song yet", not a guessed time.
7. **Move and finish.** Move a sentence between Story, Style and Rules. Narrow layouts, keyboard
   (Space after a mouse click), remove dead CSS, docs.

## Not changing

Money, rendering and image prompts. The meaning of the approval hashes: a story edit still
un-approves the story, as today. Existing films' files: nothing is migrated, and their three
concepts still read.

## Acceptance

- `pytest`, `ruff`, frontend `tsc`/tests/build and renderer tests pass. New tests: the verbatim
  refusal, 1/2/3 concepts, routing without concepts, beats validation, and old `shape` parsing.
- On a **scratch copy**, with a fake model for the scripted paths, and real calls only if D7 is
  authorized:
  - paste a mix and see it sorted, with no word changed, then move a sentence;
  - paste only style and write 1, 2 and 3 concepts within it;
  - ask the music for 1, 2 and 3, compare them, choose and read the story against the song;
  - make the first shots from it, to prove the next stage still works;
  - Tree of Love and Zero Bars open and read as before.
- Every current Story function stays reachable: approval with its change list, ratings, look,
  profile, characters, credits, promo/advert brief card and excerpt handles.

## Risks

- **Sorting quality.** The verbatim check protects your words but can't judge the sorting, so
  moving a sentence is part of the scope, not a nice-to-have.
- **Placement quality.** A Writer's timing can be plausibly wrong. It stays editable, and untimed
  passages say so.
- **Prompt changes affect all new concepts.** Versioned prompts and the eval pages make that
  traceable; only D7 tests real output.
- **Passages and timings can drift** when you edit. Beats are matched by text, and a mismatch
  shows as "not on the song yet" rather than a wrong time.

## Out of scope

The picture-based world bible, cost-before-change warnings, Writer rewrites in place, lyric-to-
section links, and redesigning the promo/advert brief card.
