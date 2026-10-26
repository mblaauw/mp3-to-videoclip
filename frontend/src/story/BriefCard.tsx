import { useEffect, useRef, useState } from "react";
import { api, type AudioWindow, type IntakePayload, type Intent, type StylePreset } from "../api";
import { notifyProjectChanged } from "../shell/projectEvents";
import { Button, Field } from "../ui";

function listText(values: string[] | undefined): string {
  return (values || []).join("\n");
}

function parseList(value: string, limit?: number): string[] {
  const list = value
    .split("\n")
    .map((item) => item.trim())
    .filter(Boolean);
  return limit ? list.slice(0, limit) : list;
}

function commaList(value: string, limit: number): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean)
    .slice(0, limit);
}

function profileName(intake: IntakePayload): string {
  return intake.kinds.find((kind) => kind.id === intake.kind)?.label || intake.kind;
}

function presetName(intake: IntakePayload, presets: StylePreset[]): string {
  return (
    presets.find((preset) => preset.id === intake.style_preset)?.name ||
    intake.style_preset ||
    "default look"
  );
}

export function BriefCard({
  slug,
  intake,
  audioWindow,
  onIntakeChange,
}: {
  slug: string;
  intake: IntakePayload;
  audioWindow: AudioWindow | null;
  onIntakeChange: (intake: IntakePayload) => void;
}) {
  const [intent, setIntent] = useState<Intent>(intake.intent || { kind: intake.kind });
  const [lists, setLists] = useState({
    reasons: listText(intake.intent?.reasons),
    mandatories: listText(intake.intent?.mandatories),
    avoid: listText(intake.intent?.avoid),
    tone: (intake.intent?.tone || []).join(", "),
  });
  const [expanded, setExpanded] = useState(
    () => !intake.intent?.message || (intake.kind === "advert" && !intake.intent?.cta?.text),
  );
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const savedTimer = useRef<number | null>(null);
  const lastSaved = useRef(JSON.stringify(intake.intent || {}));

  useEffect(() => {
    setIntent(intake.intent || { kind: intake.kind });
    setLists({
      reasons: listText(intake.intent?.reasons),
      mandatories: listText(intake.intent?.mandatories),
      avoid: listText(intake.intent?.avoid),
      tone: (intake.intent?.tone || []).join(", "),
    });
    lastSaved.current = JSON.stringify(intake.intent || {});
  }, [intake]);

  useEffect(() => {
    const open = () => setExpanded(true);
    window.addEventListener("studio:open-brief", open);
    return () => window.removeEventListener("studio:open-brief", open);
  }, []);

  useEffect(
    () => () => {
      if (savedTimer.current) window.clearTimeout(savedTimer.current);
    },
    [],
  );

  const flash = () => {
    setSaved(true);
    if (savedTimer.current) window.clearTimeout(savedTimer.current);
    savedTimer.current = window.setTimeout(() => setSaved(false), 2000);
  };

  const change = (key: keyof Intent, value: unknown) =>
    setIntent((current) => ({ ...current, [key]: value }));

  const save = async (override?: Intent) => {
    if (saving) return;
    const source = override || intent;
    const clean: Intent = {
      ...source,
      kind: intake.kind,
      reasons: (source.reasons || []).slice(0, 3),
      tone: (source.tone || []).slice(0, 3),
      cta: source.cta,
    };
    if (!clean.cta?.text?.trim() && !clean.cta?.url?.trim()) clean.cta = null;
    const bytes = JSON.stringify(clean);
    if (bytes === lastSaved.current) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await api.updateIntake(slug, { intent: clean });
      lastSaved.current = JSON.stringify(updated.intent || {});
      onIntakeChange(updated);
      flash();
      notifyProjectChanged();
    } catch (caught) {
      setError(String(caught));
    } finally {
      setSaving(false);
    }
  };

  const commitList = (key: "reasons" | "mandatories" | "avoid", limit?: number) => {
    const values = parseList(lists[key], limit);
    const next = { ...intent, [key]: values };
    setIntent(next);
    setLists((current) => ({ ...current, [key]: values.join("\n") }));
    void save(next);
  };

  const commitTone = () => {
    const values = commaList(lists.tone, 3);
    const next = { ...intent, tone: values };
    setIntent(next);
    setLists((current) => ({ ...current, tone: values.join(", ") }));
    void save(next);
  };

  const label = profileName(intake);
  const presets = intake.style_presets || [];
  const length = audioWindow
    ? audioWindow.end - audioWindow.start
    : Number(intent.length_seconds || 0);
  const cta = intent.cta;
  const summaryMessage = intent.message?.trim();
  const summaryAudience = intent.audience?.trim();

  return (
    <section className={`stage-block brief-card ${expanded ? "expanded" : ""}`}>
      <h2>
        Brief <small>{label} · the facts the film may not invent</small>
        {saved && <span className="saved-note">Saved</span>}
        {saving && <span className="saved-note">Saving…</span>}
      </h2>
      {!expanded && (
        <div className="brief-line">
          <b>
            {label} · {length ? `${length.toFixed(1)} s` : "length to set"}
          </b>{" "}
          — <i>{summaryMessage || "No message yet"}</i>
          {summaryAudience ? ` — for ${summaryAudience}` : " — for an audience to name"}
          {cta?.text || cta?.url ? (
            <>
              {" "}
              — ends on <b>{cta.text || cta.url}</b>
              {cta.url ? ` → ${cta.url}` : ""}
            </>
          ) : (
            " — no ending yet"
          )}{" "}
          · Look: {presetName(intake, presets)}
        </div>
      )}
      {!expanded && (
        <div className="row-actions">
          <Button size="small" onClick={() => setExpanded(true)}>
            Edit
          </Button>
        </div>
      )}
      {expanded && (
        <div className="brief-groups">
          <fieldset>
            <legend>The point</legend>
            <Field label="Objective">
              <textarea
                rows={2}
                value={intent.objective || ""}
                onChange={(event) => change("objective", event.target.value)}
                onBlur={() => void save()}
                placeholder="What should this make someone do?"
              />
            </Field>
            <Field label="One message">
              <input
                value={intent.message || ""}
                onChange={(event) => change("message", event.target.value)}
                onBlur={() => void save()}
                placeholder="The one thing a stranger should repeat"
                maxLength={400}
              />
            </Field>
            <Field label="Reasons (up to three, one per line)">
              <textarea
                rows={3}
                value={lists.reasons}
                onChange={(event) =>
                  setLists((current) => ({ ...current, reasons: event.target.value }))
                }
                onBlur={() => commitList("reasons", 3)}
                placeholder="Facts that support the message"
              />
            </Field>
          </fieldset>
          <fieldset>
            <legend>Who and how</legend>
            <Field label="Audience">
              <input
                value={intent.audience || ""}
                onChange={(event) => change("audience", event.target.value)}
                onBlur={() => void save()}
                placeholder="Who is this for?"
              />
            </Field>
            <Field label="Tone (up to three, comma separated)">
              <input
                value={lists.tone}
                onChange={(event) =>
                  setLists((current) => ({ ...current, tone: event.target.value }))
                }
                onBlur={commitTone}
                placeholder="warm, wry, direct"
              />
            </Field>
            <Field label="Must have (one per line)">
              <textarea
                rows={3}
                value={lists.mandatories}
                onChange={(event) =>
                  setLists((current) => ({ ...current, mandatories: event.target.value }))
                }
                onBlur={() => commitList("mandatories")}
                placeholder="A product, line or fact that must appear"
              />
            </Field>
            <Field label="Avoid (one per line)">
              <textarea
                rows={2}
                value={lists.avoid}
                onChange={(event) =>
                  setLists((current) => ({ ...current, avoid: event.target.value }))
                }
                onBlur={() => commitList("avoid")}
                placeholder="Claims, images or words to leave out"
              />
            </Field>
          </fieldset>
          <fieldset>
            <legend>Ending</legend>
            <Field label={intake.kind === "advert" ? "Call to action" : "Ending line"}>
              <input
                value={cta?.text || ""}
                onChange={(event) =>
                  change("cta", { text: event.target.value, url: cta?.url || "" })
                }
                onBlur={() => void save()}
                placeholder={intake.kind === "advert" ? "Pre-save now" : "Out now"}
                maxLength={120}
              />
            </Field>
            <Field label="Link">
              <input
                value={cta?.url || ""}
                onChange={(event) =>
                  change("cta", { text: cta?.text || "", url: event.target.value })
                }
                onBlur={() => void save()}
                placeholder="example.com"
                maxLength={300}
              />
            </Field>
          </fieldset>
        </div>
      )}
      {expanded && (
        <div className="row-actions">
          <Button size="small" variant="quiet" onClick={() => setExpanded(false)}>
            Done
          </Button>
          <span className="hint">Changes save when you leave a field.</span>
        </div>
      )}
      {error && <p className="error">{error}</p>}
    </section>
  );
}
