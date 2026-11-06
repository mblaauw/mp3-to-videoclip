import { useEffect, useState } from "react";
import { api, type ClipEstimate, type ClipModel, type ClipOptions, type ImageShot, type Job } from "../api";
import { useProjectJobs } from "../jobs/store";
import { Button } from "../ui";
import { clock, noteClipJob, progressShare, readClipJobs, type ClipJobNote } from "./clipJobs";
import { nearestLength, priceWords } from "./clipWords";

function pricePill(model: ClipModel | undefined): string | null {
  if (!model?.price) return null;
  return `from $${model.price.amount} ${model.price.unit === "clip" ? "per clip" : "per second"}`;
}

/** The clip being made: a ring that fills over the provider's usual time, and plain words. */
function ClipProgress({ job, note }: { job: Job; note: ClipJobNote | null }) {
  const [now, setNow] = useState(() => Date.now() / 1000);
  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now() / 1000), 1000);
    return () => window.clearInterval(timer);
  }, []);
  const since = job.started_at ?? note?.since ?? job.queued_at ?? now;
  const elapsed = Math.max(0, now - since);
  const typical = note?.typical ?? null;
  const share = job.status === "queued" ? 0 : progressShare(elapsed, typical);
  const radius = 22;
  const round = 2 * Math.PI * radius;
  const late = typical !== null && elapsed > typical;
  const words =
    job.status === "queued"
      ? "Waiting for the film's other work to finish."
      : typical === null
        ? `${clock(elapsed)} so far. The provider gives no usual time for this model.`
        : late
          ? `${clock(elapsed)}, longer than its usual ${clock(typical)}. A slow clip stays in the journal and is collected when it lands.`
          : `${clock(elapsed)} of about ${clock(typical)}, by the provider's own example runs.`;
  return (
    <div className="clip-progress" role="status" aria-live="polite">
      <svg className={`clip-ring ${share === null ? "spinning" : ""}`} viewBox="0 0 56 56" aria-hidden="true">
        <circle className="clip-ring-track" cx="28" cy="28" r={radius} />
        <circle
          className="clip-ring-fill"
          cx="28"
          cy="28"
          r={radius}
          strokeDasharray={round}
          strokeDashoffset={share === null ? round * 0.75 : round * (1 - share)}
        />
      </svg>
      <div className="clip-progress-copy">
        <b>Making the clip{note?.model ? ` with ${note.model}` : ""}</b>
        <span>{words}</span>
        {job.progress?.message && <small>{job.progress.message}</small>}
      </div>
    </div>
  );
}

/** A short moving version of the selected still: the model, its choices, the price, the purchase. */
export function MakeClip({
  slug,
  shot,
  disabled,
  onChanged,
}: {
  slug: string;
  shot: ImageShot;
  disabled: boolean;
  onChanged: () => void;
}) {
  const [models, setModels] = useState<ClipModel[]>([]);
  const [model, setModel] = useState<string>("");
  const [options, setOptions] = useState<ClipOptions | null>(null);
  const [seconds, setSeconds] = useState<number | null>(null);
  const [resolution, setResolution] = useState<string>("");
  const [audio, setAudio] = useState(false);
  const [prompt, setPrompt] = useState(shot.motion_prompt ?? "");
  const [quote, setQuote] = useState<ClipEstimate | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const clipJobs = useProjectJobs(slug, "clip");
  const notes = readClipJobs();
  const mine = clipJobs.find((job) => notes[job.id]?.shot === shot.id) ?? null;
  const elsewhere = !mine && clipJobs.length > 0;

  useEffect(() => setPrompt(shot.motion_prompt ?? ""), [shot.id, shot.motion_prompt]);
  useEffect(() => {
    api
      .clipModels(slug)
      .then((value) => {
        setModels(value.models);
        setModel((current) => current || value.models.find((item) => item.chosen)?.id || value.models[0]?.id || "");
      })
      .catch((caught) => setError(String(caught)));
  }, [slug]);
  useEffect(() => {
    if (!model) return;
    setOptions(null);
    setQuote(null);
    api
      .clipOptions(slug, model)
      .then((value) => {
        setOptions(value);
        setSeconds(nearestLength(value.durations, 5));
        setResolution(value.resolutions[0] ?? "");
        setAudio(false);
        setError(null);
      })
      .catch((caught) => setError(String(caught)));
  }, [slug, model]);
  // When the clip lands, the still's data changes; ask the stage to read it again.
  const jobCount = clipJobs.length;
  useEffect(() => {
    if (jobCount === 0) onChanged();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobCount]);

  const run = async (step: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await step();
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  };
  const use = (version: number | null) =>
    void run(async () => {
      await api.selectClip(slug, shot.id, version);
      onChanged();
    });
  const picked = models.find((item) => item.id === model);
  const changed = () => setQuote(null);
  const typical = quote?.typical_seconds ?? options?.typical_seconds ?? null;

  return (
    <section className="clip-maker" aria-label="Make a clip">
      <header className="clip-maker-head">
        <div>
          <b>Make a clip</b>
          <span>A short moving version of this still, from the model you choose.</span>
        </div>
        {pricePill(picked) && <span className="clip-price-pill">{pricePill(picked)}</span>}
      </header>

      {mine ? (
        <ClipProgress job={mine} note={notes[mine.id] ?? null} />
      ) : (
        <>
          {elsewhere && (
            <p className="hint clip-maker-note">A clip is being made elsewhere in this film; this still can be priced when it lands.</p>
          )}
          <div className="clip-maker-grid">
            <label className="clip-field clip-field-model">
              <span>Model</span>
              <select aria-label="Clip model" value={model} disabled={busy} onChange={(event) => setModel(event.target.value)}>
                {models.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.label}
                    {item.chosen ? " · Settings' choice" : ""}
                  </option>
                ))}
              </select>
              {picked?.price_note && <small>{picked.price_note}</small>}
            </label>
            {options && options.durations.length > 0 && (
              <div className="clip-field" role="radiogroup" aria-label="Clip length">
                <span>Length</span>
                <div className="clip-seg">
                  {options.durations.map((value) => (
                    <button
                      type="button"
                      role="radio"
                      key={value}
                      aria-checked={seconds === value}
                      onClick={() => {
                        setSeconds(value);
                        changed();
                      }}
                    >
                      {value} s
                    </button>
                  ))}
                </div>
              </div>
            )}
            {options && options.resolutions.length > 0 && (
              <div className="clip-field" role="radiogroup" aria-label="Clip size">
                <span>Size</span>
                <div className="clip-seg">
                  {options.resolutions.map((value) => (
                    <button
                      type="button"
                      role="radio"
                      key={value}
                      aria-checked={resolution === value}
                      onClick={() => {
                        setResolution(value);
                        changed();
                      }}
                    >
                      {value}
                    </button>
                  ))}
                </div>
              </div>
            )}
            {options?.audio && (
              <label className="clip-field">
                <span>Sound</span>
                <span className="clip-switch">
                  <input
                    type="checkbox"
                    aria-label="Its own sound"
                    checked={audio}
                    onChange={(event) => {
                      setAudio(event.target.checked);
                      changed();
                    }}
                  />
                  <small>{audio ? "The model's own sound, at a higher rate." : "Silent. The film's own sound plays either way."}</small>
                </span>
              </label>
            )}
            {options && !options.live && <p className="ui-state error compact">This model is not confirmed live.</p>}
            <label className="clip-field clip-field-prompt">
              <span>What moves</span>
              <textarea
                aria-label="Motion prompt"
                rows={2}
                maxLength={2000}
                value={prompt}
                placeholder={shot.motion_prompt || "The camera, the air, what shifts in the frame. The still is the picture."}
                onChange={(event) => {
                  setPrompt(event.target.value);
                  changed();
                }}
              />
              {shot.motion_why && <small>The Writer suggests motion: {shot.motion_why}</small>}
            </label>
          </div>
          <footer className="clip-maker-foot">
            {quote ? (
              <>
                <Button
                  size="small"
                  variant="primary"
                  disabled={busy || disabled || elsewhere}
                  onClick={() =>
                    void run(async () => {
                      const started = await api.generateClips(slug, quote.quote_id);
                      if (started.needs_budget) throw new Error("The budget has no room for this.");
                      if (started.job_id) {
                        noteClipJob(started.job_id, {
                          shot: shot.id,
                          model: picked?.label ?? quote.model,
                          typical: quote.typical_seconds,
                          since: Date.now() / 1000,
                        });
                      }
                      setQuote(null);
                      onChanged();
                    })
                  }
                >
                  {priceWords(quote)}
                </Button>
                <Button size="small" variant="quiet" disabled={busy} onClick={() => setQuote(null)}>
                  Not now
                </Button>
              </>
            ) : (
              <Button
                size="small"
                disabled={busy || disabled || elsewhere || !model || !options}
                onClick={() =>
                  void run(async () => {
                    const { estimate } = await api.estimateClips(slug, [shot.id], {
                      model,
                      seconds: seconds ?? undefined,
                      resolution: resolution || undefined,
                      audio: options?.audio ? audio : undefined,
                      prompt: prompt.trim() && prompt.trim() !== (shot.motion_prompt ?? "").trim() ? prompt.trim() : undefined,
                    });
                    setQuote(estimate);
                  })
                }
              >
                {busy ? "Working it out…" : "Price a clip"}
              </Button>
            )}
            <small className="hint">
              {quote?.warning
                ? quote.warning
                : typical !== null
                  ? `About ${clock(typical)} to make, by the provider's own example runs.`
                  : "The price is read before anything is bought."}
            </small>
          </footer>
        </>
      )}

      {(shot.clips ?? []).length > 0 && (
        <div className="clip-cards">
          {(shot.clips ?? []).map((clip) => {
            const inUse = shot.clip === clip.version;
            return (
              <div className={`clip-card ${inUse ? "on" : ""}`} key={clip.version}>
                <video
                  src={`/api/projects/${slug}/clips/${encodeURIComponent(shot.owner)}/${clip.version}`}
                  controls
                  muted
                  preload="metadata"
                />
                <span className="hint">
                  v{clip.version} · {clip.seconds.toFixed(1)} s · {clip.model}
                  {inUse ? " · in the film" : ""}
                  {clip.current ? "" : ", made from another still. Select that still to use it."}
                </span>
                {inUse ? (
                  <Button size="small" disabled={busy} onClick={() => use(null)}>
                    Use the still
                  </Button>
                ) : (
                  <Button size="small" disabled={busy || !clip.current} onClick={() => use(clip.version)}>
                    Use this clip
                  </Button>
                )}
              </div>
            );
          })}
        </div>
      )}
      {error && <p className="ui-state error compact" role="alert">{error}</p>}
    </section>
  );
}
