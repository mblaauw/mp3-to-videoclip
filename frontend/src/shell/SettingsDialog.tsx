import { useEffect, useRef, useState, type ReactNode } from "react";
import { api, type Settings, type SettingsTest, type SetupStatus } from "../api";
import { Button, ErrorState, useFocusTrap } from "../ui";
import { CloseIcon } from "../ui/icons";

export const SHOW_EDIT_FILE = "studio.showEditFile";

type Draft = {
  runware_api_key: string;
  llm_api_key: string;
  gateway: "opencode" | "direct";
  writer_model: string;
  editor_model: string;
  opencode_bin: string;
  opencode_workspace: string;
  brand_name: string;
  brand_partner: string;
  default_budget_usd: string;
  image_reserve_usd: string;
  default_credit_roles: string;
  remotion_dir: string;
  ffmpeg_path: string;
  show_edit_file: boolean;
};

function draftFrom(settings: Settings): Draft {
  return {
    runware_api_key: "",
    llm_api_key: "",
    gateway: settings.gateway === "opencode" ? "opencode" : "direct",
    writer_model: String(settings.writer_model || ""),
    editor_model: String(settings.editor_model || ""),
    opencode_bin: String(settings.opencode_bin || "opencode"),
    opencode_workspace: String(settings.opencode_workspace || ""),
    brand_name: String(settings.brand_name || ""),
    brand_partner: String(settings.brand_partner || ""),
    default_budget_usd: String(settings.default_budget_usd ?? 5),
    image_reserve_usd: String(settings.image_reserve_usd ?? 0.05),
    default_credit_roles: (settings.default_credit_roles || []).join(", "),
    remotion_dir: String(settings.remotion_dir || ""),
    ffmpeg_path: String(settings.ffmpeg_path || ""),
    show_edit_file: window.localStorage.getItem(SHOW_EDIT_FILE) === "1",
  };
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="settings-field">
      <span>{label}</span>
      {children}
      {hint && <em>{hint}</em>}
    </label>
  );
}

export function SettingsDialog({
  onClose,
  onSaved,
}: {
  onClose: () => void;
  onSaved: () => void;
}) {
  const [settings, setSettings] = useState<Settings | null>(null);
  const [setup, setSetup] = useState<SetupStatus | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);
  const [runware, setRunware] = useState<SettingsTest | null>(null);
  const [opencode, setOpencode] = useState<SettingsTest | null>(null);
  const dialog = useRef<HTMLDivElement>(null);
  useFocusTrap(true, dialog);

  const load = () => {
    api
      .settings()
      .then((value) => {
        setSettings(value);
        setDraft(draftFrom(value));
      })
      .catch((caught) => setError(String(caught)));
    api
      .setup()
      .then(setSetup)
      .catch(() => setSetup(null));
  };

  useEffect(() => {
    load();
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => {
    setDraft((current) => (current ? { ...current, [key]: value } : current));
    setSaved(false);
  };

  const payload = (current: Draft): Record<string, unknown> => {
    const body: Record<string, unknown> = {
      gateway: current.gateway,
      writer_model: current.writer_model.trim(),
      editor_model: current.editor_model.trim(),
      opencode_bin: current.opencode_bin.trim(),
      opencode_workspace: current.opencode_workspace.trim(),
      brand_name: current.brand_name.trim(),
      brand_partner: current.brand_partner.trim(),
      default_budget_usd: Number(current.default_budget_usd || 0),
      image_reserve_usd: Number(current.image_reserve_usd || 0.05),
      default_credit_roles: current.default_credit_roles
        .split(",")
        .map((role) => role.trim())
        .filter(Boolean),
      remotion_dir: current.remotion_dir.trim(),
      ffmpeg_path: current.ffmpeg_path.trim(),
    };
    // An empty secret means "keep the stored key"; never erase it by saving.
    if (current.runware_api_key.trim()) body.runware_api_key = current.runware_api_key.trim();
    if (current.llm_api_key.trim()) body.llm_api_key = current.llm_api_key.trim();
    return body;
  };

  const save = async (announce = true) => {
    if (!draft || busy) return false;
    setBusy("save");
    setError(null);
    try {
      const value = await api.saveSettings(payload(draft));
      setSettings(value);
      setDraft((current) => (current ? { ...current, ...draftFrom(value) } : current));
      window.localStorage.setItem(SHOW_EDIT_FILE, draft.show_edit_file ? "1" : "0");
      if (announce) setSaved(true);
      onSaved();
      return true;
    } catch (caught) {
      setError(String(caught));
      return false;
    } finally {
      setBusy(null);
    }
  };

  const test = async (kind: "runware" | "opencode") => {
    if (!draft) return;
    setBusy(kind);
    setError(null);
    if (kind === "runware") setRunware(null);
    else setOpencode(null);
    const stored = await save(false);
    if (!stored) {
      setBusy(null);
      return;
    }
    try {
      const result = await api.testSettings(kind);
      if (kind === "runware") setRunware(result);
      else setOpencode(result);
    } catch (caught) {
      setError(String(caught));
    } finally {
      setBusy(null);
    }
  };

  const hasRunware = settings?.has_runware_api_key === true;
  const hasDirectorKey = settings?.has_llm_api_key === true;
  const tools: [string, boolean][] = setup
    ? [
        ["Renderer", setup.renderer],
        ["Chrome", setup.chrome],
        ["Node", setup.node],
        ["FFmpeg", setup.ffmpeg],
        ["ffprobe", setup.ffprobe],
      ]
    : [];

  return (
    <div
      className="settings-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        className="settings-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="settings-title"
        ref={dialog}
      >
        <header>
          <div>
            <h2 id="settings-title">Settings</h2>
            <p>Stored on this computer only. Every save keeps an existing key unless you type a new one.</p>
          </div>
          <button type="button" className="icon-btn" aria-label="Close settings" onClick={onClose}>
            <CloseIcon />
          </button>
        </header>

        {!draft ? (
          error ? (
            <div className="settings-body">
              <ErrorState what="reading settings" error={error} onRetry={load} />
            </div>
          ) : (
            <div className="settings-loading">Reading settings…</div>
          )
        ) : (
          <div className="settings-body">
            {error && <ErrorState what="saving settings" error={error} compact />}
            <section className="settings-section">
              <h3>Director</h3>
              <div className="settings-grid">
                <Field label="Gateway" hint="OpenCode runs the local CLI; Direct API calls the configured endpoint.">
                  <select
                    value={draft.gateway}
                    onChange={(event) =>
                      set("gateway", event.target.value === "opencode" ? "opencode" : "direct")
                    }
                  >
                    <option value="opencode">OpenCode</option>
                    <option value="direct">Direct API</option>
                  </select>
                </Field>
                <Field label="Writer model" hint="Story, storyboard and images.">
                  <input
                    value={draft.writer_model}
                    onChange={(event) => set("writer_model", event.target.value)}
                    placeholder="provider/model"
                  />
                </Field>
                <Field label="Editor model" hint="Track and film (the cut).">
                  <input
                    value={draft.editor_model}
                    onChange={(event) => set("editor_model", event.target.value)}
                    placeholder="provider/model"
                  />
                </Field>
                {draft.gateway === "direct" && (
                  <Field
                    label="Direct API key"
                    hint={
                      hasDirectorKey
                        ? "A key is stored. Leave empty to keep it."
                        : "The director has no model key yet."
                    }
                  >
                    <input
                      type="password"
                      value={draft.llm_api_key}
                      onChange={(event) => set("llm_api_key", event.target.value)}
                      placeholder={hasDirectorKey ? "Stored" : "sk-…"}
                      autoComplete="off"
                    />
                  </Field>
                )}
                <Field label="OpenCode path" hint="Leave as “opencode” to use the one on this computer.">
                  <input
                    value={draft.opencode_bin}
                    onChange={(event) => set("opencode_bin", event.target.value)}
                    placeholder="/usr/local/bin/opencode"
                  />
                </Field>
                <Field label="OpenCode workspace" hint="Optional; a folder the gateway may use.">
                  <input
                    value={draft.opencode_workspace}
                    onChange={(event) => set("opencode_workspace", event.target.value)}
                    placeholder="Leave empty for the default"
                  />
                </Field>
              </div>
              <div className="settings-row">
                <Button size="small" onClick={() => void test("opencode")} disabled={busy !== null}>
                  {busy === "opencode" ? "Checking…" : "Test OpenCode"}
                </Button>
                {opencode && (
                  <span className={opencode.ok ? "settings-good" : "settings-bad"}>
                    {opencode.message}
                  </span>
                )}
              </div>
            </section>

            <section className="settings-section">
              <h3>Pictures</h3>
              <div className="settings-grid">
                <Field
                  label="Runware key"
                  hint={hasRunware ? "A key is stored. Leave empty to keep it." : "Required to make stills."}
                >
                  <input
                    type="password"
                    value={draft.runware_api_key}
                    onChange={(event) => set("runware_api_key", event.target.value)}
                    placeholder={hasRunware ? "Stored" : "Paste the key"}
                    autoComplete="off"
                  />
                </Field>
                <Field label="Reserve per still" hint="The price shown on every picture button.">
                  <input
                    type="number"
                    min="0.01"
                    max="10"
                    step="0.01"
                    value={draft.image_reserve_usd}
                    onChange={(event) => set("image_reserve_usd", event.target.value)}
                  />
                </Field>
              </div>
              <div className="settings-row">
                <Button size="small" onClick={() => void test("runware")} disabled={busy !== null}>
                  {busy === "runware" ? "Checking…" : "Test Runware"}
                </Button>
                {runware && (
                  <span className={runware.ok ? "settings-good" : "settings-bad"}>
                    {runware.message}
                  </span>
                )}
              </div>
            </section>

            <section className="settings-section">
              <h3>New films start with</h3>
              <div className="settings-grid">
                <Field label="Budget" hint="A starting cap in US dollars; you can raise it later.">
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    value={draft.default_budget_usd}
                    onChange={(event) => set("default_budget_usd", event.target.value)}
                  />
                </Field>
                <Field label="Opening names" hint="Shown in the opening and closing graphics.">
                  <span className="settings-pair">
                    <input
                      value={draft.brand_name}
                      onChange={(event) => set("brand_name", event.target.value)}
                      aria-label="Brand name"
                      placeholder="Artist or brand"
                    />
                    <input
                      value={draft.brand_partner}
                      onChange={(event) => set("brand_partner", event.target.value)}
                      aria-label="Brand partner"
                      placeholder="Partner"
                    />
                  </span>
                </Field>
                <Field label="Default credit roles" hint="Comma separated, e.g. director, music, visuals.">
                  <input
                    value={draft.default_credit_roles}
                    onChange={(event) => set("default_credit_roles", event.target.value)}
                  />
                </Field>
              </div>
            </section>

            <section className="settings-section">
              <h3>This computer</h3>
              <div className="settings-tools">
                {tools.length ? (
                  tools.map(([label, ok]) => (
                    <span key={label} className={ok ? "settings-good" : "settings-bad"}>
                      {label} {ok ? "ready" : "missing"}
                    </span>
                  ))
                ) : (
                  <span className="settings-muted">Tool check unavailable.</span>
                )}
              </div>
              <div className="settings-grid">
                <Field label="Renderer folder" hint="Leave empty for the pinned local renderer.">
                  <input
                    value={draft.remotion_dir}
                    onChange={(event) => set("remotion_dir", event.target.value)}
                    placeholder="Pinned renderer"
                  />
                </Field>
                <Field label="FFmpeg path" hint="Leave empty to use the one on PATH.">
                  <input
                    value={draft.ffmpeg_path}
                    onChange={(event) => set("ffmpeg_path", event.target.value)}
                    placeholder="ffmpeg"
                  />
                </Field>
              </div>
            </section>

            <section className="settings-section">
              <h3>Advanced</h3>
              <label className="settings-check">
                <input
                  type="checkbox"
                  checked={draft.show_edit_file}
                  onChange={(event) => set("show_edit_file", event.target.checked)}
                />
                Show the edit file on Film (read-only)
              </label>
              <p className="settings-muted">
                Changes go through the Editor or the cut controls. The JSON is for inspection only.
              </p>
            </section>
          </div>
        )}

        <footer>
          <span className="settings-state">
            {error ? (
              <span className="settings-bad">Something went wrong. Details are in the log.</span>
            ) : saved ? (
              "Saved"
            ) : (
              ""
            )}
          </span>
          <Button variant="quiet" onClick={onClose}>
            Close
          </Button>
          <Button variant="primary" onClick={() => void save()} disabled={!draft || busy !== null}>
            {busy === "save" ? "Saving…" : "Save settings"}
          </Button>
        </footer>
      </div>
    </div>
  );
}
