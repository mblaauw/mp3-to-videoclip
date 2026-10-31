import { useEffect, useState } from "react";
import { api, type CutSummary, type EditPayload, type EditSuggestion } from "../api";
import { ArtifactRating } from "../ArtifactRating";
import type { EditMotion, EditTransition, Grade } from "../baseFilm";
import { JobBanner } from "../jobs/JobBanner";
import type { Stage } from "../shell/nextStep";
import { usePlayerControls } from "../spine/player";
import { clock } from "../spine/wave";
import { ShotThumb } from "../storyboard/ShotThumb";
import { Button } from "../ui";
import type { CutNote } from "./cutNotes";
import { DeliveryPanel } from "./DeliveryPanel";
import {
  addCrop,
  joinMaxFrames,
  removeCrop,
  setEditMotion,
  setEditTransition,
  setGradePreset,
  setJoins,
  setLookAmount,
  SET_BY_HAND,
  updateCrop,
  type LookAmount,
  TRANSITION_TYPES,
} from "./editTimeline";
import { SeedCut } from "./SeedCut";
import { releaseMouseFocus, type FilmSelection } from "./selection";
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
      ) : selection?.kind === "delivery" ? (
        <DeliveryPanel film={film} onNavigate={onNavigate} onBack={() => onSelect(null)} />
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
          edit={edit}
          onChange={onChange}
          notes={notes}
          onSelect={onSelect}
          onSeekNote={onSeekNote}
          onNavigate={onNavigate}
        />
      )}
    </div>
  );
}

/** A cut worked out from the song's measurements, shown before anything changes. */
function SuggestCut({
  slug,
  onChange,
}: {
  slug: string;
  onChange: PanelEdit;
}) {
  const [busy, setBusy] = useState(false);
  const [suggestion, setSuggestion] = useState<EditSuggestion | null>(null);
  if (!suggestion) {
    return (
      <div className="row-actions">
        <Button
          size="small"
          disabled={busy}
          onClick={() => {
            setBusy(true);
            api
              .suggestEdit(slug)
              .then(setSuggestion, () => undefined)
              .finally(() => setBusy(false));
          }}
        >
          {busy ? "Working it out…" : "Suggest a cut"}
        </Button>
      </div>
    );
  }
  const { changes } = suggestion;
  return (
    <div className="cut-suggestion" role="group" aria-label="Suggested cut">
      <b>A cut from the song's sections and sung lines</b>
      <ul>
        <li>
          {changes.joins_moved} joins move, by up to {changes.largest_move_seconds} s
        </li>
        <li>{changes.moves_changed} camera moves change, {changes.holds} shots hold</li>
        <li>
          {changes.accents} accents, {changes.dissolves} dissolves
        </li>
        <li>{changes.sections} sections get a written feel</li>
      </ul>
      <p className="hint">The stills, their order and any text stay as they are.</p>
      <div className="row-actions">
        <Button
          size="small"
          variant="primary"
          onClick={() => {
            onChange(suggestion.edit, "the suggested cut");
            setSuggestion(null);
          }}
        >
          Use this cut
        </Button>
        <Button size="small" variant="quiet" onClick={() => setSuggestion(null)}>
          Not now
        </Button>
      </div>
    </div>
  );
}

function AgainstSeed({ changes }: { changes: NonNullable<CutSummary["against_seed"]> }) {
  const parts = [
    changes.joins_moved ? `${changes.joins_moved} joins moved` : "",
    changes.moves_changed ? `${changes.moves_changed} camera moves changed` : "",
    changes.crops ? `${changes.crops} crop cuts` : "",
    changes.accents ? `${changes.accents} accents` : "",
    changes.named_joins ? `${changes.named_joins} styled joins` : "",
  ].filter(Boolean);
  return (
    <p className="hint cut-against-seed">
      {parts.length ? `Compared with the starting cut: ${parts.join(", ")}.` : "This is still the starting cut."}
    </p>
  );
}

const PRESETS: { value: Grade["preset"]; label: string }[] = [
  { value: "neutral", label: "Neutral" },
  { value: "warm-night", label: "Warm night" },
  { value: "clean-day", label: "Clean day" },
  { value: "film-fade", label: "Film fade" },
  { value: "vivid", label: "Vivid" },
  { value: "monochrome", label: "Mono" },
];

const LOOK_AMOUNTS: { key: LookAmount; label: string }[] = [
  { key: "grain", label: "Grain" },
  { key: "weave", label: "Gate weave" },
  { key: "drift", label: "Handheld drift" },
];

function LookAmountField({
  edit,
  amount,
  onChange,
}: {
  edit: EditPayload;
  amount: { key: LookAmount; label: string };
  onChange: PanelEdit;
}) {
  const saved = edit.grade.look?.[amount.key] ?? 0;
  const [value, setValue] = useState(saved);
  useEffect(() => setValue(saved), [saved]);
  // Saved on release, so dragging doesn't write one cut per pixel.
  const commit = () => {
    if (value !== saved) void onChange(setLookAmount(edit, amount.key, value), amount.label.toLowerCase());
  };
  return (
    <label className="panel-field">
      <span>{amount.label}</span>
      <input
        type="range"
        min={0}
        max={1}
        step={0.05}
        value={value}
        aria-valuetext={value ? `${Math.round(value * 100)}%` : "Off"}
        onChange={(event) => setValue(Number(event.target.value))}
        onPointerUp={commit}
        onKeyUp={commit}
      />
    </label>
  );
}

function LookControls({ edit, onChange }: { edit: EditPayload; onChange: PanelEdit }) {
  return (
    <details className="panel-notes film-look">
      <summary>Colour and film look</summary>
      <div className="panel-options" role="group" aria-label="Grade">
        {PRESETS.map((preset) => (
          <button
            type="button"
            key={preset.value}
            aria-pressed={edit.grade.preset === preset.value}
            onClick={() => void onChange(setGradePreset(edit, preset.value), `the ${preset.label} grade`)}
          >
            {preset.label}
          </button>
        ))}
      </div>
      {LOOK_AMOUNTS.map((amount) => (
        <LookAmountField key={amount.key} edit={edit} amount={amount} onChange={onChange} />
      ))}
      <p className="hint">Text and titles stay crisp above the look.</p>
    </details>
  );
}

const CROP_ZOOMS = [1.15, 1.3, 1.45, 1.6];
const CROP_SPOTS: { label: string; x: number; y: number }[] = [
  { label: "Top left", x: 0.15, y: 0.15 },
  { label: "Top", x: 0.5, y: 0.15 },
  { label: "Top right", x: 0.85, y: 0.15 },
  { label: "Left", x: 0.15, y: 0.5 },
  { label: "Centre", x: 0.5, y: 0.5 },
  { label: "Right", x: 0.85, y: 0.5 },
  { label: "Bottom left", x: 0.15, y: 0.85 },
  { label: "Bottom", x: 0.5, y: 0.85 },
  { label: "Bottom right", x: 0.85, y: 0.85 },
];

function CropCuts({
  edit,
  id,
  fps,
  onChange,
}: {
  edit: EditPayload;
  id: string;
  fps: number;
  onChange: PanelEdit;
}) {
  const player = usePlayerControls();
  const [refused, setRefused] = useState(false);
  const crops = edit.shots.find((shot) => shot.shot_id === id)?.crops ?? [];
  return (
    <div className="film-crops">
      <b>Crop cuts</b>
      {crops.map((crop) => {
        const spot =
          CROP_SPOTS.find((item) => item.x === (crop.x ?? 0.5) && item.y === (crop.y ?? 0.5)) ?? null;
        return (
          <div className="film-crop" key={crop.frame}>
            <button
              type="button"
              className="film-crop-time"
              onClick={() => player.seek(crop.frame / fps)}
            >
              {clock(crop.frame / fps)}
            </button>
            <select
              aria-label="How far to crop in"
              value={crop.zoom}
              onChange={(event) =>
                void onChange(updateCrop(edit, id, crop.frame, { zoom: Number(event.target.value) }), "the crop")
              }
            >
              {[...new Set([...CROP_ZOOMS, crop.zoom])].map((zoom) => (
                <option key={zoom} value={zoom}>
                  {zoom.toFixed(2)}×
                </option>
              ))}
            </select>
            <select
              aria-label="Which part of the frame to keep"
              value={spot?.label ?? ""}
              onChange={(event) => {
                const chosen = CROP_SPOTS.find((item) => item.label === event.target.value);
                if (chosen) void onChange(updateCrop(edit, id, crop.frame, { x: chosen.x, y: chosen.y }), "the crop");
              }}
            >
              {!spot && <option value="">Custom</option>}
              {CROP_SPOTS.map((item) => (
                <option key={item.label}>{item.label}</option>
              ))}
            </select>
            <Button
              size="small"
              variant="quiet"
              aria-label={`Remove the crop cut at ${clock(crop.frame / fps)}`}
              onClick={() => void onChange(removeCrop(edit, id, crop.frame), "the crop cut")}
            >
              Remove
            </Button>
          </div>
        );
      })}
      <Button
        size="small"
        onClick={() => {
          const next = addCrop(edit, id, player.current() * fps);
          setRefused(!next);
          if (next) void onChange(next, "the crop cut");
        }}
      >
        Add a crop cut at the playhead
      </Button>
      {refused && <p className="hint">Move the playhead inside this shot first.</p>}
    </div>
  );
}

function Overview({
  film,
  edit,
  onChange,
  notes,
  onSelect,
  onSeekNote,
  onNavigate,
}: {
  film: FilmData;
  edit: EditPayload | null;
  onChange: PanelEdit;
  notes: CutNote[];
  onSelect: (selection: FilmSelection) => void;
  onSeekNote: (note: CutNote) => void;
  onNavigate: (stage: Stage) => void;
}) {
  const { cut, board, rendererReady, slug, workflow } = film;
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
          {cut.against_seed && <AgainstSeed changes={cut.against_seed} />}
          <SuggestCut slug={slug} onChange={onChange} />
          {edit && <LookControls edit={edit} onChange={onChange} />}
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
      {rendererReady !== false && (
        <div className="panel-delivery">
          <b>{workflow.title}</b>
          <p className="hint">{film.finalHint}</p>
          <Button size="small" variant="quiet" onClick={() => onSelect({ kind: "delivery" })}>
            Open delivery and credits
          </Button>
        </div>
      )}
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
            onClick={(event) => {
              releaseMouseFocus(event);
              void pick(option.value);
            }}
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
                onClick={(event) => {
                  releaseMouseFocus(event);
                  void onChange(
                    setEditMotion(edit, id, option.value),
                    `${id} camera set to ${option.label}`,
                  );
                }}
              >
                {option.label}
              </button>
            ))}
          </div>
          <CropCuts edit={edit} id={id} fps={fps} onChange={onChange} />
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
