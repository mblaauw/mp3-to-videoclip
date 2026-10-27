---
version: 1
task: prompts
role: writer
---
# W5 — Image prompts

Write the prompt for one generated still at a time. The prompt describes what the
camera sees in this instant, not the film around it. Save through `update_shots`
with only the `image_prompt` field you changed.

## Order

1. Subject and action: who or what, doing what, in this instant.
2. Composition and framing: where the subject sits, the crop, the focal
   hierarchy, the lens and depth of field.
3. Light, time of day and materials for this shot only.
4. `must_show` restated as visible facts, never as a caption.
5. Occupancy: state it plainly ("not a single person in frame", or the exact
   crowd). Occupancy belongs in the shot, never only in the scene text.
6. The no-text clause: no text, lettering, numbers, speech bubbles, logos or
   symbols. Every word is composited later.
7. Only the references this shot needs; say what each one supplies and do not
   copy its incidental pose or background.

## Product and bridge

A `product` prompt names the supplied product reference, its angle, placement,
scale and background, and asks for undistorted geometry and labels. Do not
invent a product feature, label or price. A generated `bridge` prompt composes
the match: name the shape, colour or position, and put it at the agreed anchor so
the editor can cut on it. A designed bridge needs no image prompt.

Do not repeat the global look, the style preset or the scene description inside
the shot text: the compiler inserts them. Do not repeat a character's identity or
wardrobe either; bind the character in the storyboard and let the compiler add
the identity and the resolved state. Keep the prompt about this frame.

## Self-check before saving

- Read the compiled prompt: does any scene text contradict the shot?
- Is every recurring person bound in `character_ids` and every place in `scene_id`?
- Does the shot text avoid repeating identity, wardrobe or the scene description?
- Is occupancy stated in the shot itself?
- Is there a no-text clause, and does the prompt describe no lettering?
- Does the product keep its supplied geometry and label?
- Does a bridge name the exact matched shape or colour?
