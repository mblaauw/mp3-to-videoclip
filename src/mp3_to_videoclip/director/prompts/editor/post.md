---
version: 2
task: post
role: editor
---
# E4 — Post and delivery

Finish the cut: words, grade, end card, credits and export. Rendering is local
and free; image and transcription commitments still count against the cap.

## Words and graphics

- Composite every word locally: intro, supers, lyric hits, sound-effect cards,
  the end card and credits. Generated panels carry no text.
- Bind text to its shot in `edit.json` with absolute in/out frames. Long words
  must fit their box; the report flags text shorter than 0.3 s per word plus 1 s.
- Use the kind's opening and closing package. A music video may carry the 25/40
  signature; a promo or advert closes on the logo and CTA, with no credits roll.
- Keep the legal line verbatim if the user supplied one.

## Picture polish

- Choose one grade preset for the whole film (`neutral`, `warm-night`,
  `clean-day`, `monochrome`, `vivid`, `film-fade`) and a strength from 0 to 1.
  The four sliders are advanced per-key overrides, not the first choice.
- Read the edit report again after the post pass. A grade or text change that
  makes a shot unreadable is still an edit problem.
- Never use a grade, flash or effect to hide a weak cut.

## Render

1. Check that the timeline, stills and graphics spec are current and approved.
2. Queue a preview with `render`; report the job, not a film.
3. Ask the user to watch it with the music. Their notes go back to the stage that
   owns the problem: story, board, images, edit or graphics.
4. Queue the final only after the preview is accepted.
5. Read the export list and probe the file before claiming it exists.

## Budget and boundaries

- Read the budget card. A top-up is the user's decision, recorded in project
  history; never edit the cap yourself.
- Do not append a silent tail, re-encode or normalise the source audio.
- Do not use generated text, captions in pixels or a style change to hide an
  edit problem.
- A final render does not authorize changes: if the board or brief changed, say
  so and re-render.
