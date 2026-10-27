import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  type ApprovalChanges,
  type ApprovalState,
  type AudioWindow,
  type Brief,
  type IntakePayload,
  type TreatmentsPayload,
} from "../api";
import { ApprovalBar, useApprovals } from "../ApprovalBar";
import { ArtifactRating } from "../ArtifactRating";
import { notifyProjectChanged, useProjectChanged } from "../shell/projectEvents";
import { SaveState, type SaveStatus } from "../ui/SaveState";
import { ProseField } from "../ui/ProseField";
import { AutoTextarea } from "../ui/AutoTextarea";
import { Button, EmptyState, ErrorState, LoadingState } from "../ui";
import { BriefCard } from "../story/BriefCard";
import { CharactersCard } from "../story/CharactersCard";
import { CreditsCard } from "../story/CreditsCard";
import { LookCard } from "../story/LookCard";
import { ProfileCard } from "../story/ProfileCard";

function conceptPrompt(hasTreatment = false): string {
  if (hasTreatment) {
    return (
      "Give me three new directions that build on the treatment in brief.treatment. " +
      "Keep its story, characters and ending and stay structurally different from each other."
    );
  }
  return "Give me three new directions for this film. Keep them structurally different and concrete.";
}

const IMPORT_PROMPT =
  "The concept I already had is saved as brief.treatment. Read it with get_brief first. " +
  "Keep its story, characters and ending, improve only what is weak, vague or not shootable, " +
  "and save the improved treatment with update_brief. Then propose three structurally different " +
  "concepts that build on it instead of replacing it.";

function sectionLength(window: AudioWindow | null): number {
  return window ? Math.max(0, window.end - window.start) : 0;
}

export function StoryStage({
  slug,
  intake,
  audioWindow,
  windowLocked = false,
  onIntakeChange,
}: {
  slug: string;
  intake: IntakePayload | null;
  audioWindow: AudioWindow | null;
  windowLocked?: boolean;
  onIntakeChange: (intake: IntakePayload) => void;
}) {
  const [brief, setBrief] = useState<Brief | null>(null);
  const [treatments, setTreatments] = useState<TreatmentsPayload | null>(null);
  const [changes, setChanges] = useState<ApprovalChanges | null>(null);
  const [treatment, setTreatment] = useState("");
  const [direction, setDirection] = useState("");
  const [style, setStyle] = useState("");
  const [savingTreatment, setSavingTreatment] = useState(false);
  const [savingFields, setSavingFields] = useState(false);
  const [fieldsDirty, setFieldsDirty] = useState(false);
  const [importText, setImportText] = useState("");
  const [importing, setImporting] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const treatmentLast = useRef("");
  const treatmentRef = useRef("");
  const savingRef = useRef(false);

  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [saveFailed, setSaveFailed] = useState(false);
  const flashSaved = () => {
    setSavedAt(Date.now());
    setSaveFailed(false);
  };

  const load = useCallback(async () => {
    try {
      const [nextBrief, nextTreatments] = await Promise.all([
        api.brief(slug),
        api.treatments(slug),
      ]);
      setBrief(nextBrief);
      setTreatments(nextTreatments);
      setTreatment(nextBrief.treatment || "");
      setDirection(nextBrief.direction || "");
      setStyle(nextBrief.style || "");
      treatmentRef.current = nextBrief.treatment || "";
      treatmentLast.current = nextBrief.treatment || "";
      setError(null);
    } catch (caught) {
      setError(String(caught));
    } finally {
      setLoading(false);
    }
  }, [slug]);

  useEffect(() => {
    setBrief(null);
    setTreatments(null);
    setChanges(null);
    setTreatment("");
    setDirection("");
    setStyle("");
    treatmentRef.current = "";
    setLoading(true);
    void load();
  }, [load]);

  useProjectChanged(slug, () => {
    setRevision((value) => value + 1);
    // The Writer can rewrite the brief while this stage stays mounted. Reload
    // it unless a reload would overwrite input the user has not saved yet.
    if (
      savingRef.current ||
      savingFields ||
      fieldsDirty ||
      treatmentRef.current !== treatmentLast.current
    ) {
      return;
    }
    void load();
  });

  useEffect(() => {
    if (!intake) {
      api
        .intake(slug)
        .then(onIntakeChange)
        .catch(() => {});
    }
  }, [intake, onIntakeChange, slug]);

  const approval: ApprovalState | null = useApprovals().states.brief || null;

  useEffect(() => {
    if (approval?.state !== "stale") {
      setChanges(null);
      return;
    }
    api
      .approvalChanges(slug, "brief")
      .then(setChanges)
      .catch(() => setChanges(null));
  }, [slug, approval?.state, approval?.expected_hash, revision]);

  const saveTreatment = useCallback(
    async (value: string) => {
      if (!brief || savingRef.current || value === treatmentLast.current) return;
      savingRef.current = true;
      setSavingTreatment(true);
      setError(null);
      try {
        const updated = await api.patchBrief(slug, { treatment: value });
        treatmentLast.current = updated.treatment || "";
        setBrief(updated);
        if (treatmentRef.current === value) {
          setTreatment(updated.treatment || "");
          treatmentRef.current = updated.treatment || "";
        }
        flashSaved();
        setRevision((current) => current + 1);
        notifyProjectChanged({ slug });
      } catch (caught) {
        setError(String(caught));
        setSaveFailed(true);
      } finally {
        savingRef.current = false;
        setSavingTreatment(false);
      }
    },
    [brief, slug],
  );

  useEffect(() => {
    if (!brief || treatment === treatmentLast.current) return;
    const timer = window.setTimeout(() => void saveTreatment(treatment), 800);
    return () => window.clearTimeout(timer);
  }, [brief, saveTreatment, treatment]);

  const saveFields = async () => {
    if (!brief) return;
    const nextDirection = direction.trim();
    const nextStyle = style.trim();
    if (
      nextDirection === (brief.direction || "") &&
      nextStyle === (brief.style || "")
    ) {
      setFieldsDirty(false);
      return;
    }
    if (savingFields) return;
    setFieldsDirty(false);
    setSavingFields(true);
    setError(null);
    try {
      const updated = await api.patchBrief(slug, {
        direction: nextDirection,
        style: nextStyle,
      });
      setBrief(updated);
      setDirection(updated.direction || "");
      setStyle(updated.style || "");
      flashSaved();
      setRevision((current) => current + 1);
      notifyProjectChanged({ slug });
    } catch (caught) {
      setError(String(caught));
      setSaveFailed(true);
    } finally {
      setSavingFields(false);
    }
  };

  useEffect(() => {
    if (!brief || !fieldsDirty) return;
    const timer = window.setTimeout(() => void saveFields(), 800);
    return () => window.clearTimeout(timer);
  }, [brief, direction, fieldsDirty, style]);

  const intakeChanged = (updated: IntakePayload) => {
    onIntakeChange(updated);
    if (updated.brief) setBrief(updated.brief);
    setRevision((value) => value + 1);
  };

  const briefChanged = (updated: Brief) => {
    setBrief(updated);
    setRevision((value) => value + 1);
  };

  const chooseConcept = async (id: string) => {
    if (!treatments) return;
    setError(null);
    try {
      const updated = await api.putTreatments(slug, {
        concepts: treatments.concepts || treatments.treatments || [],
        chosen_id: id,
      });
      setTreatments((current) =>
        current
          ? { ...current, chosen_id: updated.chosen_id, treatments: current.treatments }
          : current,
      );
      notifyProjectChanged();
    } catch (caught) {
      setError(String(caught));
    }
  };

  const askWriter = (text = conceptPrompt(!!brief?.treatment?.trim())) => {
    window.dispatchEvent(new CustomEvent("studio:ask-director", { detail: { text } }));
  };

  const importConcept = async () => {
    const value = importText.trim();
    if (!value || !brief || importing || savingTreatment || savingFields) return;
    setImporting(true);
    setError(null);
    try {
      const updated = await api.patchBrief(slug, { treatment: value });
      const saved = updated.treatment || "";
      treatmentLast.current = saved;
      treatmentRef.current = saved;
      setTreatment(saved);
      setBrief(updated);
      setImportText("");
      flashSaved();
      setRevision((current) => current + 1);
      notifyProjectChanged();
      askWriter(IMPORT_PROMPT);
    } catch (caught) {
      setError(String(caught));
    } finally {
      setImporting(false);
    }
  };

  const saveStatus: SaveStatus =
    savingTreatment || savingFields
      ? "saving"
      : saveFailed
        ? "error"
        : fieldsDirty || treatment !== treatmentLast.current
          ? "dirty"
          : savedAt
            ? "saved"
            : "idle";

  const concepts = treatments?.concepts || treatments?.treatments || [];
  const chosen = treatments?.chosen_id || null;
  const length = sectionLength(audioWindow);
  const profile = intake?.kinds.find((kind) => kind.id === intake.kind);
  const lengths = (profile?.lengths || []).filter((value) => value > 0);
  const nearest =
    lengths.length && length
      ? lengths.reduce((best, value) =>
          Math.abs(value - length) < Math.abs(best - length) ? value : best,
        )
      : null;
  const difference = nearest !== null ? length - nearest : 0;
  const advert = intake?.kind === "advert";

  const conceptImport = (
    <>
      <p className="hint">
        Paste a concept, outline or full treatment. It is saved as the Treatment first, so the
        Writer reads it as your story and improves it instead of replacing it.
      </p>
      <AutoTextarea
        value={importText}
        onChange={(event) => setImportText(event.target.value)}
        minRows={6}
        maxRows={24}
        placeholder="Paste your concept or treatment…"
        aria-label="Concept you already have"
      />
      <div className="row-actions">
        <Button
          variant="primary"
          size="small"
          disabled={!importText.trim() || importing || savingTreatment || savingFields}
          onClick={() => void importConcept()}
        >
          {importing ? "Saving…" : "Save and open the Writer"}
        </Button>
        {brief?.treatment?.trim() && (
          <span className="hint">
            Replaces the current treatment. The previous version stays in the brief history.
          </span>
        )}
      </div>
    </>
  );

  return (
    <>
      <div className="stage-head story-head">
        <div>
          <h1>Story</h1>
          <p>Pick a direction, shape the story and set the look every picture will share.</p>
          <ApprovalBar stages={["brief"]} />
        </div>
        <div className="stage-ratings" aria-label="Rate the story artifacts">
          <ArtifactRating slug={slug} artifact="brief" />
          <ArtifactRating slug={slug} artifact="treatments" />
        </div>
      </div>
      {error && (
        <ErrorState
          what={brief ? "saving the story" : "reading the story"}
          error={error}
          compact={!!brief}
          onRetry={brief ? undefined : () => void load()}
        />
      )}
      {loading && !brief && !error && <LoadingState>Reading the current story…</LoadingState>}
      {!loading && !brief && !error && (
        <EmptyState
          title="The story could not be read."
          action={
            <Button onClick={() => void load()}>Retry loading the story</Button>
          }
        >
          Nothing was changed. Try again, or check that the brief exists for this film.
        </EmptyState>
      )}

      {approval?.state === "stale" && (
        <section className="stage-block changed-panel" id="story-changes">
          <h2>Changed since you approved it</h2>
          <p>{approval.reason || changes?.reason || "The story differs from what you approved."}</p>
          {changes?.changes?.length ? (
            <dl className="change-list">
              {changes.changes.map((change) => (
                <div key={change.field}>
                  <dt>{change.field}</dt>
                  <dd>
                    <span className="before">{change.before}</span>
                    <span className="arrow">→</span>
                    <span className="after">{change.after}</span>
                  </dd>
                </div>
              ))}
            </dl>
          ) : (
            <p className="hint">
              {changes?.available
                ? "The supporting files changed; the current story is what approval will bind."
                : "This approval predates the change log. Read the current story before approving it again."}
            </p>
          )}
        </section>
      )}

      {intake && brief && intake.kind !== "music_video" && (
        <BriefCard
          slug={slug}
          intake={intake}
          audioWindow={audioWindow}
          onIntakeChange={intakeChanged}
        />
      )}

      {intake && intake.kind !== "music_video" && audioWindow && (
        <div className="excerpt-summary">
          <b>Song excerpt · {length.toFixed(1)} s</b>
          {nearest !== null && Math.abs(difference) > 0.25 && (
            <span className="excerpt-warning">
              {Math.abs(difference).toFixed(1)} s {difference > 0 ? "longer" : "shorter"} than
              the {nearest} s {advert ? "advert" : "promo"}
            </span>
          )}
          {nearest !== null && Math.abs(difference) <= 0.25 && (
            <span>matches the {nearest} s {advert ? "advert" : "promo"}</span>
          )}
          <span className="hint">
            {windowLocked
              ? "The storyboard is built on this excerpt, so it is fixed. Start a new film to choose a different part of the song."
              : `Drag the gold handles on the timeline. Fades ${audioWindow.fade_in.toFixed(1)} s in and ${audioWindow.fade_out.toFixed(1)} s out.`}
          </span>
        </div>
      )}

      <section className="stage-block concepts-block">
        <h2>
          Concepts <small>From the Writer · pick one to build on</small>
        </h2>
        {concepts.length ? (
          <>
            <div className="concepts">
              {concepts.map((concept) => (
                <button
                  type="button"
                  className="concept"
                  key={concept.id}
                  aria-pressed={chosen === concept.id}
                  onClick={() => void chooseConcept(concept.id)}
                >
                  {chosen === concept.id && <span className="chosen">Chosen</span>}
                  <h3>{concept.title}</h3>
                  <p>{concept.logline}</p>
                </button>
              ))}
            </div>
            <div className="row-actions">
              <Button size="small" variant="quiet" onClick={() => askWriter()}>
                Ask for three more
              </Button>
            </div>
            <details className="concept-import">
              <summary>I already have a concept</summary>
              <div className="concept-import-body">{conceptImport}</div>
            </details>
          </>
        ) : (
          <div className="empty-block">
            <p>
              No concepts yet. Ask the Writer for three directions, or start from one you already
              have.
            </p>
            <Button variant="primary" onClick={() => askWriter()}>
              Ask the Writer for three directions
            </Button>
            <div className="concept-import concept-import-open">
              <h3>I already have a concept</h3>
              <div className="concept-import-body">{conceptImport}</div>
            </div>
          </div>
        )}
      </section>

      <div className="stage-columns story-columns">
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
                  setFieldsDirty(true);
                }}
                onKeyDown={(event) => {
                  // One sentence: Enter finishes the field instead of breaking the line.
                  if (event.key === "Enter") {
                    event.preventDefault();
                    (event.target as HTMLTextAreaElement).blur();
                  }
                }}
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
                  setFieldsDirty(true);
                }}
                onKeyDown={(event) => {
                  // One sentence: Enter finishes the field instead of breaking the line.
                  if (event.key === "Enter") {
                    event.preventDefault();
                    (event.target as HTMLTextAreaElement).blur();
                  }
                }}
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
              setTreatment(value);
              treatmentRef.current = value;
            }}
            onCommit={() => void saveTreatment(treatmentRef.current)}
            placeholder="The story from the first frame to the last. It saves as you type."
          />
          <p className="hint">
            Click the text to edit. It saves a moment after you stop typing; there is no Save
            button.
          </p>
        </section>
        <div className="story-side">
          {intake && brief ? (
            <LookCard
              slug={slug}
              intake={intake}
              brief={brief}
              onIntakeChange={intakeChanged}
              onBriefChange={briefChanged}
            />
          ) : (
            <section className="stage-block">
              <h2>Look</h2>
              <p className="hint">Loading the appearance…</p>
            </section>
          )}
          {brief && intake?.prompt_version === 2 && (
            <ProfileCard brief={brief} onAsk={askWriter} />
          )}
          {brief && <CharactersCard slug={slug} brief={brief} onBriefChange={briefChanged} />}
        </div>
      </div>

      <CreditsCard slug={slug} />
    </>
  );
}
