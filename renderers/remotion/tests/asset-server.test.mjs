import assert from "node:assert/strict";
import {mkdirSync, mkdtempSync, symlinkSync, writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import path from "node:path";
import test from "node:test";

import {bundleKey, servedFile, startAssetServer, withServedAssets} from "../src/asset-server.mjs";

function folder() {
  const root = mkdtempSync(path.join(tmpdir(), "assets-"));
  writeFileSync(path.join(root, "abc.jpg"), "picture");
  return root;
}

test("only a real file inside the directory is served", () => {
  const root = folder();
  writeFileSync(path.join(path.dirname(root), "secret.txt"), "no");
  symlinkSync(path.join(path.dirname(root), "secret.txt"), path.join(root, "link.jpg"));
  mkdirSync(path.join(root, "dir"));
  assert.ok(servedFile(root, "/abc.jpg"));
  for (const url of ["/../secret.txt", "/%2e%2e/secret.txt", "/link.jpg", "/dir", "/", "/%zz", "/none.jpg"]) {
    assert.equal(servedFile(root, url), null, url);
  }
});

test("the server answers on loopback with the file, and refuses the rest", async () => {
  const served = await startAssetServer(folder());
  try {
    assert.match(served.url, /^http:\/\/127\.0\.0\.1:\d+$/);
    const found = await fetch(`${served.url}/abc.jpg`);
    assert.equal(found.status, 200);
    assert.equal(found.headers.get("content-type"), "image/jpeg");
    assert.equal(await found.text(), "picture");
    assert.equal((await fetch(`${served.url}/nope.jpg`)).status, 404);
    assert.equal((await fetch(`${served.url}/abc.jpg`, {method: "POST"})).status, 403);
  } finally {
    await served.close();
  }
});

test("a bundle's nested files are served with their types", async () => {
  const root = folder();
  mkdirSync(path.join(root, "public"));
  writeFileSync(path.join(root, "index.html"), "<html>");
  writeFileSync(path.join(root, "public", "bundle.js"), "code");
  const served = await startAssetServer(root);
  try {
    assert.equal((await fetch(`${served.url}/index.html`)).headers.get("content-type"), "text/html; charset=utf-8");
    assert.equal(await (await fetch(`${served.url}/public/bundle.js`)).text(), "code");
  } finally {
    await served.close();
  }
});

test("two servers never share a port", async () => {
  const [one, two] = await Promise.all([startAssetServer(folder()), startAssetServer(folder())]);
  try {
    assert.notEqual(one.url, two.url);
  } finally {
    await one.close();
    await two.close();
  }
});

test("depth layers get sources too, and a shot without them gets none", () => {
  const input = {shots: [{id: "a", image: "a.jpg", depth: {far: "f.png", mid: "m.png", near: "n.png", model: "x"}}, {id: "b", image: "b.jpg"}]};
  const served = withServedAssets(input, "http://127.0.0.1:9");
  assert.equal(served.shots[0].depth.src.near, "http://127.0.0.1:9/n.png");
  assert.equal(served.shots[0].depth.far, "f.png");
  assert.equal(served.shots[1].depth, undefined);
});

test("every still gets a source, including panes, and the input is not changed", () => {
  const input = {
    preview_banner: false,
    shots: [{id: "a", image: "x y.jpg"}, {id: "b", image: "b.png", split_panes: [{image: "p.jpg"}, {crop: {}}]}],
  };
  const before = JSON.stringify(input);
  const served = withServedAssets(input, "http://127.0.0.1:9");
  assert.equal(served.shots[0].src, "http://127.0.0.1:9/x%20y.jpg");
  assert.equal(served.shots[1].split_panes[0].src, "http://127.0.0.1:9/p.jpg");
  assert.equal(served.shots[1].split_panes[1].src, undefined);
  assert.equal(served.preview_banner, false);
  assert.equal(JSON.stringify(input), before);
});

test("a code-only key ignores the stills, and a bundled key does not", () => {
  const src = mkdtempSync(path.join(tmpdir(), "src-"));
  writeFileSync(path.join(src, "a.jsx"), "code");
  const lock = path.join(src, "lock");
  writeFileSync(lock, "lock");
  const root = folder();
  const bundled = bundleKey(src, lock, root);
  const code = bundleKey(src, lock);
  writeFileSync(path.join(root, "new.jpg"), "a new still");
  assert.notEqual(bundleKey(src, lock, root), bundled);
  assert.equal(bundleKey(src, lock), code);
  writeFileSync(path.join(src, "a.jsx"), "changed");
  assert.notEqual(bundleKey(src, lock), code);
});
