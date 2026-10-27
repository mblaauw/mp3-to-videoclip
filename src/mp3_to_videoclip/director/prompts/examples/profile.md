---
version: 1
example: profile
---
## Worked example

Treatment: two dancers meet in a rain-lit rehearsal room, then on a dry stage at
dawn. The same movement is repeated in both places.

```json
{"characters": [
  {"id": "dancer", "identity": "woman, late 20s, Black, cropped hair, strong build",
   "states": {
     "rehearsal": {"description": "grey leotard, bare feet, damp hair"},
     "stage": {"description": "ivory stage dress, hair slicked back"}},
   "default_state": "rehearsal", "references": [], "permission_confirmed": true},
  {"id": "partner", "identity": "man, early 30s, olive skin, short dark hair, lean",
   "states": {
     "rehearsal": {"description": "black shorts and tank, bare feet"},
     "stage": {"description": "ivory shirt, dark trousers"}},
   "default_state": "rehearsal", "references": [], "permission_confirmed": true}],
 "scenes": [
  {"id": "rehearsal-room", "description": "A bare studio at night: one high window, wet lino, a cold practical light and rain on the glass."},
  {"id": "stage", "description": "A dark stage at dawn: a single warm side light, dry boards, a pale cyclorama."}],
 "arc": [
  {"phase": "rehearsal", "intention": "distance and precision"},
  {"phase": "turn", "intention": "the first shared breath"},
  {"phase": "stage", "intention": "the same movement, now open"}],
 "image_rules": [
  "Single coherent frame; no collage or panel layout.",
  "Full-bleed still; no border, caption or headline.",
  "No text, lettering, logos or watermarks in generated pixels.",
  "Believable anatomy, fabric and contact shadows at the intended framing."],
 "avoid": ["posed smiles", "extra dancers in two-person shots", "readable text or signage"],
 "look": "A photorealistic 35mm film still with a restrained painterly finish. Natural skin with visible pores and fine hair, honest cotton and lino texture, accurate perspective and contact shadows. A hard side light and a cool window fill; deep but open shadows, controlled highlights, faint halation around the practical. Palette of wet grey, ivory, dry umber and one warm amber accent. Fine grain, natural colour science. Not CGI, not a glossy advert, not a waxy face."}
```

The look is rendering only. It does not name the dancers, the rooms, the story or
the per-scene light; those live in the characters, scenes and arc.
