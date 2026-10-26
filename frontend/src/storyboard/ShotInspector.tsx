import { useEffect, useRef, useState } from "react";
import {
  api,
  type ImageShot,
  type Music,
  type Shot,
  type ShotKind,
  type Storyboard,
} from "../api";
import { usePaidImages } from "../images/paid";
import { PaidCard } from "../images/PaidCard";
import { notifyProjectChanged } from "../shell/projectEvents";
import { SHOT_KINDS, isPaidShot, kindMeta, kindOf } from "../shotKinds";
import { Button } from "../ui";
import { ShotThumb } from "./ShotThumb";

function clock(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

function sectionFor(music: Music | null, seconds: number): string {
  const section = (music?.sections || []).find(
    (item) => seconds >= Number(item.start) && seconds < Number(item.end),
  );
  if (!section) return "No measured section";
  return (
    section.name ||
    (section.label && section.label !== "unreviewed"
      ? section.label
      : "Measured section")
  );
}

function splitLines(value: string, limit = 8): string[] {
  return value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .slice(0, limit);
}

export function ShotInspector({
  slug,
  shotId,
  board,
  images,
  music,
  kinds,
  proofIds,
  reserve,
  timingOwned,
  onSelect,
  onBoardChange,
  onClose,
}: {
  slug: string;
  shotId: string;
  board: Storyboard | null;
  images: ImageShot[];
  music: Music | null;
  kinds?: typeof SHOT_KINDS;
  proofIds: string[];
  reserve: string;
  timingOwned: boolean;
  onSelect: (shotId: string) => void;
  onBoardChange: (board: Storyboard) => void;
  onClose: () => void;
}) {
  const shot = board?.shots.find((item) => item.id === shotId) || null;
  const image = images.find((item) => item.id === shotId);
  const [draft, setDraft] = useState<Partial<Shot>>({});
  const [saved, setSaved] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const timer = useRef<number | null>(null);
  const savedTimer = useRef<number | null>(null);
  const draftRef = useRef<Partial<Shot>>({});
  draftRef.current = draft;
  const saveSeq = useRef(0);
  const paid = usePaidImages(slug, reserve, () => {
    notifyProjectChanged();
    setSaved(true);
  });

  useEffect(() => {
    setDraft({});
    setError(null);
    paid.clear();
    // The paid flow belongs to one shot; never carry a quote to the next.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [shotId]);

  useEffect(
    () => () => {
      if (timer.current) window.clearTimeout(timer.current);
      if (savedTimer.current) window.clearTimeout(savedTimer.current);
    },
    [],
  );

  const current: Shot | null = shot ? ({ ...shot, ...draft } as Shot) : null;
  const dirty = Object.keys(draft).length > 0;
  const index = board?.shots.findIndex((item) => item.id === shotId) ?? -1;
  const fps = board?.fps || 24;

  const flash = () => {
    setSaved(true);
    if (savedTimer.current) window.clearTimeout(savedTimer.current);
    savedTimer.current = window.setTimeout(() => setSaved(false), 2000);
  };

  const savePatch = async (patch: Partial<Shot> = {}) => {
    if (!shot) return;
    const merged = { ...draftRef.current, ...patch };
    if (!Object.keys(merged).length) return;
    const sequence = saveSeq.current + 1;
    saveSeq.current = sequence;
    setBusy(true);
    setError(null);
    try {
      const updated = await api.patchShots(slug, [{ id: shot.id, ...merged }]);
      if (sequence !== saveSeq.current) return;
      onBoardChange(updated);
      setDraft((current) => {
        const next = { ...current };
        for (const [key, value] of Object.entries(merged)) {
          if (JSON.stringify(current[key as keyof Shot]) === JSON.stringify(value)) {
            delete next[key as keyof Shot];
          }
        }
        return next;
      });
      flash();
      notifyProjectChanged();
    } catch (caught) {
      if (sequence === saveSeq.current) setError(String(caught));
    } finally {
      if (sequence === saveSeq.current) setBusy(false);
    }
  };

  const save = async () => {
    await savePatch();
  };

  const changeAndSave = (key: keyof Shot, value: unknown) => {
    setDraft((valueDraft) => ({ ...valueDraft, [key]: value }));
    void savePatch({ [key]: value });
  };

  useEffect(() => {
    if (!dirty) return;
    if (timer.current) window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => {
      timer.current = null;
      void save();
    }, 700);
    return () => {
      if (timer.current) window.clearTimeout(timer.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [draft]);

  if (!shot || !current) return null;

  const change = (key: keyof Shot, value: unknown) =>
    setDraft((valueDraft) => ({ ...valueDraft, [key]: value }));

  const changeKind = (kind: ShotKind) => {
    const next: Partial<Shot> = { kind };
    if (kind === "bridge") {
      next.bridge =
        shot.bridge ?? {
          mode: "designed",
          match: { type: "shape", anchor: [0.5, 0.5], note: "" },
        };
    } else {
      next.bridge = null;
    }
    if (kind === "split") {
      const candidates =
        board?.shots
          .filter((item) => item.id !== shot.id && kindOf(item) !== "split")
          .map((item) => item.id) ?? [];
      next.panes =
        shot.panes && shot.panes.length
          ? shot.panes
          : candidates.slice(0, 2).map((shot_id) => ({ shot_id }));
    } else {
      next.panes = [];
    }
    if (kind === "reprise") {
      next.asset_shot_id =
        shot.asset_shot_id ||
        board?.shots.find((item) => item.id !== shot.id && !item.asset_shot_id)?.id ||
        null;
    } else if (shot.asset_shot_id) {
      next.asset_shot_id = null;
    }
    if (!["upload", "product", "card", "logo", "end_card"].includes(kind)) {
      next.asset = null;
    }
    if (
      ["card", "end_card", "logo"].includes(kind) &&
      !(shot.message || "").trim() &&
      !shot.text?.length
    ) {
      next.message = shot.purpose;
    }
    if (isPaidShot({ ...shot, ...next } as Shot) && !(shot.image_prompt || "").trim()) {
      next.image_prompt = shot.purpose;
    }
    setDraft((valueDraft) => ({ ...valueDraft, ...next }));
  };

  const go = async (offset: number) => {
    if (!board) return;
    const next = board.shots[index + offset];
    if (!next) return;
    if (Object.keys(draft).length) await save();
    onSelect(next.id);
  };

  const close = async () => {
    if (Object.keys(draft).length) await save();
    onClose();
  };

  const paidKind = isPaidShot(current);
  const meta = kindMeta(kindOf(current));
  const section = sectionFor(music, current.start_frame / fps);
  const time = `${clock(current.start_frame / fps)}–${clock(
    (current.start_frame + current.duration_frames) / fps,
  )}`;
  const generated = paidKind;
  const proof = proofIds.includes(current.id);

  return (
    <aside className="director shot-inspector" aria-label={`Inspector for ${shot.id}`}>
      <header>
        <div className="director-heading">
          <h2>{shot.id}</h2>
          <div className="director-model">
            {time} · {(current.duration_frames / fps).toFixed(1)} s · {section}
          </div>
        </div>
        <Button
          size="small"
          variant="quiet"
          aria-label="Previous shot"
          disabled={index <= 0}
          onClick={() => void go(-1)}
        >
          ←
        </Button>
        <Button
          size="small"
          variant="quiet"
          aria-label="Next shot"
          disabled={!board || index >= board.shots.length - 1}
          onClick={() => void go(1)}
        >
          →
        </Button>
        <Button size="small" variant="quiet" aria-label="Close inspector" onClick={() => void close()}>
          ×
        </Button>
      </header>
      <div className="inspector-body">
        <ShotThumb slug={slug} shot={current} image={image} className="inspector-thumb" />
        <div className="inspector-meta">
          <span>{meta.label}</span>
          <span>{paidKind ? `$${reserve}` : "Made here, free"}</span>
          <span>
            {image?.review?.verdict === "accept"
              ? "Kept"
              : image?.review?.verdict === "reject"
                ? "Redo"
                : paidKind
                  ? "Not reviewed"
                  : "Local plate"}
          </span>
        </div>

        <label className="ui-field">
          <span>Kind</span>
          <select
            value={kindOf(current)}
            onChange={(event) => changeKind(event.target.value as ShotKind)}
          >
            {(kinds || SHOT_KINDS).map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
          <p className="ui-hint">
            {meta.hint}. {paidKind ? `A still costs $${reserve}.` : "Made on this computer, free."}
          </p>
        </label>

        <label className="ui-field">
          <span>Job of this shot</span>
          <textarea
            rows={2}
            value={current.purpose}
            maxLength={400}
            onChange={(event) => change("purpose", event.target.value)}
            onBlur={() => void save()}
          />
        </label>

        <label className="ui-field">
          <span>What this shot says</span>
          <textarea
            rows={2}
            value={current.message || ""}
            maxLength={400}
            onChange={(event) => change("message", event.target.value)}
            onBlur={() => void save()}
          />
        </label>

        <label className="ui-field">
          <span>On-screen text (one line per row)</span>
          <textarea
            rows={3}
            value={(current.text || []).join("\n")}
            onChange={(event) => change("text", splitLines(event.target.value))}
            onBlur={() => void save()}
          />
        </label>

        {generated ? (
          <>
            <label className="ui-field">
              <span>Picture prompt</span>
              <textarea
                rows={5}
                value={current.image_prompt || ""}
                onChange={(event) => change("image_prompt", event.target.value)}
                onBlur={() => void save()}
                placeholder="Describe the decisive still"
              />
              <p className="ui-hint">
                Editing the prompt marks this still as made from an older prompt. Nothing is
                remade until you ask.
              </p>
            </label>
            <label className="ui-field">
              <span>Must show (one per row)</span>
              <textarea
                rows={2}
                value={(current.must_show || []).join("\n")}
                onChange={(event) =>
                  change(
                    "must_show",
                    event.target.value
                      .split("\n")
                      .map((line) => line.trim())
                      .filter(Boolean),
                  )
                }
                onBlur={() => void save()}
              />
            </label>
          </>
        ) : (
          <p className="ui-hint">
            {meta.label} shots are made locally; there is no picture prompt or paid task.
          </p>
        )}

        <div className="inspector-grid">
          <label className="ui-field">
            <span>Framing</span>
            <select
              value={current.framing || ""}
              onChange={(event) => {
                changeAndSave("framing", event.target.value || null);
              }}
            >
              <option value="">—</option>
              <option value="wide">wide</option>
              <option value="medium">medium</option>
              <option value="close_up">close up</option>
              <option value="detail">detail</option>
            </select>
          </label>
          <label className="ui-field">
            <span>Camera</span>
            <select
              value={current.camera}
              disabled={timingOwned}
              onChange={(event) => {
                changeAndSave("camera", event.target.value);
              }}
            >
              <option value="hold">hold</option>
              <option value="zoom_in">push in</option>
              <option value="zoom_out">pull back</option>
              <option value="pan_left">pan left</option>
              <option value="pan_right">pan right</option>
            </select>
          </label>
        </div>

        <label className="ui-field">
          <span>Into this shot</span>
          <select
            value={current.transition || ""}
            disabled={timingOwned}
            onChange={(event) => {
              changeAndSave("transition", event.target.value || null);
            }}
          >
            <option value="">Cut</option>
            <option value="fade">Fade</option>
            <option value="wipe_left">Wipe left</option>
            <option value="wipe_right">Wipe right</option>
          </select>
          {timingOwned && <p className="ui-hint">Timing and motion are owned by the Film cut.</p>}
        </label>

        {kindOf(current) === "product" && (
          <label className="ui-field">
            <span>Product reference</span>
            <input
              value={current.product_ref || ""}
              onChange={(event) => change("product_ref", event.target.value || null)}
              onBlur={() => void save()}
              placeholder="Project-relative image path"
            />
          </label>
        )}
        {kindOf(current) === "upload" && (
          <label className="ui-field">
            <span>Uploaded asset</span>
            <input
              value={current.asset || ""}
              onChange={(event) => change("asset", event.target.value || null)}
              onBlur={() => void save()}
              placeholder="Project-relative image path"
            />
          </label>
        )}
        {kindOf(current) === "reprise" && (
          <label className="ui-field">
            <span>Repeat the still from</span>
            <select
              value={current.asset_shot_id || ""}
              onChange={(event) => {
                changeAndSave("asset_shot_id", event.target.value || null);
              }}
            >
              <option value="">—</option>
              {(board?.shots || [])
                .filter((item) => item.id !== current.id && !item.asset_shot_id)
                .map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.id}
                  </option>
                ))}
            </select>
          </label>
        )}
        {kindOf(current) === "bridge" && current.bridge && (
          <>
            <label className="ui-field">
              <span>Bridge</span>
              <select
                value={current.bridge.mode}
                onChange={(event) => {
                  changeAndSave("bridge", {
                    ...current.bridge,
                    mode: event.target.value,
                  });
                }}
              >
                <option value="designed">Designed here, free</option>
                <option value="generated">Generated still</option>
              </select>
            </label>
            <label className="ui-field">
              <span>Match</span>
              <select
                value={current.bridge.match?.type || "shape"}
                onChange={(event) => {
                  changeAndSave("bridge", {
                    ...current.bridge,
                    match: {
                      type: event.target.value,
                      anchor: current.bridge?.match?.anchor || [0.5, 0.5],
                      note: current.bridge?.match?.note || "",
                    },
                  });
                }}
              >
                <option value="shape">Shape</option>
                <option value="colour">Colour</option>
                <option value="position">Position</option>
              </select>
            </label>
          </>
        )}
        {kindOf(current) === "split" && (
          <div className="ui-field">
            <span>Panes</span>
            {(current.panes || []).map((pane, paneIndex) => (
              <select
                key={`${pane.shot_id}-${paneIndex}`}
                value={pane.shot_id}
                onChange={(event) => {
                  const panes = [...(current.panes || [])];
                  panes[paneIndex] = { ...pane, shot_id: event.target.value };
                  change("panes", panes);
                  void save();
                }}
              >
                {(board?.shots || [])
                  .filter((item) => item.id !== current.id && kindOf(item) !== "split")
                  .map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.id}
                    </option>
                  ))}
              </select>
            ))}
            {(current.panes?.length || 0) < 3 && (
              <Button
                size="small"
                variant="quiet"
                onClick={() => {
                  const used = new Set((current.panes || []).map((pane) => pane.shot_id));
                  const candidate = board?.shots.find(
                    (item) => item.id !== current.id && kindOf(item) !== "split" && !used.has(item.id),
                  );
                  if (!candidate) return;
                  change("panes", [
                    ...(current.panes || []),
                    { shot_id: candidate.id },
                  ]);
                  void save();
                }}
              >
                Add pane
              </Button>
            )}
          </div>
        )}

        <div className="row-actions">
          <Button
            size="small"
            variant="quiet"
            onClick={() =>
              window.dispatchEvent(
                new CustomEvent("studio:ask-director", {
                  detail: {
                    text: `Revise shot ${current.id} in the storyboard. Keep its ${(
                      current.duration_frames / fps
                    ).toFixed(1)} s and ${kindMeta(kindOf(current)).label} kind unless the story needs otherwise. ${current.purpose}`,
                  },
                }),
              )
            }
          >
            Ask the Writer
          </Button>
          {generated && (
            <Button
              size="small"
              disabled={paid.busy}
              onClick={() => void paid.request([current.id], proof ? "proof" : "stills", true)}
            >
              Remake still · ${reserve}
            </Button>
          )}
        </div>
        {paid.quote && (
          <PaidCard
            quote={paid.quote}
            busy={paid.busy}
            onTopUp={paid.topUp}
            onConfirm={paid.confirm}
            onCancel={paid.clear}
          />
        )}
        {paid.message && <p className="message">{paid.message}</p>}
        {paid.error && <p className="error">{paid.error}</p>}
        {saved && <p className="saved-note">Saved</p>}
        {busy && <p className="saved-note">Saving…</p>}
        {error && <p className="error">{error}</p>}
      </div>
    </aside>
  );
}
