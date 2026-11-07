import { useEffect, useMemo, useRef, useState, type MouseEvent, type ReactNode } from "react";
import type { Music, SoundPayload } from "../api";
import { usePlayerControls, usePlayerTime } from "../spine/player";
import { Waveform } from "../spine/Waveform";
import { waveformBars } from "../spine/wave";
import { PlusIcon } from "../ui/icons";
import { chosen, clockTenths, heardSpan, KIND_LABEL, packRows, rulerTicks, type Cue, type CueKind } from "./cueBands";

/** What a click on the map chose: a moment, or a shot's cut. */
export type Pick = { kind: "time"; seconds: number } | { kind: "shot"; id: string; seconds: number };

const LANES: { kind: CueKind; label: string; add: string }[] = [
  { kind: "music", label: "Music", add: "Add music" },
  { kind: "ambience", label: "Ambience", add: "Add ambience" },
  { kind: "effect", label: "Effects", add: "Add an effect" },
];

/** Pixels a cue's name needs beside or inside its band, at the map's 12px. */
const labelPixels = (id: string) => id.length * 6.6 + 18;

function clock(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

/** The width of the tracks, so names that do not fit their band can sit beside it. */
function useTrackWidth(): [React.RefObject<HTMLDivElement | null>, number] {
  const ref = useRef<HTMLDivElement | null>(null);
  const [width, setWidth] = useState(900);
  useEffect(() => {
    const node = ref.current;
    if (!node || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(([entry]) => setWidth(Math.max(1, entry.contentRect.width)));
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  return [ref, width];
}

function Lane({
  label,
  className = "",
  rows = 1,
  action,
  children,
  onPick,
}: {
  label: ReactNode;
  className?: string;
  rows?: number;
  action?: ReactNode;
  children: ReactNode;
  onPick?: (event: MouseEvent<HTMLDivElement>) => void;
}) {
  return (
    <>
      <div className={`map-label ${className}`}>
        <span>{label}</span>
        {action}
      </div>
      <div
        className={`map-track ${className} ${onPick ? "pickable" : ""}`}
        style={{ "--rows": rows } as React.CSSProperties}
        onClick={onPick}
      >
        {children}
      </div>
    </>
  );
}

/**
 * The film's sound along its length: the picture, the song or the voice, and a lane per
 * kind of cue. A cue is drawn where it is heard; a click on a lane picks a moment.
 */
export function SoundMap({
  data,
  cues,
  music,
  selected,
  pick,
  silences,
  onSelect,
  onPick,
  onAdd,
}: {
  data: SoundPayload;
  cues: Cue[];
  music: Music | null;
  selected: string | null;
  pick: Pick | null;
  silences: { start: number; end: number }[];
  onSelect: (id: string) => void;
  onPick: (pick: Pick) => void;
  onAdd: (kind: CueKind) => void;
}) {
  const player = usePlayerControls();
  const time = usePlayerTime(0);
  const duration = data.duration || 1;
  const [trackRef, width] = useTrackWidth();
  const pct = (seconds: number) => `${(Math.max(0, Math.min(duration, seconds)) / duration) * 100}%`;
  const share = (seconds: number) => `${(Math.max(0, seconds) / duration) * 100}%`;
  const bars = useMemo(() => waveformBars(music, duration), [music, duration]);
  // A story film names its lines; a song film knows only where its placed lines are spoken.
  const voice = data.lines.length
    ? data.lines
    : (data.speech ?? []).map((span, index) => ({ id: `Line ${index + 1}`, ...span }));
  const pickAt = (event: MouseEvent<HTMLDivElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    const seconds = Math.round(Math.max(0, Math.min(1, (event.clientX - box.left) / box.width)) * duration * 10) / 10;
    player.seek(seconds);
    onPick({ kind: "time", seconds });
  };
  const pickSeconds = pick?.seconds ?? null;
  const marks = (
    <>
      {pickSeconds !== null && <span className="map-pick" style={{ left: pct(pickSeconds) }} aria-hidden="true" />}
      <span className="map-playhead" style={{ left: pct(time) }} aria-hidden="true" />
    </>
  );
  const laneOf = (kind: CueKind) => {
    const least = duration * 0.004;
    const items = cues
      .filter((cue) => cue.kind === kind)
      .map((cue) => {
        const heard = heardSpan(cue, duration);
        if (!heard || cue.start_seconds === null || cue.end_seconds === null) return null;
        // The stretch the cue names, and inside it the part where its sound is heard.
        const from = Math.min(heard.start, Math.max(0, cue.start_seconds));
        const to = Math.max(heard.end, Math.min(duration, cue.end_seconds), from + least);
        const label = ((labelPixels(cue.id) + 6) / width) * duration;
        // A band wide enough for a few letters keeps its name inside, cut short if need be.
        const inside = ((to - from) / duration) * width >= Math.min(labelPixels(cue.id), 44);
        // A name that would run off the end of the film sits before its band instead.
        const side = inside ? "inside" : to + label > duration ? "before" : "after";
        const span = side === "before" ? { start: from - label, end: to } : { start: from, end: side === "after" ? to + label : to };
        return { cue, heard, from, to, side, span };
      })
      .filter((item): item is NonNullable<typeof item> => item !== null);
    const rows = packRows(items.map((item) => ({ id: item.cue.id, ...item.span })));
    const count = Math.max(1, ...Object.values(rows).map((row) => row + 1));
    return { items, rows, count };
  };
  return (
    <div className="sound-map" aria-label="Where each sound plays">
      {data.shots.length > 0 && (
        <Lane label="Picture" className="lane-picture">
          {data.shots.map((shot) => (
            <button
              type="button"
              key={shot.id}
              className={`map-shot ${pick?.kind === "shot" && pick.id === shot.id ? "picked" : ""}`}
              style={{ left: pct(shot.start), width: share(shot.end - shot.start) }}
              title={`${shot.id}, ${clock(shot.start)}–${clock(shot.end)}: pick its cut`}
              aria-label={`The cut of ${shot.id} at ${clockTenths(shot.start)}`}
              onClick={(event) => {
                event.stopPropagation();
                player.seek(shot.start);
                onPick({ kind: "shot", id: shot.id, seconds: shot.start });
              }}
            >
              {shot.still ? <img src={shot.still} alt="" loading="lazy" /> : null}
            </button>
          ))}
          {marks}
        </Lane>
      )}
      {data.beats.length > 0 && (
        <Lane label="Beats" className="lane-beats" onPick={pickAt}>
          {data.beats.map((beat) => (
            <span
              key={beat.id}
              className="map-beat"
              style={{ left: pct(beat.start), width: share(beat.end - beat.start) }}
              title={`${beat.id}, ${clock(beat.start)}–${clock(beat.end)}`}
            >
              {beat.id}
            </span>
          ))}
          {marks}
        </Lane>
      )}
      {bars.length > 0 && (
        <Lane label="Song" className="lane-song" onPick={pickAt}>
          <Waveform bars={bars} sections={music?.sections ?? []} duration={duration} />
          {silences.map((gap) => (
            <span key={gap.start} className="map-silence" style={{ left: pct(gap.start), width: share(gap.end - gap.start) }} title="Nothing to hear" />
          ))}
          {marks}
        </Lane>
      )}
      {voice.length > 0 && (
        <Lane label="Voice" className="lane-voice" onPick={pickAt}>
          {voice.map((line) => (
            <span
              key={`${line.id}-${line.start}`}
              className="map-line"
              style={{ left: pct(line.start), width: share(line.end - line.start) }}
              title={`${line.id}, ${clockTenths(line.start)}–${clockTenths(line.end)}`}
            />
          ))}
          {bars.length === 0 &&
            silences.map((gap) => (
              <span key={gap.start} className="map-silence" style={{ left: pct(gap.start), width: share(gap.end - gap.start) }} title="Nothing to hear" />
            ))}
          {marks}
        </Lane>
      )}
      {LANES.map((lane, laneIndex) => {
        const { items, rows, count } = laneOf(lane.kind);
        return (
          <Lane
            key={lane.kind}
            label={lane.label}
            className={`lane-cues ${lane.kind}`}
            rows={count}
            onPick={pickAt}
            action={
              <button type="button" className="map-add" aria-label={lane.add} title={lane.add} onClick={() => onAdd(lane.kind)}>
                <PlusIcon size={14} />
              </button>
            }
          >
            <div className="map-measure" ref={laneIndex === 0 ? trackRef : undefined} aria-hidden="true" />
            {items.length === 0 && (
              <span className="map-empty">
                {lane.kind === "music" && !data.story_film ? "The song is the music" : `No ${KIND_LABEL[lane.kind].toLowerCase()} yet`}
              </span>
            )}
            {items.map(({ cue, heard, from, to, side }) => {
              const silent = !chosen(cue);
              const span = to - from;
              const within = (seconds: number) => `${((seconds - from) / span) * 100}%`;
              return (
                <button
                  type="button"
                  key={cue.id}
                  className={`cue-band ${cue.kind} ${silent ? "silent" : ""} ${selected === cue.id ? "selected" : ""} name-${side}`}
                  style={{ left: pct(from), width: share(span), top: `calc(${rows[cue.id] ?? 0} * var(--row))` }}
                  title={`${cue.id}${cue.prompt ? `: ${cue.prompt}` : ""}`}
                  aria-pressed={selected === cue.id}
                  aria-label={`${cue.id}, ${KIND_LABEL[cue.kind].toLowerCase()} from ${clockTenths(heard.start)}${silent ? ", no sound yet" : ""}`}
                  onClick={(event) => {
                    event.stopPropagation();
                    onSelect(cue.id);
                  }}
                >
                  {!silent && (
                    <span className="band-heard" style={{ left: within(heard.start), width: `max(3px, ${((heard.end - heard.start) / span) * 100}%)` }} />
                  )}
                  {(cue.places_seconds ?? []).map((seconds, index) => (
                    <span key={`${cue.id}-${index}`} className="cue-place" style={{ left: within(seconds) }} />
                  ))}
                  <span className="band-name">{cue.id}</span>
                </button>
              );
            })}
            {marks}
          </Lane>
        );
      })}
      <div className="map-label lane-ruler" aria-hidden="true">
        <span className="map-clock">{clockTenths(time)}</span>
      </div>
      <div className="map-track lane-ruler" aria-hidden="true">
        {rulerTicks(duration).map((at) => (
          <span key={at} className="map-tick" style={{ left: pct(at) }}>
            {clock(at)}
          </span>
        ))}
      </div>
    </div>
  );
}
