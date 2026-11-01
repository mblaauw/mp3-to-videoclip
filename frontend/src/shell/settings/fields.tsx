import { createContext, useContext, useEffect, useId, useRef, useState, type ReactNode } from "react";
import type { Settings } from "../../api";
import { SaveState, type SaveStatus } from "../../ui/SaveState";
import { matches, patchAt, readAt, type Catalog } from "./settingsModel";

export type Panel = {
  settings: Settings;
  catalog: Catalog;
  query: string;
  save: (patch: Record<string, unknown>) => Promise<void>;
  /** Resolves once every save already started has landed. */
  settled: () => Promise<unknown>;
  reloadCatalog: () => Promise<void>;
};

export const PanelContext = createContext<Panel | null>(null);

export function usePanel(): Panel {
  const panel = useContext(PanelContext);
  if (!panel) throw new Error("usePanel outside the settings panel");
  return panel;
}

/** Saves one field and says so beside it. */
function useFieldSave(path: string) {
  const { save } = usePanel();
  const [status, setStatus] = useState<SaveStatus>("idle");
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const last = useRef<unknown>(undefined);
  const commit = async (value: unknown) => {
    last.current = value;
    setStatus("saving");
    try {
      await save(patchAt(path, value));
      setSavedAt(Date.now());
      setStatus("saved");
    } catch {
      setStatus("error");
    }
  };
  return { status, savedAt, commit, retry: () => void commit(last.current) };
}

export function Section({
  title,
  note,
  action,
  children,
}: {
  title: string;
  note?: string;
  action?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="settings-section">
      <div className="settings-section-head">
        <h3>{title}</h3>
        {action}
      </div>
      {note && <p className="settings-note">{note}</p>}
      <div className="settings-grid">{children}</div>
    </section>
  );
}

/** One labelled row. While searching, a row that does not match is not drawn. */
export function Row({
  id,
  label,
  hint,
  extra,
  children,
}: {
  id?: string;
  label: string;
  hint?: string;
  extra?: ReactNode;
  children: ReactNode;
}) {
  const { query } = usePanel();
  const auto = useId();
  if (!matches(query, label, hint)) return null;
  return (
    <div className="settings-field">
      <label htmlFor={id ?? auto}>{label}</label>
      <FieldId.Provider value={id ?? auto}>{children}</FieldId.Provider>
      {hint && <em>{hint}</em>}
      {extra}
    </div>
  );
}

const FieldId = createContext("");

export function useFieldId(): string {
  return useContext(FieldId);
}

export function TextRow({
  path,
  label,
  hint,
  placeholder,
  id,
}: {
  path: string;
  label: string;
  hint?: string;
  placeholder?: string;
  id?: string;
}) {
  const { settings } = usePanel();
  const stored = String(readAt(settings, path) ?? "");
  const [value, setValue] = useState(stored);
  const field = useFieldSave(path);
  useEffect(() => setValue(stored), [stored]);
  return (
    <Row id={id} label={label} hint={hint} extra={<SaveState status={field.status} savedAt={field.savedAt} onRetry={field.retry} />}>
      <Input
        value={value}
        placeholder={placeholder}
        onChange={setValue}
        onBlur={() => {
          if (value.trim() !== stored) void field.commit(value.trim());
        }}
      />
    </Row>
  );
}

function Input({
  value,
  onChange,
  onBlur,
  placeholder,
  type = "text",
  min,
  max,
  step,
}: {
  value: string;
  onChange: (value: string) => void;
  onBlur: () => void;
  placeholder?: string;
  type?: string;
  min?: string;
  max?: string;
  step?: string;
}) {
  return (
    <input
      id={useFieldId()}
      type={type}
      value={value}
      placeholder={placeholder}
      min={min}
      max={max}
      step={step}
      autoComplete="off"
      onChange={(event) => onChange(event.target.value)}
      onBlur={onBlur}
    />
  );
}

export function NumberRow({
  path,
  label,
  hint,
  min = "0",
  max,
  step = "1",
  extra,
}: {
  path: string;
  label: string;
  hint?: string;
  min?: string;
  max?: string;
  step?: string;
  extra?: ReactNode;
}) {
  const { settings } = usePanel();
  const stored = String(readAt(settings, path) ?? "");
  const [value, setValue] = useState(stored);
  const field = useFieldSave(path);
  useEffect(() => setValue(stored), [stored]);
  return (
    <Row
      label={label}
      hint={hint}
      extra={
        <>
          {extra}
          <SaveState status={field.status} savedAt={field.savedAt} onRetry={field.retry} />
        </>
      }
    >
      <Input
        type="number"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={setValue}
        onBlur={() => {
          if (value !== stored && value !== "") void field.commit(Number(value));
        }}
      />
    </Row>
  );
}

export type Option = { value: string; label: string };

const OTHER = "__other__";

/**
 * A dropdown with an "Other…" row that turns into a text field, so an id the
 * catalogue does not know yet never blocks the owner.
 */
export function ChoiceRow({
  path,
  label,
  hint,
  options,
  free = true,
  extra,
}: {
  path: string;
  label: string;
  hint?: string;
  options: Option[];
  free?: boolean;
  extra?: ReactNode;
}) {
  const { settings } = usePanel();
  const stored = String(readAt(settings, path) ?? "");
  const known = options.some((option) => option.value === stored);
  const [typing, setTyping] = useState(false);
  const [text, setText] = useState(stored);
  const field = useFieldSave(path);
  useEffect(() => {
    setText(stored);
    setTyping(false);
  }, [stored]);
  const showText = free && (typing || !known);
  const id = useId();
  return (
    <Row
      id={id}
      label={label}
      hint={hint}
      extra={
        <>
          {extra}
          <SaveState status={field.status} savedAt={field.savedAt} onRetry={field.retry} />
        </>
      }
    >
      {showText ? (
        <span className="settings-other">
          <Input
            value={text}
            placeholder="Type the id"
            onChange={setText}
            onBlur={() => {
              if (text.trim() && text.trim() !== stored) void field.commit(text.trim());
            }}
          />
          {options.length > 0 && (
            <button
              type="button"
              className="settings-link"
              onClick={() => {
                setTyping(false);
                if (!known) void field.commit(options[0].value);
              }}
            >
              Use the list
            </button>
          )}
        </span>
      ) : (
        <select
          id={id}
          value={stored}
          onChange={(event) => {
            if (event.target.value === OTHER) setTyping(true);
            else void field.commit(event.target.value);
          }}
        >
          {options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
          {free && <option value={OTHER}>Other…</option>}
        </select>
      )}
    </Row>
  );
}

export function ToggleRow({
  path,
  label,
  hint,
}: {
  path: string;
  label: string;
  hint?: string;
}) {
  const { settings, query } = usePanel();
  const field = useFieldSave(path);
  if (!matches(query, label, hint)) return null;
  return (
    <div className="settings-field">
      <label className="settings-check">
        <input
          type="checkbox"
          checked={readAt(settings, path) === true}
          onChange={(event) => void field.commit(event.target.checked)}
        />
        {label}
      </label>
      {hint && <em>{hint}</em>}
      <SaveState status={field.status} savedAt={field.savedAt} onRetry={field.retry} />
    </div>
  );
}

/** Words typed with commas, stored as a list. */
export function ListRow({
  path,
  label,
  hint,
  placeholder,
}: {
  path: string;
  label: string;
  hint?: string;
  placeholder?: string;
}) {
  const { settings } = usePanel();
  const raw = readAt(settings, path);
  const stored = Array.isArray(raw) ? raw.join(", ") : "";
  const [value, setValue] = useState(stored);
  const field = useFieldSave(path);
  useEffect(() => setValue(stored), [stored]);
  return (
    <Row label={label} hint={hint} extra={<SaveState status={field.status} savedAt={field.savedAt} onRetry={field.retry} />}>
      <Input
        value={value}
        placeholder={placeholder}
        onChange={setValue}
        onBlur={() => {
          if (value === stored) return;
          void field.commit(
            value
              .split(",")
              .map((item) => item.trim())
              .filter(Boolean),
          );
        }}
      />
    </Row>
  );
}
