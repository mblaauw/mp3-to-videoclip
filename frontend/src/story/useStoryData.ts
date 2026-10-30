import { useCallback, useEffect, useRef, useState } from "react";
import { draftError } from "../api/resources";
import {
  api,
  type ApprovalChanges,
  type ApprovalState,
  type Brief,
  type IntakePayload,
  type TreatmentsPayload,
} from "../api";
import { useApprovals } from "../ApprovalBar";
import { notifyProjectChanged, useProjectChanged } from "../shell/projectEvents";
import type { SaveStatus } from "../ui/SaveState";

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

/** Everything Story reads and saves. The parts below only draw it. */
export function useStoryData({
  slug,
  intake,
  onIntakeChange,
}: {
  slug: string;
  intake: IntakePayload | null;
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
  const treatmentBase = useRef<Brief | null>(null);
  const fieldsBase = useRef<Brief | null>(null);
  const importBase = useRef<Brief | null>(null);
  const fieldValues = useRef({ direction, style });
  fieldValues.current = { direction, style };

  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [saveFailed, setSaveFailed] = useState(false);
  const flashSaved = () => {
    setSavedAt(Date.now());
    setSaveFailed(false);
  };

  const loadEpoch = useRef(0);
  const load = useCallback(async () => {
    const epoch = ++loadEpoch.current;
    try {
      const [nextBrief, nextTreatments] = await Promise.all([
        api.brief(slug),
        api.treatments(slug),
      ]);
      if (epoch !== loadEpoch.current) return;
      if (treatmentBase.current || fieldsBase.current || importBase.current) return;
      setBrief(nextBrief);
      setTreatments(nextTreatments);
      setTreatment(nextBrief.treatment || "");
      setDirection(nextBrief.direction || "");
      setStyle(nextBrief.style || "");
      treatmentRef.current = nextBrief.treatment || "";
      treatmentLast.current = nextBrief.treatment || "";
      setError(null);
    } catch (caught) {
      if (epoch !== loadEpoch.current) return;
      setError(String(caught));
    } finally {
      if (epoch === loadEpoch.current) setLoading(false);
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
    return () => { loadEpoch.current += 1; };
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
        const updated = await api.patchBrief(slug, { treatment: value }, treatmentBase.current ?? brief);
        treatmentBase.current = treatmentRef.current === value ? null : updated;
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
        setError(draftError(caught));
        setSaveFailed(true);
      } finally {
        savingRef.current = false;
        setSavingTreatment(false);
      }
    },
    [brief, slug],
  );

  useEffect(() => {
    if (!brief || saveFailed || treatment === treatmentLast.current) return;
    const timer = window.setTimeout(() => void saveTreatment(treatment), 800);
    return () => window.clearTimeout(timer);
  }, [brief, saveTreatment, treatment, saveFailed]);

  const saveFields = async () => {
    if (!brief) return;
    const nextDirection = direction.trim();
    const nextStyle = style.trim();
    if (
      nextDirection === (brief.direction || "") &&
      nextStyle === (brief.style || "")
    ) {
      fieldsBase.current = null;
      setFieldsDirty(false);
      return;
    }
    if (savingFields) return;
    setSavingFields(true);
    setError(null);
    try {
      const updated = await api.patchBrief(slug, {
        direction: nextDirection,
        style: nextStyle,
      }, fieldsBase.current ?? brief);
      setBrief(updated);
      const unchanged = fieldValues.current.direction.trim() === nextDirection && fieldValues.current.style.trim() === nextStyle;
      fieldsBase.current = unchanged ? null : updated;
      if (unchanged) {
        setDirection(updated.direction || "");
        setStyle(updated.style || "");
        setFieldsDirty(false);
      }
      flashSaved();
      setRevision((current) => current + 1);
      notifyProjectChanged({ slug });
    } catch (caught) {
      setError(draftError(caught));
      setSaveFailed(true);
    } finally {
      setSavingFields(false);
    }
  };

  useEffect(() => {
    if (!brief || saveFailed || !fieldsDirty) return;
    const timer = window.setTimeout(() => void saveFields(), 800);
    return () => window.clearTimeout(timer);
  }, [brief, direction, fieldsDirty, style, saveFailed]);

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
      const updated = await api.patchBrief(slug, { treatment: value }, importBase.current ?? brief);
      importBase.current = null;
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
      setError(draftError(caught));
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

  return {
    brief,
    concepts,
    chosen,
    changes,
    approval,
    treatment,
    direction,
    style,
    importText,
    importing,
    savingTreatment,
    savingFields,
    loading,
    error,
    savedAt,
    saveStatus,
    treatmentBase,
    treatmentRef,
    fieldsBase,
    importBase,
    load,
    setTreatment,
    setDirection,
    setStyle,
    setImportText,
    setSaveFailed,
    setFieldsDirty,
    saveTreatment,
    saveFields,
    intakeChanged,
    briefChanged,
    chooseConcept,
    askWriter,
    importConcept,
  };
}

export type StoryData = ReturnType<typeof useStoryData>;
