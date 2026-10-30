import { useCallback, useEffect, useRef, useState } from "react";
import { api, type LyricLine } from "../api";
import { toast } from "../toast";
import { toSave } from "./lyricTiming";

/** The words with their times. Changes show at once and save shortly after. */
export function useLyricTiming(slug: string, wordsKey: unknown) {
  const [lines, setLines] = useState<LyricLine[]>([]);
  const timer = useRef<number | null>(null);
  const pending = useRef<LyricLine[] | null>(null);

  const load = useCallback(async () => {
    try {
      const next = await api.lyricTiming(slug);
      setLines(next.lines);
    } catch {
      // request() already surfaced the error.
    }
  }, [slug]);

  const flush = useCallback(async () => {
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = null;
    const value = pending.current;
    pending.current = null;
    if (!value) return;
    try {
      await api.saveLyricTiming(slug, toSave(value));
    } catch (error) {
      toast(`Could not save the line times: ${String(error)}`);
      void load();
    }
  }, [load, slug]);

  useEffect(() => {
    void load();
  }, [load, wordsKey]);

  useEffect(
    () => () => {
      void flush();
    },
    [flush],
  );

  const change = useCallback(
    (next: LyricLine[]) => {
      setLines(next);
      pending.current = next;
      if (timer.current) window.clearTimeout(timer.current);
      timer.current = window.setTimeout(() => void flush(), 400);
    },
    [flush],
  );

  return { lines, change, flush, load };
}
