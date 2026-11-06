import { useRef, useState } from "react";
import { api, type SoundPayload } from "../api";
import { useResource } from "../api/useResource";
import { JobBanner } from "../jobs/JobBanner";
import { notifyProjectChanged } from "../shell/projectEvents";
import {
  bandFor,
  chosen,
  describeAnchor,
  freshId,
  KIND_LABEL,
  type Cue,
  type CueAnchor,
  type CueKind,
} from "../sound/cueBands";
import { Button, ErrorState } from "../ui";
import "../sound/sound.css";

const ASK_PROMPT =
  "Read the brief, the shots and the lines, then write the film's sound cues with " +
  "write_sound_cues: a bed if the film needs one, an ambience per place, an effect on each " +
  "moment that earns one.";

function clock(seconds: number | null): string {
  if (seconds === null) return "–";
  const whole = Math.max(0, Math.floor(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

function stripView(cue: Cue): Omit<Cue, "start_seconds" | "end_seconds" | "versions" | "selected"> {
  const { start_seconds: _s, end_seconds: _e, versions: _v, selected: _c, ...rest } = cue;
  return rest;
}

/** The whole list is what the engine takes; every save sends it back. */
function Anchor({
  value,
  story,
  lines,
  fps,
  onChange,
  label,
}: {
  value: CueAnchor;
  story: boolean;
  lines: SoundPayload["lines"];
  fps: number;
  onChange: (next: CueAnchor) => void;
  label: string;
}) {
  if (story && lines.length) {
    const current = "line" in value ? value.line : "";
    return (
      <label>
        {label}
        <select
          value={current}
          onChange={(event) => {
            const picked = event.target.value;
            onChange(picked ? { line: picked } : { frame: label === "Start" ? 0 : -1 });
          }}
        >
          <option value="">{label === "Start" ? "the first frame" : "the end"}</option>
          {lines.map((line) => (
            <option key={line.id} value={line.id}>
              {line.id} ({clock(line.start)})
            </option>
          ))}
        </select>
      </label>
    );
  }
  const seconds = "frame" in value && value.frame >= 0 ? value.frame / fps : null;
  return (
    <label>
      {label}
      <input
        type="number"
        min="0"
        step="0.1"
        placeholder={label === "Start" ? "0" : "end"}
        value={seconds === null ? "" : Number(seconds.toFixed(2))}
        onChange={(event) => {
          const raw = event.target.value;
          onChange(raw === "" ? { frame: label === "Start" ? 0 : -1 } : { frame: Math.round(Number(raw) * fps) });
        }}
      />
    </label>
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

function CueRow({
  slug,
  cue,
  data,
  onEdit,
  onRemove,
  onData,
}: {
  slug: string;
  cue: Cue;
  data: SoundPayload;
  onEdit: (next: Cue) => void;
  onRemove: () => void;
  onData: (data: SoundPayload) => void;
}) {
  const file = useRef<HTMLInputElement>(null);
  const playing = chosen(cue);
  return (
    <div className="cue" id={`cue-${cue.id}`}>
      <div className="cue-head">
        <b>{cue.id}</b>
        <span>{KIND_LABEL[cue.kind]}</span>
        <span className="hint">
          {describeAnchor(cue.start, data.fps)} → {describeAnchor(cue.end, data.fps)}
          {cue.start_seconds !== null && cue.end_seconds !== null
            ? ` (${clock(cue.start_seconds)}–${clock(cue.end_seconds)})`
            : " (not on the film)"}
        </span>
        <span className="hint">
          {playing ? `v${playing.version} plays` : cue.versions.length ? "no version chosen" : "silent"}
        </span>
        <Button size="small" variant="quiet" onClick={onRemove}>
          Remove
        </Button>
      </div>
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
        <label>
          Kind
          <select value={cue.kind} onChange={(event) => onEdit({ ...cue, kind: event.target.value as CueKind })}>
            {(Object.keys(KIND_LABEL) as CueKind[]).map((kind) => (
              <option key={kind} value={kind}>
                {KIND_LABEL[kind]}
              </option>
            ))}
          </select>
        </label>
        <Anchor label="Start" value={cue.start} story={data.story_film} lines={data.lines} fps={data.fps} onChange={(start) => onEdit({ ...cue, start })} />
        <Anchor label="End" value={cue.end} story={data.story_film} lines={data.lines} fps={data.fps} onChange={(end) => onEdit({ ...cue, end })} />
        <label>
          Gain dB
          <input type="number" min="-60" max="12" step="1" value={cue.gain_db} onChange={(event) => onEdit({ ...cue, gain_db: Number(event.target.value) })} />
        </label>
        <label>
          Under speech dB
          <input type="number" min="-40" max="0" step="1" value={cue.duck_db} onChange={(event) => onEdit({ ...cue, duck_db: Number(event.target.value) })} />
        </label>
        <label>
          Loop
          <input type="checkbox" checked={cue.loop} onChange={(event) => onEdit({ ...cue, loop: event.target.checked })} />
        </label>
      </div>
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
        <Make slug={slug} cueIds={[cue.id]} label={cue.versions.length ? "Make it again" : "Make this sound"} />
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
    </div>
  );
}

export function SoundStage({ slug }: { slug: string }) {
  const { value: data, error, setValue } = useResource(`/api/projects/${slug}/sound`, () => api.sound(slug));
  const [drafts, setDrafts] = useState<Record<string, Cue>>({});
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
  const add = (kind: CueKind) => {
    const fresh: Cue = {
      id: freshId(kind, cues.map((cue) => cue.id)),
      kind,
      prompt: "",
      start: { frame: 0 },
      end: { frame: -1 },
      gain_db: kind === "music" ? -14 : kind === "ambience" ? -24 : -6,
      duck_db: kind === "effect" ? 0 : -10,
      loop: kind !== "effect",
      versions: [],
      selected: null,
      start_seconds: 0,
      end_seconds: data.duration,
    };
    void save([...cues, fresh]);
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
            ? "A bed under the narration, the air of each place and an effect on a moment. A cue on lines follows the takes."
            : "The song is the music. Add an effect on a moment, or an ambience under a section, by the second."}
        </p>
        <div className="sound-ruler" aria-label="Where each cue plays">
          {data.lines.map((line) => (
            <span key={line.id} className="line-mark" style={{ left: `${(line.start / data.duration) * 100}%` }} title={line.id} />
          ))}
          {cues.map((cue) => {
            const band = bandFor(cue, data.duration);
            if (!band) return null;
            return (
              <button
                type="button"
                key={cue.id}
                className={`cue-band ${cue.kind} ${chosen(cue) ? "" : "silent"}`}
                style={{ left: `${band.left}%`, width: `${band.width}%` }}
                title={`${cue.id}: ${clock(cue.start_seconds)}–${clock(cue.end_seconds)}`}
                onClick={() => document.getElementById(`cue-${cue.id}`)?.scrollIntoView({ block: "center" })}
              >
                {cue.id}
              </button>
            );
          })}
        </div>
        <div className="row-actions">
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
        {cues.length === 0 && <p className="hint">No cues yet. Add one, suggest a list, or ask the Writer.</p>}
        <div className="cue-list">
          {cues.map((cue) => (
            <CueRow
              key={cue.id}
              slug={slug}
              cue={cue}
              data={data}
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
