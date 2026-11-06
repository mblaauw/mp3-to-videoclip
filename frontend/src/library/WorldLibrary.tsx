import { useEffect, useState } from "react";
import { api } from "../api";
import { Button, ErrorState } from "../ui";
import { groupByKind, KIND_WORD, provenance, seriesIdFrom, type LibraryEntry, type Series } from "./entries";

/** The world library on the Library screen: what films settled, and the series they belong to. */
export function WorldLibrary() {
  const [entries, setEntries] = useState<LibraryEntry[]>([]);
  const [series, setSeries] = useState<Series[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [newTitle, setNewTitle] = useState("");
  const load = () =>
    api.library().then(
      (view) => {
        setEntries(view.entries);
        setSeries(view.series);
        setError(null);
      },
      (caught: unknown) => setError(caught instanceof Error ? caught.message : String(caught)),
    );
  useEffect(() => {
    void load();
  }, []);
  if (!entries.length && !series.length && !error) {
    return (
      <section className="library-section world-library">
        <h2>World library</h2>
        <p className="hint">
          Nothing promoted yet. On a film's Story page, promote a character, a place, a narrator or
          a look, and it can start the next film.
        </p>
      </section>
    );
  }
  const groups = groupByKind(entries);
  return (
    <section className="library-section world-library">
      <h2>World library</h2>
      {error && <ErrorState what="reading the library" error={error} compact />}
      {groups.map((group) => (
        <div className="world-group" key={group.kind}>
          <b className="profile-label">{KIND_WORD[group.kind]}</b>
          <ul className="world-entries">
            {group.entries.map((entry) => (
              <li key={entry.key} className="world-entry" title={entry.summary}>
                {entry.thumbnail ? <img src={entry.thumbnail} alt="" loading="lazy" /> : <span className="world-blank" aria-hidden="true" />}
                <div>
                  <b>{entry.label}</b>
                  <span className="hint">{entry.summary || entry.key}</span>
                  <span className="hint">{provenance(entry)}</span>
                </div>
              </li>
            ))}
          </ul>
        </div>
      ))}
      <div className="world-group">
        <b className="profile-label">Series</b>
        {series.map((item) => (
          <SeriesRow
            key={item.id}
            series={item}
            entries={entries}
            open={open === item.id}
            onOpen={() => setOpen(open === item.id ? null : item.id)}
            onSaved={(saved) => {
              setSeries((all) => all.map((row) => (row.id === saved.id ? saved : row)));
            }}
          />
        ))}
        <div className="row-actions">
          <input
            aria-label="New series title"
            placeholder="A new series"
            value={newTitle}
            maxLength={120}
            onChange={(event) => setNewTitle(event.target.value)}
          />
          <Button
            size="small"
            disabled={!newTitle.trim() || series.some((item) => item.id === seriesIdFrom(newTitle))}
            onClick={() =>
              void api.saveSeries(seriesIdFrom(newTitle), { title: newTitle.trim() }).then((view) => {
                setSeries(view.series);
                setNewTitle("");
                setOpen(view.saved.id);
              })
            }
          >
            Start a series
          </Button>
        </div>
      </div>
    </section>
  );
}

function SeriesRow({
  series,
  entries,
  open,
  onOpen,
  onSaved,
}: {
  series: Series;
  entries: LibraryEntry[];
  open: boolean;
  onOpen: () => void;
  onSaved: (saved: Series) => void;
}) {
  const [bible, setBible] = useState(series.bible);
  const [recurring, setRecurring] = useState<string[]>(series.recurring);
  const [busy, setBusy] = useState(false);
  const dirty = bible !== series.bible || recurring.join() !== series.recurring.join();
  return (
    <div className="series-row">
      <button type="button" className="series-head" onClick={onOpen} aria-expanded={open}>
        <b>{series.title}</b>
        <span className="hint">
          {series.episodes.length} episode{series.episodes.length === 1 ? "" : "s"} · {series.recurring.length} recurring
        </span>
      </button>
      {open && (
        <div className="series-body">
          <label className="ui-field">
            <span>Bible</span>
            <textarea
              rows={4}
              value={bible}
              maxLength={6000}
              placeholder="What every episode keeps: who, where, the rules of the world."
              onChange={(event) => setBible(event.target.value)}
            />
          </label>
          {entries.length > 0 && (
            <div className="chips">
              {entries.map((entry) => (
                <label className="ui-chip" key={entry.key}>
                  <input
                    type="checkbox"
                    checked={recurring.includes(entry.key)}
                    onChange={(event) =>
                      setRecurring((all) =>
                        event.target.checked ? [...all, entry.key] : all.filter((key) => key !== entry.key),
                      )
                    }
                  />{" "}
                  {entry.label}
                </label>
              ))}
            </div>
          )}
          {series.episodes.length > 0 && (
            <ul className="series-episodes">
              {series.episodes.map((episode) => (
                <li key={episode.slug}>
                  <a href={`#/${encodeURIComponent(episode.slug)}/story`}>
                    {episode.number}. {episode.title}
                  </a>
                </li>
              ))}
            </ul>
          )}
          <div className="row-actions">
            <Button
              size="small"
              variant="primary"
              disabled={!dirty || busy}
              onClick={() => {
                setBusy(true);
                void api
                  .saveSeries(series.id, { title: series.title, bible, recurring })
                  .then((view) => onSaved(view.saved))
                  .finally(() => setBusy(false));
              }}
            >
              Save the series
            </Button>
          </div>
        </div>
      )}
    </div>
  );
}
