import type { Storyboard } from "../api";
import type { Stage } from "../shell/nextStep";
import { Button } from "../ui";
import type { FilmData } from "./useFilmData";

/** Before a first cut exists: what to do next, and that it is optional. */
export function SeedCut({
  film,
  board,
  onNavigate,
}: {
  film: FilmData;
  board: Storyboard | null;
  onNavigate: (stage: Stage) => void;
}) {
  if (!board) {
    return (
      <div className="seed-cut">
        <h3>The storyboard comes first</h3>
        <p>Film reads the cut from the approved storyboard. Make it, then let the Editor cut it.</p>
        <div className="row-actions">
          <Button variant="primary" onClick={() => onNavigate("storyboard")}>
            Go to Storyboard
          </Button>
        </div>
      </div>
    );
  }
  return (
    <div className="seed-cut">
      <h3>Let the Editor cut it</h3>
      <p>
        The film already plays with the storyboard's timing. Make a first cut to shape joins,
        camera moves and timing here.
      </p>
      <div className="row-actions">
        <Button
          variant="primary"
          disabled={film.busy !== null}
          onClick={() => void film.seedCut()}
        >
          {film.busy === "seed" ? "Cutting…" : "Make a first cut"}
        </Button>
      </div>
      <p className="hint">Skipping it costs nothing and keeps every current approval valid.</p>
    </div>
  );
}
