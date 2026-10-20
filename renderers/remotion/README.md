# Production visual renderer

Pinned Remotion4.0.536 / React19.2.0. This package is invoked by the Python
adapter, not a second production UI or editable timeline.

```sh
npm ci --ignore-scripts --no-audit --no-fund
npm test
npm run smoke
```

The adapter is `src/mp3_to_videoclip/remotion.py`; contracts, bounds, migration and
acceptance criteria are documented once in [docs/RENDERER.md](../../docs/RENDERER.md).
For an already validated local request: `node render.mjs REQUEST.json`. Request
outputs must have a new basename and local absolute paths. Local Chrome is
required; no implicit install or browser download. `.cache`/`node_modules` are
rebuildable local dependencies, not source. Credentials and original reference
photos must never enter the staged public asset directory.
# Opt-in compact signature

`spec.layout` may be `{ "kind": "compact-v1" }`. Omission keeps the existing
joint-v1 drawing path unchanged. This is a Remotion-only placement variant, not
a new credit engine or editorial timeline. It keeps the normal intro phases,
role copy and allocated part durations. Unknown layout controls fail explicitly.

Optional `identity_switch_frame` and `handoff_frames` are integer frames local to
the existing identity part. The mark/copy fade between two fixed safe fields;
they do not slide across faces. Both controls must be supplied together and the
handoff must fit inside the identity window. Derive them from the canonical board
boundary, never from a second beat grid. A one-frame zero-opacity handoff is
intentional, not an extension of the soundtrack or credit duration.

Compact text and logo bounds are checked in the actual local browser/font before
publishing. This checks module overflow, **not** underlying image clearance or
legibility over footage. Real composited samples and user graphics approval are
still required. Missing-glyph separators are avoided with an explicit diamond.
The layout enters content/cache keys only when explicitly present; earlier
production specs are not edited or opted in.

In this variant, a `style: "caption"` part draws an ivory local comic-caption box
in the upper-left caption field. Its exact shot-bound text is preserved, measured
against the module and included with the layout in cache content. Outside this
explicit variant, the existing caption drawing is unchanged. This is not support
for generated lettering, SFX bursts or arbitrary panel animation.
