import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
  type ReactNode,
} from "react";

/** A span the player repeats while it plays (a shot, a section, the excerpt). */
export type LoopRange = { start: number; end: number; label: string };

type TimeStore = {
  get: () => number;
  subscribe: (listener: () => void) => () => void;
};

export type PlayerControls = {
  duration: number;
  playing: boolean;
  volume: number;
  muted: boolean;
  rate: number;
  loop: LoopRange | null;
  seek: (seconds: number) => void;
  seekBy: (seconds: number) => void;
  toggle: () => void;
  play: () => void;
  pause: () => void;
  setVolume: (value: number) => void;
  toggleMute: () => void;
  setRate: (value: number) => void;
  setLoop: (range: LoopRange | null) => void;
  /** The exact playhead now, without subscribing to it. */
  current: () => number;
  clock: TimeStore;
};

type PlayerContextValue = PlayerControls;

const PlayerContext = createContext<PlayerContextValue | null>(null);

const VOLUME_KEY = "studio:player-volume";

function clamp(value: number, low: number, high: number): number {
  return Math.max(low, Math.min(high, value));
}

function storedVolume(): { volume: number; muted: boolean } {
  try {
    const raw = window.localStorage.getItem(VOLUME_KEY);
    if (!raw) return { volume: 1, muted: false };
    const value = JSON.parse(raw) as { volume?: number; muted?: boolean };
    return {
      volume: clamp(Number(value.volume ?? 1), 0, 1),
      muted: Boolean(value.muted),
    };
  } catch {
    return { volume: 1, muted: false };
  }
}

/**
 * One audio element and one time store for the spine, Track, Film and the
 * director. The provider is keyed by project so switching stages never
 * restarts the song.
 *
 * The playhead lives in an external store, not in context state: consumers
 * that only need the controls (or the time once a second) no longer re-render
 * sixty times a second while the song plays.
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
  const timeRef = useRef(0);
  const listeners = useRef(new Set<() => void>());
  const [duration, setDuration] = useState(fallbackDuration || 0);
  const [playing, setPlaying] = useState(false);
  const [{ volume, muted }, setSound] = useState(storedVolume);
  const [rate, setRateState] = useState(1);
  const [loop, setLoopState] = useState<LoopRange | null>(null);
  const loopRef = useRef<LoopRange | null>(null);
  loopRef.current = loop;
  const durationRef = useRef(duration);
  durationRef.current = duration || fallbackDuration || 0;

  const publish = useCallback((value: number) => {
    if (value === timeRef.current) return;
    timeRef.current = value;
    for (const listener of listeners.current) listener();
  }, []);

  const clock = useMemo<TimeStore>(
    () => ({
      get: () => timeRef.current,
      subscribe: (listener) => {
        listeners.current.add(listener);
        return () => listeners.current.delete(listener);
      },
    }),
    [],
  );

  useEffect(() => {
    publish(0);
    setDuration(fallbackDuration || 0);
    setPlaying(false);
    setLoopState(null);
  }, [src, fallbackDuration, publish]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    audio.volume = volume;
    audio.muted = muted;
    try {
      window.localStorage.setItem(VOLUME_KEY, JSON.stringify({ volume, muted }));
    } catch {
      // Private windows may refuse storage; the setting just is not remembered.
    }
  }, [muted, volume, src]);

  useEffect(() => {
    const audio = audioRef.current;
    if (audio) audio.playbackRate = rate;
  }, [rate, src]);

  useEffect(() => {
    const audio = audioRef.current;
    if (!audio) return;
    const sync = () => {
      publish(audio.currentTime || 0);
      if (Number.isFinite(audio.duration) && audio.duration > 0) setDuration(audio.duration);
    };
    const onPlay = () => setPlaying(true);
    const onPause = () => setPlaying(false);
    const onEnded = () => {
      const range = loopRef.current;
      if (range) {
        audio.currentTime = range.start;
        void audio.play().catch(() => setPlaying(false));
        return;
      }
      setPlaying(false);
    };
    audio.addEventListener("timeupdate", sync);
    audio.addEventListener("loadedmetadata", sync);
    audio.addEventListener("durationchange", sync);
    audio.addEventListener("seeked", sync);
    audio.addEventListener("play", onPlay);
    audio.addEventListener("pause", onPause);
    audio.addEventListener("ended", onEnded);
    sync();
    return () => {
      audio.removeEventListener("timeupdate", sync);
      audio.removeEventListener("loadedmetadata", sync);
      audio.removeEventListener("durationchange", sync);
      audio.removeEventListener("seeked", sync);
      audio.removeEventListener("play", onPlay);
      audio.removeEventListener("pause", onPause);
      audio.removeEventListener("ended", onEnded);
    };
  }, [src, publish]);

  useEffect(() => {
    if (!playing) return;
    let frame = 0;
    const tick = () => {
      const audio = audioRef.current;
      if (audio) {
        const range = loopRef.current;
        if (range && audio.currentTime >= range.end) {
          audio.currentTime = range.start;
        }
        publish(audio.currentTime || 0);
      }
      frame = requestAnimationFrame(tick);
    };
    frame = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(frame);
  }, [playing, publish]);

  const seek = useCallback(
    (seconds: number) => {
      const audio = audioRef.current;
      const target = clamp(seconds, 0, durationRef.current);
      if (audio) audio.currentTime = target;
      publish(target);
    },
    [publish],
  );

  const seekBy = useCallback((seconds: number) => seek(timeRef.current + seconds), [seek]);

  const play = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;
    const range = loopRef.current;
    if (range && (audio.currentTime < range.start || audio.currentTime >= range.end)) {
      audio.currentTime = range.start;
    }
    void audio.play().catch(() => setPlaying(false));
  }, []);

  const pause = useCallback(() => {
    audioRef.current?.pause();
  }, []);

  const toggle = useCallback(() => {
    const audio = audioRef.current;
    if (!audio) return;
    if (audio.paused) play();
    else audio.pause();
  }, [play]);

  const setVolume = useCallback((value: number) => {
    setSound({ volume: clamp(value, 0, 1), muted: value <= 0 });
  }, []);

  const toggleMute = useCallback(() => {
    setSound((current) => ({
      volume: current.volume > 0 ? current.volume : 1,
      muted: !current.muted,
    }));
  }, []);

  const setRate = useCallback((value: number) => setRateState(clamp(value, 0.25, 2)), []);

  const setLoop = useCallback(
    (range: LoopRange | null) => {
      setLoopState(range);
      if (range && (timeRef.current < range.start || timeRef.current >= range.end)) {
        seek(range.start);
      }
    },
    [seek],
  );

  const current = useCallback(() => timeRef.current, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.metaKey || event.ctrlKey || event.altKey) return;
      const target = event.target as HTMLElement | null;
      if (
        target?.closest(
          "input, textarea, select, [contenteditable='true']",
        )
      ) {
        return;
      }
      if (event.code === "Space") {
        // Buttons and sliders handle Space themselves.
        if (target?.closest("button, a, [role='slider'], [role='button']")) return;
        event.preventDefault();
        toggle();
        return;
      }
      if (event.key === "m" || event.key === "M") {
        event.preventDefault();
        toggleMute();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [toggle, toggleMute]);

  const value = useMemo<PlayerContextValue>(
    () => ({
      duration,
      playing,
      volume,
      muted,
      rate,
      loop,
      seek,
      seekBy,
      toggle,
      play,
      pause,
      setVolume,
      toggleMute,
      setRate,
      setLoop,
      current,
      clock,
    }),
    [
      duration,
      playing,
      volume,
      muted,
      rate,
      loop,
      seek,
      seekBy,
      toggle,
      play,
      pause,
      setVolume,
      toggleMute,
      setRate,
      setLoop,
      current,
      clock,
    ],
  );

  return (
    <PlayerContext.Provider value={value}>
      <audio ref={audioRef} src={src ?? undefined} preload="metadata" className="player-audio" />
      {children}
    </PlayerContext.Provider>
  );
}

/** The controls only; does not re-render as the playhead moves. */
export function usePlayerControls(): PlayerControls {
  const value = useContext(PlayerContext);
  if (!value) throw new Error("usePlayer must be used inside PlayerProvider");
  return value;
}

/**
 * The playhead, re-rendering only when it moves by at least `step` seconds
 * (0 = every frame, for the playhead line and the synced preview).
 */
export function usePlayerTime(step = 0): number {
  const { clock } = usePlayerControls();
  const read = useCallback(() => {
    const value = clock.get();
    return step > 0 ? Math.floor(value / step) * step : value;
  }, [clock, step]);
  return useSyncExternalStore(clock.subscribe, read, read);
}

/** The controls plus the frame-accurate time (the spine's playhead). */
export function usePlayer(): PlayerControls & { time: number } {
  const controls = usePlayerControls();
  const time = usePlayerTime(0);
  return { ...controls, time };
}

/** Whole seconds for labels, plus an exact read for sending with a message. */
export function usePlayerClock(): { seconds: number; current: () => number } {
  const controls = usePlayerControls();
  const seconds = usePlayerTime(1);
  return { seconds, current: controls.current };
}
