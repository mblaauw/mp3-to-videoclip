import type { IntakePayload } from "../api";
import { CharactersCard } from "./CharactersCard";
import { LookCard } from "./LookCard";
import { ProfileCard } from "./ProfileCard";
import type { StoryData } from "./useStoryData";

export function WorldPart({
  slug,
  story,
  intake,
}: {
  slug: string;
  story: StoryData;
  intake: IntakePayload | null;
}) {
  const { brief, intakeChanged, briefChanged, askWriter } = story;
  return (
    <div className="story-world">
      {intake && brief ? (
        <LookCard
          slug={slug}
          intake={intake}
          brief={brief}
          onIntakeChange={intakeChanged}
          onBriefChange={briefChanged}
        />
      ) : (
        <section className="stage-block">
          <h2>Look</h2>
          <p className="hint">Loading the appearance…</p>
        </section>
      )}
      {brief && intake?.prompt_version === 2 && <ProfileCard brief={brief} onAsk={askWriter} />}
      {brief && <CharactersCard slug={slug} brief={brief} onBriefChange={briefChanged} />}
    </div>
  );
}
