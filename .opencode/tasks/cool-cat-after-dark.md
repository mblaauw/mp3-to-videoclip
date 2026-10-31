# Cool Cat After Dark: prove the tool on new films — plan

**Approved by the owner, 31 Oct 2026,** with the recommended D1–D9, except D3: the owner chose
**MiniMax Speech 2.8 HD, voice `English_Deep-VoicedGentleman`.** Authorized: up to $10 on images and voice,
up to 25 live turns.

**Objective:** make a 70 s promo, then a short advert, from song to final through Studio, fixing the
tool wherever the films show it falling short. Old productions are parked and not finished. The films
are the test: the work counts when the owner watches the result and the tool made it, not hand-edited files.

## What the code and the track showed

**Old productions.**
- Nothing called After Dark exists. The old film is **Cool Cat: After Hours**, slug `cool-cat-after-hours`,
  already in `archive/projects-2026-10-24/`. Studio doesn't list it and its slug can't collide, so
  **nothing needs renaming or moving**.
- Its cat is a different character (graphite grey, mirrored sunglasses, human crowd). Nothing is reused from it.
- `projects/` holds Forward Ever, Stof en Stilte, Tree of Love and Zero Bars. Studio has no way to park a film.

**The track.** `Midnight Brass.mp3`: exactly 70.000 s, 48 kHz stereo, with cover art, instrumental per the owner.
Measured, not listened to; nobody on this side can hear it.

| Time | What the audio does | Script expects |
| --- | --- | --- |
| 0–6.2 s | Quiet intro, almost no highs | Quiet until 9 s: fits |
| 6.2–13.0 s | Highs open up, bass still light | Filtered kick at 9 s: roughly fits |
| 13.0 s | Kick and full bass arrive | Percussion builds at 17 s: 4 s early |
| 27.6–30.0 s | **The only break** | Groove stops at about 35 s: **5 s early** |
| 30.0 s | **Full groove returns** | Reveal at 35 s: **5 s early** |
| 60.5 s | Brief dip in the bass | Brand section at 61 s: fits |
| 65–68.5 s | Falling away, last hit near 68.3 s | Clean ending: fits |
| 68.6–70 s | Near silence | Hold the card: fits |

Tempo measures about 112 BPM against the script's 110. The script's rain, thunder, chime and crowd cheer
can't be confirmed from measurements.

**What the tool can't do yet.**
- **No voiceover at all.** The script has six spoken lines, and nothing in the code handles speech.
- **No painted style for a promo.** Promos and adverts offer three styles, none of them painted. The only painted
  preset is reserved for music videos.
- **No moving pictures.** The script's puddle ripples, door opening and sweeping camera can only be suggested with stills.
- **No judge of taste,** and the Writer and Editor have no measured baseline.
- **Two model settings disagree.** The gateway is `direct`, with `deepseek-v4.1-flash`, while the only Editor pass
  that could see stills ran on `gpt-6.1-sol` through OpenCode.

## Decisions for the owner

| # | Question | Recommendation |
| --- | --- | --- |
| D1 | How do films get parked? | **A parked list in app settings.** Parked films move to a collapsed group on the home screen, and one click brings them back. No project folder is touched or moved. |
| D2 | The script's clock or the track's? | **The track's.** Same eight sequences, same order and words, retimed to the music as below. The reveal lands on the real return at 30.0 s, and the door opens into the real break. |
| D3 | Where does the voice come from? | **Owner's choice: MiniMax Speech 2.8 HD, `English_Deep-VoicedGentleman`,** through the money journal. Its price is quoted before the first line. Any voice file can also be used, so you can replace it with your own recording. |
| D4 | Sound effects? | **Not in this plan.** First find out by listening what the track already contains. |
| D5 | Motion? | **Stills, camera moves and the film look first.** Paid clips for the few shots that need them are a separate go-ahead with a price, once the cut exists. Parallax waits for your verdict on the clips you already have. |
| D6 | What may I spend? | **Up to $10 in total on images and voice** across both films, and **up to 25 live Writer, Editor and Critic turns.** Model spend isn't metered, so the turn count is the only limit. |
| D7 | Which model? | **`gpt-6.1-sol` through OpenCode for every role, from the first turn,** which means changing the gateway setting. It's the only one seen working with stills. |
| D8 | Who makes the choices? | **I act as owner, in Studio, using the browser.** The Writer and Editor do their own jobs. If one fails, I fix the tool and run it again, and say so. I stop once for you: **at the style check, before the full set of stills is bought,** since the cat's look decides the film. |
| D9 | What's the advert? | **30 s, cut from the promo's music,** made after the promo and reusing its stills as uploads, plus a few new ones if needed. It tests the excerpt window, fades and the advert rules. Message and CTA come from your text: "Find the second heartbeat", "Enter After Dark". |

**Retimed sequences (D2):**

| Sequence | Script | Track | Why |
| --- | --- | --- | --- |
| 1 The sleeping city | 0–9 | 0–6.2 | The quiet intro |
| 2 The signal | 9–17 | 6.2–13.0 | Ends as the kick arrives |
| 3 Follow the pulse | 17–26 | 13.0–22 | The groove carries the walk |
| 4 The door | 26–35 | 22–30.0 | The door opens into the break |
| 5 The reveal | 35–44 | 30.0–40 | The groove returns on the reveal |
| 6 The experience | 44–52 | 40–50 | Fast inserts on the beat |
| 7 The second heartbeat | 52–61 | 50–60.5 | Ends on the bass dip |
| 8 The brand | 61–70 | 60.5–70 | Card up as the music falls away, then held |

The Editor sets the exact frames from the song's analysis.

## Tasks (one commit each)

**Phase 1: ready to make the promo (one PR)**

1. **Park old films (D1).** Settings, API and home screen. Tests prove no project folder changes.
2. **Painted comic noir style.** A new preset from the owner's style bible, offered for promos and adverts. No artist names in prompts.
3. **Voiceover in the engine (D3).** Lines with integer-frame starts in the contract. A voice task goes through `generation.py`, so
   it's quoted, journalled and recoverable. Lines are immutable versions, like stills. The music is lowered under speech
   into a derived mix in `work/audio/`, the way excerpts already work, so the source MP3 is never changed. Changing a line
   re-mixes the audio without re-rendering pictures. Existing films' requests and the golden contract stay unchanged.
4. **Voiceover in Studio.** Write, generate, listen, replace with a file, and move lines on Film's timeline. The Player plays the mix.
   Writer and Editor can see and propose lines.
5. **One model for the crew (D7).** The Director shows which model is running and whether it can see images, and warns before an
   Editor turn that can't.

**Phase 2: make the promo (fixes go in as numbered commits, one PR)**

6. **Make it through Studio.** Track, Story (your text pasted as written), Storyboard, style check, **stop for the owner**, Images, Film, final.
   Each defect found gets a fix and a test, then the work continues. A log records each step, what broke and what it cost.
7. **The final, end to end.** The first through shot-by-shot rendering, with the broken-frame check. PNG frames, as already decided for finals.

**Phase 3: judge and measure (one PR)**

8. **The Critic.** A new role that watches frames of a cut against the brief and writes specific notes. It advises and can't change anything.
9. **Live evaluation baseline.** The first live pass of the evaluation harness, recorded as the baseline for later prompt changes.

**Phase 4: make the advert (fixes as in phase 2, one PR)**

10. **Make the advert (D9),** with the Critic in the loop. This is the first real test of the advert path.

**Phase 5: housekeeping (one PR)**

11. **CI** also runs the format check, renderer tests and frontend tests.
12. **Dependency PRs.** Merge the safe ones. Report on the `openai` and `vite` major upgrades rather than taking them blindly.
13. **README and docs** brought up to date, including what the two films proved.
14. **A fresh metadata backup,** with the off-machine copy reported on. A clean-up command for caches and old chunks, which **only you run**.

## Not changing

Old productions, their stills, approvals and renders; `archive/` and `backups/`; the source MP3 in Downloads; legacy
FFmpeg and Pillow branches, which wait until these films prove the current path. No paid clips, sound effects or lip-sync.

## Acceptance

- Each phase: `pytest`, `ruff`, the format check, frontend and renderer tests green, and the app starts. No live call in tests.
- A fresh `work/` for each film; nothing hand-edited in a project folder. Any exception is logged.
- **The promo:** 70 s to the frame, no broken frames, stills in budget, words and order as written, type composited rather
  than painted into images, the same cat throughout, and the music unchanged apart from the lowering under speech.
- **The advert:** brand visible in the first 5 s, an end card held at least 3 s.
- Old productions byte-identical at the end, checked by hash.
- **You watch both films.** Your verdict decides whether they're good; passing every check doesn't.

## Risks

- **Character drift is the biggest creative risk.** Faces drifted on Tree of Love, and this hero must hold up through close-ups. The style
  check is there to catch it early, and a painted anthropomorphic cat is untested with the current image model.
- **The voice may sound synthetic** and can't be judged from here, because I can't hear audio. Only your ears can pass it.
- **Stills can only suggest parts of this script.** Ripples, the door opening and the camera sweep may be the first place it feels like a slideshow,
  which is what D5's later decision is for.
- **Timing was measured, not heard.** The retimed sequences may need adjusting once you listen.
- **Model costs remain unmeasured,** so D6 limits turns rather than money.
- **The tasks are a lot of work.** Phases 1 and 2 give you a film to watch; the rest can be cut or reordered then.

## Out of scope

Paid video clips, parallax in the product, sound design, lip-sync, finishing any old film, and portrait versions.

## Run log

**Phase 1 done, 31 Oct:** parking, the painted style, voiceover engine and panel, and the true model name are committed. Voiceover hasn't
been used live, and its panel hasn't been opened in the app. Lines are placed by time or playhead, not by dragging on the timeline as planned.

**Promo so far.** 7 of 25 live turns, all on `gpt-6.1-sol`. $0.21 of images: 6 stills at about 3.5 cents. No voice spend.

The paste left out the script's old timecodes and "Audio:" lines, per D2 and D4. Everything else is the owner's wording.

Found by making the film, and fixed:

| Found | Fix |
| --- | --- |
| A promo couldn't use a whole track or be instrumental | The form now reads the code table and offers both |
| Tabbing through the brief lost typed words | Saves queue the newest value; a reply can't overwrite newer typing |
| The Writer's 28 shots were refused: a board could never outgrow its skeleton | `write_storyboard`, refused once a cut exists or if it drops a paid shot |
| `update_shots` returned a board too big for the gateway | It returns only the changed shots |
| The skeleton ignored the owner's sections | It cuts on them |
| The brief's Avoid list never reached the picture prompt | It joins the profile's list |

Found, not fixed:

- **References are CLI-only.** Studio can't set a character's reference image, which is probably part of why faces drift.
- **The Director covers the next-step button** at about 1024 px wide.
- **Tool results show as "showing 0 lines… saved to" a file path** in the Director.
- **Section edges from analysis ran about 0.6 s late** against the bass (13.58 and 30.70 s against 13.0 and 30.0 s). The owner's sections corrected this film.
- **Copy:** "The brief must be approved first" shows when it's approved, and "8 measured" describes owner-set sections.
- **Image rules bind every shot,** so a rule about one object can spread. The Writer needs telling.

Style check, round 2: the owner approved the look and asked for the hero's reference.

**Promo final v003, 31 Oct.** 70 s to the frame, 1,680 frames, 28 chunks rendered fresh, no broken frames, in about 4 minutes.
$1.27 of $8: $1.24 on 35 stills, $0.024 on 6 voice takes. 13 of 25 live turns, all on `gpt-6.1-sol`, none lost to a provider.
The 4 old films' 3,269 files are byte-identical to their fingerprint from before this work. The source MP3 is unchanged.

Found after the style check, and fixed:

| Found | Fix |
| --- | --- |
| Reference images were CLI-only | A crop control in Images makes a still a character's reference |
| A remake from a changed prompt left the old still selected | A still from the current prompt replaces an outdated selection |
| The one-correction limit was a dead end in Studio | A new round, with a stated reason |
| A paid question could appear off screen | It scrolls into view |
| Speech sat 3.5 to 6 dB over the groove | About 8 dB now, measured in the final |
| Reprises couldn't reframe, so their cuts changed nothing | A crop may start on a shot's first frame |
| Words on a picture were dropped silently | The report names them, and uncropped reprises |
| The brand card was a template | Logotype, tagline and CTA text over a painted card |
| One Writer save removed the hero's reference, cut the look to fit a word limit and made all 24 kept stills out of date, unreported | References survive, a preset counts only its note, and a change names the stills it affects |
| The card's words faded out before the end | `fade_in` holds to the last frame |
| Adding `fade_in` broke the report and Film's summary | Fixed, and every animation is tested |

Restoring the brief's exact text brought back every approval and still at no cost, which is the content-bound design working.

Still open:

- **Nobody has heard it.** Speech level and mix were measured; the voice, its timing and the track's own rain or thunder need the owner's ears.
- **Nobody has watched it.** Frames were sampled at about 45 moments, not played.
- **Motion.** Stills, camera moves and film look only. The ripples, door and camera sweep are suggested, not moving.
- **The cut's rhythm** alternates push and hold, a little mechanically. 10 stills went unchecked by the Editor; I looked at all of them on contact sheets.
- **The Editor's notes are out of date:** they still say "no new crops", because nothing asks it to update them.
- **A brand card made from a scene** raises advert checks on a promo, because they look for an `end_card` shot. Phase 4 needs this.
- **Small:** the storyboard stale message can blame timing when only the brief changed; Director tool results show a raw file path; the Director covers the next-step button at 1024 px.
- **The promo's first 5 s** carry no brand, by the owner's script, and the report warns about it.
