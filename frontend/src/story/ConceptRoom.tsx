import { useEffect, useMemo, useRef, useState } from "react";
import type { Concept, ConceptBeat, Music } from "../api";
import { usePlayerControls } from "../spine/player";
import { clock, waveformBars } from "../spine/wave";
import { Waveform } from "../spine/Waveform";
import { releaseMouseFocus } from "../film/selection";
import { Button } from "../ui";
import { conceptBeats, passageBeats } from "./beats";
import type { StoryData } from "./useStoryData";

const OWN = "own";

function Playhead({ duration }: { duration: number }) {
  const player = usePlayerControls();
  const line = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const draw = () => {
      if (line.current) line.current.style.left = `${(player.clock.get() / duration) * 100}%`;
    };
    draw();
    return player.clock.subscribe(draw);
  }, [duration, player.clock]);
  return <div ref={line} className="story-head-line" aria-hidden="true" />;
}

function BeatRow({
  title,
  note,
  active,
  chosen,
  beats,
  duration,
  picked,
  onShow,
  onBeat,
}: {
  title: string;
  note: string;
  active: boolean;
  chosen: boolean;
  beats: ConceptBeat[] | null;
  duration: number;
  picked: number | null;
  onShow: () => void;
  onBeat: (index: number) => void;
}) {
  return (
    <div className="story-score-row">
      <button type="button" className="story-score-name" aria-pressed={active} onClick={onShow}>
        <b>{title}</b>
        <span className={chosen ? "chosen" : undefined}>{chosen ? "Building on this" : note}</span>
      </button>
      <div className="story-lane">
        {beats ? (
          beats.map((beat, index) => (
            <button
              type="button"
              className={`story-beat ${active ? "" : "dim"}`}
              key={`${beat.start}-${index}`}
              style={{
                left: `${(beat.start / duration) * 100}%`,
                width: `calc(${((beat.end - beat.start) / duration) * 100}% - 2px)`,
              }}
              title={`${clock(beat.start)}–${clock(beat.end)}: ${beat.label}`}
              aria-pressed={active && picked === index}
              onClick={(event) => {
                releaseMouseFocus(event);
                onBeat(index);
              }}
            >
              <span>{beat.label}</span>
            </button>
          ))
        ) : (
          <p className="story-lane-empty">Not on the song yet</p>
        )}
      </div>
    </div>
  );
}

function ConceptDetail({
  concept,
  story,
  onRead,
}: {
  concept: Concept;
  story: StoryData;
  onRead: () => void;
}) {
  const { brief, chosen, concepts, writerBusy, buildOn, askForAnother } = story;
  const isChosen = chosen === concept.id;
  const hasStory = !!brief?.treatment?.trim();
  const beats = conceptBeats(concept);
  return (
    <div className="story-detail-grid">
      <div>
        <h2>{concept.title}</h2>
        <p className="story-structure">{concept.structure}</p>
        <p className="story-logline">{concept.logline}</p>
        <div className="row-actions">
          {isChosen && hasStory ? (
            <Button variant="primary" onClick={onRead}>
              Read the story
            </Button>
          ) : (
            <Button
              variant="primary"
              disabled={writerBusy}
              onClick={() => {
                void buildOn(concept).then((sent) => {
                  if (sent) onRead();
                });
              }}
            >
              {isChosen ? "Write the story" : "Build on this"}
            </Button>
          )}
          {concepts.length < 3 && (
            <Button variant="quiet" disabled={writerBusy} onClick={askForAnother}>
              Ask for another
            </Button>
          )}
        </div>
        {!isChosen && hasStory && (
          <p className="hint story-detail-note">
            This replaces the current story, and it will need approving again. The current version
            stays in the history.
          </p>
        )}
      </div>
      <div className="story-detail-column">
        <div>
          <h3>Signature moment</h3>
          <p className="story-read">{concept.signature_moment}</p>
        </div>
        <div>
          <h3>Why it fits</h3>
          <p>{concept.why}</p>
        </div>
      </div>
      <div className="story-detail-column">
        <div>
          <h3>The world</h3>
          <p>{concept.world}</p>
        </div>
        <div>
          <h3>The risk</h3>
          <p>{concept.risk}</p>
        </div>
        {!beats && concept.shape?.length ? (
          <div>
            <h3>How it moves</h3>
            <ul className="story-plain-list">
              {concept.shape.map((step) => (
                <li key={step}>{step}</li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </div>
  );
}

function OwnDetail({ story, onRead }: { story: StoryData; onRead: () => void }) {
  const { chosen, concepts, idea, writerBusy, sortMyIdea, startFromIdea, askForAnother } = story;
  const [count, setCount] = useState(2);
  if (!idea) return null;
  const sorted = idea.sorted;
  const noStory = !!sorted && sorted.story.length === 0;
  const lists: [string, string[]][] = sorted
    ? [
        ["Style", sorted.style],
        ["Rules", sorted.rules],
        ["Avoid", sorted.avoid],
      ]
    : [];
  return (
    <div className="story-detail-grid">
      <div>
        <h2>Your idea</h2>
        {!sorted && !writerBusy && (
          <p className="story-detail-note">
            Your words are saved as the story, but they aren't sorted yet, so anything about style
            or rules is still in with it.
          </p>
        )}
        {sorted && !noStory && (
          <p className="hint story-detail-note">
            This is how the Writer read it. It didn't change your words.
          </p>
        )}
        <div className="row-actions">
          {!sorted && (
            <Button variant="primary" disabled={writerBusy} onClick={sortMyIdea}>
              {writerBusy ? "The Writer is sorting…" : "Sort it with the Writer"}
            </Button>
          )}
          {!noStory && !chosen && (
            <Button variant={sorted ? "primary" : "quiet"} onClick={onRead}>
              Read the story
            </Button>
          )}
          {chosen && (
            <Button
              variant="quiet"
              disabled={writerBusy}
              onClick={() => void startFromIdea(idea.text)}
            >
              Go back to my idea
            </Button>
          )}
          {!noStory && concepts.length < 3 && (
            <Button variant="quiet" disabled={writerBusy} onClick={askForAnother}>
              Also suggest a concept
            </Button>
          )}
        </div>
        {noStory && (
          <div className="story-write-within">
            <p>You gave a style and rules but no story yet. The Writer can write one within them.</p>
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
            <div className="row-actions">
              <Button
                variant="primary"
                disabled={writerBusy}
                onClick={() => story.writeConcepts(count)}
              >
                {writerBusy
                  ? "The Writer is working…"
                  : `Write ${count === 1 ? "1 concept" : `${count} concepts`}`}
              </Button>
            </div>
          </div>
        )}
        {!noStory && (
          <div className="story-own-text story-read">{sorted?.story.join("\n\n") ?? idea.text}</div>
        )}
      </div>
      {lists.map(([name, items]) => (
        <div className="story-detail-column" key={name}>
          <div>
            <h3>{name}</h3>
            {items.length ? (
              <ul className="story-plain-list">
                {items.map((item) => (
                  <li key={item}>{item}</li>
                ))}
              </ul>
            ) : (
              <p className="hint">{name === "Style" ? "Nothing yet." : "None given."}</p>
            )}
          </div>
        </div>
      ))}
    </div>
  );
}

/** Every route on one song, so choosing is comparing how each one moves through it. */
export function ConceptRoom({
  story,
  music,
  onStart,
  onRead,
}: {
  story: StoryData;
  music: Music | null;
  onStart: () => void;
  onRead: () => void;
}) {
  const { concepts, chosen, idea, passages, writerBusy } = story;
  const player = usePlayerControls();
  const duration = player.duration || 1;
  const bars = useMemo(() => waveformBars(music, duration), [music, duration]);
  const [shown, setShown] = useState<string | null>(null);
  const [picked, setPicked] = useState<{ id: string; index: number } | null>(null);
  const stopAt = useRef<number | null>(null);

  const ownBeats = useMemo(() => passageBeats(passages), [passages]);
  const current =
    shown && (shown === OWN ? idea : concepts.some((concept) => concept.id === shown))
      ? shown
      : (chosen ?? (idea ? OWN : (concepts[0]?.id ?? null)));

  // A played beat stops at its end, so comparing two means hearing just those two.
  useEffect(
    () =>
      player.clock.subscribe(() => {
        if (stopAt.current !== null && player.clock.get() >= stopAt.current) {
          stopAt.current = null;
          player.pause();
        }
      }),
    [player],
  );

  const playBeat = (id: string, beats: ConceptBeat[], index: number) => {
    setShown(id);
    setPicked({ id, index });
    stopAt.current = beats[index].end;
    player.seek(beats[index].start);
    player.play();
  };

  if (!concepts.length && !idea) {
    return (
      <section className="stage-block">
        <div className="empty-block">
          <p>{writerBusy ? "The Writer is writing the concepts. You can watch it in the Director." : "No concepts yet."}</p>
          {!writerBusy && <Button onClick={onStart}>Choose how to start</Button>}
        </div>
      </section>
    );
  }

  const axis: number[] = [];
  const step = duration > 150 ? 30 : duration > 60 ? 15 : 5;
  for (let at = 0; at < duration; at += step) axis.push(at);
  const shownConcept = concepts.find((concept) => concept.id === current);
  const pickedBeat =
    picked && picked.id === current
      ? (current === OWN
          ? ownBeats
          : (conceptBeats(shownConcept as Concept) ?? []))[picked.index]
      : null;

  return (
    <section className="story-room">
      <div className="story-score">
        <div className="story-score-inner">
          <div className="story-score-row">
            <span />
            <div className="story-axis" aria-hidden="true">
              {axis.map((at) => (
                <span key={at} style={{ left: `${(at / duration) * 100}%` }}>
                  {clock(at)}
                </span>
              ))}
            </div>
          </div>
          <div className="story-score-row">
            <span className="hint story-song-name">The song</span>
            <div className="story-lane story-song">
              <Waveform bars={bars} sections={music?.sections ?? []} duration={duration} />
              <Playhead duration={duration} />
            </div>
          </div>
          {idea && (
            <BeatRow
              title="Your idea"
              note="In your words"
              active={current === OWN}
              chosen={!chosen && !!idea.sorted?.story.length}
              beats={ownBeats.length ? ownBeats : null}
              duration={duration}
              picked={picked?.id === OWN ? picked.index : null}
              onShow={() => setShown(OWN)}
              onBeat={(index) => playBeat(OWN, ownBeats, index)}
            />
          )}
          {concepts.map((concept) => {
            const beats = conceptBeats(concept);
            return (
              <BeatRow
                key={concept.id}
                title={concept.title}
                note={concept.structure}
                active={current === concept.id}
                chosen={chosen === concept.id}
                beats={beats}
                duration={duration}
                picked={picked?.id === concept.id ? picked.index : null}
                onShow={() => setShown(concept.id)}
                onBeat={(index) => beats && playBeat(concept.id, beats, index)}
              />
            );
          })}
        </div>
      </div>
      {writerBusy && <p className="story-working">The Writer is working. You can watch it in the Director.</p>}
      {pickedBeat && (
        <div className="story-beat-note">
          <b>{pickedBeat.label}</b>
          <span>
            {clock(pickedBeat.start)}–{clock(pickedBeat.end)}
          </span>
          <p className="story-read">{pickedBeat.text}</p>
        </div>
      )}
      <div className="story-detail">
        {current === OWN ? (
          <OwnDetail story={story} onRead={onRead} />
        ) : shownConcept ? (
          <ConceptDetail concept={shownConcept} story={story} onRead={onRead} />
        ) : null}
      </div>
    </section>
  );
}
