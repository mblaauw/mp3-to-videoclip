---
version: 2
reference: techniques
role: editor
---
# Technique library

| Technique | What it does | Use it when | Avoid when | Renderer |
| --- | --- | --- | --- | --- |
| Hard cut on a phrase or section boundary | Clean, confident structure | Default join; a new section is a new idea | Inside one continuous idea that should flow | `cut` |
| Cut on an accent | Picture lands on the music | A high-confidence drum, stab or vocal entry | Accents are weak, or every bar becomes mechanical | timing + `cut` |
| Rhythmic montage / acceleration | Shorter shots build energy | A build into a drop, chorus or reveal | The images need more reading time | timing |
| Breathing hold | Lets a moment land | After a peak, on a key lyric, on a tableau | A static image in a high-energy passage with nothing moving | `hold` |
| Push-in | Builds attention, intimacy, tension | An emotional beat, a reveal approach, a face | Three in a row; wide busy frames | `push_in` |
| Pull-back | Releases, reveals context or scale | A section end, a twist, "bigger than we thought" | An opening that needs immediate clarity | `pull_back` |
| Lateral pan | Discovers information across the frame | Wide compositions, product line-ups, landscapes | Close-ups where the crop runs out | `pan_left`, `pan_right` |
| Match cut | Links two images by shape, colour or position | A motif returns; before/after rhymes | The shapes do not actually align | storyboard match + `cut` |
| Smash cut | Abrupt energy or content contrast | Quiet to loud, calm to chaos, an ad twist | Gentle songs; overuse | `cut` |
| Jump cut | Same subject, compressed time | Progress, restlessness, a process | Different subjects, which just reads as a cut | two crops or a reprise |
| Cross-cutting | Alternates two lines to build tension | Two characters converging; product versus problem | Only one line of action exists | timing |
| Dissolve / cross-fade | Time passing, dreamy join, emotional drop | Slow songs, memory, a place change | Fast passages; one continuous action | `fade` |
| Dip to black or white | Chapter break, breath, flash of memory | Section ends, before a reveal, ad end card | Mid-phrase | `dip_to_black`, `dip_to_white` |
| Whip pan | Energetic transition with motion blur | Up-tempo section changes, ads, travel | Calm passages | `whip_pan` |
| Push / slide | Graphic, modern transition | Promos, ads, list structures, "three reasons" | Narrative films that should not feel like slides | `push`, `slide` |
| Punch-in | Small scale jump on an accent | Big hits, chorus starts, ad emphasis | More than about once per section | accent `punch_in` |
| Flash frame / light leak | Bright accent, energy, memory | Strong accents, drops, end of a montage | More than three flashes in any second; gentle songs | accent `flash`, `light_leak` |
| Split screen / triptych | Comparison or simultaneity | Before/after, options, parallel lives, ad demos | Detailed images that become too small | split panes + `split_layout` |
| Kinetic typography | Text moves with the rhythm | Short supers in ads, lyric hooks, title cards | Long sentences | text `kinetic_words` |
| Type-on, slide-up or pop | Text enters with intent | A statement, a super, a chapter line | Text that must be read instantly | text animation presets |
| Lower third / super | Calm information | Names, dates, places, offers | Busy image areas | text `lower_third`, `super` |
| End card / logo lockup | Closes the film with the brand and CTA | Every promo or advert | A film that already ended | storyboard `end_card`, `logo` |
| Grade preset | Holds the whole film in one look | Match the kind, the world and the emotional arc | It fights the stills or hides a bad cut | `grade.preset` |

A technique is justified by what the viewer feels, not by its name. If two
techniques would do the same job, choose the quieter one. Name the reason in the
edit artifact when the join is not a hard cut.
