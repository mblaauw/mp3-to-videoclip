import { useMemo, useState, type FormEvent } from "react";
import type { Music } from "../api";
import { usePlayerControls } from "../spine/player";
import { clock, waveformBars } from "../spine/wave";
import { Waveform } from "../spine/Waveform";
import { AutoTextarea } from "../ui/AutoTextarea";
import { Button } from "../ui";
import type { StoryData } from "./useStoryData";

/** What was measured, in the terms a person would choose a film by. */
function musicFacts(music: Music | null, duration: number): [string, string][] {
  const facts: [string, string][] = [];
  const tempo = music?.estimated_tempo_bpm;
  facts.push(["Length", `${clock(duration)}${tempo ? `, about ${Math.round(tempo)} BPM` : ""}`]);
  const sections = music?.sections ?? [];
  if (sections.length) facts.push(["Sections", `${sections.length} measured`]);
  const rated = sections.filter((section) => typeof section.energy === "number");
  if (rated.length > 1) {
    const span = (section: (typeof rated)[number]) =>
      `${clock(section.start)}–${clock(section.end)}`;
    const byEnergy = [...rated].sort((a, b) => Number(a.energy) - Number(b.energy));
    facts.push(["Loudest", span(byEnergy[byEnergy.length - 1])]);
    facts.push(["Quietest", span(byEnergy[0])]);
  }
  return facts;
}

export function StartPart({
  story,
  music,
  onStarted,
}: {
  story: StoryData;
  music: Music | null;
  onStarted: () => void;
}) {
  const { brief, concepts, starting, writerBusy, startFromIdea, writeConcepts } = story;
  const [text, setText] = useState("");
  const [count, setCount] = useState(2);
  const player = usePlayerControls();
  const duration = player.duration;
  const measured = !!music?.sections?.length;
  const bars = useMemo(() => waveformBars(music, duration), [music, duration]);
  const facts = musicFacts(music, duration);
  const hasStory = !!brief?.treatment?.trim();

  const submit = async (event: FormEvent) => {
    event.preventDefault();
    if (!text.trim()) return;
    if (await startFromIdea(text)) {
      setText("");
      onStarted();
    }
  };

  return (
    <div className="story-start">
      <h2 className="story-start-title">How do you want to start this film?</h2>
      {hasStory && (
        <p className="story-start-warning">
          This film already has a story. Starting again replaces it, and it will need approving
          again. The current version stays in the history.
        </p>
      )}
      <div className="story-doors">
        <form className="story-door" onSubmit={(event) => void submit(event)}>
          <h3>I have an idea</h3>
          <p>
            A story, a treatment, a style, directions, rules, shot ideas: paste whatever you have.
            Rough is fine.
          </p>
          <AutoTextarea
            className="story-read-input"
            aria-label="Your idea"
            value={text}
            disabled={starting}
            minRows={10}
            maxRows={24}
            maxLength={24000}
            onChange={(event) => setText(event.target.value)}
            placeholder={"Two strangers meet in a dream garden…\n\nSoft, hazy, photographic. No lip-sync."}
          />
          <p className="hint">
            Your words stay yours. The Writer only sorts them into story, style and rules, and lines
            the story up with the song.
          </p>
          <div className="row-actions">
            <Button variant="primary" type="submit" disabled={!text.trim() || starting || writerBusy}>
              {starting ? "Saving your idea…" : "Start from my idea"}
            </Button>
          </div>
        </form>
        <div className="story-door">
          <h3>Find concepts in the music</h3>
          <p>The Writer reads what was measured and proposes directions.</p>
          {measured ? (
            <div className="story-door-song">
              <Waveform bars={bars} sections={music?.sections ?? []} duration={duration || 1} />
            </div>
          ) : (
            <p className="hint">The song has to be measured first. Do that on Track.</p>
          )}
          <dl className="story-facts">
            {facts.map(([name, value]) => (
              <div key={name}>
                <dt>{name}</dt>
                <dd>{value}</dd>
              </div>
            ))}
          </dl>
          <div className="story-count" role="group" aria-label="How many concepts">
            <span>How many concepts?</span>
            {[1, 2, 3].map((value) => (
              <button
                type="button"
                key={value}
                aria-pressed={count === value}
                onClick={() => setCount(value)}
              >
                {value}
              </button>
            ))}
          </div>
          {concepts.length > 0 && (
            <p className="hint">These replace the concepts on file, which stay in the history.</p>
          )}
          <div className="row-actions">
            <Button
              variant="primary"
              disabled={!measured || writerBusy}
              onClick={() => {
                writeConcepts(count);
                onStarted();
              }}
            >
              {writerBusy ? "The Writer is working…" : `Write ${count === 1 ? "1 concept" : `${count} concepts`}`}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
