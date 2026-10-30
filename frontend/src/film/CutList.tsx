import { useEffect, useRef, useState } from "react";
import type { CutShot, EditPayload } from "../api";
import { ArtifactRating } from "../ArtifactRating";
import type { EditTransition } from "../baseFilm";
import type { Stage } from "../shell/nextStep";
import { ShotThumb } from "../storyboard/ShotThumb";
import { Button } from "../ui";
import { TRANSITION_TYPES } from "./editTimeline";
import type { FilmData } from "./useFilmData";

function clock(seconds: number): string {
  const value = Math.max(0, Math.floor(seconds));
  return `${Math.floor(value / 60)}:${String(value % 60).padStart(2, "0")}`;
}

function duration(seconds: number): string {
  return `${seconds.toFixed(1)} s`;
}

function TransitionEditor({
  shot,
  base,
  busy,
  onSave,
}: {
  shot: CutShot;
  base: EditPayload;
  busy: boolean;
  onSave: (change: Partial<EditTransition>, base: EditPayload) => Promise<boolean>;
}) {
  const [type, setType] = useState<EditTransition["type"]>(
    (shot.transition.type as EditTransition["type"]) || "cut",
  );
  const [frames, setFrames] = useState(shot.transition.frames);
  const [reason, setReason] = useState(shot.transition.reason || "");
  const [saving, setSaving] = useState(false);
  const draftBase = useRef(base);
  const dirty = useRef(false);
  useEffect(() => {
    if (dirty.current || saving) return;
    draftBase.current = base;
    setType((shot.transition.type as EditTransition["type"]) || "cut");
    setFrames(shot.transition.frames);
    setReason(shot.transition.reason || "");
  }, [base, shot, saving]);
  const named = type !== "cut";
  const canSave =
    named && reason.trim().length > 0 && !saving && !busy && frames >= 0 && frames <= 48;

  const save = async () => {
    if (!canSave) return;
    setSaving(true);
    try {
      if (await onSave({ type, frames, reason: reason.trim() }, draftBase.current)) dirty.current = false;
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="cut-transition-edit">
      <label>
        <span>Into {shot.shot_id}</span>
        <select
          aria-label={`Transition into ${shot.shot_id}`}
          value={type}
          disabled={saving}
          onChange={(event) => {
            dirty.current = true;
            const next = event.target.value as EditTransition["type"];
            setType(next);
            if (next !== "cut" && frames === 0) setFrames(6);
          }}
        >
          {TRANSITION_TYPES.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
      <label>
        <span>Frames</span>
        <input
          aria-label={`Transition frames into ${shot.shot_id}`}
          type="number"
          min={0}
          max={48}
          value={frames}
          disabled={!named || saving}
          onChange={(event) => { dirty.current = true; setFrames(Number(event.target.value)); }}
        />
      </label>
      {named && (
        <label className="reason">
          <span>Why this join</span>
          <input
            aria-label={`Reason for the join into ${shot.shot_id}`}
            value={reason}
            maxLength={240}
            disabled={saving}
            placeholder="Lift the chorus…"
            onChange={(event) => { dirty.current = true; setReason(event.target.value); }}
          />
        </label>
      )}
      <Button size="small" disabled={!canSave} onClick={() => void save()}>
        {saving ? "Saving…" : "Save join"}
      </Button>
    </div>
  );
}

export function CutList({
  film,
  onNavigate,
  onFiles,
}: {
  film: FilmData;
  onNavigate: (stage: Stage) => void;
  onFiles: () => void;
}) {
  const { slug, cut, board, busy, seedCut, groups, boardById, imageById, saveTransition, showEditFile } = film;
  const fps = board?.fps || 24;
  return (
          <section className="cut-section">
            <header className="cut-head">
              <div>
                <h2>{cut?.present ? "The cut" : "The film cut"}</h2>
                <p>
                  {cut?.present
                    ? "How each shot arrives, what moves, and why. The cut owns timing."
                    : "The storyboard owns timing until the Editor cuts the film."}
                </p>
              </div>
              <ArtifactRating slug={slug} artifact="edit" />
            </header>

            {!board ? (
              <div className="card seed-cut">
                <h3>The storyboard comes first</h3>
                <p>
                  Film reads the cut from the approved storyboard. Make the storyboard,
                  then let the Editor cut it.
                </p>
                <div className="row-actions">
                  <Button variant="primary" onClick={() => onNavigate("storyboard")}>
                    Go to Storyboard
                  </Button>
                </div>
              </div>
            ) : !cut?.present ? (
              <div className="card seed-cut">
                <h3>Let the Editor cut it</h3>
                <p>
                  The film already plays with the storyboard's timing. Move order, spans,
                  motion, transitions, accents and grade into a cut to shape it.
                </p>
                <div className="row-actions">
                  <Button
                    variant="primary"
                    disabled={busy !== null}
                    onClick={() => void seedCut()}
                  >
                    {busy === "seed" ? "Cutting…" : "Make a first cut"}
                  </Button>
                  <Button variant="quiet" onClick={onFiles}>
                    Keep the storyboard timing
                  </Button>
                </div>
                <p className="hint">
                  Keeping it costs nothing and keeps every current approval valid.
                </p>
              </div>
            ) : (
              <>
                {cut.hard.length > 0 && (
                  <div className="cut-findings hard">
                    <b>
                      {cut.hard.length} hard finding{cut.hard.length === 1 ? "" : "s"}
                    </b>
                    {cut.hard.map((finding) => (
                      <span key={`${finding.code}-${finding.shot_id || ""}-${finding.message}`}>
                        {finding.shot_id ? `${finding.shot_id}: ` : ""}
                        {finding.message}
                      </span>
                    ))}
                  </div>
                )}
                {cut.warnings.length > 0 && (
                  <details className="cut-findings warning-details">
                    <summary>
                      {cut.warnings.length} warning{cut.warnings.length === 1 ? "" : "s"}
                    </summary>
                    {cut.warnings.map((finding) => (
                      <span key={`${finding.code}-${finding.shot_id || ""}-${finding.message}`}>
                        {finding.shot_id ? `${finding.shot_id}: ` : ""}
                        {finding.message}
                      </span>
                    ))}
                  </details>
                )}
                <div className="cut-facts">
                  <span>{cut.counts.shots ?? 0} shots</span>
                  <span>{cut.counts.cuts ?? 0} cuts</span>
                  <span>
                    {cut.counts.holds ?? 0} holds (
                    {Math.round((cut.counts.hold_ratio || 0) * 100)}%)
                  </span>
                  <span>{cut.counts.accents ?? 0} accents</span>
                  {cut.grade && <span>Grade: {cut.grade}</span>}
                </div>
                {cut.techniques.length > 0 && (
                  <div className="cut-techniques" aria-label="Techniques in this cut">
                    {cut.techniques.map((technique) => (
                      <span
                        className="technique"
                        key={technique.name}
                        title={technique.reasons.join(" · ") || undefined}
                      >
                        {technique.name}
                        {technique.count > 1 ? ` ×${technique.count}` : ""}
                      </span>
                    ))}
                  </div>
                )}
                {cut.notes && <p className="cut-notes">{cut.notes}</p>}

                <div className="cut-sections">
                  {groups.map((group) => (
                    <section className="cut-group" key={group.section.id}>
                      <header>
                        <h3>{group.section.name}</h3>
                        <span className="hint">
                          {clock(group.section.start_frame / fps)}–
                          {clock(group.section.end_frame / fps)} · {group.shots.length}{" "}
                          {group.shots.length === 1 ? "shot" : "shots"}
                        </span>
                      </header>
                      <div className="cut-list">
                        {group.shots.map((shot) => {
                          const source = boardById.get(shot.shot_id);
                          return (
                            <article className="cut-shot" key={shot.shot_id}>
                              {source ? (
                                <ShotThumb
                                  slug={slug}
                                  shot={source}
                                  image={imageById.get(source.id)}
                                  className="cut-thumb"
                                />
                              ) : (
                                <div className="cut-thumb shot-thumb" />
                              )}
                              <div className="cut-shot-body">
                                <div className="cut-shot-line">
                                  <b>{shot.shot_id}</b>
                                  <span>{clock(shot.start_frame / fps)}</span>
                                  <span>{duration(shot.seconds)}</span>
                                  <span className="cut-arrival">{shot.transition.label}</span>
                                  <span className="cut-motion">{shot.motion.label}</span>
                                </div>
                                <p className="cut-shot-job">
                                  {source?.message || source?.purpose || "No shot content."}
                                </p>
                                <div className="cut-shot-tags">
                                  {shot.accents.map((accent) => (
                                    <span className="accent" key={`${accent.frame}-${accent.type}`}>
                                      {accent.label}
                                    </span>
                                  ))}
                                  {shot.text.map((item) => (
                                    <span className="cut-text" key={item.id}>
                                      “{item.text}”
                                    </span>
                                  ))}
                                </div>
                                {shot.reasons.length > 0 && (
                                  <div className="cut-why">
                                    {shot.reasons.map((reason) => (
                                      <span key={`${reason.kind}-${reason.label}-${reason.reason}`}>
                                        <b>{reason.label}</b> {reason.reason}
                                      </span>
                                    ))}
                                  </div>
                                )}
                                {cut.edit && (
                                  <TransitionEditor
                                    key={shot.shot_id}
                                    base={cut.edit}
                                    shot={shot}
                                    busy={busy === `join:${shot.shot_id}`}
                                    onSave={(change, base) => saveTransition(shot.shot_id, change, base)}
                                  />
                                )}
                              </div>
                            </article>
                          );
                        })}
                      </div>
                    </section>
                  ))}
                </div>

                {cut.edit && showEditFile && (
                  <details className="cut-json">
                    <summary>Edit file (read-only)</summary>
                    <pre>{JSON.stringify(cut.edit, null, 2)}</pre>
                  </details>
                )}
              </>
            )}
          </section>
  );
}
