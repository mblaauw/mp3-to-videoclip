import { useCallback, useEffect, useRef, useState } from "react";
import { api, type Music, type SoundPayload } from "../api";
import { useResource } from "../api/useResource";
import { JobBanner } from "../jobs/JobBanner";
import { notifyProjectChanged } from "../shell/projectEvents";
import { soundUrl, CueInspector, Make, PlayButton } from "../sound/CueInspector";
import { chosen, clockTenths, dbWords, freshId, heardSpan, isMoment, KIND_LABEL, placesWords, type Cue, type CueAnchor, type CueKind } from "../sound/cueBands";
import { useAudition } from "../sound/audition";
import { SoundMap, type Pick } from "../sound/SoundMap";
import { usePlayerControls } from "../spine/player";
import { Button, ErrorState } from "../ui";
import { SaveState, type SaveStatus } from "../ui/SaveState";
import "../sound/sound.css";

const ASK_PROMPT =
  "Read the brief, the shots and the lines, then write the film's sound cues with " +
  "write_sound_cues: a bed if the film needs one, an ambience per place, an effect on each " +
  "moment that earns one, on the shot's cut where a cut is the moment.";

/** A pause in typing or dragging long enough to save on. */
const SAVE_AFTER_MS = 700;

function stripView(
  cue: Cue,
): Omit<Cue, "start_seconds" | "end_seconds" | "places_seconds" | "versions" | "selected"> {
  const { start_seconds: _s, end_seconds: _e, places_seconds: _p, versions: _v, selected: _c, ...rest } = cue;
  return rest;
}

/** When a cue plays, in a few words: at a moment, over a stretch, or off the film. */
function whenWords(cue: Cue, duration: number): string {
  const heard = heardSpan(cue, duration);
  if (!heard || cue.start_seconds === null) return "not on the film";
  if (isMoment(cue) && "frame" in cue.start) return `at ${clockTenths(cue.start_seconds)}`;
  const end = cue.end_seconds ?? duration;
  const shape = cue.places ? `, ${placesWords(cue.places, cue.places_seconds?.length)}` : "";
  return `${clockTenths(cue.start_seconds)}–${clockTenths(end)}${shape}`;
}

type Report = NonNullable<SoundPayload["report"]>;

/** Nothing chosen: the mix as a whole, and what a measure of it found. */
function MixPanel({
  cues,
  report,
  measuring,
  onMeasure,
  onSelect,
}: {
  cues: Cue[];
  report: Report | null;
  measuring: boolean;
  onMeasure: () => void;
  onSelect: (id: string) => void;
}) {
  const counts = (["music", "ambience", "effect"] as CueKind[]).map((kind) => ({
    kind,
    all: cues.filter((cue) => cue.kind === kind).length,
    sounding: cues.filter((cue) => cue.kind === kind && chosen(cue)).length,
  }));
  return (
    <aside className="cue-inspector mix-panel" aria-label="The mix">
      <header className="insp-head">
        <div>
          <h3>The mix</h3>
          <p>Choose a cue on the map or in the list to shape it.</p>
        </div>
      </header>
      <ul className="mix-counts">
        {counts.map((row) => (
          <li key={row.kind} className={row.kind}>
            <span className="insp-swatch" aria-hidden="true" />
            <span>{KIND_LABEL[row.kind]}</span>
            <b>{row.all}</b>
            <small>{row.all === 0 ? "none" : row.sounding === row.all ? "all sound" : `${row.all - row.sounding} silent`}</small>
          </li>
        ))}
      </ul>
      <section className="insp-section">
        <div className="insp-section-head">
          <h4>Check the mix</h4>
          <Button size="small" disabled={measuring} onClick={onMeasure}>
            {measuring ? "Measuring…" : report ? "Measure again" : "Measure"}
          </Button>
        </div>
        {!report && <small className="hint">Listens to the mixed film for long silences, cues too close to the voice, and loudness.</small>}
        {report && (
          <>
            <dl className="mix-facts">
              <div>
                <dt>Loudness</dt>
                <dd>{report.loudness ? `${report.loudness.lufs} LUFS` : report.mixed ? "–" : "No mix yet"}</dd>
              </div>
              <div>
                <dt>Peak</dt>
                <dd>{report.loudness ? `${report.loudness.true_peak_db} dBTP` : "–"}</dd>
              </div>
              <div>
                <dt>Cues heard</dt>
                <dd>
                  {report.sounding} of {report.cues}
                </dd>
              </div>
            </dl>
            {report.notes.length === 0 ? (
              <p className="insp-note good">Nothing to fix.</p>
            ) : (
              report.notes.map((note, index) =>
                note.cue ? (
                  <button type="button" className="insp-note link" key={`${note.code}-${index}`} onClick={() => onSelect(note.cue as string)}>
                    {note.message}
                  </button>
                ) : (
                  <p className="insp-note" key={`${note.code}-${index}`}>
                    {note.message}
                  </p>
                ),
              )
            )}
          </>
        )}
      </section>
    </aside>
  );
}

export function SoundStage({ slug, music = null }: { slug: string; music?: Music | null }) {
  const { value: data, error, setValue } = useResource(`/api/projects/${slug}/sound`, () => api.sound(slug));
  const player = usePlayerControls();
  const [drafts, setDrafts] = useState<Record<string, Cue>>({});
  const [selected, setSelected] = useState<string | null>(null);
  const [pick, setPick] = useState<Pick | null>(null);
  const [busy, setBusy] = useState(false);
  const [problem, setProblem] = useState<string | null>(null);
  const [status, setStatus] = useState<SaveStatus>("idle");
  const [savedAt, setSavedAt] = useState<number | null>(null);
  const [report, setReport] = useState<Report | null>(null);
  const [measuring, setMeasuring] = useState(false);
  const pausePlayer = useCallback(() => player.pause(), [player]);
  const audition = useAudition(pausePlayer);
  const latest = useRef<{ data: SoundPayload | null; drafts: Record<string, Cue> }>({ data: null, drafts: {} });
  latest.current = { data, drafts };

  const merged = (base: SoundPayload, edits: Record<string, Cue>) => base.cues.map((cue) => edits[cue.id] ?? cue);

  /** Saves the edits on screen; an edit made while the save runs stays and saves next. */
  const flush = useCallback(async () => {
    const { data: base, drafts: edits } = latest.current;
    if (!base || Object.keys(edits).length === 0) return;
    setStatus("saving");
    try {
      const next = await api.saveSound(slug, merged(base, edits).map(stripView));
      setValue(next);
      setDrafts((now) => Object.fromEntries(Object.entries(now).filter(([id, cue]) => cue !== edits[id])));
      setStatus("saved");
      setSavedAt(Date.now());
      notifyProjectChanged({ slug });
    } catch (caught) {
      setStatus("error");
      setProblem(caught instanceof Error ? caught.message : String(caught));
    }
  }, [setValue, slug]);

  const dirty = Object.keys(drafts).length > 0;
  useEffect(() => {
    if (!dirty) return;
    setStatus("dirty");
    const timer = window.setTimeout(() => void flush(), SAVE_AFTER_MS);
    return () => window.clearTimeout(timer);
  }, [drafts, dirty, flush]);
  useEffect(() => () => void flush(), [flush]);

  if (error && !data) return <ErrorState what="reading the sound" error={String(error)} />;
  if (!data) return <p className="hint">Reading the sound…</p>;
  const cues = merged(data, drafts);
  const ordered = [...cues].sort((a, b) => (a.start_seconds ?? Infinity) - (b.start_seconds ?? Infinity) || a.id.localeCompare(b.id));
  const silent = cues.filter((cue) => !chosen(cue)).map((cue) => cue.id);
  const current = selected ? (cues.find((cue) => cue.id === selected) ?? null) : null;
  const notesFor = (id: string) => (report?.notes ?? []).filter((note) => note.cue === id).map((note) => note.message);

  /** A change to the list itself: saved at once, with any edits on screen. */
  const act = async (step: () => Promise<SoundPayload>) => {
    setBusy(true);
    setProblem(null);
    try {
      setValue(await step());
      setDrafts({});
      notifyProjectChanged({ slug });
    } catch (caught) {
      setProblem(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(false);
    }
  };
  const save = (list: Cue[]) => act(() => api.saveSound(slug, list.map(stripView)));
  const add = (kind: CueKind) => {
    const id = freshId(kind, cues.map((cue) => cue.id));
    const at = pick ? pick.seconds : player.current();
    const frame = Math.round(at * data.fps);
    // An effect lands on the pick or the playhead; a bed or an air runs from there to the end.
    const place: { start: CueAnchor; end: CueAnchor } =
      kind === "effect"
        ? pick?.kind === "shot"
          ? { start: { shot: pick.id }, end: { shot: pick.id } }
          : { start: { frame }, end: { frame } }
        : { start: pick ? (pick.kind === "shot" ? { shot: pick.id } : { frame }) : { frame: 0 }, end: { frame: -1 } };
    const fresh: Cue = {
      id,
      kind,
      prompt: "",
      ...place,
      gain_db: kind === "music" ? -14 : kind === "ambience" ? -24 : -6,
      duck_db: kind === "effect" ? 0 : -10,
      loop: kind !== "effect",
      places: null,
      model: null,
      versions: [],
      selected: null,
      start_seconds: 0,
      end_seconds: data.duration,
    };
    setSelected(id);
    void save([...cues, fresh]);
  };
  const hear = (seconds: number) => {
    audition.stop();
    player.seek(seconds);
    player.play();
  };
  const measure = async () => {
    setMeasuring(true);
    try {
      setReport(await api.soundReport(slug));
    } catch (caught) {
      setProblem(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setMeasuring(false);
    }
  };
  const silences = (report?.notes ?? [])
    .filter((note) => note.code === "silence" && typeof note.at === "number")
    .map((note) => ({ start: note.at as number, end: note.end ?? (note.at as number) }));
  return (
    <div className="sound-stage">
      <JobBanner slug={slug} kinds={["sound"]} className="in-card" />
      <header className="sound-head">
        <h2>
          Sound{" "}
          <small>
            {cues.length} cue{cues.length === 1 ? "" : "s"}, {silent.length} silent
          </small>
        </h2>
        <div className="sound-head-actions">
          <SaveState status={status} savedAt={savedAt} onRetry={() => void flush()} />
          {silent.length > 0 && <Make slug={slug} cueIds={silent} label={`Make ${silent.length === 1 ? "the silent cue" : `all ${silent.length} silent cues`}`} variant="primary" />}
          {data.suggestions > 0 && (
            <Button size="small" variant="quiet" disabled={busy} onClick={() => void act(() => api.suggestSound(slug))}>
              Suggest cues
            </Button>
          )}
          <Button
            size="small"
            variant="quiet"
            onClick={() => window.dispatchEvent(new CustomEvent("studio:ask-director", { detail: { text: ASK_PROMPT } }))}
          >
            Ask the Writer
          </Button>
        </div>
      </header>
      <p className="hint sound-lede">
        {data.story_film
          ? "A bed under the narration, the air of each place, and an effect where a moment earns one. A cue on a line follows the takes; one on a cut follows the edit."
          : "The song is the music. Lay the air of each place under it and put an effect where a moment earns one. A cue on a cut follows the edit."}
      </p>

      <SoundMap
        data={data}
        cues={cues}
        music={music}
        selected={selected}
        pick={pick}
        silences={silences}
        onSelect={setSelected}
        onPick={setPick}
        onAdd={(kind) => add(kind)}
      />
      <div className={`sound-pick ${pick ? "" : "idle"}`} aria-live="polite">
        {pick ? (
          <>
            <span>
              {pick.kind === "shot" ? (
                <>
                  The cut of <b>{pick.id}</b> at {clockTenths(pick.seconds)}
                </>
              ) : (
                <>
                  Picked <b>{clockTenths(pick.seconds)}</b>
                </>
              )}
            </span>
            <Button size="small" variant="primary" disabled={busy} onClick={() => add("effect")}>
              {pick.kind === "shot" ? `Add an effect on the cut of ${pick.id}` : `Add an effect at ${clockTenths(pick.seconds)}`}
            </Button>
            <Button size="small" variant="quiet" disabled={busy} onClick={() => add("ambience")}>
              Ambience from here
            </Button>
            <Button size="small" variant="quiet" onClick={() => setPick(null)}>
              Clear
            </Button>
          </>
        ) : (
          <span>Click a lane to pick a moment, or a picture to pick its cut. The + on a lane adds a cue there.</span>
        )}
      </div>
      {problem && <ErrorState what="saving the cues" error={problem} compact />}

      <div className="sound-work">
        <section className="cue-list-panel" aria-label="Cues">
          {cues.length === 0 ? (
            <div className="cue-empty">
              <p>No sound cues yet.</p>
              <p className="hint">Pick a moment on the map and add an effect, use + on a lane, or ask the Writer for a first list.</p>
            </div>
          ) : (
            <ol className="cue-rows">
              {ordered.map((cue) => {
                const sound = chosen(cue);
                const key = sound ? `${cue.id}/${sound.version}` : "";
                const flagged = notesFor(cue.id).length > 0;
                return (
                  <li key={cue.id} id={`cue-${cue.id}`} className={`cue-row ${cue.kind} ${selected === cue.id ? "selected" : ""} ${sound ? "" : "silent"}`}>
                    <button type="button" className="cue-row-main" aria-pressed={selected === cue.id} onClick={() => setSelected(selected === cue.id ? null : cue.id)}>
                      <span className="cue-row-top">
                        <span className="insp-swatch" aria-hidden="true" />
                        <b>{cue.id}</b>
                        <span className="cue-row-when">{whenWords(cue, data.duration)}</span>
                        {flagged && <span className="cue-flag" title="The mix check has a note on this cue">Note</span>}
                      </span>
                      <span className={`cue-row-words ${cue.prompt ? "" : "empty"}`}>{cue.prompt || "Say what it sounds like."}</span>
                    </button>
                    <span className="cue-row-side">
                      {sound ? (
                        <>
                          <span className="cue-row-level">{dbWords(cue.gain_db)}</span>
                          <PlayButton playing={audition.playing === key} label={`${cue.id} on its own`} onClick={() => audition.toggle(key, soundUrl(slug, cue.id, sound.version))} />
                        </>
                      ) : (
                        <Make slug={slug} cueIds={[cue.id]} label="Make this sound" />
                      )}
                    </span>
                  </li>
                );
              })}
            </ol>
          )}
        </section>
        {current ? (
          <CueInspector
            slug={slug}
            cue={current}
            data={data}
            pick={pick}
            notes={notesFor(current.id)}
            audition={audition}
            onEdit={(next) => setDrafts((all) => ({ ...all, [next.id]: next }))}
            onRemove={() => {
              setSelected(null);
              void save(cues.filter((item) => item.id !== current.id));
            }}
            onData={(next) => {
              setValue(next);
              notifyProjectChanged({ slug });
            }}
            onHear={hear}
            onClose={() => setSelected(null)}
          />
        ) : (
          <MixPanel cues={cues} report={report} measuring={measuring} onMeasure={() => void measure()} onSelect={setSelected} />
        )}
      </div>
    </div>
  );
}
