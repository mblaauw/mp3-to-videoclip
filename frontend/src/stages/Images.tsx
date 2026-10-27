import { useCallback, useEffect, useRef, useState } from "react";
import {
  api,
  type ApprovalState,
  type Brief,
  type Budget,
  type ImageReview,
  type ImageShot,
  type Music,
  type Storyboard,
} from "../api";
import { ApprovalBar, useApprovals } from "../ApprovalBar";
import { PaidCard } from "../images/PaidCard";
import { usePaidImages } from "../images/paid";
import { JobBanner } from "../jobs/JobBanner";
import { useProjectJobs } from "../jobs/store";
import { notifyProjectChanged, useProjectChanged } from "../shell/projectEvents";
import type { NextAction } from "../shell/nextStep";
import { kindMeta } from "../shotKinds";
import { Button, EmptyState, ErrorState, LoadingState, useFocusTrap } from "../ui";

type Card = Omit<Budget, "history">;
type Filter = "all" | "review" | "redo" | "stale" | "missing" | "kept" | "made";
type PaidRequest = NonNullable<NextAction["paid"]>;

const FILTERS: { id: Filter; label: string }[] = [
  { id: "all", label: "All" },
  { id: "review", label: "To review" },
  { id: "redo", label: "Redo" },
  { id: "stale", label: "Older prompt" },
  { id: "missing", label: "Not made" },
  { id: "kept", label: "Kept" },
  { id: "made", label: "Made here" },
];

function clock(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

function money(value: string | null | undefined): string {
  const number = Number(value || 0);
  return number.toFixed(2);
}

function sourceUrl(slug: string, shot: ImageShot): string | null {
  if (shot.plate) return shot.plate;
  if (shot.selected === null) return null;
  return `/api/projects/${slug}/images/${encodeURIComponent(shot.owner)}/${shot.selected}`;
}

function statusOf(shot: ImageShot): { tone: string; label: string } {
  if (shot.local) return { tone: "made", label: "Made here" };
  if (shot.selected === null) return { tone: "missing", label: "Not made" };
  if (shot.stale) return { tone: "stale", label: "Older prompt" };
  if (shot.review?.verdict === "accept") return { tone: "kept", label: "Kept" };
  if (shot.review?.verdict === "reject") return { tone: "redo", label: "Redo" };
  if (shot.review?.verdict === "uncertain") return { tone: "review", label: "Check" };
  return { tone: "review", label: "To review" };
}

function matches(shot: ImageShot, filter: Filter): boolean {
  if (filter === "all") return true;
  if (filter === "made") return shot.local;
  if (shot.local) return false;
  if (filter === "missing") return shot.selected === null;
  if (filter === "stale") return shot.stale;
  if (shot.selected === null) return false;
  if (filter === "kept") return !shot.stale && shot.review?.verdict === "accept";
  if (filter === "redo") return shot.review?.verdict === "reject";
  return (
    !shot.stale &&
    shot.review?.verdict !== "accept" &&
    shot.review?.verdict !== "reject"
  );
}

export function ImagesStage({
  slug,
  reserve,
  pendingPaid,
  onPendingConsumed,
  onNavigate,
}: {
  slug: string;
  reserve: string;
  pendingPaid: PaidRequest | null;
  onPendingConsumed: () => void;
  onNavigate: (stage: "storyboard" | "film") => void;
}) {
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

  const load = useCallback(async () => {
    const [imagesResult, budgetResult, briefResult, boardResult, trackResult] =
      await Promise.allSettled([
        api.images(slug),
        api.budget(slug),
        api.brief(slug),
        api.storyboard(slug),
        api.track(slug),
      ]);
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
  }, [load]);

  const paid = usePaidImages(slug, reserve, () => {
    void load();
  });

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

  const submitRedo = async (shot: ImageShot, remake: boolean) => {
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

  return (
    <>
      <div className="stage-head images-head">
        <div>
          <h1>Images</h1>
          <p>
            The style check first, then the full set. Local cards, splits, bridges, logos
            and end cards are made on this computer and cost nothing.
          </p>
          <ApprovalBar stages={["proof", "stills"]} />
        </div>
        <div className="images-budget">
          <b>${money(budget?.remaining_usd ?? null)} left</b>
          <span>
            kept {kept} of {paidShots.length} paid stills
            {counts.made ? ` · ${counts.made} made here` : ""}
          </span>
        </div>
      </div>
      {error && (
        <ErrorState
          what="reviewing the stills"
          error={error}
          compact
          onRetry={() => void load()}
        />
      )}
      {!loaded && <LoadingState>Reading the stills and the style check…</LoadingState>}
      <JobBanner slug={slug} kinds={["images"]} />

      {proofIds.length > 0 && !proofApproved && (
        <section className="style-check images-style-check">
          <div className="style-check-say">
            <b>Style check · {proofIds.length} hard shots first</b>
            <span>When they look right, make the rest. Only these three are paid now.</span>
          </div>
          <div className="style-shots">
            {proofShots.map((shot) => {
              const src = sourceUrl(slug, shot);
              return (
                <button
                  type="button"
                  className={`style-shot ${statusOf(shot).tone}`}
                  key={shot.id}
                  onClick={() => {
                    setFilter("all");
                    open(shot.id);
                  }}
                >
                  {src ? <img src={src} alt="" loading="lazy" /> : <span className="hatch" />}
                  <span>
                    <b>{shot.id}</b>
                    <em>{styleState(shot)}</em>
                  </span>
                </button>
              );
            })}
          </div>
          <div className="style-check-actions">
            {proofMissing.length > 0 ? (
              <span className="hint">
                {proofMissing.length} not made yet · make them with the button in the bar at
                the top (${price(proofMissing.length)}).
              </span>
            ) : (
              <span className="hint">
                {proofShots.every((shot) => shot.review?.verdict === "accept" && !shot.stale)
                  ? "All kept. Approve the style check in the bar at the top."
                  : `Open each one and keep or redo it (${
                      proofShots.filter((shot) => shot.review?.verdict === "accept" && !shot.stale)
                        .length
                    } of ${proofShots.length} kept).`}
              </span>
            )}
          </div>
        </section>
      )}

      <div className="images-toolbar">
        <div className="filter-chips" role="group" aria-label="Filter stills">
          {FILTERS.map((item) => (
            <button
              key={item.id}
              type="button"
              className={`filter-chip ${filter === item.id ? "on" : ""}`}
              aria-pressed={filter === item.id}
              onClick={() => setFilter(item.id)}
              disabled={item.id === "made" && counts.made === 0}
            >
              {item.label} <b>{counts[item.id]}</b>
            </button>
          ))}
        </div>
        <div className="images-actions">
          {proofApproved && older.length > 0 && (
            <Button
              size="small"
              disabled={paid.busy || imageJobs.length > 0}
              onClick={() =>
                make(
                  older.map((shot) => shot.id),
                  "stills",
                )
              }
            >
              Remake {older.length} from older prompts · ${price(older.length)}
            </Button>
          )}
          {visibleMissing.length === 1 && (
            <Button
              size="small"
              disabled={paid.busy || imageJobs.length > 0}
              onClick={() => make([visibleMissing[0].id], proofApproved ? "stills" : "proof")}
            >
              Make {visibleMissing[0].id} · ${price(1)}
            </Button>
          )}
          {visibleOlder.length === 1 && proofApproved && (
            <Button
              size="small"
              disabled={paid.busy || imageJobs.length > 0}
              onClick={() => make([visibleOlder[0].id], "stills")}
            >
              Remake {visibleOlder[0].id} · ${price(1)}
            </Button>
          )}
        </div>
      </div>

      {paid.quote && (
        <div className="paid-dock">
          <PaidCard
            quote={paid.quote}
            busy={paid.busy}
            onTopUp={paid.topUp}
            onConfirm={paid.confirm}
            onCancel={paid.clear}
          />
        </div>
      )}
      {(paid.message || paid.error) && (
        <p className={paid.error ? "error" : "message"}>{paid.error || paid.message}</p>
      )}

      {visible.length ? (
        <div className="contact-sheet">
          {visible.map((shot) => {
            const src = sourceUrl(slug, shot);
            const status = statusOf(shot);
            return (
              <button
                type="button"
                key={shot.id}
                data-still={shot.id}
                className={`still-tile ${status.tone} ${making.has(shot.owner) || making.has(shot.id) ? "making" : ""}`}
                onClick={() => open(shot.id)}
                aria-label={`Open ${shot.id}, ${status.label}`}
                aria-busy={making.has(shot.owner) || making.has(shot.id)}
              >
                {(making.has(shot.owner) || making.has(shot.id)) && (
                  <span className="still-making">
                    <i aria-hidden="true" />
                    Making…
                  </span>
                )}
                {src ? (
                  <img src={src} alt="" loading="lazy" />
                ) : (
                  <span className="still-missing">
                    <span>{kindMeta(shot.kind).icon}</span>
                    <span>Not made yet</span>
                  </span>
                )}
                <span className="still-tags">
                  <span className={`still-pill ${status.tone}`}>{status.label}</span>
                  {!shot.local && shot.versions.length > 1 && (
                    <span className="still-pill count">{shot.versions.length} versions</span>
                  )}
                </span>
                <span className="still-foot">
                  <b>{shot.id}</b>
                  <span>
                    {shotById.get(shot.id)?.purpose ||
                      shot.message ||
                      kindMeta(shot.kind).label}
                  </span>
                </span>
              </button>
            );
          })}
        </div>
      ) : loaded ? (
        <EmptyState
          title={shots.length ? "Nothing in this filter." : "No storyboard or assets yet."}
          action={
            shots.length ? undefined : (
              <Button onClick={() => onNavigate("storyboard")}>Go to Storyboard</Button>
            )
          }
        >
          {shots.length
            ? "Clear the filter to see every still."
            : "Make the storyboard first; the stills follow its shots."}
        </EmptyState>
      ) : null}

      {current && (
        <div
          className="lightbox"
          role="dialog"
          aria-modal="true"
          aria-label={`Still ${current.id}`}
          ref={lightboxRef}
        >
          <header className="lightbox-head">
            <div>
              <b>{current.id}</b>
              <span>
                {currentShot
                  ? `${clock(currentShot.start_frame / fps)} · ${(
                      currentShot.duration_frames / fps
                    ).toFixed(1)} s${
                      sectionAt(currentShot.start_frame / fps)
                        ? ` · ${sectionAt(currentShot.start_frame / fps)}`
                        : ""
                    }`
                  : kindMeta(current.kind).label}
              </span>
            </div>
            <span className="lightbox-count">
              {activeIndex + 1} of {visible.length}
            </span>
            <button
              type="button"
              className="lightbox-close"
              onClick={() => setActiveId(null)}
              aria-label="Close the lightbox"
            >
              ×
            </button>
          </header>

          <div className={`lightbox-stage ${statusOf(current).tone}`}>
            {sourceUrl(slug, current) ? (
              <img src={sourceUrl(slug, current) || ""} alt={`${current.id} still`} />
            ) : (
              <div className="lightbox-missing">
                <span>{kindMeta(current.kind).icon}</span>
                <b>Not made yet</b>
                <p>
                  {current.local
                    ? "This kind is made on this computer from the board."
                    : `Make it for $${reserve} when you are ready.`}
                </p>
                {!current.local && (
                  <Button
                    variant="primary"
                    disabled={paid.busy || imageJobs.length > 0}
                    onClick={() => {
                      makeFromLightbox(
                        [current.id],
                        proofIds.includes(current.id) && !proofApproved ? "proof" : "stills",
                      );
                    }}
                  >
                    Make this still · ${reserve}
                  </Button>
                )}
              </div>
            )}
            <span className={`still-pill ${statusOf(current).tone}`}>
              {statusOf(current).label}
            </span>
          </div>

          <footer className="lightbox-foot">
            <div className="lightbox-copy">
              <b>
                {currentShot?.purpose || current.message || kindMeta(current.kind).label}
              </b>
              {current.message && <span className="lightbox-message">{current.message}</span>}
              {current.text?.length > 0 && <p>{current.text.join(" · ")}</p>}
              {currentShot?.image_prompt && (
                <p className="lightbox-prompt">{currentShot.image_prompt}</p>
              )}
              <span className="hint">
                {current.local
                  ? "Rendered locally from the board; no paid task and no review."
                  : current.stale
                    ? "Made from an older prompt. Remake it, or review the new prompt first."
                    : current.review
                      ? `Last review: ${
                          { accept: "kept", reject: "redo", uncertain: "check again" }[
                            current.review.verdict as "accept" | "reject" | "uncertain"
                          ] || current.review.verdict
                        } · v${current.review.version}${
                          current.review.note ? ` · “${current.review.note}”` : ""
                        }`
                      : "Not reviewed yet."}
              </span>
            </div>

            {!current.local && current.versions.length > 0 && (
              <div className="version-row" aria-label="Versions">
                {current.versions.map((version) => (
                  <button
                    type="button"
                    key={version.version}
                    className={`version-pick ${
                      version.version === current.selected ? "on" : ""
                    }`}
                    disabled={working === current.id}
                    onClick={() => void selectVersion(current, version.version)}
                    aria-pressed={version.version === current.selected}
                  >
                    v{version.version}
                    <img
                      src={`/api/projects/${slug}/images/${encodeURIComponent(current.owner)}/${
                        version.version
                      }`}
                      alt=""
                      loading="lazy"
                    />
                  </button>
                ))}
              </div>
            )}

            {!current.local && current.selected !== null && (
              <div className="lightbox-keys">
                {redoOpen === current.id ? (
                  <div className="redo-box">
                    <label className="ui-field">
                      <span>What should change? The Writer rewrites the prompt.</span>
                      <textarea
                        rows={2}
                        value={redoNote}
                        onChange={(event) => setRedoNote(event.target.value)}
                        placeholder="Keep the light, change the pose… (optional)"
                        maxLength={2000}
                      />
                    </label>
                    <div className="row-actions">
                      <Button
                        size="small"
                        disabled={working === current.id}
                        onClick={() => void submitRedo(current, false)}
                      >
                        {working === current.id ? "Saving…" : "Redo · send to Writer"}
                      </Button>
                      <Button
                        size="small"
                        variant="primary"
                        disabled={working === current.id || paid.busy || imageJobs.length > 0}
                        onClick={() => void submitRedo(current, true)}
                      >
                        Remake · ${reserve}
                      </Button>
                      <Button
                        size="small"
                        variant="quiet"
                        onClick={() => {
                          setRedoOpen(null);
                          setRedoNote("");
                        }}
                      >
                        Cancel
                      </Button>
                    </div>
                  </div>
                ) : (
                  <>
                    <Button
                      size="small"
                      variant="primary"
                      disabled={working === current.id || current.stale}
                      title={
                        current.stale
                          ? "Made from an older prompt; remake it first."
                          : "Keep this exact version"
                      }
                      onClick={() => void keep(current)}
                    >
                      Keep <kbd>K</kbd>
                    </Button>
                    <Button
                      size="small"
                      disabled={working === current.id}
                      onClick={() => redo(current)}
                    >
                      Redo <kbd>R</kbd>
                    </Button>
                    <Button
                      size="small"
                      variant="quiet"
                      disabled={paid.busy || imageJobs.length > 0}
                      onClick={() => {
                        makeFromLightbox(
                          [current.id],
                          proofIds.includes(current.id) && !proofApproved
                            ? "proof"
                            : "stills",
                        );
                      }}
                    >
                      Remake · ${reserve}
                    </Button>
                  </>
                )}
              </div>
            )}
            {current.local && (
              <span className="hint">Made here, free. No Keep or Redo.</span>
            )}
            {!current.local && current.selected === null && (
              <span className="hint">Make this still before reviewing it.</span>
            )}
            <div className="lightbox-nav">
              <Button size="small" variant="quiet" onClick={() => move(-1)}>
                ←
              </Button>
              <Button size="small" variant="quiet" onClick={() => move(1)}>
                →
              </Button>
              <span className="hint">
                {current.local || current.selected === null
                  ? "← → move · Esc close"
                  : "K keep · R redo · Esc close"}
              </span>
            </div>
          </footer>
        </div>
      )}
    </>
  );
}
