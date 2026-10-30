import type { Stage } from "../shell/nextStep";
import { JobBanner } from "../jobs/JobBanner";
import { Button } from "../ui";
import type { FilmData } from "./useFilmData";

/** The gates, reviews and the final render. */
export function DeliveryCard({
  film,
  onNavigate,
}: {
  film: FilmData;
  onNavigate: (stage: Stage) => void;
}) {
  const {
    slug, workflow, checklist, checklistError, previewAttested, setPreviewAttested, busy,
    approvePreview, render, rendering, samples, setSampleIndex, setSamplesOpen, inspected,
    setInspected, canApproveTitles, approveTitles, stillsDone, finalHint,
  } = film;
  return (
            <section className="delivery-card">
              <header>
                <div>
                  <h2>{workflow.title}</h2>
                  <p role="status" aria-live="polite">{workflow.detail}</p>
                  {workflow.notice && <p role="status">{workflow.notice}</p>}
                </div>
                {checklist && (
                  <span className={`delivery-state ${workflow.ready ? "ready" : ""}`}>
                    {workflow.ready
                      ? "Delivery ready"
                      : checklist.can_final
                        ? "Gates approved"
                        : `${checklist.outstanding.length} ${checklist.outstanding.length === 1 ? "gate" : "gates"} to go`}
                  </span>
                )}
              </header>
              <ul className="check-list">
                {(checklist?.lines || []).map((item) => (
                  <li key={item.id} className={`check-item ${item.state}`}>
                    <span className="check-mark" aria-hidden="true">
                      {item.state === "done" ? "✓" : item.state === "optional" ? "–" : "•"}
                    </span>
                    <div className="check-copy">
                      <b>{item.label}</b>
                      <span>{item.detail}</span>
                      {item.state !== "done" && item.reason && item.id !== "stills" && (
                        <em>{item.reason}</em>
                      )}
                      {item.id === "preview" &&
                        item.state !== "done" &&
                        item.expected_hash && (
                          <span className="check-attest">
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
                          </span>
                        )}
                      {item.id === "preview" && item.state !== "done" && !item.expected_hash && (
                        <span className="check-attest">
                          <Button
                            size="small"
                            variant="primary"
                            disabled={busy !== null || rendering}
                            onClick={() => void render("preview")}
                          >
                            {busy === "preview" ? "Queueing…" : rendering ? "Rendering…" : "Render the preview"}
                          </Button>
                        </span>
                      )}
                      {item.id === "titles" && item.state !== "done" && item.state !== "optional" && (
                        <span className="check-attest">
                          {samples.length > 0 && (
                            <>
                              <button
                                type="button"
                                className="samples-strip"
                                onClick={() => {
                                  setSampleIndex(0);
                                  setSamplesOpen(true);
                                }}
                                aria-label="Open the graphics samples"
                              >
                                {samples.slice(0, 4).map((sample) => (
                                  <img key={sample.name} src={sample.url} alt="" loading="lazy" />
                                ))}
                              </button>
                              <label className="check-line">
                                <input
                                  type="checkbox"
                                  checked={inspected}
                                  onChange={(event) => setInspected(event.target.checked)}
                                />
                                I inspected every sample
                              </label>
                              <Button
                                size="small"
                                disabled={!canApproveTitles || busy !== null}
                                onClick={() => void approveTitles(item)}
                              >
                                {busy === "titles-approval" ? "Approving…" : "Approve intro/credits"}
                              </Button>
                            </>
                          )}
                          <Button
                            size="small"
                            variant={samples.length ? "quiet" : "primary"}
                            disabled={!stillsDone || busy !== null || rendering}
                            title={
                              stillsDone
                                ? "Render stills of the real film with its titles"
                                : "Approve every still first."
                            }
                            onClick={() => void render("titles")}
                          >
                            {busy === "titles" ? "Queueing…" : "Check titles"}
                          </Button>
                          <span className="hint">
                            Check titles renders stills of the real film with its titles; no base
                            is needed. Your intro/credits approval is manual; this does not render a
                            final.
                          </span>
                        </span>
                      )}
                    </div>
                    {item.id === "story" && item.state !== "done" && (
                      <Button size="small" variant="quiet" onClick={() => onNavigate("story")}>
                        Go to Story
                      </Button>
                    )}
                    {item.id === "storyboard" && item.state !== "done" && (
                      <Button
                        size="small"
                        variant="quiet"
                        onClick={() => onNavigate("storyboard")}
                      >
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
                  <li className="check-item blocked">
                    {checklistError
                      ? "The delivery gates cannot be read yet. Make the story and storyboard first."
                      : "Reading the gates…"}
                  </li>
                )}
              </ul>
              <JobBanner slug={slug} kinds={["render"]} className="in-card" />
              <footer>
                <Button
                  variant="primary"
                  disabled={!checklist?.can_final || busy !== null || rendering}
                  onClick={() => void render("final")}
                >
                  {busy === "final" ? "Queueing…" : "Render final"}
                </Button>
                <span className="hint">{finalHint}</span>
              </footer>
            </section>
  );
}
