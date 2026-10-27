import { useEffect, useRef, useState } from "react";
import { api, type Brief, type IntakePayload } from "../api";
import { notifyProjectChanged } from "../shell/projectEvents";
import { Button, Field } from "../ui";

function additionsFor(look: string, presetLook: string | undefined): string {
  if (!look) return "";
  if (presetLook && look === presetLook) return "";
  if (presetLook && look.startsWith(`${presetLook}\n\n`)) {
    return look.slice(presetLook.length + 2);
  }
  return look;
}

export function LookCard({
  slug,
  intake,
  brief,
  onIntakeChange,
  onBriefChange,
}: {
  slug: string;
  intake: IntakePayload;
  brief: Brief;
  onIntakeChange: (intake: IntakePayload) => void;
  onBriefChange: (brief: Brief) => void;
}) {
  const allPresets = intake.style_presets || [];
  const allowed = intake.kinds.find((kind) => kind.id === intake.kind)?.style_presets || [];
  const presets = allowed.length
    ? allPresets.filter((item) => allowed.includes(item.id))
    : allPresets;
  const preset = presets.find((item) => item.id === intake.style_preset);
  const [additions, setAdditions] = useState(() =>
    additionsFor(brief.creative?.look || "", preset?.look),
  );
  const [saved, setSaved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<number | null>(null);
  const lastSaved = useRef(brief.creative?.look || "");

  useEffect(() => {
    setAdditions(additionsFor(brief.creative?.look || "", preset?.look));
    lastSaved.current = brief.creative?.look || "";
  }, [brief.creative?.look, preset?.look]);

  useEffect(
    () => () => {
      if (timer.current) window.clearTimeout(timer.current);
    },
    [],
  );

  const flash = () => {
    setSaved(true);
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setSaved(false), 2000);
  };

  const nextLook = () => {
    if (!preset?.look) return additions.trim();
    return additions.trim() ? `${preset.look}\n\n${additions.trim()}` : preset.look;
  };

  const save = async () => {
    const value = nextLook();
    if (saving || value === lastSaved.current) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await api.patchBrief(slug, { creative: { look: value } });
      lastSaved.current = updated.creative?.look || "";
      onBriefChange(updated);
      flash();
      notifyProjectChanged();
    } catch (caught) {
      setError(String(caught));
    } finally {
      setSaving(false);
    }
  };

  const changePreset = async (id: string) => {
    setSaving(true);
    setError(null);
    try {
      const updatedIntake = await api.updateIntake(slug, { style_preset: id });
      onIntakeChange(updatedIntake);
      if (!id) {
        // Custom only detaches the preset. The saved look stays exactly as it is.
        lastSaved.current = brief.creative?.look || "";
        flash();
        notifyProjectChanged();
        return;
      }
      const chosen = updatedIntake.style_presets.find((item) => item.id === id);
      const withAdditions = chosen?.look
        ? additions.trim()
          ? `${chosen.look}\n\n${additions.trim()}`
          : chosen.look
        : additions.trim();
      const updatedBrief = await api.patchBrief(slug, {
        creative: { look: withAdditions },
      });
      lastSaved.current = updatedBrief.creative?.look || "";
      onBriefChange(updatedBrief);
      flash();
      notifyProjectChanged();
    } catch (caught) {
      setError(String(caught));
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="stage-block look-card">
      <h2>
        Look <small>One appearance every picture shares</small>
        {saved && <span className="saved-note">Saved</span>}
        {saving && <span className="saved-note">Saving…</span>}
      </h2>
      <div className="look-preset">
        <div className={`look-swatch preset-${preset?.id || "custom"}`} aria-hidden="true">
          <span>{preset?.name || "Custom"}</span>
        </div>
        <div className="look-preset-text">
          <label className="ui-field">
            <span>Style preset</span>
            <select value={intake.style_preset || ""} onChange={(event) => void changePreset(event.target.value)}>
              <option value="">Custom</option>
              {presets.map((item) => (
                <option key={item.id} value={item.id}>
                  {item.name}
                </option>
              ))}
            </select>
          </label>
          <p className="hint">{preset?.description || "A custom appearance."}</p>
        </div>
      </div>
      <Field label={preset ? "Film-specific additions" : "Look"}>
        <textarea
          rows={4}
          value={additions}
          onChange={(event) => setAdditions(event.target.value)}
          onBlur={() => void save()}
          placeholder="Wet sodium streets, one cold light source per frame…"
        />
      </Field>
      {(brief.creative?.image_rules || []).length > 0 && (
        <div className="chips">
          {(brief.creative?.image_rules || []).map((rule) => (
            <span className="ui-chip" key={rule}>
              {rule}
            </span>
          ))}
        </div>
      )}
      {error && <p className="error">{error}</p>}
      {!preset && (
        <Button size="small" variant="quiet" onClick={() => void save()}>
          Save look
        </Button>
      )}
    </section>
  );
}
