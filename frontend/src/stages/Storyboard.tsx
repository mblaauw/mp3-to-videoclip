import { useEffect, useState } from "react";
import { api, type Shot, type Storyboard } from "../api";
import { ApprovalBar } from "../ApprovalBar";

export function StoryboardStage({ slug }: { slug: string }) {
  const [board, setBoard] = useState<Storyboard | null>(null);
  const [draft, setDraft] = useState<Record<string, Partial<Shot>>>({});
  const [saving, setSaving] = useState(false);
  const [creating, setCreating] = useState(false);
  const [revision, setRevision] = useState(0);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .storyboard(slug)
      .then((data) => setBoard("available" in data ? null : data))
      .catch((e) => setError(String(e)));
  }, [slug]);

  const edit = (id: string, field: keyof Shot, value: string | number) => {
    setDraft((d) => ({ ...d, [id]: { ...d[id], [field]: value } }));
  };

  const create = async () => {
    setCreating(true);
    setError(null);
    try {
      setBoard(await api.createSkeleton(slug));
      setDraft({});
      setRevision((value) => value + 1);
    } catch (e) {
      setError(String(e));
    } finally {
      setCreating(false);
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
        Integer-frame timeline, stable shot IDs. Edit purpose, prompt, framing or camera; save to
        update the board.
      </p>
      {error && <p className="error">{error}</p>}
      <ApprovalBar slug={slug} stages={["storyboard"]} refresh={revision} />
      <div className="card">
        {board ? (
          <table>
            <thead>
              <tr>
                <th>Shot</th>
                <th>Frames</th>
                <th>Purpose</th>
                <th>Prompt</th>
                <th>Framing</th>
                <th>Camera</th>
              </tr>
            </thead>
            <tbody>
              {board.shots.map((s) => (
                <tr key={s.id}>
                  <td>{s.id}</td>
                  <td>
                    {s.start_frame}–{s.start_frame + s.duration_frames}
                  </td>
                  <td>
                    <input
                      value={(draft[s.id]?.purpose ?? s.purpose) as string}
                      onChange={(e) => edit(s.id, "purpose", e.target.value)}
                    />
                  </td>
                  <td>
                    <textarea
                      value={(draft[s.id]?.image_prompt ?? s.image_prompt) as string}
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
              ))}
            </tbody>
          </table>
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
    </>
  );
}