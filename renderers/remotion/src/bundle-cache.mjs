// Immutable, content-verified bundle publication; no Remotion/browser dependency.
import {createHash} from "node:crypto";
import {lstatSync, mkdirSync, mkdtempSync, readdirSync, readFileSync,
  renameSync, rmdirSync, writeFileSync} from "node:fs";
import path from "node:path";

export const BUNDLE_MANIFEST = "bundle-manifest.json";

function present(file) {
  try { return lstatSync(file); } catch (error) {
    if (error.code === "ENOENT") return null;
    throw error;
  }
}

function inventory(root, prefix = "") {
  const entries = [];
  if (!lstatSync(root).isDirectory()) throw new Error(`invalid bundle directory: ${root}`);
  for (const name of readdirSync(root).sort()) {
    if (!prefix && name === BUNDLE_MANIFEST) continue;
    const relative = prefix ? `${prefix}/${name}` : name;
    const full = path.join(root, name);
    const stat = lstatSync(full);
    if (stat.isDirectory()) {
      entries.push({path: relative, type: "directory"}, ...inventory(full, relative));
    } else if (stat.isFile()) {
      entries.push({path: relative, type: "file",
        sha256: createHash("sha256").update(readFileSync(full)).digest("hex")});
    } else {
      throw new Error(`nonregular bundle member: ${relative}`);
    }
  }
  return entries;
}

function requireKey(key) {
  if (typeof key !== "string" || !/^[a-f0-9]{64}$/.test(key)) {
    throw new Error("bundle key must be a full SHA256");
  }
}

export function validateBundle(cacheDir, key) {
  requireKey(key);
  const manifestPath = path.join(cacheDir, BUNDLE_MANIFEST);
  if (!lstatSync(cacheDir).isDirectory() || !lstatSync(manifestPath).isFile()) {
    throw new Error(`invalid bundle manifest at ${cacheDir}`);
  }
  const manifest = JSON.parse(readFileSync(manifestPath, "utf8"));
  const entries = inventory(cacheDir);
  if (!manifest || manifest.version !== 2 || manifest.key !== key ||
      Object.keys(manifest).sort().join(",") !== "entries,key,version" ||
      !entries.some((entry) => entry.path === "index.html" && entry.type === "file") ||
      JSON.stringify(manifest.entries) !== JSON.stringify(entries)) {
    throw new Error(`bundle integrity mismatch at ${cacheDir}; refusing reuse or repair`);
  }
  return cacheDir;
}

export async function ensureBundleCache({cacheDir, key, build}) {
  requireKey(key);
  if (present(cacheDir)) {
    validateBundle(cacheDir, key);
    return {serveUrl: cacheDir, bundleCached: true};
  }
  mkdirSync(path.dirname(cacheDir), {recursive: true});
  const staging = mkdtempSync(`${cacheDir}.staging-`);
  await build(staging);
  const manifest = {version: 2, key, entries: inventory(staging)};
  writeFileSync(path.join(staging, BUNDLE_MANIFEST), `${JSON.stringify(manifest)}\n`, {flag: "wx"});
  validateBundle(staging, key);

  // POSIX rename can replace an EMPTY directory. Serialize cooperating
  // publishers, then recheck existence before renaming, never replacing one.
  // A stale lock fails closed; neither it nor retained staging is repaired.
  const lock = `${cacheDir}.publish-lock`;
  let acquired = false;
  for (let attempt = 0; attempt < 200; attempt += 1) {
    try {
      mkdirSync(lock);
      acquired = true;
      break;
    } catch (error) {
      if (error.code !== "EEXIST") throw error;
      if (present(cacheDir)) {
        validateBundle(cacheDir, key);
        return {serveUrl: cacheDir, bundleCached: true};
      }
      await new Promise((resolve) => setTimeout(resolve, 10));
    }
  }
  if (!acquired) throw new Error(`bundle publication locked at ${lock}; evidence preserved`);
  try {
    if (present(cacheDir)) {
      validateBundle(cacheDir, key);
      return {serveUrl: cacheDir, bundleCached: true};
    }
    renameSync(staging, cacheDir);
    return {serveUrl: cacheDir, bundleCached: false};
  } finally {
    rmdirSync(lock); // Only our own newly created, empty publication lock.
  }
}
