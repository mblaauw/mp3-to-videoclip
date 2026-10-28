import assert from "node:assert/strict";
import {spawn, spawnSync} from "node:child_process";
import {mkdtempSync, mkdirSync, readFileSync, readdirSync, writeFileSync,
  unlinkSync, symlinkSync, lstatSync} from "node:fs";
import os from "node:os";
import path from "node:path";
import test from "node:test";
import {BUNDLE_MANIFEST, ensureBundleCache, validateBundle} from "../src/bundle-cache.mjs";

const key = "a".repeat(64);
function fixture() {
  const root = mkdtempSync(path.join(os.tmpdir(), "bundle-cache-test-"));
  return {root, cacheDir: path.join(root, key), key};
}
function build(dir) {
  writeFileSync(path.join(dir, "index.html"), "<html>bundle</html>");
  mkdirSync(path.join(dir, "assets"));
  writeFileSync(path.join(dir, "assets", "main.js"), "bundle bytes");
}
function snapshot(dir) {
  return readdirSync(dir).sort().map((name) => {
    const full = path.join(dir, name);
    const stat = lstatSync(full);
    return [name, stat.isSymbolicLink() ? "symlink" : stat.isDirectory()
      ? snapshot(full) : readFileSync(full).toString("hex")];
  });
}

test("valid hit verifies complete receipt without building", async () => {
  const f = fixture();
  assert.equal((await ensureBundleCache({...f, build})).bundleCached, false);
  const before = snapshot(f.root);
  assert.equal((await ensureBundleCache({...f, build: () => assert.fail("rebuilt")})).bundleCached, true);
  assert.deepEqual(snapshot(f.root), before);
  assert.equal(JSON.parse(readFileSync(path.join(f.cacheDir, BUNDLE_MANIFEST))).key, key);
});

const mutations = {
  bitflip: (dir) => writeFileSync(path.join(dir, "assets/main.js"), "changed bytes"),
  missing: (dir) => unlinkSync(path.join(dir, "assets/main.js")),
  extra: (dir) => writeFileSync(path.join(dir, "unexpected"), "evidence"),
  emptyDirectory: (dir) => mkdirSync(path.join(dir, "unexpected")),
  malformed: (dir) => writeFileSync(path.join(dir, BUNDLE_MANIFEST), "{bad"),
  wrongKey: (dir) => {
    const receipt = JSON.parse(readFileSync(path.join(dir, BUNDLE_MANIFEST)));
    receipt.key = "b".repeat(64);
    writeFileSync(path.join(dir, BUNDLE_MANIFEST), JSON.stringify(receipt));
  },
  noReceipt: (dir) => unlinkSync(path.join(dir, BUNDLE_MANIFEST)),
  symlink: (dir) => {
    unlinkSync(path.join(dir, "assets/main.js"));
    symlinkSync("../index.html", path.join(dir, "assets/main.js"));
  },
  manifestSymlink: (dir) => {
    unlinkSync(path.join(dir, BUNDLE_MANIFEST));
    symlinkSync("index.html", path.join(dir, BUNDLE_MANIFEST));
  },
  indexDirectory: (dir) => {
    unlinkSync(path.join(dir, "index.html"));
    mkdirSync(path.join(dir, "index.html"));
  },
};
for (const [label, mutate] of Object.entries(mutations)) {
  test(`${label} fails closed, preserving all evidence and never building`, async () => {
    const f = fixture();
    await ensureBundleCache({...f, build});
    mutate(f.cacheDir);
    const before = snapshot(f.root);
    await assert.rejects(ensureBundleCache({...f, build: () => assert.fail("rebuilt")}));
    assert.deepEqual(snapshot(f.root), before);
  });
}

test("partial and empty existing entries are not repaired or overwritten", async () => {
  for (const partial of [false, true]) {
    const f = fixture();
    mkdirSync(f.cacheDir);
    if (partial) writeFileSync(path.join(f.cacheDir, "index.html"), "partial");
    const before = snapshot(f.root);
    await assert.rejects(ensureBundleCache({...f, build: () => assert.fail("rebuilt")}));
    assert.deepEqual(snapshot(f.root), before);
  }
});

test("concurrent publishers reuse valid winner and retain private staging", async () => {
  const f = fixture();
  let release;
  const gate = new Promise((resolve) => { release = resolve; });
  let started = 0;
  const concurrentBuild = async (dir) => {
    build(dir);
    if (++started === 2) release();
    await gate;
  };
  const results = await Promise.all([1, 2].map(() => ensureBundleCache({...f, build: concurrentBuild})));
  assert.deepEqual(results.map((r) => r.bundleCached).sort(), [false, true]);
  validateBundle(f.cacheDir, key);
  assert.equal(readdirSync(f.root).filter((name) => name.includes(".staging-")).length, 1);
});

test("entry appearing during build is preserved, never replaced even when empty", async () => {
  const f = fixture();
  await assert.rejects(ensureBundleCache({...f, build: (dir) => {
    build(dir);
    mkdirSync(f.cacheDir);
  }}));
  assert.deepEqual(readdirSync(f.cacheDir), []);
  assert.equal(readdirSync(f.root).filter((name) => name.includes(".staging-")).length, 1);
});

test("old v1 entry and abandoned staging remain untouched", async () => {
  const f = fixture();
  const old = path.join(f.root, "a".repeat(32));
  mkdirSync(old);
  writeFileSync(path.join(old, "index.html"), "old v1");
  const stale = `${f.cacheDir}.staging-old`;
  mkdirSync(stale);
  writeFileSync(path.join(stale, "evidence"), "retained");
  await ensureBundleCache({...f, build});
  assert.equal(readFileSync(path.join(old, "index.html"), "utf8"), "old v1");
  assert.equal(readFileSync(path.join(stale, "evidence"), "utf8"), "retained");
});

test("nonregular FIFO and root symlink fail closed", async () => {
  const f = fixture();
  await ensureBundleCache({...f, build});
  assert.equal(spawnSync("mkfifo", [path.join(f.cacheDir, "pipe")]).status, 0);
  await assert.rejects(ensureBundleCache({...f, build: () => assert.fail("rebuilt")}));
  assert.equal(lstatSync(path.join(f.cacheDir, "pipe")).isFIFO(), true);
  const alias = path.join(f.root, "alias");
  symlinkSync(f.cacheDir, alias);
  await assert.rejects(ensureBundleCache({...f, cacheDir: alias, build: () => assert.fail("rebuilt")}));
  assert.equal(lstatSync(alias).isSymbolicLink(), true);
});

test("failed or incomplete build retains private staging without publishing", async () => {
  for (const failBuild of [false, true]) {
    const f = fixture();
    await assert.rejects(ensureBundleCache({...f, build: (dir) => {
      writeFileSync(path.join(dir, "evidence"), "partial build");
      if (failBuild) throw new Error("build failed");
    }}));
    assert.deepEqual(readdirSync(f.root).map((name) => name.startsWith(`${key}.staging-`)), [true]);
  }
});

test("stale publication lock fails closed and preserves lock and staging evidence", async () => {
  const f = fixture();
  const lock = `${f.cacheDir}.publish-lock`;
  mkdirSync(lock);
  writeFileSync(path.join(lock, "owner-evidence"), "investigate before recovery");
  const before = snapshot(lock);
  await assert.rejects(ensureBundleCache({...f, build}), /publication locked/);
  assert.deepEqual(snapshot(lock), before);
  assert.equal(readdirSync(f.root).includes(key), false);
  assert.equal(readdirSync(f.root).filter((name) => name.includes(".staging-")).length, 1);
});

test("independent Node processes publish the same key without overwrite", async () => {
  const f = fixture();
  const helper = new URL("../src/bundle-cache.mjs", import.meta.url).href;
  const script = `
    import {ensureBundleCache} from ${JSON.stringify(helper)};
    import {writeFileSync, existsSync} from 'node:fs';
    import path from 'node:path';
    const [root, cacheDir, key, id] = process.argv.slice(1);
    const result = await ensureBundleCache({cacheDir, key, build: async (dir) => {
      writeFileSync(path.join(dir, 'index.html'), 'identical bundle');
      writeFileSync(path.join(root, 'ready-' + id), 'ready');
      for (let n = 0; !existsSync(path.join(root, 'ready-' + (id === '1' ? '2' : '1'))); n++) {
        if (n > 500) throw new Error('peer timeout');
        await new Promise(resolve => setTimeout(resolve, 10));
      }
    }});
    console.log(JSON.stringify(result));
  `;
  const run = (id) => new Promise((resolve, reject) => {
    const child = spawn(process.execPath, ["--input-type=module", "-e", script, f.root, f.cacheDir, key, id]);
    let stdout = "", stderr = "";
    child.stdout.on("data", (data) => { stdout += data; });
    child.stderr.on("data", (data) => { stderr += data; });
    child.on("error", reject);
    child.on("close", (code) => code === 0 ? resolve(JSON.parse(stdout)) : reject(new Error(stderr)));
  });
  const results = await Promise.all([run("1"), run("2")]);
  assert.deepEqual(results.map((r) => r.bundleCached).sort(), [false, true]);
  validateBundle(f.cacheDir, key);
});
