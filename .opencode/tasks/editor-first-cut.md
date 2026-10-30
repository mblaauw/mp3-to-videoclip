# A real first cut — plan

**Approved by the owner, 30 Oct 2026,** with the recommended D1–D8, including up to 6 live Editor turns on a scratch copy.

**Objective:** make a film feel edited rather than played. The Editor cuts a real film for
the first time, stills get more life and more cuts without paying for new pictures, and a
free film look stops them feeling like a slideshow. The owner judges the result by watching
it. Step 1 of the review on 30 Oct 2026; the Critic, the Animator and paid video are later
steps. Base: `main` at `646e5fa`.

## What the code showed

- **Tree of Love's edit is the untouched seed:** 38 hard cuts, 19 holds, no accents, no text,
  neutral grade, and every section's feel `unreviewed`. It is the only film with an edit, so the
  Editor's 23 techniques have never been used on a real film.
- **`seed_edit` is deliberately faithful.** It moves ownership of an approved cut without
  changing it, so it can't become the place for better cuts. Every `zoom_in` seeds as the same
  1.00→1.08.
- **One still means one shot.** `check_board` wants exactly one decision per storyboard shot,
  so an editor can't cut within a still. Tree of Love has 38 stills for four minutes, so its cut
  density can't rise without new paid pictures or a way to re-crop.
- **The longest shot is justified.** Its 31 s `s038` carries the closing credits, so it needs
  movement, not necessarily a cut. The review overstated this one.
- **The Editor can look but isn't asked to.** `get_images` is available to it, yet `edit.md`
  sets anchors without saying to inspect a still, so a push-in can drift away from a face.
- **The Editor isn't told what Track now knows.** Corrected sections reach it, but its prompt
  doesn't use line times, and a cut on a sung line is the most natural cut in a music video.
- **The report checks hold ratio, density and repetition,** but not a long static shot, identical
  travel, or sections with no feel.
- **Nothing in the renderer adds texture.** No grain, weave, drift or directional blur. Holds
  are exactly still. `whip_pan` moves only the incoming shot, with an even blur.
- **Grade is one setting for the film,** applied with CSS filters. `FilmPanel` only displays it.
- **Approvals are safe to extend.** A change to `edit.json` already un-approves the cut and
  Film offers one-click re-approval. Optional fields serialized only when set leave existing
  hashes and `tests/golden/contract.json` alone.
- **The Editor defaults to `deepseek-v4.1-flash`,** a fast model, set in `director/opencode.py`.
  A first judgement of the Editor shouldn't rest on the cheapest model by accident.

## Decisions for the owner

| # | Question | Recommendation |
| --- | --- | --- |
| D1 | Where do better first cuts come from? | A new deterministic **Suggest a cut**, plus the Editor working from it. `seed_edit` stays faithful. A suggestion is shown before saving and can be undone, so it never changes a cut by itself. |
| D2 | How do we get more cuts without paying? | **Crop cuts:** one still cut into several framings inside its shot, such as wide, then hands, then face. Each is a hard jump on a chosen frame, within the existing 1.3× limit raised to 1.6× for crop cuts only, with a warning over 1.4× because stills soften. |
| D3 | What is in the film look? | Grain, gate weave and slow handheld drift, the last so holds breathe. All optional per film, off for every existing film. Halation and atmosphere overlays wait for review of these. |
| D4 | Does the look live in the edit? | Yes, as an optional `grade.look`. It changes the picture, so changing it should ask for the cut's sign-off like any other cut change. Text and titles stay outside it so they remain crisp. |
| D5 | Shot-to-shot colour matching? | Measure first and report outliers, with a bounded trim per shot. Tree of Love's stills already look consistent, so this is last and can be dropped if the report finds nothing. |
| D6 | Live Editor turns? | **Please authorize a capped test on a scratch copy:** up to 6 turns. Previews render locally for free. No images, no spend on stills. |
| D7 | Which model for the Editor test? | One stronger model of your choice for the judged cut, with `deepseek-v4.1-flash` on the same brief for comparison, within the 6 turns. Whichever you prefer becomes the Editor's default, shown truthfully in the Director. |
| D8 | Depth parallax? | A separate **experiment only**, with Depth Anything V2 Small (Apache-2.0, about 100 MB, downloaded once into a throwaway folder) on about 5 stills. It produces clips to judge and adds nothing to the product. The Base and Large models are non-commercial and DepthFlow is AGPL, so neither is used. |

## Tasks (one commit each, one PR)

1. **Give the Editor its material.** A `cut_material` read tool with sections and their names,
   line starts, accent candidates and each shot's passage. `editor/edit.md` v3 tells it to look at
   stills before setting anchors, cut on sung lines where it helps, and write a feel for every
   section. New report warnings: a long shot with no movement, identical travel across a run, and
   sections with no feel. Update eval checks.
2. **Suggest a cut.** A pure planner in `first_cut.py`, going through `timeline.py`/`pacing.py`,
   never ad-hoc arithmetic: move joins to section starts and sung lines within reach, vary travel
   and direction by section energy, and offer accent candidates. Every shot stays covered. Shown
   in Film as a change list with **Use this** and **Not now**, undoable through `cutEditor`.
3. **Crop cuts.** Optional `crops` on `EditShot`: integer frames with a zoom and position. Validated
   in `models.py` and `timing.mjs`, drawn by `BaseFilm` so the Player and the render match,
   accounted for in the report and in cut density, and shown on Film's timeline. An existing
   film's render request stays byte-identical.
4. **The film look.** Optional `grade.look` with bounded `grain`, `weave` and `drift`. A pre-made
   grain tile offset per frame instead of per-frame noise, deterministic by frame number, with
   enough overscan that no edge shows. Measure render time on one film; more than 25% slower
   needs a rethink.
5. **Better whips.** Both shots move and the blur runs along the move. Other transitions keep
   their exact output, and the `docs/primitives/` samples are regenerated.
6. **Film controls.** Grade preset and look in the Film panel, with the Editor able to set them.
   Show the current cut's changes against the seed so the owner can see what the Editor did.
7. **Shot colour check (D5). Dropped after measuring.** 4 of 38 stills on Tree of Love and 3 of 80
   on Zero Bars were outliers by luminance or warmth. Those identifiable look deliberate, such as
   a night scene, so an automatic trim would risk harming them. No code was added.
8. **The real cut, the experiment and acceptance.** See below. Docs and the frontend build.

## Not changing

Stills and source audio, money and image generation, `seed_edit`'s faithfulness, and every
existing cut and approval until the owner saves a new cut. No new paid call of any kind. The
Critic, the Animator and video clips are later steps.

## Acceptance

- `pytest`, `ruff`, frontend `tsc`/tests/build and renderer tests pass. New tests: render requests
  unchanged without the new fields, crop validation, deterministic grain and drift, a suggestion
  covering every shot and changing nothing until accepted, the new report warnings, and no new
  field in the golden contract. No model call in tests.
- On a **scratch copy of Tree of Love** (and Zero Bars for the suggestion):
  - **Before and after to watch:** the seed and the new cut as free local preview renders, full
    length, on one page. The owner's eye decides this, not the report.
  - Suggest a cut works with no model at all.
  - The Editor's cut uses at least sections with a written feel, varied travel and reasons for its
    non-cut joins, and has no hard report findings. Those are the floor, not proof it's good.
  - Same frames in the Player and the render on sampled frames of a look, a crop cut and a whip.
  - Render time, with and without the look.
  - The real films' bytes and approvals unchanged.
- **Parallax experiment:** about 5 stills with the same move, flat and parallax side by side, faces
  and hands included. A written go or no-go, and no product code.

## Risks

- **The Editor may not be good enough yet.** It has never been tested live on a whole film. Suggest
  a cut is the floor if it disappoints, and a poor result is a useful finding.
- **Reports can't judge taste.** A cut can pass every check and still feel wrong, which is why the
  owner watches it and why the Critic is the next step.
- **Crop cuts have a resolution limit.** Stills are 1376×768, so a 1.6× crop is about 860 pixels
  wide on a larger frame. It may look soft; the warning and D2's limit may need adjusting by eye.
- **Grain costs bitrate.** Grain makes files larger and can look blocky after streaming compression.
  Check the file size and a re-encoded sample, not only the master.
- **More choices mean more to go wrong.** Each new field needs the Python model, the renderer's
  validator and the Player to agree. Task 3 and 4 tests pin that.

## Out of scope

The Critic, the Animator, generated video, first-and-last-frame weaves, parallax in the product,
atmosphere overlays, halation, the first-cut runner, sound design and lip-sync.

## Acceptance record, 30 Oct 2026

Run on scratch copies. Real films were only read. No images, no paid image spend.

**Live Editor turns, all six authorized.** Spend wasn't measured.

| # | Model and gateway | Result |
| --- | --- | --- |
| 1 | `gemini-4-argon`, direct | Read its material and 23 stills, then the provider answered 503 |
| 2 | `kimi-k3.1-pro`, direct | Ended at once with no work; the error wasn't captured |
| 3 | `deepseek-v4-pro`, direct | **A complete cut** in about 10 minutes: no hard findings after one rejected accent amount |
| 4 | `deepseek-v4-pro`, direct | Asked to check framing, it said it couldn't see the images and changed nothing, as its rules require |
| 5 | `gpt-6.1-sol`, OpenCode | Couldn't read its own cut: the tool result was truncated to a file. Changed nothing, and said so |
| 6 | `gpt-6.1-sol`, OpenCode | **Saw the stills**, moved 18 anchors and crops, kept all 4 crop cuts, and named 3 shots it couldn't check |

The cut: a warm-cold-warm plan, a written feel per section, a dip to white at the peak, 2 dissolves,
4 crop cuts tied to lines, 7 punch-ins, 2 light leaks, `film-fade` at 0.5 and a light look. It also added
a title and four lyric lines, which nobody asked for: they're real words, but the owner decides.

**Not done from D7:** the comparison with `deepseek-v4.1-flash`. Turns 1 and 2 were lost to the provider,
and turn 6 went on vision. The prompt wording in `edit.md` was also changed during the test.

**Found and fixed in the test.** A refused model call ended a turn in silence. On the OpenCode gateway the
Editor couldn't read a whole cut, so `get_edit` now pages and `update_edit_shots` changes named shots.

**The look.** Grain 0.4, weave 0.3, drift 0.4 on the full film: 772 s against 857 s without, which is noise
since other work ran during the second, so no measurable cost. File size 57 MB to 104 MB. Grain held up on one
frame after a CRF 28 re-encode; a sample of 20 s went from 1.2 MB to 1.4 MB.

**Suggest a cut, no model.** On Tree of Love with line times: 18 joins moved by up to 1.38 s, 38 moves changed,
2 accents, no dissolves, no holds, no hard findings. No holds at all is worth judging by eye.

**Screen.** Suggest a cut, the look controls, crop rows and ticks, and the against-the-seed line all work in
Film. At 0:35.8 the Player showed the same crop and lyric as the MP4, judged by eye on one moment. The whip sample
was regenerated, but no cut here uses a whip, so the new whip has only been seen in that sample.

**Parallax experiment, not in the product.** Depth Anything V2 Small on 5 stills, about 95 MB. Depth maps
separate people from backgrounds cleanly. The go or no-go waits for the owner to watch the clips.

**Colour.** See task 7.

**Found, not fixed.** Two renders at once crashed their browser pages, probably from memory, and both hung for
almost an hour with the progress file still updating and no frames moving. Rendering one at a time worked. A hung
render should fail, not wait.

**Not proven.** The owner hasn't watched any cut yet. Suggest a cut wasn't rendered on Zero Bars, which has no
cut to compare. `s033`, `s036` and `s037` have unchecked framing. No Editor turn has run on a whole film with one
vision model from the start. Render time was measured once each.

Review page: `.opencode/scratch/first-cut-review/` (not committed).
