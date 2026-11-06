import assert from "node:assert/strict";
import { test } from "node:test";
import { groupByKind, nextEpisode, provenance, seriesIdFrom, type LibraryEntry } from "../src/library/entries.ts";

const entry = (kind: LibraryEntry["kind"], label: string, version = 1): LibraryEntry => ({
  key: `${kind}:${label}`,
  kind,
  id: label,
  version,
  label,
  from: { slug: "first", title: "First Film", at: "2026-11-05T10:00:00+00:00" },
  summary: "",
  thumbnail: null,
  files: 0,
});

test("entries group by kind in the screen's order, empty kinds left out", () => {
  const groups = groupByKind([entry("look", "house"), entry("character", "zed"), entry("character", "amy")]);
  assert.deepEqual(groups.map((group) => group.kind), ["character", "look"]);
  assert.deepEqual(groups[0].entries.map((item) => item.label), ["amy", "zed"]);
});

test("a series id is plain and never empty", () => {
  assert.equal(seriesIdFrom("The Museum of Tomorrow"), "the-museum-of-tomorrow");
  assert.equal(seriesIdFrom("  ¡Ésta! "), "esta");
  assert.equal(seriesIdFrom("???"), "series");
});

test("the next episode follows the highest number", () => {
  assert.equal(nextEpisode(null), 1);
  assert.equal(nextEpisode({ id: "m", title: "M", bible: "", recurring: [], episodes: [] }), 1);
  assert.equal(
    nextEpisode({ id: "m", title: "M", bible: "", recurring: [], episodes: [{ slug: "a", number: 3, title: "A", at: "" }, { slug: "b", number: 1, title: "B", at: "" }] }),
    4,
  );
});

test("provenance names the film and a later version", () => {
  assert.match(provenance(entry("place", "street")), /^From First Film, /);
  assert.match(provenance(entry("place", "street", 2)), / · v2$/);
});
