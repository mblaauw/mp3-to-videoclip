import { useCallback, useEffect, useRef, useState } from "react";
import { api, type TrackData } from "../api";
import { notifyProjectChanged, PROJECT_CHANGED } from "../shell/projectEvents";
import { toast } from "../toast";
import { addEdge, joinNext, moveEdge, type SectionEdit } from "./sectionEdit";

export const SECTION_EDGE = "studio:section-edge";

export function defaultName(index: number): string {
  return `Section ${index + 1}`;
}

/** Everything the Track screen reads and saves, in one place. */
export function useTrackData(slug: string) {
  const [data, setData] = useState<TrackData | null>(null);
  const [names, setNames] = useState<string[]>([]);
  const [namesSaving, setNamesSaving] = useState(false);
  const [namesSaved, setNamesSaved] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [lyricsSaving, setLyricsSaving] = useState(false);
  const [modeSaving, setModeSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const savedTimer = useRef<number | null>(null);
  const loadEpoch = useRef(0);
  const [undoDepth, setUndoDepth] = useState(0);
  const currentNames = useRef<string[]>([]);
  currentNames.current = names;
  const undoStack = useRef<{ map: boolean; sections: SectionEdit[] }[]>([]);

  const adopt = useCallback((next: TrackData) => {
    setData(next);
    setNames(
      (next.music?.sections || []).map((section, index) => section.name || defaultName(index)),
    );
  }, []);

  const load = useCallback(async () => {
    const epoch = ++loadEpoch.current;
    try {
      const next = await api.track(slug);
      if (epoch !== loadEpoch.current) return;
      adopt(next);
      setError(null);
    } catch (caught) {
      if (epoch !== loadEpoch.current) return;
      setError(String(caught));
    }
  }, [adopt, slug]);

  useEffect(() => {
    setData(null);
    setNames([]);
    undoStack.current = [];
    setUndoDepth(0);
    void load();
    return () => {
      loadEpoch.current += 1;
    };
  }, [load]);

  useEffect(() => {
    const changed = () => void load();
    window.addEventListener(PROJECT_CHANGED, changed);
    return () => window.removeEventListener(PROJECT_CHANGED, changed);
  }, [load]);

  useEffect(() => {
    if (!data || data.music) return;
    let tries = 0;
    const timer = window.setInterval(async () => {
      tries += 1;
      try {
        const next = await api.track(slug);
        adopt(next);
        if (next.music || tries >= 20) window.clearInterval(timer);
      } catch {
        if (tries >= 20) window.clearInterval(timer);
      }
    }, 3000);
    return () => window.clearInterval(timer);
  }, [adopt, data?.music, slug]);

  useEffect(
    () => () => {
      if (savedTimer.current) window.clearTimeout(savedTimer.current);
    },
    [],
  );

  const analyze = async () => {
    setAnalyzing(true);
    setError(null);
    try {
      await api.analyze(slug);
      await load();
      notifyProjectChanged();
    } catch (caught) {
      setError(String(caught));
    } finally {
      setAnalyzing(false);
    }
  };

  const saveNames = async (names = currentNames.current) => {
    const sections = data?.music?.sections || [];
    if (!sections.length || namesSaving) return;
    setNamesSaving(true);
    setError(null);
    try {
      if (data?.section_map) {
        await api.saveSectionMap(
          slug,
          sections.map((section, index) => ({
            start: Number(section.start),
            name: names[index]?.trim() || defaultName(index),
          })),
        );
        setNamesSaved(true);
        if (savedTimer.current) window.clearTimeout(savedTimer.current);
        savedTimer.current = window.setTimeout(() => setNamesSaved(false), 2000);
        notifyProjectChanged();
        return;
      }
      const saved = await api.saveMusicNotes(
        slug,
        sections.map((section, index) => ({
          start: Number(section.start),
          name: names[index]?.trim() || defaultName(index),
        })),
      );
      setNames(
        sections.map(
          (section, index) =>
            saved.sections.find(
              (item) => Math.abs(Number(item.start) - Number(section.start)) < 0.0005,
            )?.name || defaultName(index),
        ),
      );
      setNamesSaved(true);
      if (savedTimer.current) window.clearTimeout(savedTimer.current);
      savedTimer.current = window.setTimeout(() => setNamesSaved(false), 2000);
      notifyProjectChanged();
    } catch (caught) {
      setError(String(caught));
    } finally {
      setNamesSaving(false);
    }
  };

  const setMode = async (mode: "vocal" | "instrumental") => {
    if (!data || data.music_mode === mode || modeSaving) return;
    setModeSaving(true);
    setError(null);
    try {
      await api.setMusicMode(slug, mode);
      setData({ ...data, music_mode: mode });
      notifyProjectChanged();
    } catch (caught) {
      setError(String(caught));
    } finally {
      setModeSaving(false);
    }
  };

  const currentEdits = useCallback(
    (): SectionEdit[] =>
      (data?.music?.sections || []).map((section, index) => ({
        start: Number(section.start),
        name: names[index]?.trim() || section.name || defaultName(index),
      })),
    [data?.music?.sections, names],
  );

  const changeSections = useCallback(
    async (next: SectionEdit[]) => {
      const before = currentEdits();
      undoStack.current.push({ map: !!data?.section_map, sections: before });
      setUndoDepth(undoStack.current.length);
      try {
        await api.saveSectionMap(slug, next);
        await load();
        notifyProjectChanged();
      } catch (caught) {
        undoStack.current.pop();
        setUndoDepth(undoStack.current.length);
        toast(`Could not change the sections: ${String(caught)}`);
      }
    },
    [currentEdits, data?.section_map, load, slug],
  );

  const undoSections = async () => {
    const step = undoStack.current.pop();
    setUndoDepth(undoStack.current.length);
    if (!step) return;
    try {
      if (step.map) await api.saveSectionMap(slug, step.sections);
      else await api.resetSectionMap(slug);
      await load();
      notifyProjectChanged();
    } catch (caught) {
      toast(`Could not undo: ${String(caught)}`);
    }
  };

  const resetSections = async () => {
    undoStack.current.push({ map: true, sections: currentEdits() });
    setUndoDepth(undoStack.current.length);
    try {
      await api.resetSectionMap(slug);
      await load();
      notifyProjectChanged();
    } catch (caught) {
      toast(`Could not reset the sections: ${String(caught)}`);
    }
  };

  const duration = data?.duration ?? 0;
  const addSectionEdge = (time: number): boolean => {
    const next = addEdge(currentEdits(), time, duration);
    if (!next) return false;
    void changeSections(next);
    return true;
  };
  const joinSection = (index: number) => void changeSections(joinNext(currentEdits(), index));

  // The Spine owns the song strip, so a dragged edge arrives as an event.
  useEffect(() => {
    const onEdge = (event: Event) => {
      const { index, time } = (event as CustomEvent<{ index: number; time: number }>).detail;
      const before = currentEdits();
      const next = moveEdge(before, index, time, duration);
      if (next !== before && next[index]?.start !== before[index]?.start) void changeSections(next);
    };
    window.addEventListener(SECTION_EDGE, onEdge);
    return () => window.removeEventListener(SECTION_EDGE, onEdge);
  }, [changeSections, currentEdits, duration]);

  /** True when the words were saved. */
  const saveLyrics = async (text: string): Promise<boolean> => {
    if (lyricsSaving || !text.trim()) return false;
    setLyricsSaving(true);
    setError(null);
    try {
      const result = await api.saveLyrics(slug, text);
      if (result.error) {
        setError(result.error);
        return false;
      }
      await load();
      notifyProjectChanged();
      return true;
    } catch (caught) {
      setError(String(caught));
      return false;
    } finally {
      setLyricsSaving(false);
    }
  };

  return {
    data,
    names,
    setNames,
    namesSaved,
    analyzing,
    lyricsSaving,
    modeSaving,
    error,
    load,
    analyze,
    saveNames,
    setMode,
    saveLyrics,
    canUndoSections: undoDepth > 0,
    undoSections,
    resetSections,
    addSectionEdge,
    joinSection,
    changeSections,
  };
}

export type TrackModel = ReturnType<typeof useTrackData>;
