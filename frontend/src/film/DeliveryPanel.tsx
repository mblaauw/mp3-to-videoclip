import type { Stage } from "../shell/nextStep";
import { usePlayerControls } from "../spine/player";
import { CreditsCard } from "../story/CreditsCard";
import { Button } from "../ui";
import { sampleTitle } from "./titleSamples";
import type { FilmData } from "./useFilmData";

/** The gates, the preview and titles reviews, and the final render. */
export function DeliveryPanel({
  film,
  onNavigate,
  onBack,
}: {
  film: FilmData;
  onNavigate: (stage: Stage) => void;
  onBack: () => void;
}) {
  const player = usePlayerControls();
  const {
    slug, workflow, checklist, checklistError, previewAttested, setPreviewAttested, busy,
    approvePreview, render, rendering, samples, inspected, setInspected, canApproveTitles,
    approveTitles, stillsDone, finalHint, seenSamples, allSamplesSeen, openSample, live,
    sampleIndex, samplesOpen, graphics,
  } = film;
  const windows = live?.titles?.windows ?? [];
  const reviewCurrent = graphics?.current !== false;
  return (
    <>
      <header className="panel-head">
        <h2>{workflow.title}</h2>
        <p className="hint" role="status" aria-live="polite">
          {workflow.detail}
        </p>
        {workflow.notice && <p className="hint" role="status">{workflow.notice}</p>}
      </header>
      <ul className="panel-gates">
        {(checklist?.lines || []).map((item) => (
          <li key={item.id} className={item.state}>
            <span className="gate-mark" aria-hidden="true">
              {item.state === "done" ? "✓" : item.state === "optional" ? "–" : "•"}
            </span>
            <div className="gate-copy">
              <b>{item.label}</b>
              {item.state !== "done" && <span>{item.detail}</span>}
              {item.state !== "done" && item.reason && item.id !== "stills" && (
                <em>{item.reason}</em>
              )}
              {item.id === "preview" && item.state !== "done" && item.expected_hash && (
                <div className="gate-act">
                  <label className="check-line">
                    <input
                      type="checkbox"
                      checked={previewAttested}
                      onChange={(event) => setPreviewAttested(event.target.checked)}
                    />
                    I watched it continuously with the actual music
                  </label>
                  <Button
                    size="small"
                    disabled={!previewAttested || busy !== null}
                    onClick={() => void approvePreview(item)}
                  >
                    {busy === "preview-approval" ? "Approving…" : "Approve preview"}
                  </Button>
                </div>
              )}
              {item.id === "preview" && item.state !== "done" && !item.expected_hash && (
                <div className="gate-act">
                  <Button
                    size="small"
                    variant="primary"
                    disabled={busy !== null || rendering}
                    onClick={() => void render("preview")}
                  >
                    {busy === "preview" ? "Queueing…" : rendering ? "Rendering…" : "Render the preview"}
                  </Button>
                </div>
              )}
              {item.id === "titles" && item.state !== "done" && item.state !== "optional" && (
                <div className="gate-act">
                  {reviewCurrent && samples.length > 0 && (
                    <>
                      <p className="hint">
                        Open each one to see it large. {seenSamples.size} of {samples.length} seen.
                      </p>
                      <ul className="sample-list">
                        {samples.map((sample, index) => (
                          <li key={sample.name}>
                            <button
                              type="button"
                              className={`${seenSamples.has(sample.name) ? "seen" : ""} ${
                                samplesOpen && sampleIndex === index ? "open" : ""
                              }`}
                              onClick={() => {
                                player.pause();
                                if (sample.seconds != null) player.seek(sample.seconds);
                                openSample(index);
                              }}
                            >
                              <img src={sample.url} alt="" loading="lazy" />
                              <span>{sampleTitle(sample, windows)}</span>
                            </button>
                          </li>
                        ))}
                      </ul>
                      <label className="check-line">
                        <input
                          type="checkbox"
                          checked={inspected}
                          disabled={!allSamplesSeen}
                          onChange={(event) => setInspected(event.target.checked)}
                        />
                        I inspected every sample
                      </label>
                      <Button
                        size="small"
                        variant="primary"
                        disabled={!canApproveTitles || busy !== null}
                        onClick={() => void approveTitles(item)}
                      >
                        {busy === "titles-approval" ? "Approving…" : "Approve intro/credits"}
                      </Button>
                    </>
                  )}
                  <Button
                    size="small"
                    variant={reviewCurrent && samples.length ? "quiet" : "primary"}
                    disabled={!stillsDone || busy !== null || rendering}
                    title={
                      stillsDone
                        ? "Render stills of the real film with its titles"
                        : "Approve this cut first."
                    }
                    onClick={() => void render("titles")}
                  >
                    {busy === "titles" ? "Queueing…" : samples.length ? "Check titles again" : "Check titles"}
                  </Button>
                </div>
              )}
            </div>
            {item.id === "story" && item.state !== "done" && (
              <Button size="small" variant="quiet" onClick={() => onNavigate("story")}>
                Go to Story
              </Button>
            )}
            {item.id === "storyboard" && item.state !== "done" && (
              <Button size="small" variant="quiet" onClick={() => onNavigate("storyboard")}>
                Go to Storyboard
              </Button>
            )}
            {item.id === "stills" && item.state !== "done" && (
              <Button size="small" variant="quiet" onClick={() => onNavigate("images")}>
                Go to Images
              </Button>
            )}
          </li>
        ))}
        {!checklist && (
          <li className="blocked">
            {checklistError
              ? "The delivery gates cannot be read yet. Make the story and storyboard first."
              : "Reading the gates…"}
          </li>
        )}
      </ul>
      <div className="row-actions">
        <Button
          variant="primary"
          disabled={!checklist?.can_final || busy !== null || rendering}
          onClick={() => void render("final")}
        >
          {busy === "final" ? "Queueing…" : "Render final"}
        </Button>
        <Button size="small" variant="quiet" onClick={onBack}>
          Back to the cut
        </Button>
      </div>
      <p className="hint">{finalHint}</p>
      <CreditsCard slug={slug} />
    </>
  );
}
