import { useEffect } from "react";
import { api } from "../api";
import { markHeard, unsent } from "./heard";

const FLUSH_MS = 4000;

/**
 * Report the seconds a media element plays with the sound on. ``media`` names the file
 * (``renders/<name>``) or the live mix (``live:<key>``); the engine unions what it gets.
 */
export function useHeard(
  slug: string | null,
  media: string | null,
  element: HTMLMediaElement | null,
  total?: number,
) {
  useEffect(() => {
    if (!slug || !media || !element) return;
    const heard = new Set<number>();
    const sent = new Set<number>();
    let timer: number | null = null;
    const flush = () => {
      const seconds = unsent(heard, sent);
      if (!seconds.length) return;
      seconds.forEach((second) => sent.add(second));
      const length = total && total > 0 ? Math.round(total) : undefined;
      void api.recordWatched(slug, media, seconds, length).catch(() => {
        // The request helper has already shown what went wrong; the seconds are sent again later.
        seconds.forEach((second) => sent.delete(second));
      });
    };
    const tick = () => {
      markHeard(heard, element.currentTime, {
        muted: element.muted,
        volume: element.volume,
        paused: element.paused,
      });
      if (timer === null) timer = window.setTimeout(() => {
        timer = null;
        flush();
      }, FLUSH_MS);
    };
    const stop = () => {
      flush();
    };
    element.addEventListener("timeupdate", tick);
    element.addEventListener("pause", stop);
    element.addEventListener("ended", stop);
    return () => {
      element.removeEventListener("timeupdate", tick);
      element.removeEventListener("pause", stop);
      element.removeEventListener("ended", stop);
      if (timer !== null) window.clearTimeout(timer);
      flush();
    };
  }, [slug, media, element, total]);
}
