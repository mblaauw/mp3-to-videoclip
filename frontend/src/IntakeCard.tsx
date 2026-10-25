import { useEffect, useMemo, useRef, useState } from "react";
import {
  api,
  type AudioWindow,
  type Brief,
  type IntakePayload,
  type Intent,
} from "./api";

function lines(value: string[] | undefined): string {
  return (value || []).join("\n");
}

function splitLines(value: string): string[] {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean);
}

function splitTone(value: string): string[] {
  return value
    .split(",")
    .map((word) => word.trim())
    .filter(Boolean)
    .slice(0, 3);
}

function WindowWaveform({
  peaks,
  source,
  window,
  onChange,
}: {
  peaks: number[];
  source: number;
  window: AudioWindow;
  onChange: (value: AudioWindow) => void;
}) {
  const track = useRef<HTMLDivElement>(null);
  const [drag, setDrag] = useState<"start" | "end" | null>(null);
  const startPct = source > 0 ? (window.start / source) * 100 : 0;
  const endPct = source > 0 ? (window.end / source) * 100 : 100;

  const secondsAt = (clientX: number) => {
    const box = track.current?.getBoundingClientRect();
    if (!box || !box.width) return 0;
    return Math.max(0, Math.min(source, ((clientX - box.left) / box.width) * source));
  };

  const move = (edge: "start" | "end", clientX: number) => {
    const value = Math.round(secondsAt(clientX) * 10) / 10;
    if (edge === "start") {
      onChange({ ...window, start: Math.min(value, Math.max(0, window.end - 1)) });
    } else {
      onChange({ ...window, end: Math.max(value, Math.min(source, window.start + 1)) });
    }
  };

  const nudge = (edge: "start" | "end", delta: number) => {
    if (edge === "start") {
      onChange({
        ...window,
        start: Math.max(0, Math.min(window.end - 1, window.start + delta)),
      });
    } else {
      onChange({
        ...window,
        end: Math.max(window.start + 1, Math.min(source, window.end + delta)),
      });
    }
  };

  return (
    <div className="window-waveform" ref={track}>
      <div className="window-bars" aria-hidden="true">
        {peaks.length ? (
          peaks.map((height, index) => (
            <span key={index} style={{ height: `${Math.max(2, height * 100).toFixed(2)}%` }} />
          ))
        ) : (
          <p className="meta">The waveform appears after the local audio probe.</p>
        )}
      </div>
      <div
        className="window-region"
        style={{ left: `${startPct}%`, width: `${Math.max(0, endPct - startPct)}%` }}
      />
      {(["start", "end"] as const).map((edge) => {
        const position = edge === "start" ? window.start : window.end;
        return (
          <button
            key={edge}
            className={`window-handle ${edge}`}
            style={{ left: `${edge === "start" ? startPct : endPct}%` }}
            type="button"
            role="slider"
            aria-label={edge === "start" ? "Excerpt start" : "Excerpt end"}
            aria-orientation="horizontal"
            aria-valuemin={edge === "start" ? 0 : window.start + 1}
            aria-valuemax={edge === "start" ? window.end - 1 : source}
            aria-valuenow={position}
            aria-valuetext={`${position.toFixed(1)} seconds`}
            onPointerDown={(event) => {
              event.currentTarget.setPointerCapture(event.pointerId);
              setDrag(edge);
            }}
            onPointerMove={(event) => {
              if (drag === edge) move(edge, event.clientX);
            }}
            onPointerUp={() => setDrag(null)}
            onPointerCancel={() => setDrag(null)}
            onLostPointerCapture={() => setDrag(null)}
            onKeyDown={(event) => {
              if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
              event.preventDefault();
              const step = event.shiftKey ? 5 : 0.5;
              if (event.key === "Home") nudge(edge, -source);
              else if (event.key === "End") nudge(edge, source);
              else nudge(edge, event.key === "ArrowLeft" ? -step : step);
            }}
          />
        );
      })}
    </div>
  );
}

export function IntakeCard({
  slug,
  onSaved,
}: {
  slug: string;
  onSaved: (brief: Brief) => void;
}) {
  const [data, setData] = useState<IntakePayload | null>(null);
  const [intent, setIntent] = useState<Intent>({});
  const [preset, setPreset] = useState("");
  const [window, setWindow] = useState<AudioWindow | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [measuring, setMeasuring] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState<string | null>(null);

  const load = () =>
    api
      .intake(slug)
      .then((payload) => {
        setData(payload);
        setIntent(payload.intent || { kind: payload.kind });
        setPreset(payload.style_preset || "custom");
        setWindow(payload.audio_window);
        setError(null);
      })
      .catch((e) => setError(String(e)))
      .finally(() => setLoading(false));

  useEffect(() => {
    setLoading(true);
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [slug]);

  const profile = useMemo(
    () => data?.kinds.find((kind) => kind.id === data.kind) || null,
    [data],
  );
  const isVideo = data?.kind === "music_video";
  const sourceDuration = data?.source_duration || 0;
  const length = window ? Math.max(0, window.end - window.start) : data?.duration || 0;
  const presets = (data?.style_presets || []).filter(
    (value) => !profile || profile.style_presets.includes(value.id),
  );

  const field = (key: keyof Intent, value: unknown) =>
    setIntent((current) => ({ ...current, [key]: value }));

  const save = async () => {
    if (!data || saving) return;
    setSaving(true);
    setError(null);
    setMessage("");
    try {
      const clean: Intent = {
        ...intent,
        cta:
          intent.cta && (intent.cta.text?.trim() || intent.cta.url?.trim())
            ? { text: intent.cta.text || "", url: intent.cta.url || "" }
            : null,
      };
      const updated = await api.updateIntake(slug, {
        intent: clean,
        style_preset: preset === "custom" ? "" : preset,
        audio_window: isVideo ? null : window,
      });
      setData(updated);
      setIntent(updated.intent || { kind: updated.kind });
      setPreset(updated.style_preset || preset);
      setWindow(updated.audio_window);
      onSaved(updated.brief);
      if (updated.analysis_needed) {
        setMeasuring(true);
        setMessage("Window saved. Measuring the excerpt…");
        await api.analyze(slug);
        const refreshed = await api.intake(slug);
        setData(refreshed);
        setWindow(refreshed.audio_window);
        setMessage("Excerpt measured and ready for the Storyboard.");
      } else {
        setMessage("Intake saved.");
      }
    } catch (e) {
      setError(String(e));
    } finally {
      setSaving(false);
      setMeasuring(false);
    }
  };

  if (loading) return <p className="meta">Loading the intake…</p>;
  if (!data) {
    return (
      <div className="card">
        <h3>Intake</h3>
        {error && <p className="error">{error}</p>}
        <button type="button" onClick={load}>
          Retry loading the intake
        </button>
      </div>
    );
  }

  return (
    <div className="card intake-card">
      <h3>Intake — {profile?.label || data.kind}</h3>
      <p className="meta">{profile?.purpose}</p>
      {error && <p className="error">{error}</p>}
      {message && <p className="meta">{message}</p>}

      <div className="grid">
        <label>
          Working title
          <input value={data.title} readOnly />
        </label>
        <label>
          What this is for
          <textarea
            rows={2}
            value={intent.objective || ""}
            onChange={(e) => field("objective", e.target.value)}
            placeholder="One sentence with an active verb"
          />
        </label>
        <label>
          Audience
          <textarea
            rows={2}
            value={intent.audience || ""}
            onChange={(e) => field("audience", e.target.value)}
            placeholder="A specific group, not everyone"
          />
        </label>
        {isVideo ? (
          <label>
            What the song is about
            <textarea
              rows={3}
              value={intent.about || ""}
              onChange={(e) => field("about", e.target.value)}
              placeholder="In the artist's words"
            />
          </label>
        ) : (
          <label>
            Key message
            <textarea
              rows={3}
              value={intent.message || ""}
              onChange={(e) => field("message", e.target.value)}
              placeholder="The one thing a stranger should repeat"
            />
          </label>
        )}
        <label>
          Tone (three words)
          <input
            value={(intent.tone || []).join(", ")}
            onChange={(e) => field("tone", splitTone(e.target.value))}
            placeholder="urgent, warm, nocturnal"
          />
        </label>
        {isVideo ? (
          <label>
            Performance wanted?
            <select
              value={intent.performance == null ? "" : intent.performance ? "yes" : "no"}
              onChange={(e) =>
                field("performance", e.target.value === "" ? null : e.target.value === "yes")
              }
            >
              <option value="">Not decided</option>
              <option value="yes">Yes, performance-led</option>
              <option value="no">No, no performer on camera</option>
            </select>
          </label>
        ) : (
          <label>
            Reasons to believe (one per line, max 3)
            <textarea
              rows={3}
              value={lines(intent.reasons)}
              onChange={(e) => field("reasons", splitLines(e.target.value).slice(0, 3))}
              placeholder="Facts the user supplied only"
            />
          </label>
        )}
        {!isVideo && (
          <>
            <label>
              CTA text
              <input
                value={intent.cta?.text || ""}
                onChange={(e) =>
                  field("cta", {
                    text: e.target.value,
                    url: intent.cta?.url || "",
                  })
                }
                placeholder="Pre-save now"
              />
            </label>
            <label>
              CTA URL
              <input
                value={intent.cta?.url || ""}
                onChange={(e) =>
                  field("cta", {
                    text: intent.cta?.text || "",
                    url: e.target.value,
                  })
                }
                placeholder="https://example.com"
              />
            </label>
          </>
        )}
        <label>
          Must include / mandatory lines (one per line)
          <textarea
            rows={3}
            value={lines(intent.mandatories)}
            onChange={(e) => field("mandatories", splitLines(e.target.value))}
          />
        </label>
        <label>
          Must avoid (one per line)
          <textarea
            rows={3}
            value={lines(intent.avoid)}
            onChange={(e) => field("avoid", splitLines(e.target.value))}
          />
        </label>
        {!isVideo && (
          <label>
            Product / brand assets
            <textarea
              rows={3}
              value={intent.assets || ""}
              onChange={(e) => field("assets", e.target.value)}
              placeholder="Logo, product photos, brand colours, fonts; paths or links"
            />
          </label>
        )}
        <label>
          Reference links (one per line)
          <textarea
            rows={3}
            value={lines(intent.reference_links)}
            onChange={(e) => field("reference_links", splitLines(e.target.value))}
          />
        </label>
        <label>
          Anything the director should know
          <textarea
            rows={3}
            value={intent.notes || ""}
            onChange={(e) => field("notes", e.target.value)}
          />
        </label>
        <label>
          Style preset
          <select value={preset} onChange={(e) => setPreset(e.target.value)}>
            {presets.map((option) => (
              <option key={option.id} value={option.id}>
                {option.name}
                {option.protected ? " (protected core)" : ""}
              </option>
            ))}
            {(preset === "custom" ||
              !presets.some((option) => option.id === preset)) && (
              <option value="custom">Custom (keep the current look)</option>
            )}
          </select>
        </label>
      </div>

      {!isVideo && !window && (
        <div className="window-card">
          <h4>Excerpt</h4>
          <p className="meta">
            This promo uses the whole track. Add an excerpt if the cut should be shorter.
          </p>
          <button
            type="button"
            onClick={() =>
              setWindow({
                start: 0,
                end: Math.max(1, Math.min(60, sourceDuration)),
                fade_in: 0,
                fade_out: 1.5,
              })
            }
          >
            Use an excerpt
          </button>
        </div>
      )}
      {!isVideo && window && (
        <div className="window-card">
          <h4>Excerpt</h4>
          <p className="meta">
            {window.start.toFixed(1)}s–{window.end.toFixed(1)}s · {length.toFixed(1)}s from a{" "}
            {sourceDuration.toFixed(1)}s track. Drag the handles; the source file is untouched.
          </p>
          <WindowWaveform
            peaks={data.peaks}
            source={sourceDuration}
            window={window}
            onChange={setWindow}
          />
          <div className="grid">
            <label>
              Start (s)
              <input
                type="number"
                min={0}
                max={Math.max(0, window.end - 1)}
                step={0.1}
                value={window.start}
                onChange={(e) =>
                  setWindow({
                    ...window,
                    start: Math.max(0, Math.min(window.end - 1, Number(e.target.value))),
                  })
                }
              />
            </label>
            <label>
              End (s)
              <input
                type="number"
                min={window.start + 1}
                max={sourceDuration}
                step={0.1}
                value={window.end}
                onChange={(e) =>
                  setWindow({
                    ...window,
                    end: Math.max(
                      window.start + 1,
                      Math.min(sourceDuration, Number(e.target.value)),
                    ),
                  })
                }
              />
            </label>
            <label>
              Fade in (s)
              <input
                type="number"
                min={0}
                max={length}
                step={0.1}
                value={window.fade_in}
                onChange={(e) =>
                  setWindow({
                    ...window,
                    fade_in: Math.max(0, Math.min(length, Number(e.target.value))),
                  })
                }
              />
            </label>
            <label>
              Fade out (s)
              <input
                type="number"
                min={0}
                max={length}
                step={0.1}
                value={window.fade_out}
                onChange={(e) =>
                  setWindow({
                    ...window,
                    fade_out: Math.max(0, Math.min(length, Number(e.target.value))),
                  })
                }
              />
            </label>
          </div>
        </div>
      )}

      <div className="actions">
        <button type="button" onClick={save} disabled={saving || measuring}>
          {saving || measuring ? "Saving…" : "Save intake"}
        </button>
        <span className="meta">
          {measuring
            ? "Local analysis is running; nothing leaves this machine."
            : "Saving an excerpt invalidates old measurement and asks for a fresh local analysis."}
        </span>
      </div>
    </div>
  );
}
