import { useEffect, useMemo, useState } from "react";
import {
  api,
  type Brief,
  type Music,
  type Shot,
  type Storyboard,
} from "../api";
import { ApprovalBar } from "../ApprovalBar";
import { ArtifactRating } from "../ArtifactRating";
import { notifyProjectChanged, PROJECT_CHANGED } from "../shell/projectEvents";
import { isPaidShot, kindMeta, kindOf } from "../shotKinds";
import { ShotThumb } from "../storyboard/ShotThumb";
import { Button } from "../ui";

function clock(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

type Group = { key: string; title: string; range: string; shots: Shot[] };

function groupsFor(board: Storyboard, music: Music | null): Group[] {
  const fps = board.fps || 24;
  const sections = (music?.sections || []).filter(
    (section) => Number(section.end) > Number(section.start),
  );
  if (!sections.length) {
    return [{ key: "whole", title: "Whole film", range: "", shots: board.shots }];
  }
  const buckets = new Map<string, Group>();
  const groups: Group[] = sections.map((section, index) => {
    const key = `section-${index}`;
    const title =
      section.name ||
      (section.label && section.label !== "unreviewed" ? section.label : `Section ${index + 1}`);
    const group: Group = {
      key,
      title,
      range: `${clock(Number(section.start))}–${clock(Number(section.end))}`,
      shots: [],
    };
    buckets.set(key, group);
    return group;
  });
  const gaps: Group = { key: "between", title: "Between sections", range: "", shots: [] };
  for (const shot of board.shots) {
    const at = shot.start_frame / fps;
    const home = sections.findIndex(
      (section) => at >= Number(section.start) && at < Number(section.end),
    );
    if (home >= 0) groups[home].shots.push(shot);
    else gaps.shots.push(shot);
  }
  const result = groups.filter((group) => group.shots.length > 0);
  if (gaps.shots.length) result.push(gaps);
  return result;
}

export function StoryboardStage({
  slug,
  onInspect,
}: {
  slug: string;
  onInspect: (shotId: string) => void;
}) {
  const [board, setBoard] = useState<Storyboard | null>(null);
  const [music, setMusic] = useState<Music | null>(null);
  const [creating, setCreating] = useState(false);
  const [revision, setRevision] = useState(0);
  const [proofIds, setProofIds] = useState<string[]>([]);
  const [savingProof, setSavingProof] = useState(false);
  const [proofMessage, setProofMessage] = useState<string | null>(null);
  const [timingOwned, setTimingOwned] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [view, setView] = useState<"pictures" | "table">("pictures");

  useEffect(() => {
    let live = true;
    const load = () => {
      api
        .storyboard(slug)
        .then((data) => {
          if (live) setBoard("available" in data ? null : data);
        })
        .catch((caught) => {
          if (live) setError(String(caught));
        });
      api
        .brief(slug)
        .then((data: Brief) => {
          if (live) setProofIds(data.creative?.proof_shot_ids || []);
        })
        .catch(() => {
          if (live) setProofIds([]);
        });
      api
        .track(slug)
        .then((data) => {
          if (live) setMusic(data.music);
        })
        .catch(() => {
          if (live) setMusic(null);
        });
    };
    setError(null);
    load();
    window.addEventListener(PROJECT_CHANGED, load);
    return () => {
      live = false;
      window.removeEventListener(PROJECT_CHANGED, load);
    };
  }, [slug]);

  useEffect(() => {
    if (!board) {
      setTimingOwned(false);
      return;
    }
    api
      .edit(slug)
      .then((data) => setTimingOwned(data.present))
      .catch(() => setTimingOwned(false));
  }, [board, slug]);

  const create = async () => {
    setCreating(true);
    setError(null);
    try {
      setBoard(await api.createSkeleton(slug));
      setRevision((value) => value + 1);
      notifyProjectChanged();
    } catch (caught) {
      setError(String(caught));
    } finally {
      setCreating(false);
    }
  };

  const sourceShots = useMemo(
    () => board?.shots.filter((shot) => shot.asset_shot_id === null && isPaidShot(shot)) || [],
    [board],
  );
  const expectedProof = Math.min(3, sourceShots.length);

  const saveProof = async (ids: string[]) => {
    if (!board || ids.length !== expectedProof) return;
    setSavingProof(true);
    setError(null);
    try {
      const result = await api.setProofShots(slug, ids);
      setProofIds(result.proof_shot_ids);
      setProofMessage("Style-check shots changed. The story needs your approval again.");
      setRevision((value) => value + 1);
      notifyProjectChanged();
    } catch (caught) {
      setError(String(caught));
    } finally {
      setSavingProof(false);
    }
  };

  const toggleProof = (id: string) => {
    setProofMessage(null);
    const next = proofIds.includes(id)
      ? proofIds.filter((value) => value !== id)
      : proofIds.length >= expectedProof
        ? proofIds
        : [...proofIds, id];
    setProofIds(next);
    if (next.length === expectedProof) void saveProof(next);
    else if (next.length < expectedProof) {
      setProofMessage(`Pick ${expectedProof - next.length} more for the style check.`);
    }
  };

  const groups = useMemo(() => (board ? groupsFor(board, music) : []), [board, music]);
  const fps = board?.fps || 24;

  return (
    <>
      <div className="stage-head storyboard-head">
        <div>
          <h1>Storyboard</h1>
          <p>
            Integer-frame timeline, stable shot IDs. Choose each shot's kind, job, message
            and on-screen text; only scene and generated product or bridge shots cost money.
          </p>
        </div>
        <div className="stage-tools">
          <ArtifactRating slug={slug} artifact="storyboard" />
          {board && (
            <div className="board-tabs" role="group" aria-label="Storyboard view">
              <Button
                size="small"
                variant={view === "pictures" ? "primary" : "quiet"}
                aria-pressed={view === "pictures"}
                onClick={() => setView("pictures")}
              >
                Pictures
              </Button>
              <Button
                size="small"
                variant={view === "table" ? "primary" : "quiet"}
                aria-pressed={view === "table"}
                onClick={() => setView("table")}
              >
                Table
              </Button>
            </div>
          )}
        </div>
      </div>
      {error && <p className="error">{error}</p>}
      <ApprovalBar slug={slug} stages={["storyboard"]} refresh={revision} />

      {!board ? (
        <section className="card empty-card">
          <p className="empty">No storyboard yet. The brief must be approved first.</p>
          <Button variant="primary" onClick={() => void create()} disabled={creating}>
            {creating ? "Planning…" : "Create timing skeleton"}
          </Button>
          <p className="hint">
            Timing only. Fill each shot's job and prompt before approving the board.
          </p>
        </section>
      ) : (
        <>
          {expectedProof > 0 && (
            <section className={`style-check ${proofIds.length === expectedProof ? "set" : ""}`}>
              <div className="style-check-say">
                <b>
                  Style check · {proofIds.length} of {expectedProof}
                </b>
                <span>
                  Star the hardest identity or interaction first. Changing the stars asks for
                  the story to be approved again.
                </span>
              </div>
              <div className="style-check-picks">
                {proofIds.map((id) => (
                  <button
                    key={id}
                    type="button"
                    className="style-pick"
                    aria-label={`Remove ${id} from the style check`}
                    onClick={() => toggleProof(id)}
                    disabled={savingProof}
                  >
                    {id} <span aria-hidden="true">×</span>
                  </button>
                ))}
                {proofIds.length === 0 && <span className="hint">No star yet.</span>}
              </div>
              {proofIds.length < expectedProof && (
                <span className="hint">Pick {expectedProof - proofIds.length} more.</span>
              )}
              {savingProof && <span className="hint">Saving the style-check shots…</span>}
            </section>
          )}
          {proofMessage && <p className="message">{proofMessage}</p>}
          {timingOwned && (
            <p className="hint">
              Timing and motion are owned by the Film cut. Change them in Film → Cut; the
              spine below shows the current cuts.
            </p>
          )}

          {view === "pictures" ? (
            <div className="board-sections">
              {groups.map((group) => (
                <section className="board-section" key={group.key}>
                  <header className="board-section-head">
                    <h2>{group.title}</h2>
                    <span className="hint">
                      {group.range ? `${group.range} · ` : ""}
                      {group.shots.length} {group.shots.length === 1 ? "shot" : "shots"}
                    </span>
                  </header>
                  <div className="shot-grid">
                    {group.shots.map((shot) => {
                      const paid = isPaidShot(shot);
                      const starred = proofIds.includes(shot.id);
                      const kind = kindMeta(kindOf(shot));
                      const canStar =
                        paid && shot.asset_shot_id === null && expectedProof > 0;
                      return (
                        <article className={`shot-card ${starred ? "starred" : ""}`} key={shot.id}>
                          <button
                            type="button"
                            className="shot-card-open"
                            onClick={() => onInspect(shot.id)}
                            aria-label={`Inspect ${shot.id}`}
                          >
                            <ShotThumb slug={slug} shot={shot} />
                            <span className="shot-card-caption">
                              {shot.message || shot.purpose}
                            </span>
                          </button>
                          <footer className="shot-card-foot">
                            <button
                              type="button"
                              className="shot-card-id"
                              onClick={() => onInspect(shot.id)}
                            >
                              {shot.id}
                            </button>
                            <span className="shot-card-meta">
                              {(shot.duration_frames / fps).toFixed(1)} s
                            </span>
                            {paid ? (
                              <span className="price-dot" title="Paid generated still">
                                $
                              </span>
                            ) : (
                              <span className="made-here" title={kind.hint}>
                                Made here, free
                              </span>
                            )}
                            {canStar && (
                              <button
                                type="button"
                                className={`star-toggle ${starred ? "on" : ""}`}
                                aria-pressed={starred}
                                aria-label={`${starred ? "Remove" : "Star"} ${shot.id} for the style check`}
                                title="Style-check shot"
                                disabled={
                                  savingProof ||
                                  (!starred && proofIds.length >= expectedProof)
                                }
                                onClick={() => toggleProof(shot.id)}
                              >
                                ★
                              </button>
                            )}
                          </footer>
                        </article>
                      );
                    })}
                  </div>
                </section>
              ))}
            </div>
          ) : (
            <div className="table-scroll board-table">
              <table>
                <thead>
                  <tr>
                    <th>Shot</th>
                    <th>In–out</th>
                    <th>Length</th>
                    <th>Kind</th>
                    <th>Job</th>
                    <th>Cost</th>
                    <th>Style</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {board.shots.map((shot) => {
                    const paid = isPaidShot(shot);
                    const starred = proofIds.includes(shot.id);
                    const canStar = paid && shot.asset_shot_id === null && expectedProof > 0;
                    return (
                      <tr key={shot.id} className={starred ? "starred" : ""}>
                        <td>
                          <button
                            type="button"
                            className="table-shot"
                            onClick={() => onInspect(shot.id)}
                          >
                            <ShotThumb slug={slug} shot={shot} className="table-thumb" />
                            <span>{shot.id}</span>
                          </button>
                        </td>
                        <td>
                          {clock(shot.start_frame / fps)}–
                          {clock((shot.start_frame + shot.duration_frames) / fps)}
                        </td>
                        <td>{(shot.duration_frames / fps).toFixed(1)} s</td>
                        <td>
                          <span className={`kind-badge kind-${kindOf(shot)}`}>
                            {kindMeta(kindOf(shot)).icon} {kindMeta(kindOf(shot)).label}
                          </span>
                        </td>
                        <td className="table-job">{shot.purpose}</td>
                        <td>{paid ? "Paid still" : "Free"}</td>
                        <td>
                          {canStar ? (
                            <button
                              type="button"
                              className={`star-toggle ${starred ? "on" : ""}`}
                              aria-pressed={starred}
                              aria-label={`${starred ? "Remove" : "Star"} ${shot.id} for the style check`}
                              disabled={
                                savingProof || (!starred && proofIds.length >= expectedProof)
                              }
                              onClick={() => toggleProof(shot.id)}
                            >
                              ★
                            </button>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td>
                          <Button size="small" variant="quiet" onClick={() => onInspect(shot.id)}>
                            Edit
                          </Button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </>
  );
}
