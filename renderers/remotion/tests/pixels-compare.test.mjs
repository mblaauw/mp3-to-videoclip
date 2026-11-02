import assert from "node:assert/strict";
import test from "node:test";
import {deflateSync} from "node:zlib";

import {decodePng, ssim} from "./pixels-compare.mjs";

function chunk(type, data) {
  const length = Buffer.alloc(4);
  length.writeUInt32BE(data.length);
  return Buffer.concat([length, Buffer.from(type, "latin1"), data, Buffer.alloc(4)]);
}

function png(width, height, pixel) {
  const header = Buffer.alloc(13);
  header.writeUInt32BE(width, 0);
  header.writeUInt32BE(height, 4);
  header[8] = 8;
  header[9] = 0;
  const raw = Buffer.alloc((width + 1) * height);
  for (let y = 0; y < height; y += 1) {
    for (let x = 0; x < width; x += 1) raw[y * (width + 1) + 1 + x] = pixel(x, y);
  }
  return Buffer.concat([
    Buffer.alloc(8),
    chunk("IHDR", header),
    chunk("IDAT", deflateSync(raw)),
    chunk("IEND", Buffer.alloc(0)),
  ]);
}

const stripes = (x) => (x % 16 < 8 ? 40 : 200);

test("a PNG reads back as its gray values", () => {
  const image = decodePng(png(16, 8, stripes));
  assert.equal(image.width, 16);
  assert.equal(image.gray[0], 40);
  assert.equal(image.gray[8], 200);
});

test("identical images score one and a moved pattern scores far less", () => {
  const a = decodePng(png(64, 32, stripes));
  assert.equal(ssim(a, a), 1);
  const moved = decodePng(png(64, 32, (x) => stripes(x + 8)));
  assert.ok(ssim(a, moved) < 0.5);
});

test("a tiny difference still passes the threshold", () => {
  const a = decodePng(png(64, 32, stripes));
  const near = decodePng(png(64, 32, (x, y) => stripes(x) + (x + y) % 2));
  assert.ok(ssim(a, near) > 0.98);
});

test("different sizes are not the same picture", () => {
  assert.equal(ssim(decodePng(png(8, 8, stripes)), decodePng(png(16, 8, stripes))), 0);
});
