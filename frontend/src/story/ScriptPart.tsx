import { useEffect, useRef, useState } from "react";
import type { ImageShot, Storyboard, StoryPassage } from "../api";
import { imageUrl } from "../spine/Spine";
import { usePlayerControls, usePlayerTime } from "../spine/player";
import { clock } from "../spine/wave";
import { AutoTextarea } from "../ui/AutoTextarea";
import { ProseField } from "../ui/ProseField";
import { SaveState } from "../ui/SaveState";
import { Button } from "../ui";
import { passageAt } from "./beats";
import type { StoryData } from "./useStoryData";

/** One sentence: Enter finishes the field instead of breaking the line. */
function finishOnEnter(event: React.KeyboardEvent<HTMLTextAreaElement>) {
  if (event.key === "Enter") {
    event.preventDefault();
    event.currentTarget.blur();
  }
}

type PlacedShot = { id: string; start: number; end: number; message: string; url: string };

function placedShots(slug: string, board: Storyboard | null, images: ImageShot[]): PlacedShot[] {
  if (!board) return [];
  const fps = board.fps || 24;
  return board.shots.flatMap((shot) => {
    const image = images.find((item) => item.id === shot.id);
    const url = imageUrl(slug, image);
    if (!url) return [];
    const start = shot.start_frame / fps;
    return [
      {
        id: shot.id,
        start,
        end: start + shot.duration_frames / fps,
        message: image?.message || "",
        url,
      },
    ];
  });
}

/** The still at this moment of the song, once pictures exist. */
function Picture({ shots }: { shots: PlacedShot[] }) {
  const seconds = usePlayerTime(0.25);
  if (!shots.length) {
    return <div className="story-no-picture">No pictures yet. They come after the storyboard.</div>;
  }
  const shot =
    shots.find((item) => seconds >= item.start && seconds < item.end) ?? shots[shots.length - 1];
  return (
    <>
      <img className="story-picture" src={shot.url} alt="" />
      <p className="story-picture-note">
        <b>
          {shot.id}, {clock(shot.start)}
        </b>
        {shot.message && <span>{shot.message}</span>}
      </p>
    </>
  );
}

function Passages({
  passages,
  shots,
  editable,
  onEdit,
}: {
  passages: StoryPassage[];
  shots: PlacedShot[];
  editable: boolean;
  onEdit: (passage: StoryPassage, text: string) => void;
}) {
  const player = usePlayerControls();
  const seconds = usePlayerTime(0.25);
  const on = passageAt(passages, seconds);
  const [editing, setEditing] = useState<number | null>(null);
  const [draft, setDraft] = useState("");
  const shown = useRef(on);

  // Follows the song while it plays, and never moves the page under you otherwise.
  useEffect(() => {
    if (on === shown.current) return;
    shown.current = on;
    if (!player.playing || on < 0) return;
    document.getElementById(`story-passage-${on}`)?.scrollIntoView({ block: "center" });
  }, [on, player.playing]);

  return (
    <div className={player.playing ? "story-pages playing" : "story-pages"}>
      {passages.map((passage, index) => {
        const placed = passage.start !== null;
        const tiles = placed
          ? shots.filter(
              (shot) => shot.start >= Number(passage.start) && shot.start < Number(passage.end),
            )
          : [];
        if (editing === index) {
          return (
            <article className="story-passage" key={index}>
              <div className="story-when">{placed ? clock(Number(passage.start)) : ""}</div>
              <div className="story-passage-body">
                <AutoTextarea
                  className="story-read-input"
                  aria-label="Edit this passage"
                  autoFocus
                  minRows={4}
                  maxRows={24}
                  value={draft}
                  onChange={(event) => setDraft(event.target.value)}
                />
                <div className="row-actions">
                  <Button
                    size="small"
                    variant="primary"
                    disabled={!draft.trim()}
                    onClick={() => {
                      setEditing(null);
                      if (draft !== passage.text) onEdit(passage, draft);
                    }}
                  >
                    Done
                  </Button>
                  <Button size="small" variant="quiet" onClick={() => setEditing(null)}>
                    Cancel
                  </Button>
                </div>
              </div>
            </article>
          );
        }
        return (
          <article
            className={`story-passage ${index === on ? "on" : ""}`}
            id={`story-passage-${index}`}
            key={index}
          >
            <div className="story-when">
              {placed ? (
                <button
                  type="button"
                  aria-label={`Play from ${clock(Number(passage.start))}`}
                  onClick={(event) => {
                    if (event.detail > 0) event.currentTarget.blur();
                    player.seek(Number(passage.start));
                    player.play();
                  }}
                >
                  {clock(Number(passage.start))}
                </button>
              ) : (
                <span className="story-not-placed">Not on the song yet</span>
              )}
            </div>
            <div className="story-passage-body">
              <p className="story-read">{passage.text}</p>
              {tiles.length > 0 && (
                <div className="story-tiles">
                  {tiles.map((shot) => (
                    <button
                      type="button"
                      className="story-tile"
                      key={shot.id}
                      style={{ backgroundImage: `url("${shot.url}")` }}
                      title={shot.id}
                      aria-label={`Go to ${shot.id}`}
                      onClick={(event) => {
                        if (event.detail > 0) event.currentTarget.blur();
                        player.seek(shot.start);
                      }}
                    />
                  ))}
                </div>
              )}
              {editable && (
                <button
                  type="button"
                  className="story-edit-link"
                  onClick={() => {
                    setDraft(passage.text);
                    setEditing(index);
                  }}
                >
                  Edit this passage
                </button>
              )}
            </div>
          </article>
        );
      })}
    </div>
  );
}

export function ScriptPart({
  slug,
  story,
  board,
  images,
  onStart,
}: {
  slug: string;
  story: StoryData;
  board: Storyboard | null;
  images: ImageShot[];
  onStart: () => void;
}) {
  const {
    brief,
    direction,
    style,
    treatment,
    passages,
    saveStatus,
    savedAt,
    writerBusy,
    treatmentBase,
    treatmentRef,
    fieldsBase,
    setDirection,
    setStyle,
    setTreatment,
    setSaveFailed,
    setFieldsDirty,
    saveFields,
    saveTreatment,
    runWriter,
  } = story;
  const [wholeText, setWholeText] = useState(false);
  const shots = placedShots(slug, board, images);
  const fieldChanged = () => {
    fieldsBase.current ??= brief;
    setSaveFailed(false);
    setFieldsDirty(true);
  };
  const changeTreatment = (value: string) => {
    treatmentBase.current ??= brief;
    setSaveFailed(false);
    setTreatment(value);
    treatmentRef.current = value;
  };
  const saved = brief?.treatment ?? "";
  // Passage offsets count from the saved text, so editing waits for any save in progress.
  const settled = treatment === saved;
  const editPassage = (passage: StoryPassage, text: string) => {
    if (!settled) return;
    changeTreatment(saved.slice(0, passage.from) + text + saved.slice(passage.to));
  };
  const hasStory = !!treatment.trim();
  const unplaced = hasStory && passages.some((passage) => passage.start === null);

  return (
    <div className="story-script">
      <section className="story-script-main" aria-label="The story">
        <div className="story-script-bar">
          <SaveState
            status={saveStatus}
            savedAt={savedAt}
            onRetry={() => {
              void saveTreatment(treatmentRef.current);
              void saveFields();
            }}
          />
          {unplaced && !wholeText && (
            <Button
              size="small"
              disabled={writerBusy}
              onClick={() => runWriter("Put the story on the song. Keep every word.", "place")}
            >
              {writerBusy ? "The Writer is working…" : "Put it on the song"}
            </Button>
          )}
          {hasStory && (
            <Button size="small" variant="quiet" onClick={() => setWholeText(!wholeText)}>
              {wholeText ? "Read it against the song" : "Edit all the text"}
            </Button>
          )}
        </div>
        {!hasStory && !wholeText ? (
          <div className="empty-block">
            <p>{writerBusy ? "The Writer is working on this." : "No story yet."}</p>
            {!writerBusy && <Button onClick={onStart}>Choose how to start</Button>}
          </div>
        ) : wholeText ? (
          <ProseField
            label="Treatment"
            value={treatment}
            minRows={12}
            onChange={changeTreatment}
            onCommit={() => void saveTreatment(treatmentRef.current)}
            placeholder="The story from the first frame to the last. It saves as you type."
          />
        ) : (
          <Passages passages={passages} shots={shots} editable={settled} onEdit={editPassage} />
        )}
      </section>
      <aside className="story-script-side" aria-label="The picture at this point in the song">
        <Picture shots={shots} />
        <div className="direction-style story-fields">
          <label>
            Direction
            <AutoTextarea
              minRows={1}
              maxRows={5}
              value={direction}
              onChange={(event) => {
                setDirection(event.target.value.replace(/\n/g, " "));
                fieldChanged();
              }}
              onKeyDown={finishOnEnter}
              onBlur={() => window.setTimeout(() => void saveFields(), 0)}
              placeholder="What kind of film is this?"
              maxLength={1000}
            />
          </label>
          <label>
            Style
            <AutoTextarea
              minRows={1}
              maxRows={5}
              value={style}
              onChange={(event) => {
                setStyle(event.target.value.replace(/\n/g, " "));
                fieldChanged();
              }}
              onKeyDown={finishOnEnter}
              onBlur={() => window.setTimeout(() => void saveFields(), 0)}
              placeholder="One honest sentence about the medium"
              maxLength={1000}
            />
          </label>
        </div>
      </aside>
    </div>
  );
}
