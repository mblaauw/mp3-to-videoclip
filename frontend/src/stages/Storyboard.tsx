import { useEffect, useState } from "react";
import { api, type Shot, type Storyboard } from "../api";

export function StoryboardStage({ slug }: { slug: string }) {
  const [board, setBoard] = useState<Storyboard | null>(null);
  const [draft, setDraft] = useState<Record<string, Partial<Shot>>>({});
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .storyboard(slug)
      .then(setBoard)
      .catch((e) => setError(String(e)));
  }, [slug]);

  const edit = (id: string, field: keyof Shot, value: string | number) => {
    setDraft((d) => ({ ...d, [id]: { ...d[id], [field]: value } }));
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
          <p className="empty">No storyboard yet.</p>
        )}
      </div>
      <button onClick={save} disabled={saving || !Object.keys(draft).length}>
        {saving ? "Saving…" : `Save ${Object.keys(draft).length || ""} changes`}
      </button>
    </>
  );
}