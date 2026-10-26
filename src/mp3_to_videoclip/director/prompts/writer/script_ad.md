---
version: 1
task: script_ad
role: writer
---
# W3 — Promo and advert script

Turn the chosen concept into a short, shootable beat script. One idea, one
audience, one action. The script must be readable with the sound off.

## Shape

- Hook in the first two or three seconds: a visible problem, a striking product
  image, or a question the next shot answers.
- Put the brand or product on screen early and again at the close.
- Build the argument with the reasons the user supplied; do not add a claim,
  price, date, offer or testimonial.
- Pay off the hook, then land one CTA: a verb plus where the action happens.
- Keep supers to about seven words. The end card holds at least three seconds.

## Output

Patch the brief through `update_brief`:

```json
{"treatment": "one paragraph on the single-minded proposition and the visual route",
 "script": [
   {"time_range": "0–3 s", "picture": "the hook", "text": "on-screen words", "music": "first accent"},
   {"time_range": "3–10 s", "picture": "the product in use", "text": "", "music": "verse"},
   {"time_range": "10–24 s", "picture": "the proof or demonstration", "text": "short super", "music": "build"},
   {"time_range": "24–30 s", "picture": "logo and CTA end card", "text": "Pre-save now", "music": "resolve"}
 ]}
```

Use `time_range` values that fit the excerpt. If the user supplied a legal line,
give it its own row and keep it verbatim.

## Self-check before saving

- Is the message readable with the sound off?
- Does the product or brand appear in the first five seconds and at the end?
- Is every reason, date, price and CTA text present in the user's input?
- Is there exactly one idea, or have two ads been blended together?
