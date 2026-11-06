import assert from "node:assert/strict";
import test from "node:test";
import {
  adjusted,
  clock,
  fromFormat,
  keepDestinations,
  parseBudget,
  startFrom,
  stillsFor,
  timeline,
  titleFromFile,
  type Destination,
  type Format,
} from "../src/newFilm/model.ts";

const DESTINATIONS: Destination[] = [
  { id: "youtube", label: "YouTube", aspect: "16:9" },
  { id: "shorts", label: "YouTube Shorts", aspect: "9:16" },
  { id: "reels", label: "Instagram Reels", aspect: "9:16" },
  { id: "square", label: "Square feed", aspect: "1:1" },
];

const TEASER: Format = {
  id: "release-teaser",
  kind: "promo",
  label: "Release teaser",
  blurb: "",
  length: 30,
  aspect: "9:16",
  titles: "title-v1",
  destinations: ["shorts", "reels"],
  look: "clean-photographic-v1",
  structure: "Release teaser",
};

const FIVE = {
  id: "five-beat-2m",
  label: "Five beats",
  length: 120,
  beats: [
    { label: "Hook", seconds: 8 },
    { label: "World", seconds: 27 },
    { label: "Develop", seconds: 40 },
    { label: "Reveal", seconds: 30 },
    { label: "Payoff", seconds: 15 },
  ],
};

test("a format fills the form and an untouched form still is that format", () => {
  const choices = fromFormat(TEASER);
  const start = fromFormat(TEASER);
  assert.equal(adjusted(choices, start), false);
  assert.equal(adjusted({ ...choices, destinations: ["reels", "shorts"] }, start), false);
  assert.equal(adjusted({ ...choices, length: 60 }, start), true);
  assert.equal(adjusted(choices, null), true);
  choices.destinations.push("square");
  assert.deepEqual(TEASER.destinations, ["shorts", "reels"]);
});

test("the signature waits for a brand name, and a preferred look wins where it fits", () => {
  const video: Format = { ...TEASER, id: "music-video", kind: "music_video", titles: "joint-v1", look: "photographic-painted-v2" };
  assert.equal(startFrom(video, { titles: { music_video: "title-v1" } }).titles, "title-v1");
  assert.equal(startFrom(video, { titles: { music_video: "joint-v1" } }).titles, "joint-v1");
  const looks = ["photographic-painted-v2", "clean-photographic-v1"];
  assert.equal(startFrom(video, { look: "clean-photographic-v1", looks }).look, "clean-photographic-v1");
  assert.equal(startFrom(video, { look: "archival-v1", looks }).look, "photographic-painted-v2");
});

test("a new shape keeps the destinations that fit, or starts on its own first one", () => {
  assert.deepEqual(keepDestinations(["shorts", "square"], "16:9", DESTINATIONS), ["square"]);
  assert.deepEqual(keepDestinations(["shorts", "reels"], "16:9", DESTINATIONS), ["youtube"]);
  assert.deepEqual(keepDestinations(["youtube"], "9:16", DESTINATIONS), ["shorts"]);
});

test("a budget reads either decimal mark and refuses nonsense", () => {
  assert.equal(parseBudget("5,00"), 5);
  assert.equal(parseBudget("$12.5"), 12.5);
  assert.equal(parseBudget("0"), null);
  assert.equal(parseBudget("five"), null);
  assert.equal(parseBudget("1.234"), null);
  assert.equal(stillsFor(5, 0.12), 41);
  assert.equal(stillsFor(0.36, 0.12), 3);
  assert.equal(stillsFor(null, 0.12), null);
});

test("a story film's beats scale to its length and keep their shape", () => {
  const { total, segments } = timeline({ ...fromFormat(TEASER), kind: "narrative", length: 60, structure: "five-beat-2m" }, [FIVE], null);
  assert.equal(total, 60);
  assert.deepEqual(segments.map((s) => s.seconds), [4, 13.5, 20, 15, 7.5]);
});

test("a song film shows the part of the song it uses", () => {
  const teaser = fromFormat(TEASER);
  assert.deepEqual(timeline(teaser, [], 200).segments.map((s) => [s.label, s.seconds]), [
    ["First 30 s", 30],
    ["Rest of the song", 170],
  ]);
  assert.deepEqual(timeline(teaser, [], null).segments.map((s) => s.seconds), [30]);
  assert.deepEqual(timeline({ ...teaser, length: 60 }, [], 45).segments.map((s) => s.seconds), [45]);
  assert.equal(timeline({ ...teaser, length: 0 }, [], 214).total, 214);
});

test("lengths and titles read the way people say them", () => {
  assert.equal(clock(30), "30 s");
  assert.equal(clock(120), "2 min");
  assert.equal(clock(214), "3:34");
  assert.equal(titleFromFile("night_signal--final-MASTER.mp3"), "night signal final MASTER");
});
