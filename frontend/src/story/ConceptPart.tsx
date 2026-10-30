import type { AudioWindow, IntakePayload } from "../api";
import { Button } from "../ui";
import { BriefCard } from "./BriefCard";
import type { StoryData } from "./useStoryData";

function sectionLength(window: AudioWindow | null): number {
  return window ? Math.max(0, window.end - window.start) : 0;
}

/** The brief facts and excerpt a promo or advert must hold on to. */
export function FilmFacts({
  slug,
  story,
  intake,
  audioWindow,
  windowLocked,
}: {
  slug: string;
  story: StoryData;
  intake: IntakePayload | null;
  audioWindow: AudioWindow | null;
  windowLocked: boolean;
}) {
  if (!intake || intake.kind === "music_video") return null;
  const length = sectionLength(audioWindow);
  const profile = intake.kinds.find((kind) => kind.id === intake.kind);
  const lengths = (profile?.lengths || []).filter((value) => value > 0);
  const nearest =
    lengths.length && length
      ? lengths.reduce((best, value) =>
          Math.abs(value - length) < Math.abs(best - length) ? value : best,
        )
      : null;
  const difference = nearest !== null ? length - nearest : 0;
  const advert = intake.kind === "advert";
  return (
    <>
      {story.brief && (
        <BriefCard
          slug={slug}
          intake={intake}
          audioWindow={audioWindow}
          onIntakeChange={story.intakeChanged}
        />
      )}
      {audioWindow && (
        <div className="excerpt-summary">
          <b>Song excerpt · {length.toFixed(1)} s</b>
          {nearest !== null && Math.abs(difference) > 0.25 && (
            <span className="excerpt-warning">
              {Math.abs(difference).toFixed(1)} s {difference > 0 ? "longer" : "shorter"} than
              the {nearest} s {advert ? "advert" : "promo"}
            </span>
          )}
          {nearest !== null && Math.abs(difference) <= 0.25 && (
            <span>matches the {nearest} s {advert ? "advert" : "promo"}</span>
          )}
          <span className="hint">
            {windowLocked
              ? "The storyboard is built on this excerpt, so it is fixed. Start a new film to choose a different part of the song."
              : `Drag the gold handles on the timeline. Fades ${audioWindow.fade_in.toFixed(1)} s in and ${audioWindow.fade_out.toFixed(1)} s out.`}
          </span>
        </div>
      )}
    </>
  );
}

export function ConceptPart({ story, onStart }: { story: StoryData; onStart: () => void }) {
  const { concepts, chosen, chooseConcept, writeConcepts, writerBusy } = story;
  return (
    <section className="stage-block concepts-block">
      <h2>
        Concepts <small>From the Writer · pick one to build on</small>
      </h2>
      {concepts.length ? (
        <>
          <div className="concepts">
            {concepts.map((concept) => (
              <button
                type="button"
                className="concept"
                key={concept.id}
                aria-pressed={chosen === concept.id}
                onClick={() => void chooseConcept(concept.id)}
              >
                {chosen === concept.id && <span className="chosen">Chosen</span>}
                <h3>{concept.title}</h3>
                <p>{concept.logline}</p>
              </button>
            ))}
          </div>
          <div className="row-actions">
            <Button size="small" variant="quiet" disabled={writerBusy} onClick={() => writeConcepts(3)}>
              Ask for three more
            </Button>
          </div>
        </>
      ) : (
        <div className="empty-block">
          <p>{writerBusy ? "The Writer is working on this." : "No concepts yet."}</p>
          {!writerBusy && <Button onClick={onStart}>Choose how to start</Button>}
        </div>
      )}
    </section>
  );
}
