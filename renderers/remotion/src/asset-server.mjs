// A loopback file server for one render: the stills, so the bundle holds code only and a
// new still never rebundles, and the bundle, on a port no other renderer can be using.
// It serves one directory of immutable files, to this computer alone, and nothing outside.
import {createHash} from "node:crypto";
import {createReadStream, lstatSync, readdirSync, readFileSync, realpathSync} from "node:fs";
import {createServer} from "node:http";
import path from "node:path";

const LOOPBACK = new Set(["127.0.0.1", "::1", "::ffff:127.0.0.1"]);
const TYPES = {
  ".jpg": "image/jpeg",
  ".jpeg": "image/jpeg",
  ".png": "image/png",
  ".webp": "image/webp",
  ".mp4": "video/mp4",
  ".html": "text/html; charset=utf-8",
  ".js": "text/javascript; charset=utf-8",
  ".css": "text/css; charset=utf-8",
  ".json": "application/json",
  ".map": "application/json",
  ".woff2": "font/woff2",
};

/** The real file a URL path names inside `root`, or null for anything else. */
export function servedFile(root, urlPath) {
  let name;
  try {
    name = decodeURIComponent(urlPath.split("?")[0]).replace(/^\/+/, "");
  } catch {
    return null;
  }
  if (!name || name.includes("\0")) return null;
  const base = realpathSync(root);
  const target = path.resolve(base, name);
  if (path.dirname(target) !== base && !target.startsWith(`${base}${path.sep}`)) return null;
  try {
    if (!lstatSync(target).isFile()) return null;
  } catch {
    return null;
  }
  return target;
}

export function startAssetServer(root) {
  const server = createServer((request, response) => {
    if (!LOOPBACK.has(request.socket.remoteAddress) || !["GET", "HEAD"].includes(request.method)) {
      response.writeHead(403).end();
      return;
    }
    const file = servedFile(root, request.url);
    if (!file) {
      response.writeHead(404).end();
      return;
    }
    response.writeHead(200, {
      "Content-Type": TYPES[path.extname(file).toLowerCase()] ?? "application/octet-stream",
      "Cache-Control": "public, max-age=31536000, immutable",
    });
    if (request.method === "HEAD") response.end();
    else createReadStream(file).pipe(response);
  });
  return new Promise((resolve, reject) => {
    server.once("error", reject);
    server.listen(0, "127.0.0.1", () => {
      resolve({
        url: `http://127.0.0.1:${server.address().port}`,
        close: () => new Promise((done) => server.close(done)),
      });
    });
  });
}

/** The content-addressed clip files a film's own request names. */
export function clipFiles(input) {
  return new Set((input?.shots ?? []).flatMap((shot) => (shot.clip ? [shot.clip.file] : [])));
}

/** True only for a file this request named, on this computer. Everything else stays refused. */
export function isOwnClip(src, names) {
  let url;
  try {
    url = new URL(src);
  } catch {
    return false;
  }
  if (url.protocol !== "http:" || !["127.0.0.1", "localhost"].includes(url.hostname)) return false;
  const name = decodeURIComponent(url.pathname.split("/").pop() ?? "");
  return names.has(name);
}

function withSource(item, url) {
  return item.image ? {...item, src: `${url}/${encodeURIComponent(item.image)}`} : item;
}

function withLayerSources(depth, url) {
  const src = {};
  for (const layer of ["far", "mid", "near"]) src[layer] = `${url}/${encodeURIComponent(depth[layer])}`;
  return {...depth, src};
}

/** The render's input with every still loaded from the server. The request is untouched. */
export function withServedAssets(input, url) {
  return {
    ...input,
    shots: (input.shots ?? []).map((shot) => ({
      ...withSource(shot, url),
      ...(shot.split_panes ? {split_panes: shot.split_panes.map((pane) => withSource(pane, url))} : {}),
      ...(shot.depth ? {depth: withLayerSources(shot.depth, url)} : {}),
      ...(shot.clip ? {clip: {...shot.clip, src: `${url}/${encodeURIComponent(shot.clip.file)}`}} : {}),
    })),
  };
}

function sha256File(file) {
  return createHash("sha256").update(readFileSync(file)).digest("hex");
}

function listFiles(root, prefix = "") {
  const files = [];
  for (const entry of readdirSync(root, {withFileTypes: true}).sort((a, b) => a.name.localeCompare(b.name))) {
    const full = path.join(root, entry.name);
    const relative = prefix === "" ? entry.name : `${prefix}/${entry.name}`;
    if (entry.isDirectory()) files.push(...listFiles(full, relative));
    else if (entry.isFile()) files.push([relative, full]);
  }
  return files;
}

/**
 * Content key for the bundle: every source file and the lockfile. With `assetRoot` it
 * also holds every asset, for a bundle that carries them; without it, code alone.
 */
export function bundleKey(srcDir, lockfile, assetRoot = null) {
  const hash = createHash("sha256");
  hash.update(`mp3-to-videoclip-remotion-bundle-${assetRoot ? "v2" : "v3-code-only"}\n`);
  for (const [relative, full] of listFiles(srcDir)) {
    hash.update(`src:${relative}:${sha256File(full)}\n`);
  }
  hash.update(`lock:${sha256File(lockfile)}\n`);
  if (assetRoot) {
    for (const [relative, full] of listFiles(assetRoot)) {
      hash.update(`asset:${relative}:${sha256File(full)}\n`);
    }
  }
  return hash.digest("hex");
}
