import { useState } from "react";
import { api } from "../api";
import { notifyProjectChanged } from "../shell/projectEvents";
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
  const [variantError, setVariantError] = useState<string | null>(null);
  const [rate48, setRate48] = useState(false);
  const [loudness, setLoudness] = useState(false);
  const [jpeg, setJpeg] = useState(false);
  const loudnessRefusal = checklist?.loudness_refusal ?? null;
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
                  <p className="hint">A half-size preview, to watch with the music.</p>
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
      <fieldset className="final-options">
        <legend>Final options</legend>
        <label className="settings-check">
          <input type="checkbox" checked={rate48} onChange={(event) => setRate48(event.target.checked)} />{" "}
          48 kHz sound
        </label>
        <label className="settings-check">
          <input
            type="checkbox"
            checked={loudness && !loudnessRefusal}
            disabled={Boolean(loudnessRefusal)}
            onChange={(event) => setLoudness(event.target.checked)}
          />{" "}
          Normalise to −14 LUFS
        </label>
        {loudnessRefusal && <p className="hint">{loudnessRefusal}</p>}
        <label className="settings-check">
          <input type="checkbox" checked={jpeg} onChange={(event) => setJpeg(event.target.checked)} />{" "}
          Capture as JPEG 90 (smaller and faster; PNG is the default until you have watched one)
        </label>
      </fieldset>
      <div className="row-actions">
        <Button
          variant="primary"
          disabled={!checklist?.can_final || busy !== null || rendering}
          onClick={() =>
            void render("final", {
              ...(rate48 ? { sample_rate: 48000 as const } : {}),
              ...(loudness && !loudnessRefusal ? { loudness: true } : {}),
              ...(jpeg ? { capture: "jpeg90" as const } : {}),
            })
          }
        >
          {busy === "final" ? "Queueing…" : "Render final"}
        </Button>
        <Button size="small" variant="quiet" onClick={onBack}>
          Back to the cut
        </Button>
      </div>
      <p className="hint">{finalHint}</p>
      <div className="row-actions">
        {(["9:16", "1:1"] as const).map((shape) => (
          <Button
            key={shape}
            size="small"
            disabled={busy !== null || rendering}
            onClick={() => {
              setVariantError(null);
              api
                .renderVariant(slug, shape)
                .then(() => notifyProjectChanged({ slug }))
                .catch((caught) =>
                  setVariantError(caught instanceof Error ? caught.message : String(caught)),
                );
            }}
          >
            Render {shape}
          </Button>
        ))}
      </div>
      <p className="hint">
        A version of the current final, from the same cut. Check its framing with the shape buttons
        under the picture first.
      </p>
      {variantError && <p className="ui-state error compact" role="alert">{variantError}</p>}
      <CreditsCard slug={slug} />
    </>
  );
}
