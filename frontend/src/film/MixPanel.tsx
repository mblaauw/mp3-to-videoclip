import { useState } from "react";
import { api, type MixSpec, type ScriptPayload } from "../api";
import { notifyProjectChanged } from "../shell/projectEvents";

function Decibels({
  label,
  value,
  low,
  high,
  disabled,
  onCommit,
}: {
  label: string;
  value: number;
  low: number;
  high: number;
  disabled: boolean;
  onCommit: (value: number) => void;
}) {
  return (
    <label className="mix-number">
      {label}
      <input
        key={value}
        type="number"
        step={1}
        min={low}
        max={high}
        defaultValue={value}
        disabled={disabled}
        onBlur={(event) => {
          const next = Number(event.target.value);
          if (next !== value && next >= low && next <= high) onCommit(next);
        }}
      />
    </label>
  );
}

function measured(payload: ScriptPayload): string {
  const receipt = payload.soundtrack.receipt;
  if (!payload.soundtrack.built) return "Changed since the last build. Build it to hear this.";
  if (receipt?.output_lufs == null) return "Built. All silence so far, so nothing to measure.";
  const peak = receipt.output_true_peak_db;
  return `${receipt.output_lufs.toFixed(1)} LUFS measured${
    peak == null ? "" : `, true peak ${peak.toFixed(1)} dB`
  }`;
}

/** A story film's sound under the voice: the bed, its ducking and the fades. */
export function MixPanel({ slug, payload }: { slug: string; payload: ScriptPayload }) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const mix: MixSpec = payload.soundtrack.mix ?? {};
  const run = (work: () => Promise<unknown>) => {
    setBusy(true);
    setError(null);
    work()
      .then(() => notifyProjectChanged())
      .catch((caught) => setError(caught instanceof Error ? caught.message : String(caught)))
      .finally(() => setBusy(false));
  };
  const bed = mix.bed;
  return (
    <div className="mix-panel">
      <h3>The mix</h3>
      <p className="hint">{measured(payload)}</p>
      <div className="mix-row">
        {bed ? (
          <>
            <Decibels
              label="Bed dB"
              value={bed.gain_db}
              low={-60}
              high={0}
              disabled={busy}
              onCommit={(gain_db) => run(() => api.setMix(slug, { bed: { ...bed, gain_db } }))}
            />
            <Decibels
              label="Under the voice dB"
              value={bed.duck_db}
              low={-40}
              high={0}
              disabled={busy}
              onCommit={(duck_db) => run(() => api.setMix(slug, { bed: { ...bed, duck_db } }))}
            />
          </>
        ) : (
          <span className="hint">No bed.</span>
        )}
        <label className="mix-file">
          {bed ? "Replace the bed" : "Add a bed"}
          <input
            type="file"
            accept="audio/*"
            disabled={busy}
            onChange={(event) => {
              const file = event.target.files?.[0];
              event.target.value = "";
              if (!file) return;
              run(async () => {
                const { path } = await api.addSound(slug, file);
                await api.setMix(slug, {
                  bed: { path, gain_db: bed?.gain_db ?? -14, duck_db: bed?.duck_db ?? -10 },
                });
              });
            }}
          />
        </label>
      </div>
      <div className="mix-row">
        <Decibels
          label="Fade in s"
          value={mix.fade_in ?? 0}
          low={0}
          high={30}
          disabled={busy}
          onCommit={(fade_in) => run(() => api.setMix(slug, { fade_in }))}
        />
        <Decibels
          label="Fade out s"
          value={mix.fade_out ?? 0}
          low={0}
          high={30}
          disabled={busy}
          onCommit={(fade_out) => run(() => api.setMix(slug, { fade_out }))}
        />
        <button type="button" className="ui-button small" disabled={busy} onClick={() => run(() => api.buildSoundtrack(slug))}>
          {busy ? "Working…" : "Build the mix"}
        </button>
      </div>
      {mix.ambience?.length ? (
        <p className="hint">{mix.ambience.length} ambience spans under the lines.</p>
      ) : null}
      {error && <p className="ui-state error compact" role="alert">{error}</p>}
    </div>
  );
}
