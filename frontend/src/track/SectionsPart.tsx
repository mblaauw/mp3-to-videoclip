import { useEffect, useRef } from "react";
import type { Music } from "../api";
import { usePlayerControls, usePlayerTime } from "../spine/player";
import { clock, sectionColor } from "../spine/wave";
import { PlayIcon } from "../ui/icons";
import { defaultName, type TrackModel } from "./useTrackData";

type Section = NonNullable<Music["sections"]>[number];

const BARS = 24;

/** Each section's loudness, measured against the whole song rather than named. */
export function loudnessShape(music: Music, start: number, end: number): number[] {
  const windows = music.fine_windows ?? [];
  const levels = windows.map((window) => Number(window.level_db ?? -60));
  if (!levels.length) return [];
  const floor = Math.min(...levels);
  const span = Math.max(...levels) - floor || 1;
  const inside = windows
    .filter((window) => Number(window.time) >= start && Number(window.time) < end)
    .map((window) => Number(window.level_db ?? -60));
  if (!inside.length) return [];
  const shape: number[] = [];
  for (let bar = 0; bar < BARS; bar += 1) {
    const slice = inside.slice(
      Math.floor((bar / BARS) * inside.length),
      Math.max(Math.floor((bar / BARS) * inside.length) + 1, Math.ceil(((bar + 1) / BARS) * inside.length)),
    );
    const mean = slice.reduce((sum, level) => sum + level, 0) / slice.length;
    // Squared so a mastered song, nearly level in dB, still shows its shape.
    shape.push(((mean - floor) / span) ** 2);
  }
  return shape;
}

function Shape({ values }: { values: number[] }) {
  if (!values.length) return <span className="track-shape" />;
  return (
    <svg
      className="track-shape"
      viewBox={`0 0 ${BARS * 3} 22`}
      role="img"
      aria-label="Loudness of this section, against the whole song"
      fill="currentColor"
    >
      {values.map((value, index) => {
        const height = Math.max(1, value * 22);
        return <rect key={index} x={index * 3} y={22 - height} width={2.2} height={height} />;
      })}
    </svg>
  );
}

export function SectionsPart({ model }: { model: TrackModel }) {
  const { data, names, setNames, namesSaved, analyzing, analyze, saveNames } = model;
  const music = data?.music;
  const sections: Section[] = music?.sections || [];
  const player = usePlayerControls();
  const time = usePlayerTime(0.1);
  const { clock: playerClock, pause, seek, play } = player;
  const stopAt = useRef<{ start: number; end: number } | null>(null);

  // A section played on its own stops at its end; moving elsewhere cancels that.
  useEffect(
    () =>
      playerClock.subscribe(() => {
        const range = stopAt.current;
        if (!range) return;
        const now = playerClock.get();
        if (now < range.start - 0.25 || now > range.end + 0.5) stopAt.current = null;
        else if (now >= range.end) {
          stopAt.current = null;
          pause();
        }
      }),
    [playerClock, pause],
  );

  const playSection = (section: Section) => {
    stopAt.current = { start: Number(section.start), end: Number(section.end) };
    seek(Number(section.start));
    play();
  };

  return (
    <section className="track-sections" aria-label="Sections">
      <div className="track-head">
        <h2>Sections</h2>
        <small>Name them the way you talk about the song</small>
        {namesSaved && <span className="saved-note">Saved</span>}
      </div>
      {!sections.length && (
        <div className="empty-block">
          <p>No measured sections yet.</p>
          <button type="button" className="ui-btn ui-btn--primary" onClick={analyze} disabled={analyzing}>
            {analyzing ? "Measuring…" : "Measure the song"}
          </button>
        </div>
      )}
      {music &&
        sections.map((section, index) => (
          <div
            className={`track-sec ${
              time >= Number(section.start) && time < Number(section.end) ? "now" : ""
            }`}
            key={`${section.start}-${index}`}
            style={{ borderLeftColor: sectionColor(index) }}
          >
            <button
              type="button"
              className="track-play"
              aria-label={`Play ${names[index] ?? defaultName(index)}`}
              onClick={() => playSection(section)}
            >
              <PlayIcon size={11} />
            </button>
            <input
              value={names[index] ?? defaultName(index)}
              aria-label={`Name for section ${index + 1}`}
              maxLength={80}
              onChange={(event) =>
                setNames((current) => {
                  const next = [...current];
                  next[index] = event.target.value;
                  return next;
                })
              }
              onBlur={() => void saveNames()}
            />
            <span className="t">{clock(Number(section.start))}</span>
            <Shape values={loudnessShape(music, Number(section.start), Number(section.end))} />
          </div>
        ))}
    </section>
  );
}
