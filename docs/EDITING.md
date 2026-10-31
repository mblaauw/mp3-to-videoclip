# Editing: the cut list owns time

T4 moved timing and motion out of the storyboard into `work/edit.json`. The
storyboard still owns content: shot kind, purpose, message, prompt, source image,
on-screen words and framing. The edit owns order, frame spans, transitions,
camera motion, accents, text timing and grade.

`work/edit.json` is authoritative when present. A production without it keeps
its original storyboard timing and its original approval hashes. Nothing is
migrated on read: seeding an edit is an explicit user action.

## Edit decision list

```json
{
  "sections": [
    {
      "id": "chorus-1",
      "start_frame": 1440,
      "end_frame": 2160,
      "feel": "release, wide and bright",
      "density_per_10s": 3,
      "techniques": ["cut on accent", "pull-back"]
    }
  ],
  "shots": [
    {
      "shot_id": "s014",
      "start_frame": 1440,
      "duration_frames": 60,
      "motion": {
        "type": "push_in",
        "from": 1.0,
        "to": 1.08,
        "easing": "smoothstep",
        "anchor": [0.55, 0.4],
        "reason": "approach the reveal"
      },
      "transition_in": {
        "type": "whip_pan",
        "frames": 8,
        "direction": "left",
        "reason": "chorus entry"
      },
      "accents": [
        {
          "frame": 1440,
          "type": "punch_in",
          "amount": 1.04,
          "duration_frames": 6,
          "reason": "first chorus hit"
        }
      ],
      "text": [
        {
          "id": "t3",
          "style": "super",
          "text": "OUT 14 NOV",
          "in_frame": 1452,
          "out_frame": 1500,
          "animation": "type_on",
          "reason": "date lands with the line"
        }
      ]
    }
  ],
  "grade": {"preset": "warm-night", "strength": 0.6},
  "notes": "Why this cut, in one line."
}
```

All shot, accent and text frames are absolute output frames. Every storyboard
shot appears exactly once, ordered by `start_frame`, and the spans are contiguous
from frame 0 to the storyboard's full duration. `transition_in` belongs to the
incoming shot; its `frames` become the overlap handle on the previous plate.
Non-cut transitions need handle frames and a stated reason.

### Enums

- Motion: `hold`, `push_in`, `pull_back`, `pan_left`, `pan_right`; scale 1.00–1.30.
- Transition: `cut`, `fade`, `wipe_left`, `wipe_right`, `dip_to_black`,
  `dip_to_white`, `whip_pan`, `push`, `slide`.
- Accent: `punch_in`, `flash`, `light_leak`.
- Text style: `super`, `title`, `lower_third`, `lyric`, `card`.
- Text animation: `fade`, `type_on`, `slide_up`, `pop`, `kinetic_words`.
- Split layout: `row`, `column`, `grid`.
- Grade preset: `neutral`, `warm-night`, `clean-day`, `monochrome`, `vivid`,
  `film-fade`; the four legacy sliders remain per-key advanced overrides.

## Effective timeline

`production.resolved_assets` loads the edit, applies it to the content board and
attaches the matching `EditShot` and `Grade` to each `RenderShot`. The MP4
renderer and the Studio Player therefore receive the same effective spans and
the same edit metadata. Storyboard writes can still change content; once an edit
exists, `update_shots` rejects timing and motion fields and the Storyboard
timeline is read-only. Edit controls and the report live in Film.

The edit binds into `preview_board_hash` and the `stills` stage hash. With no
edit, both hashes are byte-identical to the pre-T4 values. The legacy
`Shot.transition` and `timing.TRANSITIONS` contract is untouched; new edit
transitions are a separate enum so old boards and their approval hashes stay
stable.

## Report

`edits.report` computes:

- coverage and contiguity;
- cuts per 10 s per section against the plan and the event-map energy label;
- repetition of motion, transition and framing;
- reading time for card shots and text layers;
- hold ratio, per section and overall;
- accent use and flash rate;
- transition handles and reasons;
- advert/promo checks: brand or product in the first five seconds, an end card
  of at least three seconds, and mandatory wording present;
- technique usage with stated reasons.

Hard findings are coverage, a non-cut transition without handle frames, a
non-cut transition without a reason, and more than three `flash` accents in any
one-second window. Everything else is a warning for judgement. The report is
returned by `GET /api/projects/<slug>/edit`, shown in Film, and included in the
Editor's project snapshot.

## Renderer primitives

The shared `renderers/remotion/src/timing.mjs` and `BaseFilm.jsx` implement the
primitives for both outputs:

| Family | Implementations |
| --- | --- |
| Transitions | fade, wipe, dip to black, dip to white, whip pan, push, slide |
| Accents | punch-in camera bump, flash frame, light leak |
| Split | two-pane row/column, three-pane triptych/grid |
| Text | fade, type-on, slide-up, pop, kinetic words |
| Grade | six presets with strength and slider overrides |

`request.mjs` validates the edit payload and refuses a render with more than
three flash accents in any one-second window. This is the renderer's own limit,
not only a report warning.

A shot can also carry `crops`: jumps to new framings of its own still on chosen
frames, up to 1.6× with a report warning past 1.4×, because stills go soft. They are
how one still becomes several cuts without a new paid picture. `grade.look` adds grain,
gate weave and slow handheld drift, each 0 to 1 and off by default. It is deterministic
by frame, so the Player and the MP4 match, and text stays crisp above it. Both fields
are absent when unused, so older cuts render and hash as before.

Two-second visual samples and a gallery are in `docs/primitives/`. They render
through the production composition; `docs/primitives/render_samples.mjs`
regenerates them. `renderers/remotion/tests/edit-primitives.test.mjs` unit-tests
every primitive, the split rectangles, the flash rule and the request refusal.
