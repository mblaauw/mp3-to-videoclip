import { useCallback, useEffect, useState } from "react";
import { api, type NarrationFacts, type NarrationPrice } from "../api";
import { useProjectChanged } from "../shell/projectEvents";
import { priceWords } from "../shell/settings/settingsModel";
import { Buy } from "../script/Buy";
import { ErrorState } from "../ui";

function rate(price: NarrationPrice): string {
  if (!price) return "Price unknown";
  return priceWords({
    id: "",
    provider: "",
    label: "",
    capabilities: [],
    price: { amount: price.amount, unit: price.unit },
    price_note: "",
    price_checked: price.checked,
    recommended: [],
    source: "static",
  });
}

function money(value: string | null): string {
  if (value === null) return "a price the catalogue does not state";
  const amount = Number(value);
  return amount < 0.01 ? "under a cent" : `about $${amount.toFixed(2)}`;
}

/** Who speaks, with what, at what price, and where the words fall. */
export function NarrationCard({ slug }: { slug: string }) {
  const [facts, setFacts] = useState<NarrationFacts | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const load = useCallback(() => {
    api.narration(slug).then(setFacts, (caught) => setError(String(caught)));
  }, [slug]);
  useEffect(load, [load]);
  useProjectChanged(slug, load);

  if (error && !facts) {
    return (
      <section className="stage-block narration-card">
        <h2>Narration</h2>
        <ErrorState what="reading the narration" error={error} compact />
      </section>
    );
  }
  if (!facts) return null;

  const chosen = facts.voices.find((voice) => voice.id === facts.voice);
  const providers = [...new Set(facts.voices.map((voice) => voice.provider_label))];
  const change = async (voice: string, model?: string) => {
    setBusy(true);
    setError(null);
    try {
      await api.chooseVoice(slug, voice, model);
      load();
    } catch (caught) {
      setError(String(caught));
    } finally {
      setBusy(false);
    }
  };
  const script = facts.script;

  return (
    <section className="stage-block narration-card">
      <h2>
        Narration{" "}
        <small>
          {chosen?.label ?? facts.voice} · {facts.model_label} · {rate(facts.price)}
        </small>
      </h2>
      {facts.persona && <p className="hint narration-persona">{facts.persona}</p>}
      <div className="narration-fields">
        <label className="panel-field">
          <span>Voice</span>
          <select
            aria-label="Narrator"
            value={facts.voice}
            disabled={busy}
            onChange={(event) => void change(event.target.value)}
          >
            {providers.map((label) => (
              <optgroup key={label} label={label}>
                {facts.voices
                  .filter((voice) => voice.provider_label === label)
                  .map((voice) => (
                    <option key={voice.id} value={voice.id}>
                      {voice.label}
                      {voice.price ? ` · $${voice.price.amount} per 1,000 characters` : ""}
                    </option>
                  ))}
              </optgroup>
            ))}
            {!chosen && <option value={facts.voice}>{facts.voice}</option>}
          </select>
        </label>
        {facts.provider === "elevenlabs" && (
          <label className="panel-field">
            <span>Spoken with</span>
            <select
              aria-label="Narration model"
              value={facts.model}
              disabled={busy}
              onChange={(event) => void change(facts.voice, event.target.value)}
            >
              {facts.elevenlabs_models.map((model) => (
                <option key={model.id} value={model.id}>
                  {model.label}
                  {model.price ? ` · $${model.price.amount} per 1,000 characters` : ""}
                </option>
              ))}
              {!facts.elevenlabs_models.some((model) => model.id === facts.model) && (
                <option value={facts.model}>{facts.model}</option>
              )}
            </select>
          </label>
        )}
        <div className="panel-field">
          <span>Hear it</span>
          {chosen?.preview_url ? (
            <audio controls preload="none" src={chosen.preview_url} aria-label="The provider's free sample" />
          ) : script.first_line ? (
            <span className="narration-hear">
              <Buy slug={slug} label="Hear line 1" lineIds={[script.first_line]} regenerate />
              <small>No free sample from this provider; the first line is a take through the journal.</small>
            </span>
          ) : (
            <small>No free sample from this provider. Hear it on Script once there are lines.</small>
          )}
        </div>
      </div>
      <p className="hint">
        {script.lines
          ? `${script.lines} lines, ${script.characters.toLocaleString()} characters: ${money(script.cost_usd)} to record at the catalogue rate. ${script.recorded} recorded. A film keeps the voice and model it locked, however Settings change.`
          : "No lines yet. The script decides what recording costs: characters at the catalogue rate."}
      </p>
      {script.beats.length > 0 && (
        <ol className="narration-beats">
          {script.beats.map((beat) => (
            <li key={beat.id}>
              <b>{beat.label}</b>
              <span>
                {beat.lines ? `${beat.lines} line${beat.lines === 1 ? "" : "s"}` : "no lines"}
                {beat.lines ? `, ${beat.recorded} recorded` : ""}
              </span>
            </li>
          ))}
        </ol>
      )}
      {error && <ErrorState what="changing the voice" error={error} compact />}
    </section>
  );
}
