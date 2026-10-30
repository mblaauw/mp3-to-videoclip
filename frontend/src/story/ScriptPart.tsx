import { AutoTextarea } from "../ui/AutoTextarea";
import { ProseField } from "../ui/ProseField";
import { SaveState } from "../ui/SaveState";
import type { StoryData } from "./useStoryData";

/** One sentence: Enter finishes the field instead of breaking the line. */
function finishOnEnter(event: React.KeyboardEvent<HTMLTextAreaElement>) {
  if (event.key === "Enter") {
    event.preventDefault();
    event.currentTarget.blur();
  }
}

export function ScriptPart({ story }: { story: StoryData }) {
  const {
    brief,
    direction,
    style,
    treatment,
    saveStatus,
    savedAt,
    treatmentBase,
    treatmentRef,
    fieldsBase,
    setDirection,
    setStyle,
    setTreatment,
    setSaveFailed,
    setFieldsDirty,
    saveFields,
    saveTreatment,
  } = story;
  const fieldChanged = () => {
    fieldsBase.current ??= brief;
    setSaveFailed(false);
    setFieldsDirty(true);
  };
  return (
    <section className="stage-block treatment-block">
      <h2>
        Treatment
        <SaveState
          status={saveStatus}
          savedAt={savedAt}
          onRetry={() => {
            void saveTreatment(treatmentRef.current);
            void saveFields();
          }}
        />
      </h2>
      <div className="direction-style">
        <label>
          Direction
          <AutoTextarea
            minRows={1}
            maxRows={5}
            value={direction}
            onChange={(event) => {
              setDirection(event.target.value.replace(/\n/g, " "));
              fieldChanged();
            }}
            onKeyDown={finishOnEnter}
            onBlur={() => window.setTimeout(() => void saveFields(), 0)}
            placeholder="What kind of film is this?"
            maxLength={1000}
          />
        </label>
        <label>
          Style
          <AutoTextarea
            minRows={1}
            maxRows={5}
            value={style}
            onChange={(event) => {
              setStyle(event.target.value.replace(/\n/g, " "));
              fieldChanged();
            }}
            onKeyDown={finishOnEnter}
            onBlur={() => window.setTimeout(() => void saveFields(), 0)}
            placeholder="One honest sentence about the medium"
            maxLength={1000}
          />
        </label>
      </div>
      <ProseField
        label="Treatment"
        value={treatment}
        minRows={12}
        onChange={(value) => {
          treatmentBase.current ??= brief;
          setSaveFailed(false);
          setTreatment(value);
          treatmentRef.current = value;
        }}
        onCommit={() => void saveTreatment(treatmentRef.current)}
        placeholder="The story from the first frame to the last. It saves as you type."
      />
      <p className="hint">
        Click the text to edit. It saves a moment after you stop typing; there is no Save button.
      </p>
    </section>
  );
}
