import { useEffect, useState } from "react";
import { api, type ApprovalState } from "./api";

const LABEL: Record<string, string> = {
  approved: "approved",
  stale: "changed since approval",
  missing: "not approved",
  unavailable: "not ready",
};

export function ApprovalBar({
  slug,
  stages,
  refresh = 0,
}: {
  slug: string;
  stages: string[];
  refresh?: number;
}) {
  const [items, setItems] = useState<ApprovalState[]>([]);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [attested, setAttested] = useState<Record<string, boolean>>({});
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const keys = stages.join(",");

  const load = () => {
    api
      .approvals(slug, stages)
      .then((d) => setItems(d.stages))
      .catch((e) => setError(String(e)));
  };

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slug, keys, refresh]);

  const approve = async (item: ApprovalState) => {
    if (!item.expected_hash) return;
    const note = (notes[item.stage] || "").trim();
    if (!note) return;
    setBusy(item.stage);
    setError(null);
    try {
      await api.approve(slug, item.stage, {
        expected_hash: item.expected_hash,
        note,
        confirmed: true,
        ...(item.stage === "preview" ? { preview_watched: !!attested[item.stage] } : {}),
        ...(item.stage === "graphics" ? { inspected: !!attested[item.stage] } : {}),
        ...(item.stage === "lyrics" ? { acknowledge_uncertain: !!attested[item.stage] } : {}),
      });
      setNotes((n) => ({ ...n, [item.stage]: "" }));
      setAttested((current) => ({ ...current, [item.stage]: false }));
      load();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(null);
    }
  };

  if (!items.length) return null;
  return (
    <section className="card approvals">
      <h3>Approval</h3>
      {items.map((item) => (
        <div className="row" key={item.stage}>
          <div className="who">
            <strong>{item.stage}</strong>{" "}
            <span className={`chip ${item.state}`}>{LABEL[item.state]}</span>
            {item.at && (
              <span className="meta"> {new Date(item.at).toLocaleString()}</span>
            )}
            {item.note && <div className="meta">{item.note}</div>}
            {item.state === "unavailable" && item.error && (
              <div className="meta">{item.error}</div>
            )}
          </div>
          {item.state !== "approved" && item.expected_hash && (
            <div className="approve">
              {["preview", "graphics", "lyrics"].includes(item.stage) && (
                <label className="attest">
                  <input
                    type="checkbox"
                    checked={!!attested[item.stage]}
                    onChange={(e) =>
                      setAttested((current) => ({ ...current, [item.stage]: e.target.checked }))
                    }
                  />
                  {item.stage === "preview"
                    ? "I watched the preview continuously with the actual music"
                    : item.stage === "graphics"
                      ? "I inspected the composited graphics samples"
                      : "I reviewed the flagged lyric lines"}
                </label>
              )}
              <input
                value={notes[item.stage] || ""}
                onChange={(e) =>
                  setNotes((n) => ({ ...n, [item.stage]: e.target.value }))
                }
                placeholder="what did you check?"
              />
              <button
                onClick={() => approve(item)}
                disabled={
                  busy === item.stage ||
                  !(notes[item.stage] || "").trim() ||
                  ((item.stage === "preview" || item.stage === "graphics") &&
                    !attested[item.stage])
                }
              >
                {busy === item.stage ? "…" : "Approve"}
              </button>
            </div>
          )}
        </div>
      ))}
      {error && <p className="error">{error}</p>}
    </section>
  );
}
