import { useCallback, useEffect, useRef, useState } from "react";
import { api, type EditPayload, type VoiceEstimate, type VoiceLine } from "../api";
import { errorCopy } from "../api/errors";
import { usePlayerControls } from "../spine/player";
import { clock } from "../spine/wave";
import { Button } from "../ui";
import type { PanelEdit } from "./FilmPanel";
import { addVoiceLine, removeVoiceLine, setVoiceStart, updateVoiceLine } from "./voiceLines";

function LineRow({
  slug,
  row,
  edit,
  fps,
  totalFrames,
  onChange,
  onTakes,
}: {
  slug: string;
  row: VoiceLine;
  edit: EditPayload;
  fps: number;
  totalFrames: number;
  onChange: PanelEdit;
  onTakes: () => void;
}) {
  const player = usePlayerControls();
  const [text, setText] = useState(row.text);
  useEffect(() => setText(row.text), [row.text]);
  const [start, setStart] = useState((row.start_frame / fps).toFixed(2));
  useEffect(() => setStart((row.start_frame / fps).toFixed(2)), [row.start_frame, fps]);
  const file = useRef<HTMLInputElement>(null);

  const commitText = () => {
    const words = text.trim();
    if (!words || words === row.text) {
      setText(row.text);
      return;
    }
    void onChange(updateVoiceLine(edit, row.id, { text: words }), "the line's words");
  };
  const commitStart = () => {
    const seconds = Number(start);
    if (!Number.isFinite(seconds)) {
      setStart((row.start_frame / fps).toFixed(2));
      return;
    }
    const next = setVoiceStart(edit, row.id, seconds, fps, totalFrames);
    void onChange(next, "where the line starts");
  };

  return (
    <div className="voice-line">
      <textarea
        aria-label="Spoken words"
        rows={2}
        value={text}
        onChange={(event) => setText(event.target.value)}
        onBlur={commitText}
      />
      <div className="row-actions">
        <button type="button" className="film-crop-time" onClick={() => player.seek(row.start_frame / fps)}>
          {clock(row.start_frame / fps)}
        </button>
        <label className="voice-start">
          <span>Starts at</span>
          <input
            type="text"
            inputMode="decimal"
            aria-label="Start time in seconds"
            value={start}
            onChange={(event) => setStart(event.target.value)}
            onBlur={commitStart}
          />
          <span>s</span>
        </label>
        <Button
          size="small"
          variant="quiet"
          onClick={() =>
            void onChange(
              setVoiceStart(edit, row.id, player.current(), fps, totalFrames),
              "where the line starts",
            )
          }
        >
          Use playhead
        </Button>
      </div>
      <label className="panel-field">
        <span>Level {row.gain_db ? `${row.gain_db > 0 ? "+" : ""}${row.gain_db} dB` : ""}</span>
        <input
          type="range"
          min={-12}
          max={12}
          step={1}
          defaultValue={row.gain_db}
          key={row.gain_db}
          aria-valuetext={`${row.gain_db} decibels`}
          onPointerUp={(event) =>
            void onChange(
              updateVoiceLine(edit, row.id, { gain_db: Number(event.currentTarget.value) }),
              "the line's level",
            )
          }
          onKeyUp={(event) =>
            void onChange(
              updateVoiceLine(edit, row.id, { gain_db: Number(event.currentTarget.value) }),
              "the line's level",
            )
          }
        />
      </label>
      {!row.current && (
        <p className="hint">
          {row.takes.length ? "These words have changed, so this line needs a new take." : "No take yet."}
        </p>
      )}
      {row.runs_into_next && <p className="voice-warning">This take runs into the next line.</p>}
      {row.runs_past_end && <p className="voice-warning">This take runs past the end of the film.</p>}
      {row.takes.length > 0 && (
        <div className="voice-takes">
          <select
            aria-label="Which take to use"
            value={row.selected ?? ""}
            onChange={(event) =>
              void api.selectVoiceTake(slug, row.id, Number(event.target.value)).then(onTakes, () => undefined)
            }
          >
            {row.takes.map((take) => (
              <option key={take.version} value={take.version}>
                Take {take.version}: {take.seconds.toFixed(1)} s
                {take.source === "upload" ? ", your recording" : ""}
                {take.text !== row.text ? ", older words" : ""}
              </option>
            ))}
          </select>
          {row.selected !== null && (
            <audio controls preload="none" src={`/api/projects/${slug}/voice/${row.id}/${row.selected}`} />
          )}
        </div>
      )}
      <div className="row-actions">
        <Button size="small" variant="quiet" onClick={() => file.current?.click()}>
          Use my own recording
        </Button>
        <input
          ref={file}
          hidden
          type="file"
          accept="audio/*"
          onChange={(event) => {
            const chosen = event.target.files?.[0];
            event.target.value = "";
            if (chosen) void api.uploadVoiceTake(slug, row.id, chosen).then(onTakes, () => undefined);
          }}
        />
        <Button
          size="small"
          variant="quiet"
          onClick={() => void onChange(removeVoiceLine(edit, row.id), "the removed line")}
        >
          Remove
        </Button>
      </div>
    </div>
  );
}

/** Write the spoken lines, place them, make or supply their takes, and hear them. */
export function VoicePanel({
  slug,
  edit,
  fps,
  totalFrames,
  onChange,
  onSound,
  onBack,
}: {
  slug: string;
  edit: EditPayload;
  fps: number;
  totalFrames: number;
  onChange: PanelEdit;
  /** The film's sound changed, so the Player must load the new mix. */
  onSound: () => void;
  onBack: () => void;
}) {
  const player = usePlayerControls();
  const [rows, setRows] = useState<VoiceLine[]>([]);
  const [voiceName, setVoiceName] = useState("");
  const [estimate, setEstimate] = useState<VoiceEstimate | null>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);

  const load = useCallback(async () => {
    const value = await api.voice(slug);
    setRows(value.lines);
    setVoiceName(value.voice);
  }, [slug]);
  useEffect(() => {
    void load().catch(() => undefined);
  }, [load, edit]);

  const takesChanged = useCallback(() => {
    void load().catch(() => undefined);
    onSound();
  }, [load, onSound]);

  const usedIds = rows.map((row) => row.id);
  const missing = rows.filter((row) => !row.current).length;

  const askPrice = async () => {
    setBusy(true);
    setProblem(null);
    try {
      setEstimate(await api.estimateVoice(slug));
    } catch {
      // The request helper has already shown what went wrong.
    } finally {
      setBusy(false);
    }
  };

  const makeTakes = async () => {
    if (!estimate) return;
    setBusy(true);
    setProblem(null);
    try {
      const started = await api.generateVoice(slug, estimate.quote_id);
      if ("needs_budget" in started) {
        setProblem("This film's budget has no room for these takes. Add to the budget first.");
        return;
      }
      setEstimate(null);
      for (;;) {
        const job = await api.job(started.job_id);
        if (!["queued", "running", "stopping"].includes(job.status)) {
          if (job.status !== "succeeded") setProblem(errorCopy(job.code) || job.error || "The takes could not be made.");
          break;
        }
        await new Promise((resolve) => setTimeout(resolve, 1000));
      }
      takesChanged();
    } catch {
      // The request helper has already shown what went wrong.
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <header className="panel-head">
        <h2>Voiceover</h2>
        <Button size="small" variant="quiet" onClick={onBack}>
          Back
        </Button>
      </header>
      <p className="hint">
        The music dips under each line. Your source recording is never changed. Voice: {voiceName}.
      </p>
      {rows.map((row) => (
        <LineRow
          key={row.id}
          slug={slug}
          row={row}
          edit={edit}
          fps={fps}
          totalFrames={totalFrames}
          onChange={onChange}
          onTakes={takesChanged}
        />
      ))}
      <div className="row-actions">
        <Button
          size="small"
          onClick={() =>
            void onChange(
              addVoiceLine(edit, Math.round(player.current() * fps), "New line", usedIds),
              "a new line",
            )
          }
        >
          Add a line at the playhead
        </Button>
        {missing > 0 && !estimate && (
          <Button size="small" variant="primary" disabled={busy} onClick={() => void askPrice()}>
            {busy ? "Working…" : `Make ${missing === 1 ? "1 take" : `${missing} takes`}`}
          </Button>
        )}
      </div>
      {estimate && (
        <div className="cut-suggestion" role="group" aria-label="Confirm the takes">
          <b>
            {estimate.tasks} {estimate.tasks === 1 ? "take" : "takes"}, {estimate.characters} characters
          </b>
          <p className="hint">Up to ${estimate.reserve_usd} is set aside from this film's budget.</p>
          <div className="row-actions">
            <Button size="small" variant="primary" disabled={busy} onClick={() => void makeTakes()}>
              {busy ? "Making them…" : "Make them"}
            </Button>
            <Button size="small" variant="quiet" disabled={busy} onClick={() => setEstimate(null)}>
              Not now
            </Button>
          </div>
        </div>
      )}
      {problem && <p className="voice-warning">{problem}</p>}
    </>
  );
}
