import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";

type PlayerContextValue = {
  time: number;
  duration: number;
  playing: boolean;
  seek: (seconds: number) => void;
  seekBy: (seconds: number) => void;
  toggle: () => void;
  pause: () => void;
};

const PlayerContext = createContext<PlayerContextValue | null>(null);

function clamp(value: number, low: number, high: number): number {
  return Math.max(low, Math.min(high, value));
}

/**
 * One audio element and one time store for the spine, Track and Film. The
 * provider is keyed by project so switching stages never restarts the song.
 */
export function PlayerProvider({
  src,
  fallbackDuration,
  children,
}: {
  src: string | null;
  fallbackDuration: number;
  children: ReactNode;
}) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(fallbackDuration || 0);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    setTime(0);
    setDuration(fallbackDuration || 0);
    setPlaying(false);
  }, [src, fallbackDuration]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    const sync = () => {
      setTime(audio.currentTime || 0);
      if (Number.isFinite(audio.duration) && audio.duration > 0) setDuration(audio.duration);
    };
    const onPlay = () => setPlaying(true);
    const onPause = () => setPlaying(false);
    const onEnded = () => setPlaying(false);
    audio.addEventListener("timeupdate", sync);
    audio.addEventListener("loadedmetadata", sync);
    audio.addEventListener("durationchange", sync);
    audio.addEventListener("play", onPlay);
    audio.addEventListener("pause", onPause);
    audio.addEventListener("ended", onEnded);
    sync();
    return () => {
      audio.removeEventListener("timeupdate", sync);
      audio.removeEventListener("loadedmetadata", sync);
      audio.removeEventListener("durationchange", sync);
      audio.removeEventListener("play", onPlay);
      audio.removeEventListener("pause", onPause);
      audio.removeEventListener("ended", onEnded);
    };
  }, [src]);

  useEffect(() => {
    if (!playing) return;
    let frame = 0;
    const tick = () => {
      const audio = audioRef.current;
      if (audio) setTime(audio.currentTime || 0);
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing]);

  const seek = useCallback(
    (seconds: number) => {
      const audio = audioRef.current;
      const target = clamp(seconds, 0, duration || fallbackDuration || 0);
      if (audio) audio.currentTime = target;
      setTime(target);
    },
    [duration, fallbackDuration],
  );

  const seekBy = useCallback((seconds: number) => seek(time + seconds), [seek, time]);

  const toggle = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;
    if (audio.paused) {
      void audio.play().catch(() => setPlaying(false));
    } else {
      audio.pause();
    }
  }, []);

  const pause = useCallback(() => {
    audioRef.current?.pause();
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.code !== "Space" || event.metaKey || event.ctrlKey || event.altKey) return;
      const target = event.target as HTMLElement | null;
      if (
        target?.closest(
          "input, textarea, select, button, a, [contenteditable='true'], [role='slider']",
        )
      ) {
        return;
      }
      event.preventDefault();
      toggle();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggle]);

  const value = useMemo<PlayerContextValue>(
    () => ({ time, duration, playing, seek, seekBy, toggle, pause }),
    [time, duration, playing, seek, seekBy, toggle, pause],
  );

  return (
    <PlayerContext.Provider value={value}>
      <audio ref={audioRef} src={src ?? undefined} preload="metadata" className="player-audio" />
      {children}
    </PlayerContext.Provider>
  );
}

export function usePlayer(): PlayerContextValue {
  const value = useContext(PlayerContext);
  if (!value) throw new Error("usePlayer must be used inside PlayerProvider");
  return value;
}
