import { useCallback, useEffect, useRef, useState } from "react";
import { api, type ApprovalState, type Brief, type ImageReview, type ImageShot, type Music, type Storyboard } from "../api";
import { useApprovals } from "../ApprovalBar";
import { usePaidImages } from "./paid";
import { useProjectJobs } from "../jobs/store";
import { notifyProjectChanged, useProjectChanged } from "../shell/projectEvents";
import { useFocusTrap } from "../ui";
import { type Card, type Filter, type PaidRequest, matches, money, statusOf } from "./imageStatus";

export type ImagesStageProps = {
  slug: string;
  reserve: string;
  pendingPaid: PaidRequest | null;
  onPendingConsumed: () => void;
  onNavigate: (stage: "storyboard" | "film") => void;
};

export function useImagesData({
  slug,
  reserve,
  pendingPaid,
  onPendingConsumed,
}: ImagesStageProps) {
  const [shots, setShots] = useState<ImageShot[]>([]);
  const [budget, setBudget] = useState<Card | null>(null);
  const [proofIds, setProofIds] = useState<string[]>([]);
  const [board, setBoard] = useState<Storyboard | null>(null);
  const [music, setMusic] = useState<Music | null>(null);
  const [filter, setFilter] = useState<Filter>("all");
  const [activeId, setActiveId] = useState<string | null>(null);
  const [redoOpen, setRedoOpen] = useState<string | null>(null);
  const [redoNote, setRedoNote] = useState("");
  const [working, setWorking] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loaded, setLoaded] = useState(false);
  const approvals: Record<string, ApprovalState> = useApprovals().states;
  const imageJobs = useProjectJobs(slug, "images");
  const consumed = useRef<string | null>(null);
  const refreshTimer = useRef<number | null>(null);
  const refreshPending = useRef(false);
  const lightboxRef = useRef<HTMLDivElement>(null);

  const loadEpoch = useRef(0);
  const load = useCallback(async () => {
    const epoch = ++loadEpoch.current;
    const [imagesResult, budgetResult, briefResult, boardResult, trackResult] =
      await Promise.allSettled([
        api.images(slug),
        api.budget(slug),
        api.brief(slug),
        api.storyboard(slug),
        api.track(slug),
      ]);
    if (epoch !== loadEpoch.current) return;
    if (imagesResult.status === "fulfilled") {
      setShots(imagesResult.value.shots);
      setError(null);
    } else setError(String(imagesResult.reason));
    if (budgetResult.status === "fulfilled") setBudget(budgetResult.value);
    if (briefResult.status === "fulfilled") {
      const brief = briefResult.value as Brief;
      setProofIds(brief.creative?.proof_shot_ids || []);
    }
    if (boardResult.status === "fulfilled") {
      setBoard("available" in boardResult.value ? null : boardResult.value);
    }
    if (trackResult.status === "fulfilled") setMusic(trackResult.value.music);
    setLoaded(true);
  }, [slug]);

  // Stills land one by one while a batch runs; every notice reloads the sheet.
  useProjectChanged(slug, () => void load());

  useEffect(() => {
    setFilter("all");
    setActiveId(null);
    setRedoOpen(null);
    setError(null);
    consumed.current = null;
    void load();
    return () => { loadEpoch.current += 1; };
  }, [load]);

  const paid = usePaidImages(slug, reserve, () => {
    void load();
  });

  // Whatever a paid request needs answered must be on screen, not above the fold.
  const answerRef = useRef<HTMLDivElement>(null);
  const waitingForAnswer = Boolean(paid.quote || paid.newRound || paid.error);
  useEffect(() => {
    if (waitingForAnswer) answerRef.current?.scrollIntoView({ block: "center" });
  }, [waitingForAnswer, paid.quote, paid.newRound, paid.error]);

  const scheduleRefresh = () => {
    if (refreshTimer.current) window.clearTimeout(refreshTimer.current);
    refreshPending.current = true;
    refreshTimer.current = window.setTimeout(() => {
      refreshTimer.current = null;
      refreshPending.current = false;
      void load();
      notifyProjectChanged({ slug });
    }, 800);
  };

  useEffect(
    () => () => {
      if (refreshTimer.current) window.clearTimeout(refreshTimer.current);
      if (refreshPending.current) notifyProjectChanged({ slug });
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps -- runs once on leaving, for the slug this screen opened with
    [],
  );

  useEffect(() => {
    if (!pendingPaid) return;
    const key = `${pendingPaid.scope}:${pendingPaid.ids.join(",")}`;
    if (consumed.current === key) {
      onPendingConsumed();
      return;
    }
    consumed.current = key;
    void paid.request(pendingPaid.ids, pendingPaid.scope, false);
    onPendingConsumed();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pendingPaid]);

  // Which queued stills have not arrived yet: a shot is done once it has more
  // versions than it had when the batch was queued.
  const baseline = useRef<{ key: string; counts: Map<string, number> }>({
    key: "",
    counts: new Map(),
  });
  const queuedKey = paid.queued.join(",");
  if (baseline.current.key !== queuedKey) {
    baseline.current = {
      key: queuedKey,
      counts: new Map(shots.map((shot) => [shot.owner, shot.versions.length])),
    };
  }
  const making = new Set(
    imageJobs.length
      ? paid.queued.filter((id) => {
          const shot = shots.find((item) => item.owner === id || item.id === id);
          const before = baseline.current.counts.get(shot?.owner || id) ?? 0;
          return !shot || shot.versions.length <= before;
        })
      : [],
  );
  const { clearQueued } = paid;
  useEffect(() => {
    if (!imageJobs.length && paid.queued.length) clearQueued();
  }, [imageJobs.length, paid.queued.length, clearQueued]);

  const visible = shots.filter((shot) => matches(shot, filter));
  const counts: Record<Filter, number> = {
    all: shots.length,
    review: shots.filter((shot) => matches(shot, "review")).length,
    redo: shots.filter((shot) => matches(shot, "redo")).length,
    stale: shots.filter((shot) => matches(shot, "stale")).length,
    missing: shots.filter((shot) => matches(shot, "missing")).length,
    kept: shots.filter((shot) => matches(shot, "kept")).length,
    made: shots.filter((shot) => matches(shot, "made")).length,
  };

  const paidShots = shots.filter((shot) => shot.paid);
  const kept = paidShots.filter((shot) => !shot.stale && shot.review?.verdict === "accept").length;
  const proof = approvals.proof;
  const proofApproved = proof?.state === "approved";
  const proofShots = shots.filter((shot) => proofIds.includes(shot.id));
  const proofMissing = proofShots.filter((shot) => shot.selected === null);
  const proofStale = proofShots.filter((shot) => shot.selected !== null && shot.stale);
  const older = paidShots.filter((shot) => shot.stale);
  const visibleMissing = visible.filter((shot) => !shot.local && shot.selected === null);
  const visibleOlder = visible.filter((shot) => shot.stale);

  const activeIndex = visible.findIndex((shot) => shot.id === activeId);
  const current = activeIndex >= 0 ? visible[activeIndex] : null;
  const shotById = new Map((board?.shots || []).map((shot) => [shot.id, shot]));
  const currentShot = current ? shotById.get(current.id) : undefined;
  useFocusTrap(!!current, lightboxRef);
  const fps = board?.fps || 24;
  const sectionAt = (seconds: number) => {
    const section = (music?.sections || []).find(
      (item) => seconds >= Number(item.start) && seconds < Number(item.end),
    );
    if (!section) return null;
    return (
      section.name ||
      (section.label && section.label !== "unreviewed" ? section.label : null)
    );
  };

  const price = (count: number) => money(String(Number(reserve) * count));

  const nextUnreviewed = (id: string) => {
    const start = shots.findIndex((shot) => shot.id === id);
    for (let step = 1; step < shots.length; step += 1) {
      const shot = shots[(start + step) % shots.length];
      if (
        shot.paid &&
        shot.selected !== null &&
        !shot.stale &&
        shot.review?.verdict !== "accept"
      ) {
        return shot.id;
      }
    }
    return null;
  };

  const open = (id: string) => {
    setActiveId(id);
    setRedoOpen(null);
    setRedoNote("");
  };

  const move = (offset: number) => {
    if (!visible.length) return;
    const index = visible.findIndex((shot) => shot.id === activeId);
    const next = visible[Math.min(Math.max(index + offset, 0), visible.length - 1)];
    if (next) {
      open(next.id);
      const tile = document.querySelector(`[data-still="${next.id}"]`);
      tile?.scrollIntoView({ block: "nearest" });
    }
  };

  const keep = async (shot: ImageShot) => {
    if (shot.local || shot.selected === null) return;
    if (shot.stale) {
      setError("This still was made from an older prompt. Remake it before keeping it.");
      return;
    }
    const next = nextUnreviewed(shot.id);
    if (shot.review?.verdict === "accept") {
      setActiveId(next);
      return;
    }
    if (working === shot.id) return;
    const version = shot.selected;
    setWorking(shot.id);
    setError(null);
    try {
      await api.reviewImage(slug, {
        shot_id: shot.id,
        version,
        verdict: "accept",
        inspected: true,
      });
      const chosen = shot.versions.find((item) => item.version === version);
      const review: ImageReview = {
        shot_id: shot.owner,
        version,
        sha256: chosen?.sha256 || "",
        input_hash: chosen?.input_hash || "",
        verdict: "accept",
        note: "",
        reviewer: "studio",
        inspected: true,
        at: new Date().toISOString(),
      };
      setShots((current) =>
        current.map((item) => (item.id === shot.id ? { ...item, review } : item)),
      );
      setActiveId(next);
      setWorking(null);
      scheduleRefresh();
    } catch (caught) {
      setError(String(caught));
      setWorking(null);
    }
  };

  const redo = (shot: ImageShot) => {
    if (shot.local || shot.selected === null) return;
    setRedoOpen(shot.id);
    setRedoNote("");
    setError(null);
  };

  const submitRedo = async (shot: ImageShot, remake: boolean, edit = false) => {
    if (shot.local || shot.selected === null) return;
    setWorking(shot.id);
    setError(null);
    try {
      await api.reviewImage(slug, {
        shot_id: shot.id,
        version: shot.selected,
        verdict: "reject",
        note: redoNote.trim(),
        inspected: true,
      });
      notifyProjectChanged({ slug });
      await load();
      setRedoOpen(null);
      setActiveId(null);
      setRedoNote("");
      if (edit) {
        // The prompt stays as it is: the note goes to the model with the still itself.
        await paid.request([shot.id], proofIds.includes(shot.id) ? "proof" : "stills", true, {
          edit_from: { [shot.id]: shot.selected },
          edit_note: redoNote.trim(),
        });
        return;
      }
      window.dispatchEvent(
        new CustomEvent("studio:ask-director", {
          detail: {
            text: `Shot ${shot.id}: ${redoNote.trim() || "please rewrite this still."}`,
          },
        }),
      );
      if (remake) {
        await paid.request(
          [shot.id],
          proofIds.includes(shot.id) ? "proof" : "stills",
          true,
        );
      }
    } catch (caught) {
      setError(String(caught));
    } finally {
      setWorking(null);
    }
  };

  const selectVersion = async (shot: ImageShot, version: number) => {
    if (shot.selected === version) return;
    setWorking(shot.id);
    setError(null);
    try {
      await api.selectImage(slug, shot.id, version);
      notifyProjectChanged({ slug });
      await load();
    } catch (caught) {
      setError(String(caught));
    } finally {
      setWorking(null);
    }
  };

  const make = (ids: string[], scope: "proof" | "stills") => {
    setError(null);
    void paid.request(ids, scope, false);
  };

  const makeFromLightbox = (ids: string[], scope: "proof" | "stills") => {
    setActiveId(null);
    make(ids, scope);
    window.setTimeout(() => {
      document.querySelector(".images-toolbar")?.scrollIntoView({ block: "start" });
    }, 180);
  };

  const keyboard = useRef({ keep, redo, move, close: () => setActiveId(null) });
  keyboard.current = { keep, redo, move, close: () => setActiveId(null) };

  useEffect(() => {
    if (!activeId) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        keyboard.current.close();
        return;
      }
      const tag = (event.target as HTMLElement | null)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
      if (event.key === "ArrowRight") {
        event.preventDefault();
        keyboard.current.move(1);
      } else if (event.key === "ArrowLeft") {
        event.preventDefault();
        keyboard.current.move(-1);
      } else if (event.key.toLowerCase() === "k" && current) {
        event.preventDefault();
        void keyboard.current.keep(current);
      } else if (event.key.toLowerCase() === "r" && current) {
        event.preventDefault();
        keyboard.current.redo(current);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [activeId, current]);

  const styleState = (shot: ImageShot) => statusOf(shot).label;

  return { activeIndex, answerRef, board, budget, counts, current, currentShot, error, filter, fps, imageJobs, keep, kept, lightboxRef, load, loaded, make, makeFromLightbox, making, move, older, open, paid, paidShots, price, proof, proofApproved, proofIds, proofMissing, proofShots, proofStale, redo, redoNote, redoOpen, sectionAt, selectVersion, setActiveId, setFilter, setRedoNote, setRedoOpen, shotById, shots, styleState, submitRedo, visible, visibleMissing, visibleOlder, working };
}
