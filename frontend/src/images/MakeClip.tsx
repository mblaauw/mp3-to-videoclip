import { useEffect, useState } from "react";
import { api, type ClipEstimate, type ClipModel, type ClipOptions, type ImageShot } from "../api";
import { Button } from "../ui";
import { modelWords, nearestLength, priceWords } from "./clipWords";

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

  return (
    <div className="make-clip">
      <div className="make-clip-choices">
        <label className="ui-field">
          <span>Model</span>
          <select
            aria-label="Clip model"
            value={model}
            disabled={busy}
            onChange={(event) => setModel(event.target.value)}
          >
            {models.map((item) => (
              <option key={item.id} value={item.id}>
                {modelWords(item)}
                {item.chosen ? " (Settings' choice)" : ""}
              </option>
            ))}
          </select>
          {picked?.price_note && <small>{picked.price_note}</small>}
        </label>
        {options && (
          <>
            {options.durations.length > 0 && (
              <div className="ui-field" role="radiogroup" aria-label="Clip length">
                <span>Length</span>
                <span className="chips">
                  {options.durations.map((value) => (
                    <button
                      type="button"
                      role="radio"
                      key={value}
                      className={`ui-chip ${seconds === value ? "on" : ""}`}
                      aria-checked={seconds === value}
                      onClick={() => {
                        setSeconds(value);
                        changed();
                      }}
                    >
                      {value} s
                    </button>
                  ))}
                </span>
              </div>
            )}
            {options.resolutions.length > 0 && (
              <div className="ui-field" role="radiogroup" aria-label="Clip size">
                <span>Size</span>
                <span className="chips">
                  {options.resolutions.map((value) => (
                    <button
                      type="button"
                      role="radio"
                      key={value}
                      className={`ui-chip ${resolution === value ? "on" : ""}`}
                      aria-checked={resolution === value}
                      onClick={() => {
                        setResolution(value);
                        changed();
                      }}
                    >
                      {value}
                    </button>
                  ))}
                </span>
              </div>
            )}
            {options.audio && (
              <label className="ui-field make-clip-switch">
                <span>Its own sound</span>
                <span>
                  <input
                    type="checkbox"
                    checked={audio}
                    onChange={(event) => {
                      setAudio(event.target.checked);
                      changed();
                    }}
                  />{" "}
                  <small>The model makes sound for the clip, at a higher rate. The film's own sound plays either way.</small>
                </span>
              </label>
            )}
            {!options.live && <p className="ui-state error compact">This model is not confirmed live.</p>}
          </>
        )}
        <label className="ui-field make-clip-prompt">
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
      <div className="make-clip-actions">
        {quote ? (
          <>
            <Button
              size="small"
              variant="primary"
              disabled={busy || disabled}
              onClick={() =>
                void run(async () => {
                  const started = await api.generateClips(slug, quote.quote_id);
                  if (started.needs_budget) throw new Error("The budget has no room for this.");
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
            {quote.warning && <small className="hint">{quote.warning}</small>}
          </>
        ) : (
          <Button
            size="small"
            disabled={busy || disabled || !model || !options}
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
      </div>
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
              {clip.current ? "" : ", made from another still. Select that still to use it."}
            </span>
            {inUse ? (
              <Button size="small" disabled={busy} onClick={() => use(null)}>
                Use the still
              </Button>
            ) : (
              <Button
                size="small"
                disabled={busy || !clip.current}
                onClick={() => use(clip.version)}
              >
                Use this clip
              </Button>
            )}
          </div>
        );
      })}
      {error && <p className="ui-state error compact" role="alert">{error}</p>}
    </div>
  );
}
