import { useMemo, useRef, useState } from "react";
import { api, type ScriptLine, type ScriptPayload, type Take } from "../api";
import { useResource } from "../api/useResource";
import { lineAt, parsePasted } from "../script/parse";
import { notifyProjectChanged } from "../shell/projectEvents";
import { Button, ErrorState } from "../ui";
import "../script/script.css";

const WRITE_PROMPT =
  "Read the brief and the structure's beats, then write the narration with write_script: one " +
  "line per sentence or two, each on a beat with a direction, and every invented fact listed.";

function clock(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

/** Budgets against what the words will take, and what they did take once they are said. */
function BeatSheet({ data }: { data: ScriptPayload }) {
  const rows = data.report.beats.length
    ? data.report.beats
    : data.beats.beats.map((beat) => ({
        id: beat.id,
        label: beat.label,
        budget: beat.budget,
        estimate: 0,
        measured: null,
        over: null,
      }));
  const rules = new Map(data.beats.beats.map((beat) => [beat.id, beat.rule]));
  return (
    <section className="stage-block beat-sheet">
      <h2>
        Beats <small>{data.beats.label}</small>
      </h2>
      {rows.map((beat) => {
        const used = beat.measured ?? beat.estimate;
        const share = beat.budget ? Math.min(100, (used / beat.budget) * 100) : 0;
        return (
          <div className="beat-row" key={beat.id}>
            <div className="beat-head">
              <b>{beat.label}</b>
              <span className={used > beat.budget ? "beat-over" : undefined}>
                {used.toFixed(1)} of {beat.budget.toFixed(0)} s
                {beat.measured === null ? " estimated" : " measured"}
              </span>
            </div>
            <div className="beat-bar" aria-hidden="true">
              <span style={{ width: `${share}%` }} className={used > beat.budget ? "over" : undefined} />
            </div>
            {rules.get(beat.id) && <p className="hint">{rules.get(beat.id)}</p>}
          </div>
        );
      })}
      {data.report.notes.map((note) => (
        <p className="hint" key={note}>
          {note}
        </p>
      ))}
      {data.narration.measured_rate && (
        <p className="hint">
          Measured {data.narration.measured_rate} words a second; the estimate assumed{" "}
          {data.script?.reading_rate_wps}.
        </p>
      )}
      {data.report.invented.length > 0 && (
        <div className="profile-list">
          <b className="profile-label">Invented</b>
          {data.report.invented.map((claim) => (
            <p className="hint" key={`${claim.line}-${claim.text}`}>
              {claim.line}: {claim.text}
            </p>
          ))}
        </div>
      )}
    </section>
  );
}

/** Two clicks: first the price, then the purchase. */
function Buy({
  slug,
  label,
  lineIds,
  regenerate,
}: {
  slug: string;
  label: string;
  lineIds?: string[];
  regenerate?: boolean;
}) {
  const [quote, setQuote] = useState<{ id: string; price: string; lines: number } | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const run = async (step: () => Promise<void>) => {
    setBusy(true);
    setError(null);
    try {
      await step();
    } catch (caught) {
      setError(String(caught));
    } finally {
      setBusy(false);
    }
  };
  return (
    <span className="make-sharper">
      {quote ? (
        <>
          <Button
            size="small"
            variant="primary"
            disabled={busy}
            onClick={() =>
              void run(async () => {
                const started = await api.generateLines(slug, quote.id);
                if (started.needs_budget) throw new Error("The budget has no room for this.");
                setQuote(null);
              })
            }
          >
            Buy {quote.lines} line{quote.lines === 1 ? "" : "s"} · ${quote.price}
          </Button>
          <Button size="small" variant="quiet" disabled={busy} onClick={() => setQuote(null)}>
            Not now
          </Button>
        </>
      ) : (
        <Button
          size="small"
          disabled={busy}
          onClick={() =>
            void run(async () => {
              const made = await api.estimateLines(slug, { line_ids: lineIds, regenerate });
              setQuote({ id: made.quote_id, price: made.reserve_usd, lines: made.tasks });
            })
          }
        >
          {busy ? "Working it out…" : label}
        </Button>
      )}
      {error && <ErrorState what="pricing the takes" error={error} compact />}
    </span>
  );
}

function LineRow({
  slug,
  line,
  data,
  current,
  onChange,
  onSave,
  onData,
}: {
  slug: string;
  line: ScriptLine;
  data: ScriptPayload;
  current: boolean;
  onChange: (next: ScriptLine) => void;
  onSave: () => void;
  onData: (data: ScriptPayload) => void;
}) {
  const entry = data.narration.lines[line.id];
  const stale = data.narration.stale.includes(line.id);
  const timing = data.timing.lines.find((row) => row.id === line.id);
  const [open, setOpen] = useState(false);
  const file = useRef<HTMLInputElement>(null);
  const keep = async (take: Take) => {
    onData(await api.keepTake(slug, line.id, take.version));
    notifyProjectChanged({ slug });
  };
  return (
    <div
      className={`script-line ${current ? "current" : ""}`}
      tabIndex={0}
      onKeyDown={(event) => {
        if (event.target !== event.currentTarget) return;
        const newest = entry?.versions[entry.versions.length - 1];
        if (event.key === "k" && newest) void keep(newest);
        if (event.key === "r") setOpen(true);
      }}
    >
      <div className="script-line-head">
        <b>{line.id}</b>
        <span>{line.beat}</span>
        {timing && (
          <span>
            {clock(timing.start)}, {(timing.end - timing.start).toFixed(1)} s {timing.source}
          </span>
        )}
        {stale && <span className="beat-over">The words changed since this take</span>}
        <Button size="small" variant="quiet" onClick={() => setOpen(!open)}>
          {entry?.versions.length ?? 0} take{entry?.versions.length === 1 ? "" : "s"}
        </Button>
      </div>
      <textarea
        aria-label={`Words of ${line.id}`}
        rows={2}
        value={line.text}
        maxLength={600}
        onChange={(event) => onChange({ ...line, text: event.target.value })}
        onBlur={onSave}
      />
      <div className="script-line-fields">
        <label>
          Pause
          <input
            type="number"
            min="0"
            max="20"
            step="0.1"
            value={line.pause_after}
            onChange={(event) => onChange({ ...line, pause_after: Number(event.target.value) })}
            onBlur={onSave}
          />
        </label>
        <label>
          Direction
          <input
            value={line.direction}
            maxLength={400}
            onChange={(event) => onChange({ ...line, direction: event.target.value })}
            onBlur={onSave}
          />
        </label>
      </div>
      {open && (
        <div className="takes">
          {(entry?.versions ?? []).map((take) => (
            <div className="take" key={take.version}>
              <span>
                v{take.version} · {take.seconds.toFixed(1)} s · {take.voice ?? "your recording"}
                {entry?.selected === take.version ? " · in the film" : ""}
              </span>
              <audio
                controls
                preload="none"
                src={`/api/projects/${slug}/narration/${line.id}/${take.version}`}
              />
              <Button size="small" variant="quiet" onClick={() => void keep(take)}>
                Keep
              </Button>
            </div>
          ))}
          <div className="row-actions">
            <Buy slug={slug} label="Redo this line" lineIds={[line.id]} regenerate />
            <Button size="small" variant="quiet" onClick={() => file.current?.click()}>
              Use my recording
            </Button>
            <input
              ref={file}
              type="file"
              accept="audio/*"
              hidden
              onChange={(event) => {
                const picked = event.target.files?.[0];
                if (picked) void api.uploadTake(slug, line.id, picked).then(onData);
              }}
            />
          </div>
        </div>
      )}
    </div>
  );
}

export function ScriptStage({ slug }: { slug: string }) {
  const { value: data, error, setValue } = useResource(`/api/projects/${slug}/script`, () =>
    api.script(slug),
  );
  const [drafts, setDrafts] = useState<Record<string, ScriptLine>>({});
  const [paste, setPaste] = useState("");
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [time, setTime] = useState(0);
  const lines = useMemo(
    () => (data?.script?.lines ?? []).map((line) => drafts[line.id] ?? line),
    [data, drafts],
  );
  if (error && !data) return <ErrorState what="reading the script" error={String(error)} />;
  if (!data) return <p className="hint">Reading the script…</p>;
  const act = async (step: () => Promise<ScriptPayload>) => {
    setBusy(true);
    setProblem(null);
    try {
      setValue(await step());
      setDrafts({});
      notifyProjectChanged({ slug });
    } catch (caught) {
      setProblem(String(caught));
    } finally {
      setBusy(false);
    }
  };
  const structure = data.script?.structure ?? data.beats.structure;
  const saveLines = () => {
    if (!Object.keys(drafts).length) return;
    void act(() => api.saveScript(slug, { structure, lines }));
  };
  const said = lineAt(data.timing.lines, time);
  return (
    <div className="script-stage">
      <BeatSheet data={data} />
      <div className="script-main">
        {problem && <ErrorState what="saving the script" error={problem} compact />}
        {!data.script ? (
          <section className="stage-block">
            <h2>Script</h2>
            <p className="hint">
              Ask the Writer, or paste your own lines. One line per row; start a row with a beat
              name, as in "hook: words", to place it yourself.
            </p>
            <div className="row-actions">
              <Button
                variant="primary"
                size="small"
                onClick={() =>
                  window.dispatchEvent(
                    new CustomEvent("studio:ask-director", { detail: { text: WRITE_PROMPT } }),
                  )
                }
              >
                Ask the Writer
              </Button>
            </div>
            <textarea
              aria-label="Paste the script"
              rows={10}
              value={paste}
              onChange={(event) => setPaste(event.target.value)}
            />
            <div className="row-actions">
              <Button
                size="small"
                disabled={busy || !paste.trim()}
                onClick={() =>
                  void act(() =>
                    api.saveScript(slug, {
                      structure,
                      lines: parsePasted(paste, data.beats.beats),
                    }),
                  )
                }
              >
                Save these lines
              </Button>
            </div>
          </section>
        ) : (
          <>
            <section className="stage-block">
              <h2>
                Voice <small>{data.narration.voice}</small>
              </h2>
              <div className="row-actions">
                <select
                  aria-label="Narrator"
                  value={data.narration.voice}
                  onChange={(event) => void act(() => api.chooseVoice(slug, event.target.value))}
                >
                  {data.voices.map((voice) => (
                    <option key={voice.id} value={voice.id}>
                      {voice.label || voice.id}
                    </option>
                  ))}
                  {!data.voices.some((voice) => voice.id === data.narration.voice) && (
                    <option value={data.narration.voice}>{data.narration.voice}</option>
                  )}
                </select>
                <Buy slug={slug} label="Hear the first line" lineIds={[lines[0]?.id]} regenerate />
                <Buy slug={slug} label="Record the lines" />
                <Button
                  size="small"
                  disabled={busy}
                  onClick={() => void act(() => api.buildSoundtrack(slug))}
                >
                  {busy ? "Building…" : "Hear a draft"}
                </Button>
                <Button
                  size="small"
                  variant="quiet"
                  disabled={!data.alignment.ready}
                  title={
                    data.alignment.ready
                      ? "Word times from the kept takes, on this computer"
                      : "Captions are per line on this computer"
                  }
                  onClick={() => void api.alignTakes(slug)}
                >
                  Time the words
                </Button>
              </div>
              {data.soundtrack.url && (
                <>
                  <audio
                    controls
                    src={data.soundtrack.url}
                    onTimeUpdate={(event) => setTime(event.currentTarget.currentTime)}
                  />
                  <p className="script-caption">{said?.text ?? " "}</p>
                  <p className="hint">
                    {clock(data.soundtrack.receipt?.seconds ?? data.duration)} long.{" "}
                    {data.soundtrack.receipt?.lines_with_takes ?? 0} of{" "}
                    {data.soundtrack.receipt?.lines ?? lines.length} lines have a voice; the rest are
                    silence of their estimated length.
                  </p>
                </>
              )}
            </section>
            <section className="stage-block">
              <h2>
                Lines <small>K keeps the newest take, R opens the takes</small>
              </h2>
              {lines.map((line) => (
                <LineRow
                  key={line.id}
                  slug={slug}
                  line={line}
                  data={data}
                  current={said?.id === line.id}
                  onChange={(next) => setDrafts((all) => ({ ...all, [next.id]: next }))}
                  onSave={saveLines}
                  onData={setValue}
                />
              ))}
            </section>
          </>
        )}
      </div>
    </div>
  );
}
