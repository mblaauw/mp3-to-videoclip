import { ArtifactRating } from "../ArtifactRating";
import type { Stage } from "../shell/nextStep";
import { ShotThumb } from "../storyboard/ShotThumb";
import { SeedCut } from "./SeedCut";
import type { FilmData } from "./useFilmData";

function clock(seconds: number): string {
  const value = Math.max(0, Math.floor(seconds));
  return `${Math.floor(value / 60)}:${String(value % 60).padStart(2, "0")}`;
}

function duration(seconds: number): string {
  return `${seconds.toFixed(1)} s`;
}

export function CutList({
  film,
  onNavigate,
}: {
  film: FilmData;
  onNavigate: (stage: Stage) => void;
}) {
  const { slug, cut, board, groups, boardById, imageById, showEditFile } = film;
  const fps = board?.fps || 24;
  return (
          <section className="cut-section">
            <header className="cut-head">
              <div>
                <h2>{cut?.present ? "The cut" : "The film cut"}</h2>
                <p>
                  {cut?.present
                    ? "How each shot arrives, what moves, and why. Change them on the timeline."
                    : "The storyboard owns timing until the Editor cuts the film."}
                </p>
              </div>
              <ArtifactRating slug={slug} artifact="edit" />
            </header>

            {!cut?.present ? (
              <SeedCut film={film} board={board} onNavigate={onNavigate} />
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
