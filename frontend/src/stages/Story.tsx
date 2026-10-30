import { useEffect, useState } from "react";
import type { AudioWindow, IntakePayload, Music } from "../api";
import { ApprovalBar } from "../ApprovalBar";
import { ArtifactRating } from "../ArtifactRating";
import { ConceptRoom } from "../story/ConceptRoom";
import { CreditsCard } from "../story/CreditsCard";
import { FilmFacts } from "../story/FilmFacts";
import { ScriptPart } from "../story/ScriptPart";
import { StartPart } from "../story/StartPart";
import { StoryChanges } from "../story/StoryChanges";
import { useStoryData } from "../story/useStoryData";
import { WorldPart } from "../story/WorldPart";
import { Button, EmptyState, ErrorState, LoadingState } from "../ui";

export type StoryPart = "start" | "concept" | "story" | "world" | "credits";

const PARTS: { id: StoryPart; label: string }[] = [
  { id: "start", label: "Start" },
  { id: "concept", label: "Concept" },
  { id: "story", label: "Story" },
  { id: "world", label: "World" },
  { id: "credits", label: "Credits" },
];

export function StoryStage({
  slug,
  intake,
  audioWindow,
  windowLocked = false,
  onIntakeChange,
  music,
}: {
  slug: string;
  intake: IntakePayload | null;
  audioWindow: AudioWindow | null;
  windowLocked?: boolean;
  onIntakeChange: (intake: IntakePayload) => void;
  music: Music | null;
}) {
  const story = useStoryData({ slug, intake, onIntakeChange });
  const { brief, concepts, loading, error, load } = story;
  const [picked, setPicked] = useState<StoryPart | null>(null);
  // Until you pick, a film opens where it is: its story, its concepts, or the start.
  const part: StoryPart =
    picked ?? (brief?.treatment?.trim() ? "story" : concepts.length ? "concept" : "start");

  useEffect(() => {
    const show = (event: Event) => {
      const next = (event as CustomEvent<StoryPart>).detail;
      if (PARTS.some((item) => item.id === next)) setPicked(next);
    };
    window.addEventListener("studio:story-part", show);
    return () => window.removeEventListener("studio:story-part", show);
  }, []);

  return (
    <>
      <div className="stage-head story-head">
        <div>
          <h1>Story</h1>
          <p>Pick a direction, shape the story and set the look every picture will share.</p>
          <ApprovalBar stages={["brief"]} />
        </div>
        <div className="stage-ratings" aria-label="Rate the story artifacts">
          <ArtifactRating slug={slug} artifact="brief" />
          <ArtifactRating slug={slug} artifact="treatments" />
        </div>
      </div>
      {error && (
        <ErrorState
          what={brief ? "saving the story" : "reading the story"}
          error={error}
          compact={!!brief}
          onRetry={brief ? undefined : () => void load()}
        />
      )}
      {loading && !brief && !error && <LoadingState>Reading the current story…</LoadingState>}
      {!loading && !brief && !error && (
        <EmptyState
          title="The story could not be read."
          action={<Button onClick={() => void load()}>Retry loading the story</Button>}
        >
          Nothing was changed. Try again, or check that the brief exists for this film.
        </EmptyState>
      )}

      <StoryChanges story={story} />

      {brief && (
        <>
      <nav className="story-parts" aria-label="Story parts">
        {PARTS.map((item) => (
          <Button
            key={item.id}
            size="small"
            variant={part === item.id ? "primary" : "quiet"}
            aria-pressed={part === item.id}
            onClick={() => setPicked(item.id)}
          >
            {item.label}
          </Button>
        ))}
      </nav>

      {(part === "start" || part === "concept") && (
        <FilmFacts
          slug={slug}
          story={story}
          intake={intake}
          audioWindow={audioWindow}
          windowLocked={windowLocked}
        />
      )}
      {part === "start" && (
        <StartPart story={story} music={music} onStarted={() => setPicked("concept")} />
      )}
      {part === "concept" && (
        <ConceptRoom
          story={story}
          music={music}
          onStart={() => setPicked("start")}
          onRead={() => setPicked("story")}
        />
      )}
      {part === "story" && <ScriptPart story={story} />}
      {part === "world" && <WorldPart slug={slug} story={story} intake={intake} />}
      {part === "credits" && <CreditsCard slug={slug} />}
        </>
      )}
    </>
  );
}
