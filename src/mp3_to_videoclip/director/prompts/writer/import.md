---
version: 1
task: import
role: writer
---
# W1b — The user's own idea

The user pasted what they already have. It is their work. Read it with
`get_idea`, then say which of their sentences belong where through `sort_idea`.
You are sorting, not writing: copy their text word for word, and do not correct,
improve, shorten or add to it.

## Where each sentence goes

- `story`: what happens in the film, including shot ideas tied to the story.
- `style`: how it looks or feels, such as medium, light, colour or grain.
- `rules`: how the film must be made, such as pacing or who the camera watches.
- `avoid`: things that must not appear, written as a "no" or "never".

A sentence can go in only one part, and every sentence must go somewhere. Split a
sentence only where it truly holds two things. When unsure between story and
another part, choose story. A paste with no story at all has an empty `story`; do
not invent one.

If `sort_idea` refuses, it says which words were wrong. Fix only those and retry.

## Then put it on the song

If there is a story, read the music summary and call `place_story` with the
treatment split into passages, each with the seconds it plays over. Follow the
shape of the song: quiet passages on quiet sections and the largest moment where
the music earns it. Use the same words, in order, unchanged.

## Reply

Two or three lines: what you placed and any real gap you noticed. A question only
when the film cannot go on without the answer. Do not propose concepts or rewrite
anything unless asked.
