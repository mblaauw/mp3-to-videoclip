/** The still sources of a cut, nearest the given frame first, each once. */
export function stillSources(
  shots: readonly { start_frame?: number; src?: string | null; split_panes?: readonly { src?: string | null }[] | null }[],
  frame: number,
): string[] {
  const ordered = [...shots].sort(
    (a, b) => Math.abs((a.start_frame ?? 0) - frame) - Math.abs((b.start_frame ?? 0) - frame),
  );
  const sources = new Set<string>();
  for (const shot of ordered) {
    if (shot.src) sources.add(shot.src);
    for (const pane of shot.split_panes ?? []) if (pane.src) sources.add(pane.src);
  }
  return [...sources];
}

/**
 * Fetch and decode stills ahead of time, a few at once, so a jump along the film finds its
 * picture ready instead of showing black. Returns a function that stops loading more.
 */
export function preloadStills(sources: readonly string[], atOnce = 4): () => void {
  let next = 0;
  let stopped = false;
  // Holding each image stops the browser dropping its decoded picture straight away.
  const held: HTMLImageElement[] = [];
  const loadNext = () => {
    if (stopped || next >= sources.length) return;
    const image = new Image();
    held.push(image);
    image.src = sources[next++];
    void image.decode().catch(() => undefined).then(loadNext);
  };
  for (let slot = 0; slot < atOnce; slot += 1) loadNext();
  return () => {
    stopped = true;
    held.length = 0;
  };
}
