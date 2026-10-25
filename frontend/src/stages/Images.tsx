import { useEffect, useRef, useState } from "react";
import { api, type Budget, type BudgetDecision, type ImageEstimate, type ImageShot } from "../api";
import { ApprovalBar } from "../ApprovalBar";

type Card = Omit<Budget, "history">;

export function ImagesStage({ slug }: { slug: string }) {
  const [shots, setShots] = useState<ImageShot[]>([]);
  const [budget, setBudget] = useState<Card | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [reserve, setReserve] = useState("0.05");
  const [regenerate, setRegenerate] = useState(false);
  const [estimate, setEstimate] = useState<ImageEstimate | null>(null);
  const [decision, setDecision] = useState<BudgetDecision | null>(null);
  const [uploadsConfirmed, setUploadsConfirmed] = useState(false);
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const initialized = useRef(false);

  const load = () => {
    api
      .images(slug)
      .then((d) => {
        setShots(d.shots);
        setRevision((value) => value + 1);
        if (!initialized.current) {
          initialized.current = true;
          setSelected(new Set(d.shots.filter((s) => !s.versions.length).map((s) => s.id)));
        }
      })
      .catch((e) => setError(String(e)));
    api
      .budget(slug)
      .then((b) => setBudget(b))
      .catch(() => setBudget(null));
  };

  useEffect(() => {
    initialized.current = false;
    setSelected(new Set());
    setEstimate(null);
    setDecision(null);
    setMessage(null);
    setError(null);
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slug]);

  const clearQuote = () => {
    setEstimate(null);
    setDecision(null);
    setError(null);
  };

  const toggle = (id: string) => {
    clearQuote();
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const selectMissing = () => {
    clearQuote();
    setSelected(new Set(shots.filter((s) => !s.versions.length).map((s) => s.id)));
  };

  const selectAll = () => {
    clearQuote();
    setSelected(new Set(shots.map((s) => s.id)));
  };

  const clearSelection = () => {
    clearQuote();
    setSelected(new Set());
  };

  const runEstimate = async () => {
    if (!selected.size) return;
    setBusy("estimate");
    setError(null);
    setMessage(null);
    try {
      const res = await api.imageEstimate(slug, {
        shot_ids: [...selected],
        reserve_usd: reserve,
        scope: "stills",
        regenerate,
      });
      if (res.error || !res.estimate || !res.decision) {
        setEstimate(null);
        setDecision(null);
        setError(res.error || "estimate failed");
      } else {
        setEstimate(res.estimate);
        setDecision(res.decision);
        if (res.budget) setBudget(res.budget);
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(null);
    }
  };

  const generate = async () => {
    if (!estimate) return;
    setBusy("generate");
    setError(null);
    setMessage(null);
    try {
      const res = await api.generateImages(slug, {
        quote_id: estimate.quote_id,
        note: note.trim(),
        uploads_confirmed: uploadsConfirmed,
      });
      if (res.error) {
        setError(res.error);
      } else if (res.needs_budget) {
        const suggested = res.decision?.suggested_usd;
        setError(
          `The cap does not cover this batch${suggested ? `; add $${suggested} to continue` : ""}.`,
        );
      } else {
        setMessage(`Queued ${res.tasks} stills, $${res.reserve_usd} reserved.`);
        setEstimate(null);
        setDecision(null);
        if (res.budget) setBudget(res.budget);
        setTimeout(load, 2500);
      }
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
      {message && <p className="message">{message}</p>}

      <div className="card">
        <h3>Budget</h3>
        <div className="pre">
          cap {budget?.cap_usd ?? "—"} · committed {budget?.committed_usd ?? "—"} · remaining{" "}
          {budget?.remaining_usd ?? "—"}
        </div>
      </div>

      <ApprovalBar slug={slug} stages={["proof"]} refresh={revision} />

      <div className="card">
        <h3>Generate ({selected.size} selected)</h3>
        <div className="toolbar">
          <button onClick={selectMissing}>Select missing</button>
          <button onClick={selectAll}>Select all</button>
          <button onClick={clearSelection} disabled={!selected.size}>
            Clear
          </button>
          <label className="inline">
            reserve / shot $
            <input
              type="number"
              min="0.01"
              step="0.01"
              value={reserve}
              onChange={(e) => {
                clearQuote();
                setReserve(e.target.value);
              }}
            />
          </label>
          <label className="inline">
            <input
              type="checkbox"
              checked={regenerate}
              onChange={(e) => {
                clearQuote();
                setRegenerate(e.target.checked);
              }}
            />
            regenerate unchanged
          </label>
          <button onClick={runEstimate} disabled={!selected.size || busy !== null}>
            {busy === "estimate" ? "Quoting…" : "Estimate"}
          </button>
        </div>

        {estimate && decision && (
          <div className="quote">
            <div className="pre">
              {estimate.tasks} new still{estimate.tasks === 1 ? "" : "s"} · $
              {estimate.reserve_usd} reserved
              {decision.ok
                ? ` · fits the cap (remaining $${decision.remaining ?? "—"})`
                : ` · needs $${decision.suggested_usd ?? "more"} more`}
            </div>
            {estimate.uploads_required && (
              <label className="inline">
                <input
                  type="checkbox"
                  checked={uploadsConfirmed}
                  onChange={(e) => setUploadsConfirmed(e.target.checked)}
                />
                reference images may be uploaded to the provider
              </label>
            )}
            <input
              className="note"
              value={note}
              onChange={(e) => setNote(e.target.value)}
              placeholder="note for the spending record (optional)"
            />
            <button
              onClick={generate}
              disabled={
                !decision.ok ||
                busy !== null ||
                (estimate.uploads_required && !uploadsConfirmed)
              }
            >
              {busy === "generate" ? "Authorizing…" : `Generate ${estimate.tasks} stills`}
            </button>
          </div>
        )}
      </div>

      {shots.length ? (
        shots.map((s) => (
          <div className="card" key={s.id}>
            <h3>
              <label className="inline">
                <input
                  type="checkbox"
                  checked={selected.has(s.id)}
                  onChange={() => toggle(s.id)}
                />
                {s.id}
              </label>{" "}
              · {s.versions.length} version{s.versions.length === 1 ? "" : "s"}
            </h3>
            <div className="versions">
              {s.versions.length ? (
                s.versions.map((v) => (
                  <figure
                    key={v.version}
                    className={v.version === s.selected ? "version selected" : "version"}
                  >
                    <img
                      src={`/api/projects/${slug}/images/${encodeURIComponent(s.owner)}/${v.version}`}
                      alt={`${s.id} version ${v.version}`}
                      loading="lazy"
                      onClick={() => selectVersion(slug, s.id, v.version, load, setError)}
                    />
                    <figcaption>
                      <button
                        className={v.version === s.selected ? "active" : ""}
                        onClick={() => selectVersion(slug, s.id, v.version, load, setError)}
                        disabled={v.version === s.selected}
                      >
                        v{v.version}
                        {v.version === s.selected ? " selected" : ""}
                      </button>
                      <span className="meta">{v.path.split("/").slice(-1)[0]}</span>
                    </figcaption>
                  </figure>
                ))
              ) : (
                "No versions yet."
              )}
            </div>
          </div>
        ))
      ) : (
        <p className="empty">No storyboard or assets yet.</p>
      )}
    </>
  );
}

async function selectVersion(
  slug: string,
  shotId: string,
  version: number,
  reload: () => void,
  setError: (value: string | null) => void,
) {
  setError(null);
  try {
    await api.selectImage(slug, shotId, version);
    reload();
  } catch (e) {
    setError(String(e));
  }
}
