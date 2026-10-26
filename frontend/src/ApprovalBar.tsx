import { useEffect, useState } from "react";
import { api, type ApprovalState } from "./api";
import { notifyProjectChanged } from "./shell/projectEvents";

const LABEL: Record<string, string> = {
  approved: "approved",
  stale: "changed since approval",
  missing: "not approved",
  unavailable: "not ready",
};

const BUTTON: Record<string, string> = {
  analysis: "Approve analysis",
  lyrics: "Approve lyrics",
  brief: "Approve story",
  storyboard: "Approve storyboard",
  proof: "Approve style check",
  preview: "Approve preview",
  stills: "Approve all stills",
  graphics: "Approve graphics",
};

export function ApprovalBar({
  slug,
  stages,
  refresh = 0,
  onApproved,
}: {
  slug: string;
  stages: string[];
  refresh?: number;
  onApproved?: () => void;
}) {
  const [items, setItems] = useState<ApprovalState[]>([]);
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [notesOpen, setNotesOpen] = useState<Record<string, boolean>>({});
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
    setBusy(item.stage);
    setError(null);
    try {
      await api.approve(slug, item.stage, {
        expected_hash: item.expected_hash,
        note: (notes[item.stage] || "").trim(),
        confirmed: true,
        ...(item.stage === "preview" ? { preview_watched: !!attested[item.stage] } : {}),
        ...(item.stage === "graphics" ? { inspected: !!attested[item.stage] } : {}),
        ...(item.stage === "lyrics" ? { acknowledge_uncertain: !!attested[item.stage] } : {}),
      });
      setNotes((n) => ({ ...n, [item.stage]: "" }));
      setNotesOpen((n) => ({ ...n, [item.stage]: false }));
      setAttested((current) => ({ ...current, [item.stage]: false }));
      load();
      notifyProjectChanged();
      onApproved?.();
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
      {items.map((item) => {
        const attestation = ["preview", "graphics", "lyrics"].includes(item.stage);
        const attestedOk = !attestation || !!attested[item.stage];
        return (
          <div className="row" key={item.stage}>
            <div className="who">
              <strong>{item.stage}</strong>{" "}
              <span className={`chip ${item.state}`}>{LABEL[item.state]}</span>
              {item.at && (
                <span className="meta"> {new Date(item.at).toLocaleString()}</span>
              )}
              {item.reason && <div className="meta">{item.reason}</div>}
              {!item.reason && item.note && <div className="meta">{item.note}</div>}
              {item.state === "unavailable" && item.error && (
                <div className="meta">{item.error}</div>
              )}
            </div>
            {item.state !== "approved" && item.expected_hash && (
              <div className="approve">
                {attestation && (
                  <label className="attest">
                    <input
                      type="checkbox"
                      checked={!!attested[item.stage]}
                      onChange={(e) =>
                        setAttested((current) => ({
                          ...current,
                          [item.stage]: e.target.checked,
                        }))
                      }
                    />
                    {item.stage === "preview"
                      ? "I watched the preview continuously with the actual music"
                      : item.stage === "graphics"
                        ? "I inspected the composited graphics samples"
                        : "I reviewed the lyric lines"}
                  </label>
                )}
                {notesOpen[item.stage] ? (
                  <input
                    value={notes[item.stage] || ""}
                    onChange={(e) =>
                      setNotes((n) => ({ ...n, [item.stage]: e.target.value }))
                    }
                    placeholder="What did you check? (optional)"
                    maxLength={2000}
                    aria-label={`Approval note for ${item.stage}`}
                  />
                ) : (
                  <button
                    type="button"
                    className="quiet"
                    onClick={() =>
                      setNotesOpen((current) => ({ ...current, [item.stage]: true }))
                    }
                  >
                    Add a note
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => approve(item)}
                  disabled={busy === item.stage || !attestedOk}
                >
                  {busy === item.stage ? "…" : BUTTON[item.stage] || "Approve"}
                </button>
              </div>
            )}
          </div>
        );
      })}
      {error && <p className="error">{error}</p>}
    </section>
  );
}
