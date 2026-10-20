// Throttled, atomic progress reporting for the render CLI.
//
// The Python caller polls this file while the render runs, so a long silent
// render becomes an observable phase instead of an unexplained wait. Progress is
// a courtesy to the caller: a broken or unwritable path must never fail a render,
// so every write is best-effort and errors are swallowed.
import {renameSync, rmSync, writeFileSync} from "node:fs";
import path from "node:path";

export const PROGRESS_VERSION = 1;

/**
 * @param {string|undefined|null} file target path; disabled when absent
 * @param {{now?: () => number, everyMs?: number}} [options]
 */
export function createProgressWriter(file, options = {}) {
  const now = options.now ?? (() => Date.now());
  const everyMs = options.everyMs ?? 500;
  let lastWritten = -Infinity;
  let lastPhase = null;

  if (!file) return {update() {}, close() {}};

  function write(payload) {
    const temporary = path.join(
      path.dirname(file),
      `.${path.basename(file)}.tmp-${process.pid}`,
    );
    try {
      writeFileSync(temporary, `${JSON.stringify(payload, null, 2)}\n`);
      renameSync(temporary, file);
    } catch {
      rmSync(temporary, {force: true});
    }
  }

  return {
    /** `phase` changes always write; frame ticks are throttled. */
    update(payload) {
      const stamp = now();
      const forced = payload.phase !== lastPhase;
      if (!forced && stamp - lastWritten < everyMs) return;
      lastWritten = stamp;
      lastPhase = payload.phase ?? lastPhase;
      write({version: PROGRESS_VERSION, updated_at: new Date().toISOString(), ...payload});
    },
    close() {
      try {
        rmSync(file, {force: true});
      } catch {
        // A leftover progress file is harmless; the durable record lives elsewhere.
      }
    },
  };
}
