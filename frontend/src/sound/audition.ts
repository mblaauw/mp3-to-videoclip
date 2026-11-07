import { useCallback, useEffect, useRef, useState } from "react";

/** One sound heard on its own, away from the film: a second press, or another sound, stops it. */
export function useAudition(onStart?: () => void): {
  playing: string | null;
  toggle: (key: string, url: string) => void;
  stop: () => void;
} {
  const audio = useRef<HTMLAudioElement | null>(null);
  const [playing, setPlaying] = useState<string | null>(null);
  const stop = useCallback(() => {
    audio.current?.pause();
    audio.current = null;
    setPlaying(null);
  }, []);
  useEffect(() => stop, [stop]);
  const toggle = useCallback(
    (key: string, url: string) => {
      if (playing === key) {
        stop();
        return;
      }
      audio.current?.pause();
      const next = new Audio(url);
      audio.current = next;
      next.addEventListener("ended", () => {
        if (audio.current === next) setPlaying(null);
      });
      onStart?.();
      setPlaying(key);
      void next.play().catch(() => {
        if (audio.current === next) setPlaying(null);
      });
    },
    [onStart, playing, stop],
  );
  return { playing, toggle, stop };
}
