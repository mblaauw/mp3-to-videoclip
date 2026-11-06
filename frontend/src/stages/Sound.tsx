import { useRef, useState, type ReactNode } from "react";
import { api, type SoundPayload } from "../api";
import { useResource } from "../api/useResource";
import { JobBanner } from "../jobs/JobBanner";
import { notifyProjectChanged } from "../shell/projectEvents";
import {
  anchorKind,
  anchorOf,
  bandFor,
  chosen,
  describeAnchor,
  freshId,
  KIND_LABEL,
  placesWords,
  type AnchorKind,
  type Cue,
  type CueAnchor,
  type CueKind,
  type CuePlaces,
} from "../sound/cueBands";
import { usePlayerControls, usePlayerTime } from "../spine/player";
import { Button, ErrorState } from "../ui";
import "../sound/sound.css";

const ASK_PROMPT =
  "Read the brief, the shots and the lines, then write the film's sound cues with " +
  "write_sound_cues: a bed if the film needs one, an ambience per place, an effect on each " +
  "moment that earns one, on the shot's cut where a cut is the moment.";

/** What a click on the spine chose: a moment, or a shot's cut. */
type Pick = { kind: "time"; seconds: number } | { kind: "shot"; id: string };

function clock(seconds: number | null): string {
  if (seconds === null) return "–";
  const whole = Math.max(0, Math.floor(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

function stripView(
  cue: Cue,
): Omit<Cue, "start_seconds" | "end_seconds" | "places_seconds" | "versions" | "selected"> {
  const { start_seconds: _s, end_seconds: _e, places_seconds: _p, versions: _v, selected: _c, ...rest } = cue;
  return rest;
}

/** The film along its length: shots, beats, lines, the cues and the playhead; a click seeks. */
function Spine({
  data,
  cues,
  pick,
  onPick,
}: {
  data: SoundPayload;
  cues: Cue[];
  pick: Pick | null;
  onPick: (pick: Pick) => void;
}) {
  const player = usePlayerControls();
  const time = usePlayerTime(0);
  const duration = data.duration || 1;
  const at = (seconds: number) => `${(Math.max(0, Math.min(duration, seconds)) / duration) * 100}%`;
  const seekTo = (event: React.MouseEvent<HTMLElement>) => {
    const box = event.currentTarget.getBoundingClientRect();
    const share = Math.max(0, Math.min(1, (event.clientX - box.left) / box.width));
    const seconds = Math.round(share * duration * 10) / 10;
    player.seek(seconds);
    onPick({ kind: "time", seconds });
  };
  return (
    <div className="sound-spine" aria-label="Where each cue plays">
      {data.shots.length > 0 && (
        <div className="spine-shots" role="list" aria-label="Shots">
          {data.shots.map((shot) => (
            <button
              type="button"
              role="listitem"
              key={shot.id}
              className={`spine-shot ${pick?.kind === "shot" && pick.id === shot.id ? "picked" : ""}`}
              style={{ left: at(shot.start), width: `${((shot.end - shot.start) / duration) * 100}%` }}
              title={`${shot.id}, ${clock(shot.start)}–${clock(shot.end)}`}
              onClick={() => {
                player.seek(shot.start);
                onPick({ kind: "shot", id: shot.id });
              }}
            >
              {shot.still ? <img src={shot.still} alt="" loading="lazy" /> : null}
              <span>{shot.id}</span>
            </button>
          ))}
        </div>
      )}
      {data.beats.length > 0 && (
        <div className="spine-beats" aria-label="Beats">
          {data.beats.map((beat) => (
            <span
              key={beat.id}
              className="spine-beat"
              style={{ left: at(beat.start), width: `${((beat.end - beat.start) / duration) * 100}%` }}
              title={`${beat.id}, ${clock(beat.start)}–${clock(beat.end)}`}
            >
              {beat.id}
            </span>
          ))}
        </div>
      )}
      <div className="sound-ruler" onClick={seekTo}>
        {data.lines.map((line) => (
          <span key={line.id} className="line-mark" style={{ left: at(line.start) }} title={line.id} />
        ))}
        {cues.map((cue) => {
          const band = bandFor(cue, duration);
          if (!band) return null;
          return (
            <button
              type="button"
              key={cue.id}
              className={`cue-band ${cue.kind} ${chosen(cue) ? "" : "silent"}`}
              style={{ left: `${band.left}%`, width: `${band.width}%` }}
              title={`${cue.id}: ${clock(cue.start_seconds)}–${clock(cue.end_seconds)}, ${placesWords(cue.places, cue.places_seconds?.length)}`}
              onClick={(event) => {
                event.stopPropagation();
                document.getElementById(`cue-${cue.id}`)?.scrollIntoView({ block: "center" });
              }}
            >
              {cue.id}
            </button>
          );
        })}
        {cues.map((cue) =>
          (cue.places_seconds ?? []).map((seconds, index) => (
            <span
              key={`${cue.id}-${index}`}
              className={`cue-place ${cue.kind}`}
              style={{ left: at(seconds) }}
              title={`${cue.id} at ${seconds.toFixed(1)} s`}
            />
          )),
        )}
        <span className="sound-playhead" style={{ left: at(time) }} aria-hidden="true" />
      </div>
      <div className="spine-foot hint">
        <span>{clock(time)} of {clock(data.duration)}</span>
        <span>Click the spine to move the playhead; click a shot to pick its cut.</span>
      </div>
    </div>
  );
}

/** A start or an end: a moment, a shot's cut, or on a story film a line or a beat. */
function AnchorField({
  label,
  value,
  data,
  atEnd,
  onChange,
}: {
  label: string;
  value: CueAnchor;
  data: SoundPayload;
  atEnd: boolean;
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
  return (
    <div className="cue-anchor">
      <label>
        {label}
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
      </label>
      <label>
        <span className="sr-only">{label} value</span>
        {kind === "frame" ? (
          <input
            type="number"
            min="0"
            step="0.1"
            aria-label={`${label} seconds`}
            placeholder={atEnd ? "end" : "0"}
            value={current}
            onChange={(event) => onChange(anchorOf("frame", event.target.value, data.fps, atEnd))}
          />
        ) : (
          <select
            aria-label={`${label} ${kind}`}
            value={current}
            onChange={(event) => onChange(anchorOf(kind, event.target.value, data.fps, atEnd))}
          >
            {(kind === "shot" ? data.shots : kind === "line" ? data.lines : data.beats).map((item) => (
              <option key={item.id} value={item.id}>
                {item.id} ({clock(item.start)})
              </option>
            ))}
          </select>
        )}
      </label>
    </div>
  );
}

/** Once, every so often, at every cut, or at anchors of your own. */
function PlacesField({
  cue,
  data,
  pick,
  onChange,
}: {
  cue: Cue;
  data: SoundPayload;
  pick: Pick | null;
  onChange: (next: CuePlaces) => void;
}) {
  const places = cue.places ?? null;
  const mode = !places ? "once" : "at" in places ? "at" : "every";
  const atList = places && "at" in places ? places.at : [];
  const pickedAnchor: CueAnchor | null =
    pick?.kind === "shot" ? { shot: pick.id } : pick ? { frame: Math.round(pick.seconds * data.fps) } : null;
  return (
    <div className="cue-places">
      <label>
        Plays
        <select
          aria-label="Plays"
          value={mode}
          onChange={(event) => {
            const next = event.target.value;
            if (next === "once") onChange(null);
            else if (next === "every") onChange({ every: 2, jitter: 0 });
            else onChange({ at: data.shots.length ? data.shots.map((shot) => ({ shot: shot.id })) : [{ frame: 0 }] });
          }}
        >
          <option value="once">Once, start to end</option>
          <option value="every">Every so many seconds</option>
          <option value="at">At places of your own</option>
        </select>
      </label>
      {places && "every" in places && (
        <>
          <label>
            Every, s
            <input
              type="number"
              min="0.25"
              step="0.25"
              aria-label="Every seconds"
              value={places.every}
              onChange={(event) => onChange({ ...places, every: Math.max(0.25, Number(event.target.value) || 0.25) })}
            />
          </label>
          <label>
            Give or take, s
            <input
              type="number"
              min="0"
              step="0.05"
              aria-label="Jitter seconds"
              value={places.jitter ?? 0}
              onChange={(event) => onChange({ ...places, jitter: Math.max(0, Number(event.target.value) || 0) })}
            />
          </label>
        </>
      )}
      {places && "at" in places && (
        <div className="cue-at">
          {atList.map((anchor, index) => (
            <span className="ui-chip" key={`${describeAnchor(anchor, data.fps)}-${index}`}>
              {describeAnchor(anchor, data.fps)}
              <button
                type="button"
                aria-label={`Remove the place ${describeAnchor(anchor, data.fps)}`}
                onClick={() => onChange({ at: atList.filter((_item, at) => at !== index) })}
              >
                ×
              </button>
            </span>
          ))}
          <span className="row-actions">
            {pickedAnchor && (
              <Button size="small" variant="quiet" onClick={() => onChange({ at: [...atList, pickedAnchor] })}>
                Add {pick?.kind === "shot" ? `the cut of ${pick.id}` : `${pick?.kind === "time" ? pick.seconds.toFixed(1) : ""} s`}
              </Button>
            )}
            {data.shots.length > 0 && (
              <Button size="small" variant="quiet" onClick={() => onChange({ at: data.shots.map((shot) => ({ shot: shot.id })) })}>
                Every cut
              </Button>
            )}
          </span>
        </div>
      )}
      <small className="hint">{placesWords(cue.places, cue.places_seconds?.length)}; bought once.</small>
    </div>
  );
}

/** Two clicks: first the price, then the purchase. */
function Make({ slug, cueIds, label }: { slug: string; cueIds: string[]; label: string }) {
  const [quote, setQuote] = useState<{ id: string; price: string; count: number; model: string } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
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
  if (quote) {
    return (
      <span className="cue-version">
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
          Make {quote.count} · ${quote.price}
        </Button>
        <span className="hint">{quote.model}</span>
        <Button size="small" variant="quiet" disabled={busy} onClick={() => setQuote(null)}>
          Not now
        </Button>
        {error && <ErrorState what="making the sound" error={error} compact />}
      </span>
    );
  }
  return (
    <span className="cue-version">
      <Button
        size="small"
        disabled={busy || cueIds.length === 0}
        onClick={() =>
          void run(async () => {
            const made = await api.estimateSound(slug, cueIds);
            setQuote({ id: made.quote_id, price: made.reserve_usd, count: made.tasks.length, model: made.model });
          })
        }
      >
        {busy ? "Working it out…" : label}
      </Button>
      {error && <ErrorState what="pricing the sound" error={error} compact />}
    </span>
  );
}

function Field({ label, children }: { label: string; children: ReactNode }) {
  return (
    <label>
      {label}
      {children}
    </label>
  );
}

function CueRow({
  slug,
  cue,
  data,
  pick,
  open,
  onOpen,
  onEdit,
  onRemove,
  onData,
}: {
  slug: string;
  cue: Cue;
  data: SoundPayload;
  pick: Pick | null;
  open: boolean;
  onOpen: (open: boolean) => void;
  onEdit: (next: Cue) => void;
  onRemove: () => void;
  onData: (data: SoundPayload) => void;
}) {
  const file = useRef<HTMLInputElement>(null);
  const playing = chosen(cue);
  const musicModels = data.models.filter((model) => model.for === "music");
  const modelLabel = (id: string | null | undefined) =>
    data.models.find((model) => model.id === id)?.label ?? data.models.find((model) => model.chosen && model.for === (cue.kind === "music" ? "music" : "effects"))?.label ?? "Settings' model";
  const when =
    cue.start_seconds !== null && cue.end_seconds !== null
      ? `${describeAnchor(cue.start, data.fps)} → ${describeAnchor(cue.end, data.fps)} (${clock(cue.start_seconds)}–${clock(cue.end_seconds)})`
      : `${describeAnchor(cue.start, data.fps)} → ${describeAnchor(cue.end, data.fps)} (not on the film)`;
  return (
    <div className={`cue ${open ? "open" : ""}`} id={`cue-${cue.id}`}>
      <div className="cue-summary">
        <b>{cue.id}</b>
        <span className={`cue-kind ${cue.kind}`}>{KIND_LABEL[cue.kind]}</span>
        <span className="hint">{when}</span>
        <span className="hint">{placesWords(cue.places, cue.places_seconds?.length)}</span>
        <span className="hint">{cue.gain_db} dB</span>
        <span className="hint">
          {playing ? `v${playing.version} plays` : cue.versions.length ? "no version chosen" : "silent"}
        </span>
        <span className="cue-summary-actions">
          <Make slug={slug} cueIds={[cue.id]} label={cue.versions.length ? "Make it again" : "Make this sound"} />
          <Button size="small" variant="quiet" aria-expanded={open} onClick={() => onOpen(!open)}>
            {open ? "Done" : "Edit"}
          </Button>
          <Button size="small" variant="quiet" onClick={onRemove}>
            Remove
          </Button>
        </span>
      </div>
      {cue.prompt.trim() === "" && !open && <p className="hint">No prompt yet; open it and say what it sounds like.</p>}
      {open && (
        <>
          <textarea
            aria-label={`What ${cue.id} sounds like`}
            rows={2}
            maxLength={600}
            placeholder="What it sounds like: instrument, texture, room, weather, distance. No picture."
            value={cue.prompt}
            onChange={(event) => onEdit({ ...cue, prompt: event.target.value })}
          />
          {cue.why && <p className="hint">{cue.why}</p>}
          <div className="cue-fields">
            <Field label="Kind">
              <select value={cue.kind} onChange={(event) => onEdit({ ...cue, kind: event.target.value as CueKind, model: null })}>
                {(Object.keys(KIND_LABEL) as CueKind[]).map((kind) => (
                  <option key={kind} value={kind}>
                    {KIND_LABEL[kind]}
                  </option>
                ))}
              </select>
            </Field>
            <AnchorField label="Start" value={cue.start} data={data} atEnd={false} onChange={(start) => onEdit({ ...cue, start })} />
            <AnchorField label="End" value={cue.end} data={data} atEnd onChange={(end) => onEdit({ ...cue, end })} />
            <Field label="Gain dB">
              <input type="number" min="-60" max="12" step="1" value={cue.gain_db} onChange={(event) => onEdit({ ...cue, gain_db: Number(event.target.value) })} />
            </Field>
            <Field label="Under speech dB">
              <input type="number" min="-40" max="0" step="1" value={cue.duck_db} onChange={(event) => onEdit({ ...cue, duck_db: Number(event.target.value) })} />
            </Field>
            <Field label="Loop">
              <input type="checkbox" checked={cue.loop} onChange={(event) => onEdit({ ...cue, loop: event.target.checked })} />
            </Field>
            {cue.kind === "music" && musicModels.length > 1 && (
              <Field label="Made with">
                <select aria-label="Music model" value={cue.model ?? ""} onChange={(event) => onEdit({ ...cue, model: event.target.value || null })}>
                  <option value="">Settings' choice ({musicModels.find((model) => model.chosen)?.label ?? "none"})</option>
                  {musicModels.map((model) => (
                    <option key={model.id} value={model.id}>
                      {model.label}
                      {model.price ? ` · $${model.price.amount} per ${model.price.unit}` : ""}
                    </option>
                  ))}
                </select>
              </Field>
            )}
          </div>
          <PlacesField cue={cue} data={data} pick={pick} onChange={(places) => onEdit({ ...cue, places })} />
          <p className="hint">Made with {modelLabel(cue.model)}.</p>
          {cue.versions.map((version) => (
            <div className="cue-version" key={version.version}>
              <span>
                v{version.version} · {version.seconds.toFixed(1)} s · {version.source === "upload" ? "your file" : version.model}
                {version.cost_usd ? ` · $${version.cost_usd}` : ""}
                {cue.selected === version.version ? " · in the film" : ""}
              </span>
              <audio controls preload="none" src={`/api/projects/${slug}/sound/${cue.id}/${version.version}`} />
              {cue.selected === version.version ? (
                <Button size="small" variant="quiet" onClick={() => void api.selectSound(slug, cue.id, null).then(onData)}>
                  Mute
                </Button>
              ) : (
                <Button size="small" variant="quiet" onClick={() => void api.selectSound(slug, cue.id, version.version).then(onData)}>
                  Keep
                </Button>
              )}
            </div>
          ))}
          <div className="cue-version">
            <Button size="small" variant="quiet" onClick={() => file.current?.click()}>
              Bring your own
            </Button>
            <input
              ref={file}
              type="file"
              accept="audio/*"
              hidden
              onChange={(event) => {
                const picked = event.target.files?.[0];
                if (picked) void api.uploadSound(slug, cue.id, picked).then(onData);
              }}
            />
          </div>
        </>
      )}
    </div>
  );
}

export function SoundStage({ slug }: { slug: string }) {
  const { value: data, error, setValue } = useResource(`/api/projects/${slug}/sound`, () => api.sound(slug));
  const [drafts, setDrafts] = useState<Record<string, Cue>>({});
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [pick, setPick] = useState<Pick | null>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [report, setReport] = useState<SoundPayload["report"]>(null);
  if (error && !data) return <ErrorState what="reading the sound" error={String(error)} />;
  if (!data) return <p className="hint">Reading the sound…</p>;
  const cues = data.cues.map((cue) => drafts[cue.id] ?? cue);
  const act = async (step: () => Promise<SoundPayload>) => {
    setBusy(true);
    setProblem(null);
    try {
      setValue(await step());
      setDrafts({});
      notifyProjectChanged({ slug });
    } catch (caught) {
      setProblem(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  };
  const save = (list: Cue[]) => act(() => api.saveSound(slug, list.map(stripView)));
  const dirty = Object.keys(drafts).length > 0;
  const silent = cues.filter((cue) => !chosen(cue)).map((cue) => cue.id);
  const add = (kind: CueKind, where?: { start: CueAnchor; end: CueAnchor }) => {
    const id = freshId(kind, cues.map((cue) => cue.id));
    const fresh: Cue = {
      id,
      kind,
      prompt: "",
      start: where?.start ?? { frame: 0 },
      end: where?.end ?? { frame: -1 },
      gain_db: kind === "music" ? -14 : kind === "ambience" ? -24 : -6,
      duck_db: kind === "effect" ? 0 : -10,
      loop: kind !== "effect",
      places: null,
      model: null,
      versions: [],
      selected: null,
      start_seconds: 0,
      end_seconds: data.duration,
    };
    setOpen((all) => ({ ...all, [id]: true }));
    void save([...cues, fresh]);
  };
  const addAtPick = () => {
    if (!pick) return;
    if (pick.kind === "shot") add("effect", { start: { shot: pick.id }, end: { shot: pick.id } });
    else {
      const frame = Math.round(pick.seconds * data.fps);
      add("effect", { start: { frame }, end: { frame: Math.min(frame + 2 * data.fps, Math.round(data.duration * data.fps)) } });
    }
  };
  return (
    <div className="sound-stage">
      <JobBanner slug={slug} kinds={["sound"]} className="in-card" />
      <section className="stage-block">
        <h2>
          Sound <small>{cues.length} cue{cues.length === 1 ? "" : "s"}, {silent.length} silent</small>
        </h2>
        <p className="hint">
          {data.story_film
            ? "A bed under the narration, the air of each place and an effect on a moment: a cut, a beat, a line, or every so many seconds. A cue on lines follows the takes; one on a cut follows the edit."
            : "The song is the music. Add an effect on a cut or a moment, an ambience under a section, or one sound every so many seconds."}
        </p>
        <Spine data={data} cues={cues} pick={pick} onPick={setPick} />
        <div className="row-actions">
          {pick && (
            <Button size="small" variant="primary" disabled={busy} onClick={addAtPick}>
              {pick.kind === "shot" ? `Add an effect on the cut of ${pick.id}` : `Add an effect at ${pick.seconds.toFixed(1)} s`}
            </Button>
          )}
          <Button size="small" onClick={() => add("music")}>Add music</Button>
          <Button size="small" onClick={() => add("ambience")}>Add ambience</Button>
          <Button size="small" onClick={() => add("effect")}>Add an effect</Button>
          {data.suggestions > 0 && (
            <Button size="small" variant="quiet" disabled={busy} onClick={() => void act(() => api.suggestSound(slug))}>
              Suggest cues
            </Button>
          )}
          <Button
            size="small"
            variant="quiet"
            onClick={() => window.dispatchEvent(new CustomEvent("studio:ask-director", { detail: { text: ASK_PROMPT } }))}
          >
            Ask the Writer
          </Button>
          {silent.length > 0 && <Make slug={slug} cueIds={silent} label={`Make every silent cue (${silent.length})`} />}
        </div>
        {problem && <ErrorState what="saving the cues" error={problem} compact />}
      </section>
      <section className="stage-block">
        <div className="cue-head">
          <h2>Cues</h2>
          {dirty && (
            <>
              <Button size="small" variant="primary" disabled={busy} onClick={() => void save(cues)}>
                Save the cues
              </Button>
              <Button size="small" variant="quiet" disabled={busy} onClick={() => setDrafts({})}>
                Undo
              </Button>
            </>
          )}
        </div>
        {cues.length === 0 && <p className="hint">No cues yet. Add one, click the spine to place an effect, suggest a list, or ask the Writer.</p>}
        <div className="cue-list">
          {cues.map((cue) => (
            <CueRow
              key={cue.id}
              slug={slug}
              cue={cue}
              data={data}
              pick={pick}
              open={!!open[cue.id]}
              onOpen={(next) => setOpen((all) => ({ ...all, [cue.id]: next }))}
              onEdit={(next) => setDrafts((all) => ({ ...all, [next.id]: next }))}
              onRemove={() => void save(cues.filter((item) => item.id !== cue.id))}
              onData={(next) => {
                setValue(next);
                notifyProjectChanged({ slug });
              }}
            />
          ))}
        </div>
      </section>
      <section className="stage-block">
        <div className="cue-head">
          <h2>What the ear hears</h2>
          <Button size="small" variant="quiet" disabled={busy} onClick={() => void api.soundReport(slug).then(setReport)}>
            Listen through
          </Button>
        </div>
        {report ? (
          <div className="sound-notes">
            <p className="hint">
              {report.cues} cue{report.cues === 1 ? "" : "s"}, {report.sounding} with a sound.
              {report.loudness ? ` The mix measures ${report.loudness.lufs} LUFS.` : report.mixed ? "" : " No mix to measure yet."}
            </p>
            {report.notes.length === 0 && <p className="hint">Nothing to report.</p>}
            {report.notes.map((note, index) => (
              <p className="hint" key={`${note.code}-${index}`}>
                {note.message}
              </p>
            ))}
          </div>
        ) : (
          <p className="hint">Measures the current mix: silences, cues too close to the voice, loudness.</p>
        )}
      </section>
    </div>
  );
}
