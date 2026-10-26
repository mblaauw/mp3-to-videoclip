import { useEffect, useState } from "react";
import { api, type Brief, type Shot, type ShotKind, type Storyboard } from "../api";
import { ApprovalBar } from "../ApprovalBar";
import { ArtifactRating } from "../ArtifactRating";
import { SHOT_KINDS, isPaidShot, kindMeta, kindOf } from "../shotKinds";
import { notifyProjectChanged, PROJECT_CHANGED } from "../shell/projectEvents";

export function StoryboardStage({ slug }: { slug: string }) {
  const [board, setBoard] = useState<Storyboard | null>(null);
  const [draft, setDraft] = useState<Record<string, Partial<Shot>>>({});
  const [saving, setSaving] = useState(false);
  const [creating, setCreating] = useState(false);
  const [revision, setRevision] = useState(0);
  const [proofIds, setProofIds] = useState<string[]>([]);
  const [savingProof, setSavingProof] = useState(false);
  const [proofMessage, setProofMessage] = useState<string | null>(null);
  const [timingOwned, setTimingOwned] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .storyboard(slug)
      .then((data) => setBoard("available" in data ? null : data))
      .catch((e) => setError(String(e)));
    api
      .brief(slug)
      .then((data: Brief) => setProofIds(data.creative?.proof_shot_ids || []))
      .catch(() => setProofIds([]));
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

  useEffect(() => {
    const reload = () => {
      api
        .storyboard(slug)
        .then((data) => setBoard("available" in data ? null : data))
        .catch((caught) => setError(String(caught)));
    };
    window.addEventListener(PROJECT_CHANGED, reload);
    return () => window.removeEventListener(PROJECT_CHANGED, reload);
  }, [slug]);

  const edit = (id: string, field: keyof Shot, value: unknown) => {
    setDraft((d) => ({ ...d, [id]: { ...d[id], [field]: value } }));
  };

  const patch = (id: string, value: Partial<Shot>) => {
    setDraft((d) => ({ ...d, [id]: { ...d[id], ...value } }));
  };

  const changeKind = (shot: Shot, value: string) => {
    const kind = value as ShotKind;
    const next: Partial<Shot> = { kind };
    if (kind === "bridge") {
      next.bridge =
        shot.bridge ?? {
          mode: "designed",
          match: { type: "shape", anchor: [0.5, 0.5], note: "" },
        };
    } else {
      next.bridge = null;
    }
    if (kind === "split") {
      const candidates =
        board?.shots
          .filter((item) => item.id !== shot.id && kindOf(item) !== "split")
          .map((item) => item.id) ?? [];
      next.panes =
        shot.panes && shot.panes.length
          ? shot.panes
          : candidates.slice(0, 2).map((shot_id) => ({ shot_id }));
    } else {
      next.panes = [];
    }
    if (kind === "reprise") {
      next.asset_shot_id =
        shot.asset_shot_id ??
        board?.shots.find((item) => item.id !== shot.id && !item.asset_shot_id)?.id ??
        null;
    }
    if (!["upload", "product", "card", "logo", "end_card"].includes(kind)) {
      next.asset = null;
    }
    if (isPaidShot({ ...shot, ...next }) && !shot.image_prompt?.trim()) {
      next.image_prompt = shot.purpose;
    }
    patch(shot.id, next);
  };

  const create = async () => {
    setCreating(true);
    setError(null);
    try {
      setBoard(await api.createSkeleton(slug));
      setDraft({});
      setRevision((value) => value + 1);
      notifyProjectChanged();
    } catch (e) {
      setError(String(e));
    } finally {
      setCreating(false);
    }
  };

  const sourceShots = board?.shots.filter((shot) => isPaidShot(shot)) || [];
  const expectedProof = Math.min(3, sourceShots.length);

  const toggleProof = (id: string) => {
    setProofMessage(null);
    const next = proofIds.includes(id)
      ? proofIds.filter((value) => value !== id)
      : proofIds.length >= expectedProof
        ? proofIds
        : [...proofIds, id];
    setProofIds(next);
    if (next.length === expectedProof) void saveProof(next);
  };

  const saveProof = async (ids = proofIds) => {
    if (!board || ids.length !== expectedProof) return;
    setSavingProof(true);
    setError(null);
    try {
      const result = await api.setProofShots(slug, ids);
      setProofIds(result.proof_shot_ids);
      setProofMessage("Style-check shots changed. The story needs your approval again.");
      setRevision((value) => value + 1);
      notifyProjectChanged();
    } catch (e) {
      setError(String(e));
    } finally {
      setSavingProof(false);
    }
  };

  const save = async () => {
    const changes = Object.entries(draft).map(([id, value]) => ({ id, ...value }));
    if (!changes.length) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await api.patchShots(slug, changes);
      setBoard(updated);
      setDraft({});
      setRevision((value) => value + 1);
      notifyProjectChanged();
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <h2>Storyboard</h2>
      <p className="sub">
        Integer-frame timeline, stable shot IDs. Choose each shot's kind, job, message and
        on-screen text; only scene and generated product/bridge shots cost money.
      </p>
      {error && <p className="error">{error}</p>}
      <ApprovalBar slug={slug} stages={["storyboard"]} refresh={revision} />
      {board && expectedProof > 0 && (
        <div className="card">
          <h3>
            Style-check shots ({proofIds.length} of {expectedProof})
          </h3>
          <p className="meta">
            Pick the hardest identity or interaction to inspect first, not the safest portrait.
            Changing a star asks for the story to be approved again.
          </p>
          <div className="proof-list">
            {sourceShots.map((shot) => (
              <label key={shot.id} className={proofIds.includes(shot.id) ? "chosen" : ""}>
                <span aria-hidden="true" className="star">
                  ★
                </span>
                <input
                  type="checkbox"
                  checked={proofIds.includes(shot.id)}
                  onChange={() => toggleProof(shot.id)}
                  disabled={savingProof || (!proofIds.includes(shot.id) && proofIds.length >= expectedProof)}
                />
                {shot.id}
              </label>
            ))}
          </div>
          {savingProof && <p className="meta">Saving the style-check shots…</p>}
          {proofMessage && <p className="message">{proofMessage}</p>}
        </div>
      )}
      <div className="card">
        {board ? (
          <>
            <h3>Shots</h3>
            {timingOwned && (
              <p className="meta">
                Timing and motion are owned by the Film cut. Change them in Film → Cut;
                the spine below shows the current cuts.
              </p>
            )}
            <div className="table-scroll">
            <table>
            <thead>
              <tr>
                <th>Shot</th>
                <th>Frames</th>
                <th>Kind</th>
                <th>Purpose</th>
                <th>Message</th>
                <th>Text</th>
                <th>Prompt</th>
                <th>Framing</th>
                <th>Camera</th>
              </tr>
            </thead>
            <tbody>
              {board.shots.map((s) => {
                const current = { ...s, ...draft[s.id] } as Shot;
                const paid = isPaidShot(current);
                return (
                <tr key={s.id}>
                  <td>{s.id}</td>
                  <td>
                    {s.start_frame}–{s.start_frame + s.duration_frames}
                  </td>
                  <td>
                    <span className="kind-badge" title={kindMeta(kindOf(current)).hint}>
                      {kindMeta(kindOf(current)).icon}
                    </span>
                    <select
                      aria-label={`Kind for ${s.id}`}
                      value={kindOf(current)}
                      onChange={(e) => changeKind(s, e.target.value)}
                    >
                      {SHOT_KINDS.map((kind) => (
                        <option key={kind.id} value={kind.id}>
                          {kind.icon} {kind.label}
                        </option>
                      ))}
                    </select>
                  </td>
                  <td>
                    <input
                      value={(draft[s.id]?.purpose ?? s.purpose) as string}
                      onChange={(e) => edit(s.id, "purpose", e.target.value)}
                    />
                  </td>
                  <td>
                    <input
                      value={(draft[s.id]?.message ?? s.message ?? "") as string}
                      onChange={(e) => edit(s.id, "message", e.target.value)}
                    />
                  </td>
                  <td>
                    <textarea
                      aria-label={`On-screen text for ${s.id}`}
                      placeholder="one line per card line"
                      value={(draft[s.id]?.text ?? s.text ?? []).join("\n")}
                      onChange={(e) =>
                        edit(
                          s.id,
                          "text",
                          e.target.value
                            .split("\n")
                            .map((line) => line.trim())
                            .filter(Boolean),
                        )
                      }
                    />
                  </td>
                  <td>
                    <textarea
                      aria-label={`Prompt for ${s.id}`}
                      placeholder={paid ? "Describe the decisive still" : "Local kind — no generated image"}
                      disabled={!paid}
                      value={(draft[s.id]?.image_prompt ?? s.image_prompt ?? "") as string}
                      onChange={(e) => edit(s.id, "image_prompt", e.target.value)}
                    />
                  </td>
                  <td>
                    <select
                      value={(draft[s.id]?.framing ?? s.framing ?? "") as string}
                      onChange={(e) => edit(s.id, "framing", e.target.value)}
                    >
                      <option value="">—</option>
                      <option value="wide">wide</option>
                      <option value="medium">medium</option>
                      <option value="close_up">close_up</option>
                      <option value="detail">detail</option>
                    </select>
                  </td>
                  <td>
                    <select
                      value={(draft[s.id]?.camera ?? s.camera) as string}
                      disabled={timingOwned}
                      onChange={(e) => edit(s.id, "camera", e.target.value)}
                    >
                      <option value="hold">hold</option>
                      <option value="zoom_in">zoom_in</option>
                      <option value="zoom_out">zoom_out</option>
                      <option value="pan_left">pan_left</option>
                      <option value="pan_right">pan_right</option>
                    </select>
                  </td>
                </tr>
              );
              })}
            </tbody>
          </table>
            </div>
          </>
        ) : (
          <>
            <p className="empty">No storyboard yet. The brief must be approved first.</p>
            <button onClick={create} disabled={creating}>
              {creating ? "Planning…" : "Create timing skeleton"}
            </button>
            <p className="meta">
              Timing only. Fill each shot's purpose and prompt before approving the board.
            </p>
          </>
        )}
      </div>
      <button onClick={save} disabled={saving || !Object.keys(draft).length}>
        {saving ? "Saving…" : `Save ${Object.keys(draft).length || ""} changes`}
      </button>
      <div className="card">
        <h3>Rate this storyboard</h3>
        <ArtifactRating slug={slug} artifact="storyboard" />
      </div>
    </>
  );
}
