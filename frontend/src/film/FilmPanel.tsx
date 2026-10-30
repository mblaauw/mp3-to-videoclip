import { useEffect, useState } from "react";
import type { EditPayload } from "../api";
import { ArtifactRating } from "../ArtifactRating";
import type { EditMotion, EditTransition } from "../baseFilm";
import { JobBanner } from "../jobs/JobBanner";
import type { Stage } from "../shell/nextStep";
import { clock } from "../spine/wave";
import { ShotThumb } from "../storyboard/ShotThumb";
import { CreditsCard } from "../story/CreditsCard";
import { Button } from "../ui";
import type { CutNote } from "./cutNotes";
import { DeliveryCard } from "./DeliveryCard";
import {
  joinMaxFrames,
  setEditMotion,
  setEditTransition,
  setJoins,
  SET_BY_HAND,
  TRANSITION_TYPES,
} from "./editTimeline";
import { SeedCut } from "./SeedCut";
import type { FilmSelection } from "./selection";
import type { FilmData } from "./useFilmData";

const MOTIONS: { value: EditMotion["type"]; label: string }[] = [
  { value: "hold", label: "Hold" },
  { value: "push_in", label: "Push in" },
  { value: "pull_back", label: "Pull back" },
  { value: "pan_left", label: "Pan left" },
  { value: "pan_right", label: "Pan right" },
];

const typeLabel = (type: string) =>
  TRANSITION_TYPES.find((item) => item.value === type)?.label ?? type;

export type PanelEdit = (next: EditPayload, label: string) => Promise<boolean>;

/** One panel; what it shows follows the selection. */
export function FilmPanel({
  film,
  edit,
  notes,
  selection,
  onSelect,
  onChange,
  onWatchJoin,
  onSeekNote,
  onNavigate,
}: {
  film: FilmData;
  edit: EditPayload | null;
  notes: CutNote[];
  selection: FilmSelection;
  onSelect: (selection: FilmSelection) => void;
  onChange: PanelEdit;
  onWatchJoin: (id: string) => void;
  onSeekNote: (note: CutNote) => void;
  onNavigate: (stage: Stage) => void;
}) {
  const note = selection?.kind === "note" ? notes[selection.index] : null;
  return (
    <div className="film-panel">
      <JobBanner slug={film.slug} kinds={["render"]} className="in-card" />
      {selection?.kind === "join" && edit ? (
        <JoinPanel
          key={selection.ids.join()}
          film={film}
          edit={edit}
          ids={selection.ids}
          onChange={onChange}
          onWatch={onWatchJoin}
          onDone={() => onSelect(null)}
        />
      ) : selection?.kind === "shot" ? (
        <ShotPanel
          film={film}
          edit={edit}
          id={selection.id}
          onChange={onChange}
          onDone={() => onSelect(null)}
        />
      ) : note ? (
        <>
          <header className="panel-head">
            <h2>{note.title}</h2>
          </header>
          {note.why && <p>{note.why}</p>}
          <div className="row-actions">
            {note.shotId && (
              <Button
                size="small"
                variant="quiet"
                onClick={() => onSelect({ kind: "shot", id: note.shotId as string })}
              >
                Open the shot
              </Button>
            )}
            <Button size="small" variant="quiet" onClick={() => onSelect(null)}>
              All notes
            </Button>
          </div>
        </>
      ) : (
        <Overview
          film={film}
          notes={notes}
          onSelect={onSelect}
          onSeekNote={onSeekNote}
          onNavigate={onNavigate}
        />
      )}
    </div>
  );
}

function Overview({
  film,
  notes,
  onSelect,
  onSeekNote,
  onNavigate,
}: {
  film: FilmData;
  notes: CutNote[];
  onSelect: (selection: FilmSelection) => void;
  onSeekNote: (note: CutNote) => void;
  onNavigate: (stage: Stage) => void;
}) {
  const { cut, board, rendererReady, slug } = film;
  return (
    <>
      <header className="panel-head">
        <h2>The cut</h2>
        <p className="hint">Select a join or a shot on the timeline and this panel follows it.</p>
      </header>
      {!cut?.present ? (
        <SeedCut film={film} board={board} onNavigate={onNavigate} />
      ) : (
        <>
          <p className="panel-stats">
            <span><b>{cut.counts.shots ?? 0}</b> shots</span>
            <span><b>{cut.counts.cuts ?? 0}</b> cuts</span>
            <span><b>{cut.counts.holds ?? 0}</b> held</span>
            <span><b>{cut.counts.accents ?? 0}</b> accents</span>
            {cut.grade && <span>Grade: <b>{cut.grade}</b></span>}
          </p>
          {cut.hard.length > 0 && (
            <div className="cut-findings hard">
              <b>{cut.hard.length} to fix before delivery</b>
              {cut.hard.map((finding) => (
                <span key={`${finding.code}-${finding.shot_id || ""}-${finding.message}`}>
                  {finding.message}
                </span>
              ))}
            </div>
          )}
          {cut.notes && <p className="cut-notes">{cut.notes}</p>}
          <ArtifactRating slug={slug} artifact="edit" />
          {notes.length > 0 && (
            <details className="panel-notes" open={notes.length <= 6}>
              <summary>
                {notes.length} {notes.length === 1 ? "note" : "notes"} on this cut
              </summary>
              <ul>
                {notes.map((note) => (
                  <li key={note.index}>
                    <button
                      type="button"
                      onClick={() => {
                        onSelect({ kind: "note", index: note.index });
                        onSeekNote(note);
                      }}
                    >
                      {note.title}
                    </button>
                  </li>
                ))}
              </ul>
            </details>
          )}
        </>
      )}
      {rendererReady !== false && <DeliveryCard film={film} onNavigate={onNavigate} />}
      <CreditsCard slug={slug} />
    </>
  );
}

function JoinPanel({
  film,
  edit,
  ids,
  onChange,
  onWatch,
  onDone,
}: {
  film: FilmData;
  edit: EditPayload;
  ids: string[];
  onChange: PanelEdit;
  onWatch: (id: string) => void;
  onDone: () => void;
}) {
  const { slug, boardById, imageById, board } = film;
  const fps = board?.fps || 24;
  const shots = ids
    .map((id) => edit.shots.find((shot) => shot.shot_id === id))
    .filter((shot): shot is NonNullable<typeof shot> => !!shot);
  const first = shots[0];
  const types = new Set(shots.map((shot) => shot.transition_in.type));
  const type = types.size === 1 ? first?.transition_in.type : null;
  const maxFrames = joinMaxFrames(edit, ids);
  const savedFrames = first?.transition_in.frames ?? 0;
  const [frames, setFrames] = useState(savedFrames);
  const savedNote = first?.transition_in.reason ?? "";
  const shownNote = savedNote === SET_BY_HAND ? "" : savedNote;
  const [note, setNote] = useState(shownNote);
  useEffect(() => setFrames(savedFrames), [savedFrames]);
  useEffect(() => setNote(shownNote), [shownNote]);
  if (!first) return null;

  const index = edit.shots.indexOf(first);
  const previous = edit.shots[index - 1];
  const count = shots.length;
  const name = count > 1 ? `${count} joins` : `Join into ${first.shot_id}`;

  const pick = async (next: EditTransition["type"]) => {
    const length = next === "cut" ? 0 : Math.min(maxFrames, frames > 0 ? frames : 12);
    const saved = await onChange(setJoins(edit, ids, next, length), `${name} set to ${typeLabel(next)}`);
    if (saved && next !== "cut" && count === 1) onWatch(first.shot_id);
  };
  const commitFrames = async () => {
    if (!type || frames === savedFrames) return;
    const saved = await onChange(
      setJoins(edit, ids, type, frames),
      `${name} set to ${frames} frames`,
    );
    if (saved && count === 1) onWatch(first.shot_id);
  };
  const commitNote = () => {
    const value = note.trim();
    if (value === shownNote) return;
    void onChange(
      setEditTransition(edit, first.shot_id, { reason: value || SET_BY_HAND }),
      `Note added to ${name.toLowerCase()}`,
    );
  };

  return (
    <>
      <header className="panel-head">
        <h2>{name}</h2>
        <p className="hint">
          {count > 1
            ? "Changes apply to all of them."
            : `At ${clock(first.start_frame / fps)}`}
        </p>
      </header>
      {count === 1 && previous && (
        <div className="join-pair">
          {[previous, first].map((shot, position) => {
            const source = boardById.get(shot.shot_id);
            return (
              <div key={shot.shot_id}>
                {source && (
                  <ShotThumb slug={slug} shot={source} image={imageById.get(source.id)} />
                )}
                <small>
                  {shot.shot_id}, {(shot.duration_frames / fps).toFixed(1)} s
                </small>
                {position === 0 && <i aria-hidden="true">◆</i>}
              </div>
            );
          })}
        </div>
      )}
      <div className="panel-options" role="group" aria-label="Transition">
        {TRANSITION_TYPES.map((option) => (
          <button
            type="button"
            key={option.value}
            aria-pressed={option.value === type}
            disabled={option.value !== "cut" && maxFrames < 1}
            onClick={() => void pick(option.value)}
          >
            {option.label}
          </button>
        ))}
      </div>
      {maxFrames < 1 && <p className="hint">These shots are too short for a transition.</p>}
      {type && type !== "cut" && maxFrames >= 1 && (
        <label className="panel-field">
          <span>
            Length <em>{frames} frames, {(frames / fps).toFixed(2)} s</em>
          </span>
          <input
            type="range"
            min={1}
            max={maxFrames}
            value={Math.min(frames, maxFrames)}
            onChange={(event) => setFrames(Number(event.target.value))}
            onPointerUp={() => void commitFrames()}
            onKeyUp={() => void commitFrames()}
          />
        </label>
      )}
      {count === 1 && type && type !== "cut" && (
        <label className="panel-field">
          <span>Note (optional)</span>
          <input
            type="text"
            value={note}
            maxLength={240}
            placeholder="Why this join?"
            onChange={(event) => setNote(event.target.value)}
            onBlur={commitNote}
            onKeyDown={(event) => {
              if (event.key === "Enter") event.currentTarget.blur();
            }}
          />
        </label>
      )}
      <div className="row-actions">
        {count === 1 && (
          <Button size="small" variant="quiet" onClick={() => onWatch(first.shot_id)}>
            Watch this join
          </Button>
        )}
        <Button size="small" variant="quiet" onClick={onDone}>
          Done
        </Button>
      </div>
      <p className="hint">Changes save as you make them.</p>
    </>
  );
}

function ShotPanel({
  film,
  edit,
  id,
  onChange,
  onDone,
}: {
  film: FilmData;
  edit: EditPayload | null;
  id: string;
  onChange: PanelEdit;
  onDone: () => void;
}) {
  const { slug, boardById, imageById, board, cut } = film;
  const fps = board?.fps || 24;
  const source = boardById.get(id);
  const decision = edit?.shots.find((shot) => shot.shot_id === id);
  const summary = cut?.shots.find((shot) => shot.shot_id === id);
  const start = decision?.start_frame ?? source?.start_frame ?? 0;
  const frames = decision?.duration_frames ?? source?.duration_frames ?? 0;
  return (
    <>
      {source && <ShotThumb slug={slug} shot={source} image={imageById.get(id)} />}
      <header className="panel-head">
        <h2>{id}</h2>
        <p className="hint">
          {clock(start / fps)}, {(frames / fps).toFixed(1)} s
          {summary?.section_name ? `, in ${summary.section_name}` : ""}
        </p>
      </header>
      <p>{source?.message || source?.purpose}</p>
      {edit && decision ? (
        <div>
          <h3 className="panel-sub">Camera move</h3>
          <div className="panel-options" role="group" aria-label="Camera move">
            {MOTIONS.map((option) => (
              <button
                type="button"
                key={option.value}
                aria-pressed={decision.motion.type === option.value}
                onClick={() =>
                  void onChange(
                    setEditMotion(edit, id, option.value),
                    `${id} camera set to ${option.label}`,
                  )
                }
              >
                {option.label}
              </button>
            ))}
          </div>
        </div>
      ) : (
        <p className="hint">Make a first cut to change the camera move here.</p>
      )}
      <div className="row-actions">
        <Button size="small" variant="quiet" onClick={onDone}>
          Done
        </Button>
      </div>
    </>
  );
}
