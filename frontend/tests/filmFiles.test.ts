import assert from "node:assert/strict";
import test from "node:test";
import { filmFiles, filmLabel, selectFilm } from "../src/filmFiles.ts";
import type { FilmFile } from "../src/api.ts";

const base: FilmFile = { kind: "renders", name: "base.mp4", classification: "base", verified: true, current: true, delivery_ready: false };
const final: FilmFile = { ...base, name: "final.mp4", classification: "final", delivery_ready: true };

test("prefer verified current final, preserve explicit selection and refresh metadata", () => {
  assert.equal(selectFilm([base, final], null), final);
  assert.equal(selectFilm([base, final], base), base);
  const stale = { ...final, current: false, delivery_ready: false };
  assert.equal(selectFilm([base, stale], null), base);
  assert.equal(selectFilm([base, stale], final), stale);
});

test("legacy lists stay unknown; directory and filename cannot imply final", () => {
  const files = filmFiles({ exports: ["final.mp4"], previews: ["preview.mp4"] });
  assert.ok(files.every((file) => file.classification === "unknown"));
  assert.equal(filmLabel(files[0]), "Unknown report");
  assert.equal(filmLabel(base, true), "Base film — no intro/credits");
  assert.equal(filmLabel(base, false), "Base film");
  assert.equal(filmLabel(base), "Base film");
  assert.equal(filmLabel(final), "Final delivery");
});
