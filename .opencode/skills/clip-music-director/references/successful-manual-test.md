# Successful manual style test — reference example, not the default scene

The user reported the following prompt worked **very very well style-wise** in
their manual Runware test. This is user feedback, not an independently reviewed
image or a promise of exact repetition. The reusable default is `DEFAULT_STYLE`
in `src/mp3_to_videoclip/profiles.py`. Do not copy this scene/text/lens into every
film. The numerical artist weighting is prose, not a supported API control.

**Subsequent actual control approval:** the tracked generated image from task
`2edbbe00-18a2-4776-9aca-67d863f5ea36` was displayed to the user, who replied
“the style is perfect.” `profiles.STYLE_BENCHMARK` identifies its exact private
original and provenance; `work/style-approval.json` records the explicit decision.
It is now the rendering benchmark across stories, not a template for this man,
rooftop, rain, lens, lettering or cover layout. New story transfer still needs
actual proof inspection. Future control candidates never inherit this approval.

This exact text is retained verbatim as `profiles.ROOFTOP_CONTROL_PROMPT`, the
style-control fixture: one tracked calibration image, Nano Banana 2.1, at most
USD 0.10, no references, no automatic retry, and its own lettering request intact
(the one deliberate exception to local text). The result is a candidate judged by
the user, never an automatic golden reference.

```text
A fully painted comic cover panel driven toward photorealism: a realistic
depiction in the painted tradition of Alex Ross and Gabriele Dell'Otto, weighted
roughly 70% Ross for photographic anatomy, skin and lighting, 30% Dell'Otto for
crushed blacks, hard specular highlights and gritty texture.

A lone adult man in a soaked charcoal overcoat stands on a wet rooftop at night,
seen from a low heroic angle, chin lifted, rain streaking past him in diagonal
silver lines. Behind him the city drops into a deep canyon of brick and steel,
one warm sodium streetlight and one cold searchlight beam converging on his
shoulders.

Rendered at photographic fidelity with a brush: skin with visible pores, stubble
and subsurface scattering, individual wet hairs, rain beading on the fabric,
visible wool and canvas weave, leather scuffed and creased, accurate near-to-far
perspective and volume. Shot on a 50mm lens at f/2.0, the figure tack sharp while
the city falls into soft focus behind him, veiling glare and a faint lens flare
where the searchlight crosses the frame, controlled blown highlights on the wet
coat, fine 35mm film grain, natural colour science, believable exposure.

From the Dell'Otto side, translated into photographic terms: ink-black shadow
shapes with detail crushed out, brilliant specular whites, hard rim light, gritty
high-contrast punch, and the faintest trace of halftone print grain in the
shadows.

Hyper-detailed photorealism rendered entirely by brush — a painting that could be
mistaken for a photograph. Not a 3D render, not CGI, not a cel-shaded or
outlined cartoon, not waxy plastic skin.

Headline text: the exact words "THE LAST LIGHT" in heavy condensed capitals with
a slight upward arc, across the upper third of the frame, dark ink with a thin
warm rim light and a hard ink shadow beneath. A small caption box in the
lower-left corner reads exactly "The city never sleeps." in modest regular
capitals. All lettering clean, typeset, correctly spelled and fully readable, set
like sharp offset print. No other text, numbers, logos, symbols or watermarks
anywhere in the frame.

Wide 16:9 composition, cinematic scale, 1376x768.
```

The image-generation text clauses above were requested for that manual test.
Production titles, captions, SFX and credits remain local typography unless the
user explicitly chooses otherwise. Do not retain both this lettering request
and a contradictory no-text rule in the same compiled prompt.
