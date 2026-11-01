/**
 * Saves one value at a time and never loses the newest. A value asked for while a
 * save is running waits, and only the latest waiting value is sent.
 */
export function latestSave<T>(send: (value: T) => Promise<void>) {
  let running = false;
  let waiting: { value: T } | null = null;
  return async (value: T): Promise<void> => {
    waiting = { value };
    if (running) return;
    running = true;
    try {
      while (waiting) {
        const next: { value: T } = waiting;
        waiting = null;
        await send(next.value);
      }
    } finally {
      running = false;
    }
  };
}
