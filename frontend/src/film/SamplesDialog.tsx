import { useEffect, useRef } from "react";
import type { GraphicsSample } from "../api";
import { Button, useFocusTrap } from "../ui";
import type { FilmData } from "./useFilmData";

function clock(seconds: number): string {
  const value = Math.max(0, Math.floor(seconds));
  return `${Math.floor(value / 60)}:${String(value % 60).padStart(2, "0")}`;
}

/** "card-02 at 3:28 · frame 4992" for a composition sample; the file name otherwise. */
function sampleLabel(sample: GraphicsSample | undefined): string {
  if (!sample) return "Sample";
  if (sample.frame == null || sample.seconds == null) return sample.name;
  return `${sample.window ?? "film"} at ${clock(sample.seconds)} · frame ${sample.frame}`;
}

/** Every titles sample at full size, with the inspected attestation beside it. */
export function SamplesDialog({ film }: { film: FilmData }) {
  const {
    samples, samplesOpen, setSamplesOpen, sampleIndex, setSampleIndex, inspected, setInspected,
    titlesLine, canApproveTitles, busy, approveTitles,
  } = film;
  const samplesRef = useRef<HTMLDivElement>(null);
  useFocusTrap(samplesOpen && samples.length > 0, samplesRef);

  useEffect(() => {
    if (!samplesOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setSamplesOpen(false);
      if (event.key === "ArrowRight") {
        setSampleIndex((index) =>
          Math.min(index + 1, Math.max(samples.length - 1, 0)),
        );
      }
      if (event.key === "ArrowLeft") setSampleIndex((index) => Math.max(index - 1, 0));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [samplesOpen, samples.length]);

  if (!samplesOpen || samples.length === 0) return null;
  return (
        <div
          className="samples-lightbox"
          role="dialog"
          aria-modal="true"
          aria-label="Graphics samples"
          ref={samplesRef}
        >
          <header>
            <b>{sampleLabel(samples[sampleIndex])}</b>
            <span>
              {sampleIndex + 1} of {samples.length}
            </span>
            <button
              type="button"
              className="lightbox-close"
              aria-label="Close the samples"
              onClick={() => setSamplesOpen(false)}
            >
              ×
            </button>
          </header>
          <div className="samples-stage">
            <img src={samples[sampleIndex]?.url} alt={`Graphics sample ${sampleIndex + 1}`} />
          </div>
          <footer>
            <Button
              size="small"
              variant="quiet"
              onClick={() => setSampleIndex((index) => Math.max(index - 1, 0))}
            >
              ←
            </Button>
            <Button
              size="small"
              variant="quiet"
              onClick={() =>
                setSampleIndex((index) => Math.min(index + 1, samples.length - 1))
              }
            >
              →
            </Button>
            <label className="check-line">
              <input
                type="checkbox"
                checked={inspected}
                onChange={(event) => setInspected(event.target.checked)}
              />
              I inspected every sample
            </label>
            {titlesLine && (
              <Button
                size="small"
                variant="primary"
                disabled={!canApproveTitles || busy !== null}
                onClick={() => void approveTitles(titlesLine)}
              >
                {busy === "titles-approval" ? "Approving…" : "Approve intro/credits"}
              </Button>
            )}
            <Button size="small" variant="quiet" onClick={() => setSamplesOpen(false)}>
              Close
            </Button>
          </footer>
        </div>
  );
}
