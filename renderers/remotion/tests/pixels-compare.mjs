// A PNG reader and structural similarity in plain JavaScript, so the pixel check adds no dependency.
import {inflateSync} from "node:zlib";

const CHANNELS = {0: 1, 2: 3, 4: 2, 6: 4};

function paeth(a, b, c) {
  const p = a + b - c;
  const pa = Math.abs(p - a);
  const pb = Math.abs(p - b);
  const pc = Math.abs(p - c);
  if (pa <= pb && pa <= pc) return a;
  return pb <= pc ? b : c;
}

/** 8-bit non-interlaced PNG to grayscale: {width, height, gray}. */
export function decodePng(buffer) {
  let at = 8;
  let width = 0;
  let height = 0;
  let channels = 0;
  const data = [];
  while (at < buffer.length) {
    const length = buffer.readUInt32BE(at);
    const type = buffer.toString("latin1", at + 4, at + 8);
    const body = buffer.subarray(at + 8, at + 8 + length);
    if (type === "IHDR") {
      width = body.readUInt32BE(0);
      height = body.readUInt32BE(4);
      channels = CHANNELS[body[9]];
      if (body[8] !== 8 || !channels || body[12] !== 0) throw new Error("unsupported PNG");
    } else if (type === "IDAT") {
      data.push(body);
    }
    at += 12 + length;
  }
  const raw = inflateSync(Buffer.concat(data));
  const stride = width * channels;
  const rows = new Uint8Array(height * stride);
  for (let y = 0; y < height; y += 1) {
    const filter = raw[y * (stride + 1)];
    const line = y * (stride + 1) + 1;
    for (let x = 0; x < stride; x += 1) {
      const left = x >= channels ? rows[y * stride + x - channels] : 0;
      const up = y > 0 ? rows[(y - 1) * stride + x] : 0;
      const corner = x >= channels && y > 0 ? rows[(y - 1) * stride + x - channels] : 0;
      const predicted = [0, left, up, (left + up) >> 1, paeth(left, up, corner)][filter];
      rows[y * stride + x] = (raw[line + x] + predicted) & 255;
    }
  }
  const gray = new Float64Array(width * height);
  for (let i = 0; i < gray.length; i += 1) {
    const p = i * channels;
    gray[i] = channels >= 3 ? 0.299 * rows[p] + 0.587 * rows[p + 1] + 0.114 * rows[p + 2] : rows[p];
  }
  return {width, height, gray};
}

/** Mean structural similarity over 8×8 blocks of two same-sized gray images. 1 is identical. */
export function ssim(a, b, block = 8) {
  if (a.width !== b.width || a.height !== b.height) return 0;
  const c1 = (0.01 * 255) ** 2;
  const c2 = (0.03 * 255) ** 2;
  let total = 0;
  let count = 0;
  for (let y = 0; y + block <= a.height; y += block) {
    for (let x = 0; x + block <= a.width; x += block) {
      let meanA = 0;
      let meanB = 0;
      for (let j = 0; j < block; j += 1) {
        for (let i = 0; i < block; i += 1) {
          meanA += a.gray[(y + j) * a.width + x + i];
          meanB += b.gray[(y + j) * a.width + x + i];
        }
      }
      const n = block * block;
      meanA /= n;
      meanB /= n;
      let varA = 0;
      let varB = 0;
      let cov = 0;
      for (let j = 0; j < block; j += 1) {
        for (let i = 0; i < block; i += 1) {
          const da = a.gray[(y + j) * a.width + x + i] - meanA;
          const db = b.gray[(y + j) * a.width + x + i] - meanB;
          varA += da * da;
          varB += db * db;
          cov += da * db;
        }
      }
      varA /= n - 1;
      varB /= n - 1;
      cov /= n - 1;
      total +=
        ((2 * meanA * meanB + c1) * (2 * cov + c2)) /
        ((meanA * meanA + meanB * meanB + c1) * (varA + varB + c2));
      count += 1;
    }
  }
  return total / count;
}
