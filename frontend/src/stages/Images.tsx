import { shown } from "../storyboard/placeholders";
import { ApprovalBar } from "../ApprovalBar";
import { ReferencePicker } from "../images/ReferencePicker";
import { MakeClip } from "../images/MakeClip";
import { MakeSharper } from "../images/MakeSharper";
import { NewRoundCard } from "../images/NewRoundCard";
import { PaidCard } from "../images/PaidCard";
import { JobBanner } from "../jobs/JobBanner";
import { notifyProjectChanged } from "../shell/projectEvents";
import { kindMeta } from "../shotKinds";
import { Button, EmptyState, ErrorState, LoadingState } from "../ui";
import { StyleCheck } from "../images/StyleCheck";
import { type ImagesStageProps, useImagesData } from "../images/useImagesData";
import { FILTERS, clock, money, sourceUrl, statusOf } from "../images/imageStatus";

export function ImagesStage(props: ImagesStageProps) {
  const { slug, reserve, onNavigate } = props;
  const data = useImagesData(props);
  const { activeIndex, answerRef, budget, counts, current, currentShot, error, filter, fps, imageJobs, keep, kept, lightboxRef, load, loaded, make, makeFromLightbox, making, move, older, open, paid, paidShots, price, proofApproved, proofIds, redo, redoNote, redoOpen, sectionAt, selectVersion, setActiveId, setFilter, setRedoNote, setRedoOpen, shotById, shots, submitRedo, visible, visibleMissing, visibleOlder, working } = data;
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
        <StyleCheck data={data} props={props} />
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

      <div ref={answerRef}>
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
      {paid.newRound && (
        <div className="paid-dock">
          <NewRoundCard
            shots={paid.newRound.used}
            busy={paid.busy}
            onStart={(note) => void paid.startNewRound(note)}
            onCancel={paid.clear}
          />
        </div>
      )}
      {(paid.message || paid.error) && (
        <p className={paid.error ? "error" : "message"}>{paid.error || paid.message}</p>
      )}
      </div>

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
                    {shown(shotById.get(shot.id)?.purpose) ||
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
                {shown(currentShot?.purpose) || current.message || kindMeta(current.kind).label}
              </b>
              {current.message && <span className="lightbox-message">{current.message}</span>}
              {current.text?.length > 0 && <p>{current.text.join(" · ")}</p>}
              {currentShot && shown(currentShot.image_prompt) && (
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

            {!current.local && !current.stale && current.selected != null && (
              <MakeSharper
                slug={slug}
                shotId={current.id}
                disabled={imageJobs.length > 0}
                onStarted={() => notifyProjectChanged({ slug })}
              />
            )}
            {current.paid && !current.stale && current.selected != null && current.id === current.owner && (
              <MakeClip
                slug={slug}
                shot={current}
                disabled={imageJobs.length > 0}
                onChanged={() => notifyProjectChanged({ slug })}
              />
            )}
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
                    {version.derivation ? ` · ${version.derivation.factor}×` : ""}
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
              <ReferencePicker
                key={`${current.owner}-${current.selected}`}
                slug={slug}
                shotId={current.owner}
                version={current.selected}
                src={`/api/projects/${slug}/images/${encodeURIComponent(current.owner)}/${current.selected}`}
              />
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
                        disabled={
                          working === current.id ||
                          paid.busy ||
                          imageJobs.length > 0 ||
                          !redoNote.trim()
                        }
                        title={redoNote.trim() ? undefined : "Say what should change first"}
                        onClick={() => void submitRedo(current, true, true)}
                      >
                        Edit this one · ${reserve}
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
