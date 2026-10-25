import { useEffect, useState } from "react";
import { api, type ApprovalState } from "./api";

const LABEL: Record<string, string> = {
  approved: "approved",
  stale: "changed since approval",
  missing: "not approved",
  unavailable: "not ready",
};

export function ApprovalBar({ slug, stages }: { slug: string; stages: string[] }) {
  const [items, setItems] = useState<ApprovalState[]>([]);
  const [notes, setNotes] = useState<Record<string, string>>({});
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
  }, [slug, keys]);

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
      });
      setNotes((n) => ({ ...n, [item.stage]: "" }));
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
              <input
                value={notes[item.stage] || ""}
                onChange={(e) =>
                  setNotes((n) => ({ ...n, [item.stage]: e.target.value }))
                }
                placeholder="what did you check?"
              />
              <button
                onClick={() => approve(item)}
                disabled={busy === item.stage || !(notes[item.stage] || "").trim()}
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
