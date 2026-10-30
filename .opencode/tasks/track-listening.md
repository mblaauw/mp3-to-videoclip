# Track listening room — plan

**Approved by the owner, 30 Oct 2026,** with the recommended D1–D8.

**Objective:** turn Track from a table of measurements into a place where you listen to
the song. The words are put on the song automatically and for free, the lyric tags
propose the song's real structure, and you correct it by ear with nothing you can't
undo. As tried in the prototype (`.opencode/scratch/track-listening-prototype/`) and
measured in `.opencode/scratch/lyric-timing-test/`. Base: PR 51's branch; PRs 48–50 are still open.

## What the test showed

Two songs, local tools, no provider call. Only Stof en Stilte has a reference: its nine
section starts by ear.

| Method | Within 5 s of a section start | Typical gap | Worst gap |
| --- | ---: | ---: | ---: |
| `work/music.json` (what Track uses) | 5 / 9 | not calculated | 61 s |
| `work/music-deep.json` | 7 / 9 | about 4 s | 7.9 s |
| Parakeet on isolated vocals | 8 / 9 | 0.2 s | 5.1 s (a 0:00 start before the singing) |
| stable-ts on isolated vocals | 9 / 9 | 0.6 s | 3.0 s |

- Words heard exactly: 93% English, 80% Dutch rap. Good for timing and for a draft, not
  good enough to keep unread.
- On Tree of Love the tags found a hook at 1:50 and the outro at 3:12, inside two long
  sections the analysis didn't split.
- Isolating vocals changed little except the outliers: the full mix put the Tree of Love
  outro about 3 s early.
- Parakeet leaves out what it can't place. stable-ts places every word by design, so it
  can't report a miss.
- Time: about 1m45 per song to isolate vocals on an idle CPU, and about 4m30 through the
  app with the Studio running; under 10 s for Parakeet.
- Line timing has been judged by the owner's ear on Tree of Love only.

## What the code showed

- **`work/music.json` and `work/lyrics.json` sit in the approval chain.**
  `stage_hash("brief")` includes its upstream `lyrics`, and `lyrics` includes `analysis`.
  Writing times or new edges into either file would un-approve every later stage.
- **Tags are already kept.** Pasted `[Spoken Hook]` lines stay in `lyrics.lines`, but LRC
  parsing and `save_lyrics` have no way to hold times next to untimed tags.
- **`music_notes.save` refuses any start that isn't measured,** and has one name per
  measured section, so it can't hold a moved edge.
- **`edits._section_names` matches names to the cut's sections by position.** A map with a
  different number of sections would shift names on existing cuts.
- **`edits._seed_sections` reads `music.json` only when a cut is first seeded.** Existing
  cuts keep their sections, so new edges can reach new cuts alone.
- **`/analyze` always re-measures** and rewrites `music.json`, so it can't be the reset.
- **The Spine and its player are already under Track,** with the waveform, sections and
  playhead. The prototype's strip at the top would be a second player.
- **The project needs Python 3.12–3.13,** while the test ran on 3.11 with `torch` 2.5.1
  pinned for Demucs. A private environment keeps them apart.

## Decisions for the owner

| # | Question | Recommendation |
| --- | --- | --- |
| D1 | How do the tools get installed? | A private environment with pinned versions, set up by a button that states the download first (about 3 GB). The Studio calls it as a separate process, so the base install stays light and PyTorch can't conflict with it. A fresh clone works without it. |
| D2 | Isolate vocals by default? | Yes. It costs about 2 minutes once per song, and section edges are what the timing is for. The result is cached by source hash. |
| D3 | Where do line times live? | A new `work/lyric-timing.json` beside the lyrics, like `story-beats.json`. `lyrics.json` keeps the words, so timing a song never un-approves a story. Editing the words clears only the times of lines that changed. |
| D4 | Where do section changes live, and what do they reach? | A new `work/section-map.json`, with names following it. `music.json` is never touched, and Reset just removes your changes, with Undo for each step. The Writer and Director see the map, and new cuts are seeded from it. Existing cuts and approvals stay as they are. |
| D5 | Where does the song strip go? | Use the existing Spine at the bottom and add the edge dragging there, rather than a second player. This differs from the prototype, so please check it in review. |
| D6 | Which detected edges do tags snap to? | Both `music.json` and the deep analysis, moving a start only to an edge up to 5 s before it. A song with no tags gets line times and no proposal; a song with no words keeps today's detection. |
| D7 | Should Parakeet draft words when you have none? | Yes, as a free local replacement for the Transcribe button removed in PR 51. The draft lands in the paste box and nothing is saved until you save it. The paid CLI path stays as it is. |
| D8 | Keep "Sounds like 62 / 123 / 246"? | No. It steers nothing, and making it steer pacing is separate work. Keep "about 123 BPM" on the quiet facts line. |

## Tasks (one commit each, one PR)

1. **Split the screen, no behaviour change.** `stages/Track.tsx` becomes a data hook plus
   parts. The next action moves to the top bar, the stats become one quiet line, the
   lyrics move to the reading serif, and the page has one scroll area. Each section's
   loudness shape replaces "loud / medium / quiet".
2. **Listening.** Through the shell's player: play a section and stop at its end, click a
   timed line to hear it, highlight the current section and line and follow it, and
   Space after a mouse click.
3. **Line times and tapping.** `domain/lyric_timing.py`, `work/lyric-timing.json` and its
   API: per line `start`, `end`, `source` (auto or tapped) and the text it was made for.
   Tags are headings and never timed. Tap-along with Undo, 0.75× and ¼ s nudges. Mismatched
   or missing lines read as "not on the song yet", never a guessed time.
4. **Automatic timing.** An engine module with no web imports: set up the private
   environment, run Demucs and Parakeet as a separate process, and match heard words to the
   known words with the tested alignment. It runs as a job with visible steps and Stop.
   Unmatched lines stay untimed. A new run never overwrites tapped lines without asking. On
   a machine that can't run it, the button says so and tapping still works.
5. **Draft words.** When a vocal song has no lyrics, offer the draft from D7, clearly marked
   as heard rather than known.
6. **Section map.** `work/section-map.json` and its API: move an edge on the Spine, add one
   at the playhead, join two, Undo and Reset to detected sections, with keyboard control of
   edges. Names move to the map; `music-notes.json` still reads for existing films.
   `_section_names` is matched by the cut's own start frames rather than position.
7. **The lyric structure.** Propose sections from tags and line times (D6), shown as a
   proposal you accept, and undoable. Per-row name offers come from your own tags.
8. **Reach the rest of the Studio.** `get_lyrics`, the Director's context and the Writer see
   line times and the map, marked as estimates unless tapped. New cuts seed from the map.
   Docs, then the acceptance run.

9. **Added during the build, the words in the MP3.** All four Suno MP3s here carry their
   lyrics and tags in the file. When a film has no words, Track offers them with one click, to
   read and save. Tag names drop production notes such as `[Intro: spoken low, ...]`.

## Not changing

Money, rendering, image prompts and the meaning of approval hashes. The bytes of
`music.json` and `lyrics.json`, source audio, and every existing cut. Nothing is migrated.
No provider call is added; the tools run on this computer and the song isn't uploaded.

## Acceptance

- `pytest`, `ruff`, frontend `tsc`/tests/build and renderer tests pass. Tests use a fake
  runner, and never download or run the real tools. New tests: approval hashes unchanged by
  timing and map writes, tag parsing, word matching with lines unheard, words edited after
  timing, tapped lines protected, name matching on an old cut, and a Studio with no private
  environment.
- On **scratch copies**, with the real local tools on the project's Python:
  - Stof en Stilte scores at least as well as the table above against its nine starts;
  - Tree of Love gets its nine sections, then Undo and Reset restore the detected ten;
  - Zero Bars, with no lyrics, gets a draft and nothing saved until saved;
  - a third Suno song is timed, as a fresh case the plan wasn't tuned on;
  - Tree of Love and Zero Bars keep their approvals, and their cuts open unchanged;
  - a new cut seeds from the map; narrow layout has no sideways scroll; Stop leaves no
    half-written file.
- Every current Track function stays reachable: Vocals/Instrumental, names, paste and LRC,
  analysis, and the promo/advert and instrumental views.

## Risks

- **Platform.** The private environment uses its own Python 3.11, the version tested, so the
  project's Python doesn't matter. `parakeet-mlx` is Apple Silicon only; other machines keep
  tapping.
- **Few songs.** Two songs, one with a reference. A singer, language or dense mix could do
  worse, so times stay marked as estimates and fixable by ear.
- **Tags aren't the song.** Suno can depart from its tags, which is why the structure is a
  proposal.
- **Instrumental starts are untested.** They come from where the last word ends, and the test
  only scored sung starts.
- **Licences and upkeep.** Parakeet is CC BY 4.0, which needs attribution. Demucs is MIT, its
  repository is archived, and its README states no separate licence for the weights. Neither
  blocks local use by the owner; the docs record both.
- **PR order.** PRs 48–50 touch `director/context.py` and `docs/ARCHITECTURE.md`, and PR 48
  still targets `film/story-room`. Task 8 is simpler once they've landed.

## Out of scope

Suno's unofficial timing data, SongFormer and other automatic labelling, making tempo steer
pacing, word-level highlighting, re-timing existing cuts to corrected sections, and replacing
the paid transcription path.

## Acceptance record, 30 Oct 2026

Run on scratch copies; `projects/` was only read. Local tools only: no provider call, no
upload, no spend. Tools were installed by the Studio's own button into a throwaway folder.

**Against the owner's nine Stof en Stilte starts by ear, through the shipped code.**

| Measure | Within 5 s | Typical gap | Worst gap |
| --- | ---: | ---: | ---: |
| First sung word of each known section | 8 / 9 | 0.2 s | 5.1 s (0:00, before the singing) |
| Sections proposed from the MP3's own tags | 9 / 9 | 0.2 s | 4.0 s |

The tags gave exactly nine sections, against 15 from the deep analysis. 63 of 67 lines were
placed; a line needs half its words heard, which is stricter than the earlier test's 65.
Stof en Stilte is archived, so this ran on the engine, not the screen.

**Tree of Love, through the screen.** 35 of 36 lines. Sections 0:00, 0:32, 0:48 Instrumental
Break, 1:17 Spoken Verse, 1:50 Spoken Hook, 2:10 Breakdown, 2:25 Instrumental Build, 2:54 Spoken
Hook, 3:12 Outro. Reset restored the detected ten. Approval hashes for analysis, lyrics, brief
and storyboard, plus `music.json`, `lyrics.json` and `edit.json`, were unchanged with times and
a map in place.

**Zero Bars, the fresh song, through the screen.** With the MP3's words: 44 of 46 lines,
in order, 89% of words matched and 88% exact, and 12 sections from its tags. The two missed
lines are the short "Hold still—" and "Silence—". A draft from the song, with no lyrics given,
was usable but wrong in places ("I might want help" for "One held breath"), and was not saved until told.

**Also checked.** Setup after stating its download, 40 s with caches. A run took about 4m30 with
the Studio running. Stop on a real run ended the worker within seconds, marked the job cancelled
and left no partial file. Dragging an edge with the mouse, keyboard moves, join, Undo, Undo of a
Reset, name offers, tap-along with Undo and 0.75×, nudging, and no sideways scroll at 375 px.

**Found while testing, and fixed.** Deep edges pulled sections back across sung lines, so an edge
now stops at the last sung word. A released edge compared with its dragged position, so a mouse
drag saved nothing.

**Saving words re-opens approvals, as it always has.** On a copy of Zero Bars, adding the words
turned Story to Changed and later stages to Not ready, because `lyrics.json` is in the chain.
Text and pictures don't change. Save now says so. Whether to do that to the real Zero Bars is the
owner's call: its story was approved with no words.

**Not proven.** Line timing on the Zero Bars and Stof en Stilte copies wasn't judged by ear.
Instrumental starts have no reference. No live Writer turn has used line times or a section map.
The promo, advert and instrumental views weren't re-tested on screen; their logic moved unchanged.
