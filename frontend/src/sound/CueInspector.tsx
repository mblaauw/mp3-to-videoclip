import { useEffect, useRef, useState, type ReactNode } from "react";
import { api, type SoundPayload } from "../api";
import { OPEN_BUDGET } from "../api/errorAction";
import { ApiError, errorAction } from "../api/errors";
import { notifyProjectChanged } from "../shell/projectEvents";
import { Button, ErrorState } from "../ui";
import { CloseIcon, PauseIcon, PlayIcon } from "../ui/icons";
import {
  anchorKind,
  anchorOf,
  anchorSeconds,
  chosen,
  clockTenths,
  dbWords,
  describeAnchor,
  dollars,
  fitWords,
  isMoment,
  KIND_LABEL,
  placesWords,
  playsMode,
  withPlays,
  type AnchorKind,
  type Cue,
  type CueAnchor,
  type CueKind,
  type PlaysMode,
} from "./cueBands";
import type { Pick } from "./SoundMap";

type Audition = { playing: string | null; toggle: (key: string, url: string) => void };

export const soundUrl = (slug: string, cue: string, version: number) => `/api/projects/${slug}/sound/${cue}/${version}`;

function Segmented<T extends string>({
  label,
  value,
  options,
  onChange,
}: {
  label: string;
  value: T;
  options: { id: T; label: string }[];
  onChange: (next: T) => void;
}) {
  return (
    <div className="sound-seg" role="radiogroup" aria-label={label}>
      {options.map((option) => (
        <button type="button" role="radio" key={option.id} aria-checked={value === option.id} onClick={() => onChange(option.id)}>
          {option.label}
        </button>
      ))}
    </div>
  );
}

function Section({ title, children, aside }: { title: string; children: ReactNode; aside?: ReactNode }) {
  return (
    <section className="insp-section">
      <div className="insp-section-head">
        <h4>{title}</h4>
        {aside}
      </div>
      {children}
    </section>
  );
}

export function PlayButton({ playing, label, onClick }: { playing: boolean; label: string; onClick: () => void }) {
  return (
    <button type="button" className={`sound-play ${playing ? "playing" : ""}`} aria-label={playing ? `Stop ${label}` : `Play ${label}`} aria-pressed={playing} onClick={onClick}>
      {playing ? <PauseIcon size={14} /> : <PlayIcon size={14} />}
    </button>
  );
}

type Problem = { message: string; code?: string; fault: boolean };

function problemOf(caught: unknown): Problem {
  if (caught instanceof ApiError) return { message: caught.message, code: caught.code, fault: caught.status >= 500 };
  return { message: caught instanceof Error ? caught.message : String(caught), fault: true };
}

/** A refusal is a sentence with its one way out; only a fault is "something went wrong". */
function MakeProblem({ problem, what }: { problem: Problem; what: string }) {
  if (problem.fault) return <ErrorState what={what} error={problem.message} compact />;
  const action = errorAction(problem.code);
  return (
    <p className="ui-state error compact sound-refusal" role="alert">
      {problem.message}
      {action && "budget" in action && (
        <Button size="small" variant="quiet" onClick={() => window.dispatchEvent(new Event(OPEN_BUDGET))}>
          {action.label}
        </Button>
      )}
    </p>
  );
}

/** Two clicks: first the price, then the purchase. `blocked` says why it cannot be priced yet. */
export function Make({ slug, cueIds, label, variant = "default", blocked, prepare }: { slug: string; cueIds: string[]; label: string; variant?: "default" | "primary" | "quiet"; blocked?: string; prepare?: () => Promise<void> }) {
  const [quote, setQuote] = useState<{ id: string; price: string; count: number; model: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<Problem | null>(null);
  const run = async (step: () => Promise<void>) => {
    setBusy(true);
    setProblem(null);
    try {
      await step();
    } catch (caught) {
      setProblem(problemOf(caught));
    } finally {
      setBusy(false);
    }
  };
  if (quote) {
    return (
      <span className="sound-make quoted">
        <span className="sound-make-buttons">
          <Button
            size="small"
            variant="primary"
            disabled={busy}
            onClick={() =>
              void run(async () => {
                const started = await api.generateSound(slug, quote.id);
                if (started.needs_budget) throw new Error("The budget has no room for this.");
                setQuote(null);
                notifyProjectChanged({ slug });
              })
            }
          >
            Make {quote.count} · {dollars(quote.price)}
          </Button>
          <Button size="small" variant="quiet" disabled={busy} onClick={() => setQuote(null)}>
            Not now
          </Button>
        </span>
        <span className="hint">with {quote.model}</span>
        {problem && <MakeProblem problem={problem} what="making the sound" />}
      </span>
    );
  }
  return (
    <span className="sound-make">
      <Button
        size="small"
        variant={variant}
        disabled={busy || cueIds.length === 0 || Boolean(blocked)}
        title={blocked}
        onClick={() =>
          void run(async () => {
            // The price is of the saved cues: words typed a moment ago are saved first.
            await prepare?.();
            const made = await api.estimateSound(slug, cueIds);
            setQuote({ id: made.quote_id, price: made.reserve_usd, count: made.tasks.length, model: made.model_label || made.model });
          })
        }
      >
        {busy ? "Working out the price…" : label}
      </Button>
      {blocked && <span className="hint">{blocked}</span>}
      {problem && <MakeProblem problem={problem} what="pricing the sound" />}
    </span>
  );
}

/** A start, an end or a moment: a time, a shot's cut, or on a story film a line or a beat. */
function AnchorField({
  label,
  value,
  data,
  atEnd,
  pick,
  onChange,
}: {
  label: string;
  value: CueAnchor;
  data: SoundPayload;
  atEnd: boolean;
  pick: Pick | null;
  onChange: (next: CueAnchor) => void;
}) {
  const kind = anchorKind(value);
  const kinds: { id: AnchorKind; label: string }[] = [
    { id: "frame", label: "Time" },
    ...(data.shots.length ? [{ id: "shot" as const, label: "Shot's cut" }] : []),
    ...(data.story_film && data.lines.length ? [{ id: "line" as const, label: "Line" }] : []),
    ...(data.story_film && data.beats.length ? [{ id: "beat" as const, label: "Beat" }] : []),
  ];
  const current =
    kind === "shot" && "shot" in value
      ? value.shot
      : kind === "line" && "line" in value
        ? value.line
        : kind === "beat" && "beat" in value
          ? value.beat
          : "frame" in value && value.frame >= 0
            ? String(Number((value.frame / data.fps).toFixed(2)))
            : "";
  const first = (next: AnchorKind): string =>
    next === "shot" ? (data.shots[0]?.id ?? "") : next === "line" ? (data.lines[0]?.id ?? "") : next === "beat" ? (data.beats[0]?.id ?? "") : "";
  const picked: CueAnchor | null = pick?.kind === "shot" ? { shot: pick.id } : pick ? { frame: Math.round(pick.seconds * data.fps) } : null;
  const same = picked !== null && JSON.stringify(picked) === JSON.stringify(value);
  return (
    <div className="insp-anchor">
      <span className="insp-anchor-label">{label}</span>
      <select
        aria-label={`${label} kind`}
        value={kind}
        onChange={(event) => {
          const next = event.target.value as AnchorKind;
          onChange(anchorOf(next, first(next), data.fps, atEnd));
        }}
      >
        {kinds.map((item) => (
          <option key={item.id} value={item.id}>
            {item.label}
          </option>
        ))}
      </select>
      {kind === "frame" ? (
        <span className="insp-seconds">
          <input
            type="number"
            min="0"
            step="0.1"
            aria-label={`${label} seconds`}
            placeholder={atEnd ? "the end" : "0"}
            value={current}
            onChange={(event) => onChange(anchorOf("frame", event.target.value, data.fps, atEnd))}
          />
          <span aria-hidden="true">s</span>
        </span>
      ) : (
        <select
          aria-label={`${label} ${kind}`}
          value={current}
          onChange={(event) => onChange(anchorOf(kind, event.target.value, data.fps, atEnd))}
        >
          {(kind === "shot" ? data.shots : kind === "line" ? data.lines : data.beats).map((item) => (
            <option key={item.id} value={item.id}>
              {item.id} · {clockTenths(item.start)}
            </option>
          ))}
        </select>
      )}
      {picked && !same && (
        <button type="button" className="insp-use-pick" onClick={() => onChange(picked)}>
          Use {pick?.kind === "shot" ? `the cut of ${pick.id}` : clockTenths(pick?.seconds ?? 0)}
        </button>
      )}
    </div>
  );
}

function Level({
  label,
  hint,
  value,
  min,
  max,
  onChange,
}: {
  label: string;
  hint: string;
  value: number;
  min: number;
  max: number;
  onChange: (next: number) => void;
}) {
  return (
    <label className="insp-level">
      <span className="insp-level-head">
        <span>{label}</span>
        <output>{dbWords(value)}</output>
      </span>
      <input type="range" min={min} max={max} step="1" value={value} aria-label={label} onChange={(event) => onChange(Number(event.target.value))} />
      <small>{hint}</small>
    </label>
  );
}

/** One cue, all of it: what it sounds like, where, how loud, and the sounds made for it. */
export function CueInspector({
  slug,
  cue,
  data,
  pick,
  notes,
  audition,
  onEdit,
  onRemove,
  onData,
  onHear,
  onClose,
  onSaveNow,
}: {
  slug: string;
  cue: Cue;
  data: SoundPayload;
  pick: Pick | null;
  notes: string[];
  audition: Audition;
  onEdit: (next: Cue) => void;
  onRemove: () => void;
  onData: (data: SoundPayload) => void;
  onHear: (seconds: number) => void;
  onClose: () => void;
  onSaveNow: () => Promise<void>;
}) {
  const file = useRef<HTMLInputElement>(null);
  const describe = useRef<HTMLTextAreaElement>(null);
  // The words stay as typed; the saved cue trims them, and a save must not move the caret.
  const [words, setWords] = useState(cue.prompt);
  const [removing, setRemoving] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  useEffect(() => {
    setWords(cue.prompt);
    setRemoving(false);
    setProblem(null);
    if (!cue.prompt) describe.current?.focus();
    // Only a different cue resets the words; a save of this one leaves them alone.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cue.id]);
  const playing = chosen(cue);
  const moment = isMoment(cue);
  const mode = playsMode(cue);
  const musicModels = data.models.filter((model) => model.for === "music");
  const modelLabel = (id: string | null | undefined) => data.models.find((model) => model.id === id)?.label ?? id ?? "";
  const madeWith =
    data.models.find((model) => model.id === cue.model)?.label ??
    data.models.find((model) => model.chosen && model.for === (cue.kind === "music" ? "music" : "effects"))?.label ??
    "Settings' model";
  const where = { fps: data.fps, duration: data.duration, shots: data.shots, lines: data.lines, beats: data.beats };
  const change = (patch: Partial<Cue>) => {
    const next = { ...cue, ...patch };
    if (patch.start || patch.end) {
      next.start_seconds = anchorSeconds(next.start, where, false);
      next.end_seconds = anchorSeconds(next.end, where, true);
    }
    onEdit(next);
  };
  const call = (step: Promise<SoundPayload>) =>
    void step.then(onData).catch((caught) => setProblem(caught instanceof Error ? caught.message : String(caught)));
  const fit = fitWords(cue);
  const startAt = cue.start_seconds ?? 0;
  return (
    <aside className={`cue-inspector ${cue.kind}`} aria-label={`Cue ${cue.id}`}>
      <header className="insp-head">
        <span className="insp-swatch" aria-hidden="true" />
        <div>
          <h3>{cue.id}</h3>
          <p>
            {KIND_LABEL[cue.kind]} · {moment ? `at ${clockTenths(startAt)}` : `${clockTenths(startAt)}–${clockTenths(cue.end_seconds ?? data.duration)}`}
            {cue.start_seconds === null ? " · not on the film" : ""}
          </p>
        </div>
        <button type="button" className="insp-close" aria-label="Close the cue" onClick={onClose}>
          <CloseIcon />
        </button>
      </header>

      <div className="insp-listen">
        {playing ? (
          <>
            <PlayButton
              playing={audition.playing === `${cue.id}/${playing.version}`}
              label={`${cue.id} on its own`}
              onClick={() => audition.toggle(`${cue.id}/${playing.version}`, soundUrl(slug, cue.id, playing.version))}
            />
            <span>On its own</span>
            <Button size="small" variant="quiet" onClick={() => onHear(Math.max(0, startAt - 2))}>
              Hear it in the film
            </Button>
          </>
        ) : (
          <>
            <span className="insp-silent">No sound yet</span>
            <Make
              slug={slug}
              cueIds={[cue.id]}
              label="Make this sound"
              variant="primary"
              prepare={onSaveNow}
              blocked={words.trim() ? undefined : "Say what it sounds like first."}
            />
          </>
        )}
      </div>

      <label className="insp-describe">
        <span>What it sounds like</span>
        <textarea
          ref={describe}
          aria-label={`What ${cue.id} sounds like`}
          rows={3}
          maxLength={600}
          placeholder="Instrument, texture, room, weather, distance. Say what is heard, not what is seen."
          value={words}
          onChange={(event) => {
            setWords(event.target.value);
            change({ prompt: event.target.value });
          }}
        />
        {cue.why && <small className="insp-why">Why: {cue.why}</small>}
      </label>

      <Section title="Kind">
        <Segmented
          label="Kind"
          value={cue.kind}
          options={(Object.keys(KIND_LABEL) as CueKind[]).map((kind) => ({ id: kind, label: KIND_LABEL[kind] }))}
          onChange={(kind) => change({ kind, model: null })}
        />
      </Section>

      <Section title="When">
        <Segmented
          label="When"
          value={moment ? "moment" : "stretch"}
          options={[
            { id: "moment", label: "At a moment" },
            { id: "stretch", label: "Over a stretch" },
          ]}
          onChange={(shape) => {
            if (shape === "moment") change({ end: cue.start, places: null });
            else {
              const from = cue.start_seconds ?? 0;
              change({ end: { frame: Math.min(Math.round((from + 4) * data.fps), Math.round(data.duration * data.fps)) } });
            }
          }}
        />
        {moment ? (
          <AnchorField label="At" value={cue.start} data={data} atEnd={false} pick={pick} onChange={(anchor) => change({ start: anchor, end: anchor })} />
        ) : (
          <>
            <AnchorField label="From" value={cue.start} data={data} atEnd={false} pick={pick} onChange={(start) => change({ start })} />
            <AnchorField label="To" value={cue.end} data={data} atEnd pick={pick} onChange={(end) => change({ end })} />
          </>
        )}
        {moment && "shot" in cue.start && <small className="hint">From the cut; a sound longer than the shot stops at the next cut.</small>}
      </Section>

      {!moment && (
        <Section title="Plays">
          <Segmented<PlaysMode>
            label="Plays"
            value={mode}
            options={[
              { id: "loop", label: "Loop to fill" },
              { id: "once", label: "Once" },
              { id: "every", label: "Every few seconds" },
              { id: "at", label: "At chosen places" },
            ]}
            onChange={(next) => change(withPlays(next, data.shots.map((shot) => shot.id)))}
          />
          {cue.places && "every" in cue.places && (
            <div className="insp-pair">
              <label>
                <span>Every</span>
                <span className="insp-seconds">
                  <input
                    type="number"
                    min="0.25"
                    step="0.25"
                    aria-label="Every seconds"
                    value={cue.places.every}
                    onChange={(event) => cue.places && "every" in cue.places && change({ places: { ...cue.places, every: Math.max(0.25, Number(event.target.value) || 0.25) } })}
                  />
                  <span aria-hidden="true">s</span>
                </span>
              </label>
              <label>
                <span>Give or take</span>
                <span className="insp-seconds">
                  <input
                    type="number"
                    min="0"
                    step="0.05"
                    aria-label="Jitter seconds"
                    value={cue.places.jitter ?? 0}
                    onChange={(event) => cue.places && "every" in cue.places && change({ places: { ...cue.places, jitter: Math.max(0, Number(event.target.value) || 0) } })}
                  />
                  <span aria-hidden="true">s</span>
                </span>
              </label>
            </div>
          )}
          {cue.places && "at" in cue.places && (
            <div className="insp-places">
              {cue.places.at.map((anchor, index) => (
                <span className="ui-chip" key={`${describeAnchor(anchor, data.fps)}-${index}`}>
                  {describeAnchor(anchor, data.fps)}
                  <button
                    type="button"
                    aria-label={`Remove the place ${describeAnchor(anchor, data.fps)}`}
                    onClick={() => cue.places && "at" in cue.places && change({ places: { at: cue.places.at.filter((_item, at) => at !== index) } })}
                  >
                    ×
                  </button>
                </span>
              ))}
              {pick && (
                <Button
                  size="small"
                  variant="quiet"
                  onClick={() =>
                    cue.places &&
                    "at" in cue.places &&
                    change({ places: { at: [...cue.places.at, pick.kind === "shot" ? { shot: pick.id } : { frame: Math.round(pick.seconds * data.fps) }] } })
                  }
                >
                  Add {pick.kind === "shot" ? `the cut of ${pick.id}` : clockTenths(pick.seconds)}
                </Button>
              )}
              {data.shots.length > 0 && (
                <Button size="small" variant="quiet" onClick={() => change({ places: { at: data.shots.map((shot) => ({ shot: shot.id })) } })}>
                  Every cut
                </Button>
              )}
            </div>
          )}
          {cue.places && <small className="hint">{placesWords(cue.places, cue.places_seconds?.length)}: one sound, made once and placed each time.</small>}
        </Section>
      )}

      <Section title="Level">
        <Level label="Volume" hint="Against the film's own sound." value={cue.gain_db} min={-60} max={12} onChange={(gain_db) => change({ gain_db })} />
        <Level
          label="Under the voice"
          hint={data.speech?.length || data.lines.length ? "How far it drops while someone speaks." : "Nobody speaks in this film yet; this only matters under a voice."}
          value={cue.duck_db}
          min={-40}
          max={0}
          onChange={(duck_db) => change({ duck_db })}
        />
      </Section>

      <Section title="Sounds" aside={<small className="hint">Made with {madeWith}</small>}>
        {cue.kind === "music" && musicModels.length > 1 && (
          <select className="insp-model" aria-label="Music model" value={cue.model ?? ""} onChange={(event) => change({ model: event.target.value || null })}>
            <option value="">Settings' choice ({musicModels.find((model) => model.chosen)?.label ?? "none"})</option>
            {musicModels.map((model) => (
              <option key={model.id} value={model.id}>
                {model.label}
                {model.price ? ` · $${model.price.amount} per ${model.price.unit}` : ""}
              </option>
            ))}
          </select>
        )}
        {cue.versions.length > 0 && (
          <ol className="insp-versions">
            {[...cue.versions].reverse().map((version) => {
              const key = `${cue.id}/${version.version}`;
              const inFilm = cue.selected === version.version;
              return (
                <li key={version.version} className={inFilm ? "in-film" : ""}>
                  <PlayButton playing={audition.playing === key} label={`version ${version.version}`} onClick={() => audition.toggle(key, soundUrl(slug, cue.id, version.version))} />
                  <span className="insp-version-words">
                    <b>Version {version.version}</b>
                    <small>
                      {version.seconds.toFixed(1)} s · {version.source === "upload" ? "your file" : modelLabel(version.model)}
                      {version.cost_usd ? ` · ${dollars(version.cost_usd)}` : ""}
                    </small>
                  </span>
                  {inFilm ? (
                    <span className="insp-in-film">
                      In the film
                      <Button size="small" variant="quiet" onClick={() => call(api.selectSound(slug, cue.id, null))}>
                        Silence
                      </Button>
                    </span>
                  ) : (
                    <Button size="small" onClick={() => call(api.selectSound(slug, cue.id, version.version))}>
                      Use this
                    </Button>
                  )}
                </li>
              );
            })}
          </ol>
        )}
        {fit && <small className="hint">{fit}</small>}
        <div className="insp-actions">
          {playing || cue.versions.length > 0 ? <Make slug={slug} cueIds={[cue.id]} label="Make another version" prepare={onSaveNow} blocked={words.trim() ? undefined : "Say what it sounds like first."} /> : null}
          <Button size="small" variant="quiet" onClick={() => file.current?.click()}>
            Use your own file
          </Button>
          <input
            ref={file}
            type="file"
            accept="audio/*"
            hidden
            onChange={(event) => {
              const picked = event.target.files?.[0];
              if (picked) call(api.uploadSound(slug, cue.id, picked));
              event.target.value = "";
            }}
          />
        </div>
        {problem && <ErrorState what="changing the sound" error={problem} compact />}
      </Section>

      {notes.length > 0 && (
        <Section title="From the mix check">
          {notes.map((note) => (
            <p className="insp-note" key={note}>
              {note}
            </p>
          ))}
        </Section>
      )}

      <footer className="insp-foot">
        {removing ? (
          <>
            <span>Remove {cue.id}? Its sounds stay on disk.</span>
            <Button size="small" className="danger" onClick={onRemove}>
              Remove
            </Button>
            <Button size="small" variant="quiet" onClick={() => setRemoving(false)}>
              Keep it
            </Button>
          </>
        ) : (
          <Button size="small" variant="quiet" onClick={() => setRemoving(true)}>
            Remove this cue
          </Button>
        )}
      </footer>
    </aside>
  );
}
