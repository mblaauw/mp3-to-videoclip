# The Museum of Tomorrow 001: The House Key: proving the story film

**Owner, 2 Nov 2026:** test the short story film on this concept, cap $5, voice `English_magnetic_voiced_man`. Episodes for YouTube.
Claude acts as owner in the Studio, on the standing "approve things yourself". The owner's bible said a female curator; the owner's
voice choice overrides it, and the curator's words stay as written.

## Found by making the film, and fixed

| Found | Fix |
| --- | --- |
| The default voice `English_Magnetic_Male_2` was never on MiniMax's schema | The real id, `English_magnetic_voiced_man`, in the catalogue and default |
| A story film could not be 140 s | 140 is a length; the budgets scale with it |
| `gpt-6.1-sol` through OpenCode Go answers 400 "Model is unavailable", and the Writer said only "error 400" | The refusal names the model and points at Settings. Roles moved to `gpt-6-luna`, the first model of the owner's to answer through Go |
| The only small text styles sat in a dark chip that read as the lower third the bible bans | `gallery_title` and `gallery_label`, fine spaced capitals on the picture, set in Fraunces by the film's grade |
| The Editor layered text over an end card that draws its own, doubling the title, and no check said so | A `text_over_card` warning |
| No story film could ever buy its stills: with no source hash it read as an old film, so the full set needed an approved preview, and a preview with placeholders can never be approved | The guided marker of a soundtrack film is its own by slug |
| The Studio's package and vertical-version buttons were always refused, "invalid render kind": their tests called the engine directly | The runner knows both kinds, and a test pins every kind the routes name |

Four render browsers stalled twice more on this 16 GB Mac (two previews queued together, then a final); one browser passed every time, about 8 minutes for 140 s. The launch config sets `STUDIO_RENDER_WORKERS=1`; the guard's cause is still unproved.

## The film, final v004

140 s to the frame, 3,360 frames scanned, none broken, -16.0 LUFS, -1.9 dB peak. `projects/the-museum-of-tomorrow-001-the-house-key/`, with its package.
The spoken lines match the owner's text word for word by script. 20 shots: 19 stills, one reprise of the key for the end, two clips in the cut.

**Cost:** $1.44 spent of $5, with $0.50 still reserved. 23 voice takes $0.12; 23 stills and 2 sheets about $0.90; 2 clips $0.42. 8 of 25 live turns on `gpt-6-luna`, plus 1 lost to `gpt-6.1-sol`. Model use isn't priced.

Proved for the first time on real providers: narration through the journal, sheets as references, era stills, `videoInference` clips, the Critic on `gpt-6-luna`. The journal held when a clip did not return: no new spending, nothing charged twice.

## Not done or not proven

- **Clip s018 (fingers closing) is stuck.** Task `220e9503-5a86-4c8f-9cc3-7b4a96e2a503`: Runware said processing, then 504 for over an hour. $0.21 of the reservation is held and the journal refuses new spending until it resolves. `clip recover` collects it and never resubmits. If it is never returned, `clip resolve-task` records what the billing page shows.
- **Not bought because of that:** the final light fade (s020 needs its own still and clip, about $0.25) and the upscales (under 1 cent). The bible's "spotlight fades" is not in the film: the key stays lit.
- **Nobody has heard it.** The voice, its pacing and the 140 s of narration over silence need the owner's ears. Sound design doesn't exist: no signature, ambience or music, and the Studio can't make them, only mix files it is given.
- **Nobody has watched it in motion.** Frames were sampled; the Critic saw frames too. Holds are many, so it may feel like a slideshow.
- **The bible's female curator** is a man's voice by the owner's decision.
- **The look preset** was replaced by the owner's words after the Writer chose a painted preset that said "never a photograph".
- **The Writer put a voice id in the narrator's era field,** and the Editor's type needed correcting twice: frames, not the report, showed both.
- **Small:** a change of label colour in the cut makes the stills approval stale. The title's small type on Script overlaps the next-step strip when the page opens scrolled. The beat meters show pauses as overrun in red. `caption_overlap` fires on layers that sit apart, top and bottom.
- **Vertical version and one-click first draft** were not run: this film is 16:9, and a first draft refuses a story film.

## Tool fixes after the film, 2 Nov

Owner: "make all fixes that are not related to the actual content productions."

- **The render stall was not memory and not a sleeping Mac.** A browser finished every chunk, wrote its summary, removed its progress file and stayed alive, because `render.mjs` never told Node to exit. The Studio ended it after 120 s and failed the render. A first theory, that long encodes looked like stalls, was tested on a scratch copy and was wrong: it was reverted. With the exit, four browsers on the same 140 s film went from a failure at 303 s to a pass in 209 s, against about 8 minutes with one. The memory guard's count of inactive pages is unchanged and unproved either way.
- A fresh install defaults to `gpt-6-luna` through OpenCode Go for every role. An OpenAI key alone now needs a role changed in Settings.
- The song map is held in memory. An old `work/song-map.json` stays where it is, unread. Other read paths were not audited for writes.
- A stuck paid task shows under the budget, with a free re-check and a settled amount that needs evidence. Live, on s018, it reported the provider down and spent nothing. Settling it was tested only on a fixture.
- A clip batch stops at the first clip still out, so one slow clip no longer fails the job.
- Only speech overruns a beat. `caption_overlap` looks at where styles sit, and that table is by hand: it must follow `BaseFilm.jsx`.
- The two-row top bar cannot become three rows or run into the budget, and the Director opens under it. Checked at 1440, 1024, 800 and 375.

**Left as designed:** a change to the cut makes the stills approval stale, because that approval signs the cut, and the bar already says "Approve this cut". Removing it would un-approve every existing film's hash. A change to a local shot makes the style check stale, because local proof entries are part of it.

**Not fixes, so not done:** reuse across a series, a first draft for story films, sound generation, and `legacy/` and the `openai` upgrade, which are the owner's calls. "Stale storyboard message blames timing", from the Cool Cat run, was not reproduced or changed.

## Maintenance run, 2 Nov

Owner: "do a total maintenance run... clean clean clean."

- **Proved through the Studio's own routes, on a scratch copy of the Museum:** final, then 9:16 and 1:1 versions, four browsers, 233 s, 229 s and 161 s, 3,360 frames each, none broken. Subjects hold on real stills and long type wraps. Every 9:16 shot is flagged soft, since the crop enlarges a 768-high still; square has none. A version needs a current final, so a renderer change means one free re-render first.
- **Removed:** six unreferenced names, the schema 1 migration no route reached, stale frontend exports. Backend routes and frontend calls match.
- **The `openai` 3.x upgrade (PR 71)** behaves the same as 1.x through the Director's adapter against a real local streaming socket, and 35 Director tests pass. On 3 Nov, on the owner's word, one live probe through OpenCode Go streamed text, called a tool and reported usage, and it was merged. That probe sent no picture and no tool result back, though its header said it did.
- **Renderer `npm audit`:** `zod` (high) and `fast-uri` (moderate) sit in Remotion's dev packages, reached only on this computer. The fix moves the renderer's lock, which un-approves every film's renderer sign-off, so it waits for a chosen upgrade.
- **Metadata snapshot:** `backups/projects-metadata-20261102T185739Z.zip`, with the Museum. An off-machine copy is still unchecked.

**Left for the owner:** remote branches, two unmerged local branches and two local branches ahead of their remotes, all from merged or closed PRs; 1.9 GB in `.opencode/scratch`; 7.6 GB of rebuildable caches, by `scripts/clean_caches.py --yes`. `legacy/` also waits: `graphics.py`'s source is in the renderer's hash, so removing the drawers it alone uses would un-approve films.

## Making it better, 3 Nov

- **Text over text is measured, not looked up.** `caption_overlap` places each layer where `BaseFilm.jsx` draws it, wraps its words at the film's width and flags two layers whose lines come within 2% of the frame. A test reads every number back out of the renderer, so the hand table can no longer drift. A logotype over a title, and a title long enough to wrap down into a tagline, are now caught; the four films on disk give the same warnings as before.
- **A voice id in the narrator's words is refused**, by the profile tool and by a brief patch, and named: "put it in voice_id". This is the slip the Writer made on this film.
- **The live probe does what it says.** `scripts/probe_llm.py [role]` goes by the role's own route, sends a picture and sends the tool result back, and exits non-zero if any check fails. A recorded stream tests it; it has not been run live in this form.
- **The Script title over the next-step strip** did not reproduce, scrolled or not, at 1024 wide. The top bar rework of 2 Nov is the likely fix.
