import { useEffect, useRef, useState } from "react";
import { api, type Music } from "../api";
import { usePlayerControls, usePlayerTime } from "../spine/player";
import { clock, sectionColor } from "../spine/wave";
import { PlayIcon } from "../ui/icons";
import type { SectionEdit } from "./sectionEdit";
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

export function SectionsPart({ slug, model }: { slug: string; model: TrackModel }) {
  const {
    data,
    names,
    setNames,
    namesSaved,
    analyzing,
    analyze,
    saveNames,
    canUndoSections,
    undoSections,
    resetSections,
    addSectionEdge,
    joinSection,
    changeSections,
  } = model;
  const music = data?.music;
  const sections: Section[] = music?.sections || [];
  const player = usePlayerControls();
  const time = usePlayerTime(0.1);
  const { clock: playerClock, pause, seek, play } = player;
  const stopAt = useRef<{ start: number; end: number } | null>(null);
  const [edgeRefused, setEdgeRefused] = useState(false);
  const [focused, setFocused] = useState(-1);
  const [proposal, setProposal] = useState<SectionEdit[] | null>(null);
  const [proposing, setProposing] = useState(false);
  const tags = [
    ...new Set(
      (data?.lyrics?.lines || []).flatMap((line) => {
        const match = line.trim().match(/^\[([^[\]]+)\]$/);
        return match ? [match[1].trim()] : [];
      }),
    ),
  ];

  const propose = async () => {
    setProposing(true);
    try {
      const result = await api.proposeSections(slug);
      setProposal(result.sections);
    } catch {
      // request() already surfaced the error.
    } finally {
      setProposing(false);
    }
  };

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
        {edgeRefused && <span className="track-refused">Too close to an edge</span>}
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
              onFocus={() => setFocused(index)}
              onBlur={() => {
                setFocused(-1);
                void saveNames();
              }}
            />
            <span className="t">{clock(Number(section.start))}</span>
            <Shape values={loudnessShape(music, Number(section.start), Number(section.end))} />
            <button
              type="button"
              className="track-join"
              aria-label={`Join ${names[index] ?? defaultName(index)} with the next section`}
              title="Join with the next section"
              disabled={index === sections.length - 1}
              onClick={() => joinSection(index)}
            >
              ⌄
            </button>
            {focused === index && tags.length > 0 && (
              <div className="track-offers">
                {tags.map((tag) => (
                  <button
                    type="button"
                    key={tag}
                    className="track-chip"
                    // Keep the field focused until the name is taken.
                    onPointerDown={(event) => event.preventDefault()}
                    onClick={() => {
                      const next = [...names];
                      next[index] = tag;
                      setNames(next);
                      void saveNames(next);
                    }}
                  >
                    {tag}
                  </button>
                ))}
              </div>
            )}
          </div>
        ))}
      {proposal && (
        <div className="track-proposal" role="group" aria-label="Sections from your lyric tags">
          <h3>From your lyric tags</h3>
          <ul>
            {proposal.map((item) => (
              <li key={item.start}>
                <span>{clock(item.start)}</span> {item.name}
              </li>
            ))}
          </ul>
          <div className="row-actions">
            <button
              type="button"
              className="ui-btn ui-btn--primary ui-btn--small"
              onClick={() => {
                void changeSections(proposal);
                setProposal(null);
              }}
            >
              Use these sections
            </button>
            <button
              type="button"
              className="ui-btn ui-btn--small ui-btn--quiet"
              onClick={() => setProposal(null)}
            >
              Not now
            </button>
          </div>
        </div>
      )}
      {!!sections.length && (
        <div className="row-actions track-edge-actions">
          {tags.length > 0 && (
            <button
              type="button"
              className={`ui-btn ui-btn--small ${data?.section_map ? "" : "ui-btn--primary"}`}
              onClick={() => void propose()}
              disabled={proposing}
            >
              {proposing ? "Reading the structure…" : "Use the lyric structure"}
            </button>
          )}
          <button
            type="button"
            className="ui-btn ui-btn--small"
            onClick={() => {
              const added = addSectionEdge(player.current());
              setEdgeRefused(!added);
            }}
          >
            Add an edge at the playhead
          </button>
          {canUndoSections && (
            <button type="button" className="ui-btn ui-btn--small" onClick={() => void undoSections()}>
              Undo
            </button>
          )}
          {data?.section_map && (
            <button type="button" className="ui-btn ui-btn--small" onClick={() => void resetSections()}>
              Reset to detected sections
            </button>
          )}
        </div>
      )}
      {!!sections.length && (
        <p className="hint">
          Drag a line on the song below to move an edge. Your changes never alter the song or the
          measurement.
        </p>
      )}
    </section>
  );
}
