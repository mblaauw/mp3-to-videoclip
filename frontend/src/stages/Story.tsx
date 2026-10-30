import { useEffect, useState } from "react";
import type { AudioWindow, IntakePayload } from "../api";
import { ApprovalBar } from "../ApprovalBar";
import { ArtifactRating } from "../ArtifactRating";
import { ConceptPart, FilmFacts } from "../story/ConceptPart";
import { CreditsCard } from "../story/CreditsCard";
import { ScriptPart } from "../story/ScriptPart";
import { StoryChanges } from "../story/StoryChanges";
import { useStoryData } from "../story/useStoryData";
import { WorldPart } from "../story/WorldPart";
import { Button, EmptyState, ErrorState, LoadingState } from "../ui";

export type StoryPart = "concept" | "story" | "world" | "credits";

const PARTS: { id: StoryPart; label: string }[] = [
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
}: {
  slug: string;
  intake: IntakePayload | null;
  audioWindow: AudioWindow | null;
  windowLocked?: boolean;
  onIntakeChange: (intake: IntakePayload) => void;
}) {
  const story = useStoryData({ slug, intake, onIntakeChange });
  const { brief, loading, error, load } = story;
  const [picked, setPicked] = useState<StoryPart | null>(null);
  // Until you pick, a film with a story opens on it and a new film on the concepts.
  const part: StoryPart = picked ?? (brief?.treatment?.trim() ? "story" : "concept");

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

      {part === "concept" && (
        <>
          <FilmFacts
            slug={slug}
            story={story}
            intake={intake}
            audioWindow={audioWindow}
            windowLocked={windowLocked}
          />
          <ConceptPart story={story} />
        </>
      )}
      {part === "story" && <ScriptPart story={story} />}
      {part === "world" && <WorldPart slug={slug} story={story} intake={intake} />}
      {part === "credits" && <CreditsCard slug={slug} />}
    </>
  );
}
