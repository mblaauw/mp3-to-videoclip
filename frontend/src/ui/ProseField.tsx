import { useEffect, useRef, useState } from "react";
import { AutoTextarea } from "./AutoTextarea";
import { Markdown } from "./Markdown";

/**
 * Long text that is mostly *read* (a treatment, a concept): shown as set type
 * at a reading measure, and turned into an editor with one click or keypress.
 * Editing keeps the same typography, so switching modes does not reflow the
 * page under the cursor.
 */
export function ProseField({
  value,
  onChange,
  onCommit,
  placeholder,
  label,
  minRows = 8,
  maxRows = 40,
  disabled = false,
}: {
  value: string;
  onChange: (value: string) => void;
  /** Called when editing ends (blur or Escape). */
  onCommit?: () => void;
  placeholder: string;
  label: string;
  minRows?: number;
  maxRows?: number;
  disabled?: boolean;
}) {
  const [editing, setEditing] = useState(false);
  const area = useRef<HTMLTextAreaElement>(null);

  useEffect(() => {
    if (editing) {
      const element = area.current;
      element?.focus();
      // Start at the end; a click into prose should not jump to the top.
      if (element) element.setSelectionRange(element.value.length, element.value.length);
    }
  }, [editing]);

  if (!editing && value.trim()) {
    return (
      <div className="prose-field">
        <div
          className="prose-read"
          role="button"
          tabIndex={disabled ? -1 : 0}
          aria-label={`${label}. Press Enter to edit.`}
          onClick={(event) => {
            // Let people select and copy text without dropping into the editor.
            if (window.getSelection()?.toString()) return;
            if ((event.target as HTMLElement).closest("a")) return;
            if (!disabled) setEditing(true);
          }}
          onKeyDown={(event) => {
            if (disabled) return;
            if (event.key === "Enter" || event.key === "e") {
              event.preventDefault();
              setEditing(true);
            }
          }}
        >
          <Markdown text={value} className="prose" />
        </div>
        {!disabled && (
          <button type="button" className="prose-edit" onClick={() => setEditing(true)}>
            Edit
          </button>
        )}
      </div>
    );
  }

  return (
    <div className="prose-field editing">
      <AutoTextarea
        ref={area}
        className="prose-input"
        value={value}
        minRows={minRows}
        maxRows={maxRows}
        disabled={disabled}
        placeholder={placeholder}
        aria-label={label}
        onChange={(event) => onChange(event.target.value)}
        onFocus={() => setEditing(true)}
        onBlur={() => {
          setEditing(false);
          onCommit?.();
        }}
        onKeyDown={(event) => {
          if (event.key === "Escape") {
            event.preventDefault();
            (event.target as HTMLTextAreaElement).blur();
          }
        }}
      />
      {editing && (
        <p className="prose-help">
          Markdown is fine: blank line for a new paragraph, <code>## </code> for a heading,{" "}
          <code>- </code> for a list. Esc to finish.
        </p>
      )}
    </div>
  );
}
