# Critic modes: story, board and pixels

Detail for the `visual-critic`. The mandate stays one-line in `SKILL.md`; this
file fixes the three modes, the report shape and the honesty rule. The critic is
read-only in every mode: no file writes, no shell, no helpers, no paid tool, no
dispatching.

## The three modes

| Mode | Reviews | Claims allowed |
| --- | --- | --- |
| **story** | a `short-film-writer` text draft | text review only |
| **board** | a `visual-director` storyboard/prompt draft | text review only |
| **pixels** | actual generated images and the sequence | pixel inspection of files read |

Story and board modes are a **text review of a draft**: the critic has read no
image and must say so. Only pixels mode may claim pixel inspection, and only for
the files it actually opened.

## Fixed report shape

One row per finding — evidence, consequence, proposed fix, severity:

| Field | Meaning |
| --- | --- |
| evidence | the file, byte/version scope or frame actually read |
| consequence | what breaks or is lost if it ships |
| proposed fix | the smallest change that answers it, not a whole-frame roll |
| severity | blocker / should-fix / note |

Prose without those four fields is not a finding and must not be forwarded as one.

## Coverage honesty

List, explicitly: **inspected**, **unreadable**, **not reviewed**. A failed or
timed-out reviewer is unavailable evidence, never a pass. Never forward images
into the coordinating session, and never report an unseen file as reviewed.

## Pixel budget (complements `shot-review.md`)

Practical batch: **6–8 image occurrences including references**; hard ceiling
**15** in one fresh session, with headroom kept below it. The ceiling is
cumulative over that session's history — re-reads, crops and a later round spend
the same allowance, and a blocked session cannot be recovered by a smaller batch
in place. No mandatory re-reads and no per-frame review divisions — coverage is
complete over the real set, and a green report never proves the images are good.
Severity calibration and accept/uncertain/reject dispositions stay in
`shot-review.md`; this file adds no new verdict vocabulary.
