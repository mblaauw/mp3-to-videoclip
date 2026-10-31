# Faster, trustworthy renders — plan

**Approved by the owner, 31 Oct 2026,** with the recommended D1–D6.

**Objective:** seeing a changed shot in a real render should take under a minute, not 13, and a
render should never hand over a broken frame. Base: PR 54 (`film/editor-first-cut`), which should
merge first because T4 changes its film look.

## What the study and the code showed

**Broken frames are in finished films.** While testing joins, one frame of a render came out as a
3×3 tiled fragment of the picture, for 1/24 s. A scan then flagged 9 such frames across 41,810
frames in 9 files. 8 were looked at and are broken; `suggested.mp4` frame 3454 was flagged only.

| File | Frames flagged |
| --- | --- |
| `stof-en-stilte-final-v004.mp4` | 3945 (2:44) |
| `tree-of-love-final-v001.mp4` | 5593 (3:53) |
| Review `seed.mp4` | 2633, 3151, 3854 |
| Review `suggested.mp4` | 3454 |
| Review `editor.mp4` | 5021, 5027 |
| Test stretch, single pass | 475 (the same frame was fine when rendered again) |
| `forward-ever-base-v002.mp4`, `tree-of-love-base-v002.mp4`, test stretch joined | none |

It happens with PNG and JPEG, with and without the look, and isn't repeatable, which points at the
browser's frame capture. The cause isn't established. In `tree-of-love-final-v001` the titles stay
sharp over the broken picture, so the fault was already in the base. Nothing checks for this: output
verification measures frames, size and audio, not pictures. The scan can miss a glitch in a low-contrast
shot, and only the newest renders of each film were scanned.

**Shot chunks work.** Real frames of the Editor's cut, 8 shots, 600 frames, JPEG at 2 frames at once:

| Measure | Result |
| --- | --- |
| Single pass | 44.6 s |
| Same 8 shots separately, one browser | 48.7 s, about 0.5 s extra per shot |
| One shot alone | 3.9–13.6 s |
| Joining without re-encoding | 0.7 s |
| Joined file | 600 frames, even timing, 14.8 MB against 14.7 MB |
| Similarity to the single pass | 0.990 average, no dip at joins beyond ordinary re-render noise |

Each chunk starts on a shot's first frame, and transitions belong to the incoming shot, so no join falls
inside a transition. This is one test on one stretch; nobody has watched the joined result yet.

**Other things in the code:**

- A chunk's picture depends only on its own shot, and on the previous shot during a transition, plus
  titles and the brand plate where they overlap.
- Accents, text and crops use absolute frames, but move with their shot, so a chunk's key can use frames
  relative to its start. That lets a moved shot be reused.
- **The film look can't be reused that way:** grain, weave and drift use the absolute frame and the shot's
  index, so changing one shot's length would re-render everything after it. See T4.
- **Two renders can still run at once in the app:** the job runner only serializes per project.
- **`_run_streaming` waits forever** on a hung renderer, and has no stop check.
- **Any renderer change clears approvals tied to it.** `implementation_hash` covers `render.mjs`, `src/`
  and `remotion.py`, and preview and titles reviews bind it. PR 54 already does this once.
- Previews and finals bind the movie's bytes and inputs, not how it was made, so chunks don't change what
  an approval means.

## Decisions for the owner

| # | Question | Recommendation |
| --- | --- | --- |
| D1 | Which renders use JPEG frames? | Previews and bases, at quality 95. **Finals stay PNG** until you've watched a JPEG film at full screen and said so. |
| D2 | May a final reuse chunks from earlier edits? | **No.** A final renders every chunk fresh, still in chunks, so a key bug can never reach a delivered film. It keeps the full render time, and finals are rare. |
| D3 | May the look change so moved shots can be reused? | **Yes.** Grain, weave and drift count from the shot's own start and seed from its id. It looks equally random, the Player matches, and no real film has a look yet. |
| D4 | What happens to a broken frame? | **Find it, confirm it by re-rendering that frame, replace its chunk, check again.** A second failure fails the render and names the frame. No silent frame patching. |
| D5 | The two finished films with a broken frame? | **Not part of this plan.** They're never rewritten, so a fix is a new final version through the normal gates. It's your call per film, once T7 is in. |
| D6 | Headless Chrome? | **Decide after this.** It adds about 20% at most, and needs a consented download. |

## Tasks (one commit each, one PR)

1. **Fail a stuck render, and allow one at a time.** A watchdog in `remotion.py`: if the frame count stops
   moving for 120 s (more generous while bundling), kill the renderer and its browser and fail with a plain
   message. Honour a stop request during a render. A machine-wide render lock, so a second render waits and
   says so, covering the app and the CLI.
2. **Broken-frame check.** A new engine module: find frames unlike both neighbours while the neighbours match
   each other, with a low threshold, then confirm each suspect by re-rendering that frame alone, because a real
   flash or dip looks the same to the scan. Calibrated on the frames above, with a planted low-contrast glitch
   in the tests. Results go in the render report. Measure the scan's time on a full film.
3. **JPEG frames per D1.** An optional capture setting in the base request, validated in `request.mjs`. Graphics
   stay PNG for alpha. Golden contract regenerated, with the reason in the commit.
4. **Film look relative to its shot, per D3.** `lookState` takes the frame within the shot and a seed from its id.
   Same function in the Player and the render. `lookState` tests updated.
5. **Chunks and their keys.** Pure Python, new module: split a film at shot starts and compute each chunk's key.
   The key takes everything in the compiled shots **except a short named list of position fields**, so a future
   field invalidates by default instead of serving a stale picture. Implementation revision, size, fps and capture
   settings are all in the key. Tests: changing any field of a sample shot changes the key of the chunks showing
   it; shifting a shot along the timeline doesn't.
6. **Render a list of chunks.** `render.mjs` takes a list of frame ranges and outputs, keeps one browser open, and
   publishes each chunk atomically, so an interrupted render resumes. Progress counts across chunks. Investigate
   the known process-exit delay here, since it would dominate a short render: the test exited cleanly with
   `process.exit` after the browser closed, but the docs record a decision against forcing exit without an
   explanation, so it needs one.
7. **Wire it into `render_base`.** Reuse chunks whose keys match, render the rest, repair per D4, join with stream
   copy, check frame count and timing, and hand the result to the existing mux and verification unchanged. Chunks
   live in `work/remotion-chunks/` with a receipt each, verified on reuse. Corruption fails loudly, as the base
   cache does today. Finals per D2.
8. **Show it, and steady the Player.** Film shows "12 of 38 shots, 26 reused". The Player loads the next shots' stills
   ahead so a jump doesn't show black; measure before and after. Smaller stand-in stills only if this isn't enough.
9. **Acceptance, slow-frame look and docs.** See below. One verbose render to look for the slow step, time-boxed:
   no code unless it finds something clear. Update `docs/RENDER_PERFORMANCE.md` and `docs/ARCHITECTURE.md`.

## Not changing

Stills and source audio, real films and their renders, money and image generation, delivery gates, the alpha graphics
path, the legacy FFmpeg branches, and the Chrome the app uses. No paid call of any kind. No cleanup of old renders.

## Acceptance

- `pytest`, `ruff`, frontend and renderer tests pass; the app starts. No real browser or provider call in unit tests.
- On a **scratch copy of Tree of Love with the Editor's cut:**
  - A fresh full render, with its time. Target under 8 minutes, against 12–14 today.
  - Change one shot's camera and re-render: only its chunks render, the others are byte-identical. Target under
    1 minute including mux and verification.
  - Change one shot's length: later shots are reused, and frames are compared with a fresh full render at sampled
    points to prove a reused chunk shows the right picture.
  - Kill a render halfway: it resumes. Hang a renderer on purpose: it fails within the watchdog's limit.
  - Scan the finished film: no broken frames. Plant one: it's found and repaired.
  - Same frames in the Player and the render on sampled frames, including a look and a transition.
  - The joined MP4 plays through its joins in QuickTime and the browser.
- **The owner watches** one JPEG film and its joins, which decides D1 for finals.
- The real films' bytes unchanged.

## Risks

- **A wrong key would show a stale picture,** the worst failure here. T5's rule, the comparison in acceptance and D2 are
  the defences.
- **Approvals tied to the renderer clear once.** Any film reviewed under the old renderer asks for its check again.
- **Disk grows.** Each new set of chunks adds to `work/`, at about 100 MB for a whole film, and the repo's rules mean nothing
  is cleaned up. An explicit, owner-run clean-up can follow if it matters.
- **Chunks are separately encoded,** so quality could shift slightly at a join. The numbers show nothing, but only watching
  will settle it.
- **The broken frames' cause is unknown.** The check treats the symptom, and it can miss low-contrast glitches. A frequency test
  at one frame at a time, in T2, may show whether concurrency matters.
- **The numbers come from short stretches.** The full-film times above are targets until T9 measures them.

## Out of scope

Headless Chrome, a non-browser renderer, GPU and hardware encoding, half-size previews, faster model variants, and re-rendering the
two finished films.

Evidence: `.opencode/scratch/render-speed-study/` (not committed).
