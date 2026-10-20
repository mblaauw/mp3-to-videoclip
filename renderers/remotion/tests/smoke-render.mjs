#!/usr/bin/env node
// Bounded end-to-end smoke test for render.mjs: one real 160x90 base render.
//
// It writes its own temporary asset root (two generated PNGs), a request and a
// temporary bundle cache, runs the CLI exactly as the Python adapter will, and
// checks the published output, the sidecar contract, the request hash and the
// no-overwrite rule. Nothing here is a film: it is the smallest real proof that
// the entry point, the local Chrome and the local encoder work.
//
//   npm run smoke          # full check
//   KEEP_SMOKE=1 npm run smoke   # keep the temporary directory for inspection
import {spawnSync} from "node:child_process";
import {existsSync, mkdirSync, mkdtempSync, readFileSync, rmSync, statSync, writeFileSync} from "node:fs";
import {tmpdir} from "node:os";
import path from "node:path";
import process from "node:process";
import {fileURLToPath} from "node:url";
import {deflateSync} from "node:zlib";

import {requestSha256} from "../src/request.mjs";

const RENDERER_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const WIDTH = 160;
const HEIGHT = 90;
const FPS = 6;
const SHOTS = [
  {id: "s1", image: "shot-1.png", start_frame: 0, duration_frames: 6, dissolve_frames: 2, camera: "hold"},
  {id: "s2", image: "shot-2.png", start_frame: 6, duration_frames: 4, camera: "zoom_in"},
];
const FRAMES = 10;
const SIDECAR_FIELDS = [
  "frames",
  "width",
  "height",
  "fps",
  "kind",
  "request_sha256",
  "render_seconds",
  "remotion_version",
  "bundle_cached",
];

// --------------------------------------------------------------------------- //
// a real 8-bit truecolour PNG, so the smoke test needs no binary fixture
// --------------------------------------------------------------------------- //
const CRC_TABLE = (() => {
  const table = new Int32Array(256);
  for (let n = 0; n < 256; n += 1) {
    let c = n;
    for (let k = 0; k < 8; k += 1) c = (c & 1) === 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
    table[n] = c;
  }
  return table;
})();

function crc32(buffer) {
  let crc = -1;
  for (const byte of buffer) crc = CRC_TABLE[(crc ^ byte) & 0xff] ^ (crc >>> 8);
  return (crc ^ -1) >>> 0;
}

function chunk(type, data) {
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length);
  const payload = Buffer.concat([Buffer.from(type, "latin1"), data]);
  const crc = Buffer.alloc(4);
  crc.writeUInt32BE(crc32(payload));
  return Buffer.concat([length, payload, crc]);
}

function png(width, height, [r, g, b]) {
  const ihdr = Buffer.alloc(13);
  ihdr.writeUInt32BE(width, 0);
  ihdr.writeUInt32BE(height, 4);
  ihdr[8] = 8;
  ihdr[9] = 2;
  const stride = 1 + width * 3;
  const raw = Buffer.alloc(height * stride);
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) {
      const at = y * stride + 1 + x * 3;
      raw[at] = r;
      raw[at + 1] = g;
      raw[at + 2] = b;
    }
  }
  return Buffer.concat([
    Buffer.from([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a]),
    chunk("IHDR", ihdr),
    chunk("IDAT", deflateSync(raw)),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

function assert(condition, message) {
  if (!condition) throw new Error(message);
}

function runCli(args) {
  const result = spawnSync(process.execPath, [path.join(RENDERER_ROOT, "render.mjs"), ...args], {
    cwd: RENDERER_ROOT,
    encoding: "utf8",
    timeout: 600_000,
  });
  if (result.error) throw result.error;
  return result;
}

function main() {
  const work = mkdtempSync(path.join(tmpdir(), "mp3-to-videoclip-smoke-"));
  try {
    const assetRoot = path.join(work, "assets");
    mkdirSync(assetRoot, {recursive: true});
    writeFileSync(path.join(assetRoot, "shot-1.png"), png(WIDTH, HEIGHT, [24, 18, 48]));
    writeFileSync(path.join(assetRoot, "shot-2.png"), png(WIDTH, HEIGHT, [180, 60, 40]));

    const output = path.join(work, "smoke.mp4");
    const request = {
      kind: "base",
      output,
      width: WIDTH,
      height: HEIGHT,
      fps: FPS,
      frames: FRAMES,
      assetRoot,
      concurrency: 2,
      input: {shots: SHOTS},
    };
    const requestPath = path.join(work, "request.json");
    writeFileSync(requestPath, `${JSON.stringify(request, null, 2)}\n`);
    const cacheRoot = path.join(work, "cache");

    const first = runCli([requestPath, "--cache-dir", cacheRoot]);
    process.stdout.write(first.stdout ?? "");
    process.stderr.write(first.stderr ?? "");
    assert(first.status === 0, `render.mjs exited ${first.status}`);
    const stdoutLines = (first.stdout ?? "").trim().split("\n");
    assert(stdoutLines.length === 1, `stdout must be one JSON line, got ${stdoutLines.length}`);
    const summary = JSON.parse(stdoutLines[0]);
    assert(summary.output === output, "stdout must report the output path");
    assert(summary.kind === "base", "stdout must report the kind");
    assert(summary.frames === FRAMES && summary.width === WIDTH && summary.height === HEIGHT);
    assert(existsSync(output), "no output file was published");
    assert(statSync(output).size > 0, "published output is empty");

    const sidecarPath = `${output}.render.json`;
    assert(existsSync(sidecarPath), "no JSON sidecar was written");
    const sidecar = JSON.parse(readFileSync(sidecarPath, "utf8"));
    for (const field of SIDECAR_FIELDS) {
      assert(sidecar[field] !== undefined, `sidecar is missing ${field}`);
    }
    assert(sidecar.request_sha256 === requestSha256(request), "sidecar request hash does not match the request");
    assert(sidecar.kind === "base" && sidecar.frames === FRAMES && sidecar.fps === FPS);
    assert(sidecar.bundle_cached === false, "the first render should have built the bundle");
    assert(sidecar.render_seconds > 0, "render_seconds must be measured");

    const second = runCli([requestPath, "--cache-dir", cacheRoot]);
    assert(second.status !== 0, "a second render over an existing output must fail");
    assert(
      /refusing to overwrite/.test(second.stderr ?? ""),
      `expected the no-overwrite refusal, got: ${(second.stderr ?? "").trim()}`,
    );

    process.stdout.write(
      `smoke: ok  ${WIDTH}x${HEIGHT} ${FRAMES} frames  ` +
        `${statSync(output).size} bytes  ${sidecar.render_seconds}s  ` +
        `remotion ${sidecar.remotion_version}\n`,
    );
  } finally {
    if (process.env.KEEP_SMOKE === "1") process.stdout.write(`smoke: kept ${work}\n`);
    else rmSync(work, {recursive: true, force: true});
  }
}

main();
