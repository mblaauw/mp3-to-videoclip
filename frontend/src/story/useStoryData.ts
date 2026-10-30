import { useCallback, useEffect, useRef, useState } from "react";
import { draftError } from "../api/resources";
import {
  api,
  type ApprovalChanges,
  type ApprovalState,
  type Brief,
  type Concept,
  type Idea,
  type StoryPassage,
  type IntakePayload,
  type TreatmentsPayload,
} from "../api";
import { useApprovals } from "../ApprovalBar";
import { notifyProjectChanged, useProjectChanged } from "../shell/projectEvents";
import type { SaveStatus } from "../ui/SaveState";

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
  const [idea, setIdea] = useState<Idea | null>(null);
  const [passages, setPassages] = useState<StoryPassage[]>([]);
  const [starting, setStarting] = useState(false);
  const [writerBusy, setWriterBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const treatmentLast = useRef("");
  const treatmentRef = useRef("");
  const savingRef = useRef(false);
  const treatmentBase = useRef<Brief | null>(null);
  const fieldsBase = useRef<Brief | null>(null);
  const fieldValues = useRef({ direction, style });
  fieldValues.current = { direction, style };

  const concepts = treatments?.concepts || treatments?.treatments || [];
  const chosen = treatments?.chosen_id || null;

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
      const [nextBrief, nextTreatments, nextIdea] = await Promise.all([
        api.brief(slug),
        api.treatments(slug),
        api.idea(slug),
      ]);
      if (epoch !== loadEpoch.current) return;
      if (treatmentBase.current || fieldsBase.current) return;
      setBrief(nextBrief);
      setTreatments(nextTreatments);
      setIdea(nextIdea.idea);
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
    setIdea(null);
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
    if (!treatments) return false;
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
      return true;
    } catch (caught) {
      setError(String(caught));
      return false;
    }
  };

  useEffect(() => {
    const busy = (event: Event) => setWriterBusy(Boolean((event as CustomEvent<boolean>).detail));
    window.addEventListener("studio:writer-busy", busy);
    return () => window.removeEventListener("studio:writer-busy", busy);
  }, []);

  /** Opens the Writer with this in the composer, to read and send yourself. */
  const askWriter = (text: string) => {
    window.dispatchEvent(new CustomEvent("studio:ask-director", { detail: { text } }));
  };

  /** Sends the Writer one named job now, with the Director open so you can watch it. */
  const runWriter = (text: string, task: string) => {
    window.dispatchEvent(new CustomEvent("studio:ask-director", { detail: { text, task, send: true } }));
  };

  const sortMyIdea = () => {
    runWriter("Sort the idea I just pasted and put its story on the song. Keep my words.", "import");
  };

  const startFromIdea = async (text: string) => {
    if (!brief || starting) return false;
    setStarting(true);
    setError(null);
    try {
      const saved = await api.keepIdea(slug, text);
      setIdea(saved.idea);
      if (chosen) await api.putTreatments(slug, { concepts, chosen_id: null });
      notifyProjectChanged({ slug });
      sortMyIdea();
      return true;
    } catch (caught) {
      setError(draftError(caught));
      return false;
    } finally {
      setStarting(false);
    }
  };

  useEffect(() => {
    let live = true;
    api
      .storyPassages(slug)
      .then((value) => {
        if (live) setPassages(value.passages);
      })
      .catch(() => {});
    return () => {
      live = false;
    };
  }, [slug, brief?.treatment, revision]);

  /** Concepts from the music, within any style or rules already on the brief. */
  const writeConcepts = (count: number) => {
    runWriter(
      `Write ${count === 1 ? "one concept" : `${count} concepts`} from the measured music. ` +
        "Keep to any style and rules I already gave.",
      "concepts",
    );
  };

  /** One more route: the ones on file stay exactly as they are. */
  const askForAnother = () => {
    runWriter(
      concepts.length
        ? "Add one more concept and keep the ones on file word for word."
        : "Suggest one concept that builds on my story and keeps its story, characters and ending.",
      "concepts",
    );
  };

  /** Choose a route and have its story written. Says whether the Writer was asked. */
  const buildOn = async (concept: Concept) => {
    if (!(await chooseConcept(concept.id))) return false;
    const replacing = brief?.treatment?.trim()
      ? " It replaces the treatment on file, which stays in the history."
      : "";
    runWriter(
      `Write the story from the concept "${concept.title}", and put it on the song.${replacing}`,
      intake?.kind === "promo" || intake?.kind === "advert" ? "script_ad" : "script_mv",
    );
    return true;
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

  return {
    brief,
    concepts,
    chosen,
    changes,
    approval,
    treatment,
    direction,
    style,
    idea,
    passages,
    starting,
    writerBusy,
    savingTreatment,
    savingFields,
    loading,
    error,
    savedAt,
    saveStatus,
    treatmentBase,
    treatmentRef,
    fieldsBase,
    load,
    setTreatment,
    setDirection,
    setStyle,
    setSaveFailed,
    setFieldsDirty,
    saveTreatment,
    saveFields,
    intakeChanged,
    briefChanged,
    chooseConcept,
    askWriter,
    runWriter,
    sortMyIdea,
    startFromIdea,
    writeConcepts,
    askForAnother,
    buildOn,
  };
}

export type StoryData = ReturnType<typeof useStoryData>;
