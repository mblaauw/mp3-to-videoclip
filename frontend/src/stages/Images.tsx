import { useEffect, useState } from "react";
import { api, type ImageShot } from "../api";

export function ImagesStage({ slug }: { slug: string }) {
  const [shots, setShots] = useState<ImageShot[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = () =>
    api
      .images(slug)
      .then((d) => setShots(d.shots))
      .catch((e) => setError(String(e)));

  useEffect(() => {
    load();
  }, [slug]);

  const select = async (shotId: string, version: number) => {
    setBusy(shotId);
    try {
      await api.selectImage(slug, shotId, version);
      await load();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(null);
    }
  };

  return (
    <>
      <h2>Images</h2>
      <p className="sub">Versions per shot. Select the one to render.</p>
      {error && <p className="error">{error}</p>}
      {shots.length ? (
        shots.map((s) => (
          <div className="card" key={s.id}>
            <h3>
              {s.id} · {s.versions.length} version{s.versions.length === 1 ? "" : "s"}
            </h3>
            <div className="pre">
              {s.versions.length
                ? s.versions.map((v) => (
                    <div key={v.version}>
                      <button
                        className={v.version === s.selected ? "active" : ""}
                        onClick={() => select(s.id, v.version)}
                        disabled={busy === s.id}
                      >
                        v{v.version}
                      </button>{" "}
                      <span className="meta">{v.path.split("/").slice(-2).join("/")}</span>
                    </div>
                  ))
                : "No versions yet."}
            </div>
          </div>
        ))
      ) : (
        <p className="empty">No storyboard or assets yet.</p>
      )}
    </>
  );
}