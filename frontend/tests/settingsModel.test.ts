import assert from "node:assert/strict";
import test from "node:test";
import {
  matches,
  missingForFilm,
  modelsFor,
  patchAt,
  priceWords,
  readAt,
  recommendedPictures,
  recommendedRoles,
  recommendedVoices,
  type Catalog,
  type CatalogModel,
} from "../src/shell/settings/settingsModel.ts";

function model(id: string, provider: string, capabilities: string[], recommended: string[] = []): CatalogModel {
  return { id, provider, label: id, capabilities, price: null, price_note: "", price_checked: "", recommended, source: "static" };
}

const catalog = {
  providers: [],
  models: [
    model("sol", "openai", ["text", "vision"], ["writer", "critic"]),
    model("flash", "opencode-go", ["text"], ["editor"]),
    model("speech", "runware", ["speech"], ["narrator"]),
  ],
  voices: [
    { id: "a", provider: "runware", model: "speech", label: "A", language: "en", preview_url: "", recommended: false },
    { id: "b", provider: "runware", model: "speech", label: "B", language: "en", preview_url: "", recommended: true },
  ],
  computer: {},
  lyric_tools: { supported: true, reason: null, ready: false, download_gb: 3 },
  depth_tools: { supported: true, reason: null, ready: false, download_gb: 1.5 },
  notes: {},
} as Catalog;

test("a dotted path becomes a patch and reads back", () => {
  const patch = patchAt("roles.writer.model", "m");
  assert.deepEqual(patch, { roles: { writer: { model: "m" } } });
  assert.equal(readAt(patch, "roles.writer.model"), "m");
  assert.equal(readAt(patch, "roles.editor.model"), undefined);
});

test("a role is only offered models that can do its job", () => {
  assert.deepEqual(modelsFor(catalog, ["text", "vision"]).map((m) => m.id), ["sol"]);
  assert.deepEqual(modelsFor(catalog, ["text"], "opencode-go").map((m) => m.id), ["flash"]);
});

test("a model with no verified price says so, and no price is made up", () => {
  assert.equal(priceWords(model("x", "y", [])), "Price unknown");
  assert.equal(priceWords(undefined), "Price unknown");
  const priced = { ...model("x", "y", []), price: { amount: "0.10", unit: "1k_chars" }, price_checked: "2026-11-01" };
  assert.equal(priceWords(priced), "$0.10 per 1,000 characters, read 2026-11-01");
});

test("reset restores each recommended choice and leaves the rest of a role alone", () => {
  assert.deepEqual(recommendedRoles(catalog), {
    roles: {
      writer: { provider: "openai", model: "sol" },
      editor: { provider: "opencode-go", model: "flash" },
      critic: { provider: "openai", model: "sol" },
      narrator: { provider: "runware", model: "speech" },
    },
  });
  assert.deepEqual(recommendedVoices(catalog), { voices: { provider: "runware", default_voice: "b" } });
  assert.deepEqual(recommendedPictures(["look"]), {
    pictures: { image_model_by_look: { look: "" }, video_model: "", upscaler: "" },
  });
});

test("with nothing set up, the checklist names all four and where to fix each", () => {
  const missing = missingForFilm({ roles: { writer: { provider: "openai" } } }, { renderer: false, ffmpeg: false });
  assert.deepEqual(
    missing.map((item) => [item.id, item.tab, item.field]),
    [
      ["writer-key", "keys", "key-openai"],
      ["runware-key", "keys", "key-runware"],
      ["renderer", "computer", "install-renderer"],
      ["ffmpeg", "computer", "tool-ffmpeg"],
    ],
  );
});

test("a Writer with a key and a ready computer need nothing", () => {
  const ready = { renderer: true, ffmpeg: true };
  assert.deepEqual(missingForFilm({ role_keys: { writer: true }, has_runware_key: true }, ready), []);
});

test("search matches any of the words, ignoring case", () => {
  assert.equal(matches("RESERVE", "Reserve per still"), true);
  assert.equal(matches("nothing", "Reserve per still", undefined), false);
  assert.equal(matches(" ", "anything"), true);
});
