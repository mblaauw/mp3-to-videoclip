import { useEffect, useState } from "react";
import { api, type ProjectSummary } from "../api";
import { Button } from "../ui";

/** Bring a still another film made: a copy with its provenance, for this upload shot. */
export function FromAnotherFilm({ slug, onBrought }: { slug: string; onBrought: (path: string) => void }) {
  const [films, setFilms] = useState<ProjectSummary[]>([]);
  const [from, setFrom] = useState("");
  const [shot, setShot] = useState("");
  const [version, setVersion] = useState(1);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  useEffect(() => {
    api.projects().then(
      (all) => setFilms(all.filter((film) => film.slug !== slug && !film.error)),
      () => setFilms([]),
    );
  }, [slug]);
  if (!films.length) return null;
  return (
    <div className="ui-field from-film">
      <span>From another film</span>
      <div className="inline-fields">
        <select aria-label="Film" value={from} onChange={(event) => setFrom(event.target.value)}>
          <option value="">Choose a film…</option>
          {films.map((film) => (
            <option key={film.slug} value={film.slug}>
              {film.title}
            </option>
          ))}
        </select>
        <input aria-label="Shot id" placeholder="s001" value={shot} onChange={(event) => setShot(event.target.value.trim())} />
        <input aria-label="Version" type="number" min="1" step="1" value={version} onChange={(event) => setVersion(Math.max(1, Math.round(Number(event.target.value) || 1)))} />
        <Button
          size="small"
          disabled={!from || !shot || busy}
          onClick={() => {
            setBusy(true);
            setNote(null);
            void api
              .bringStill(slug, from, shot, version)
              .then((row) => {
                onBrought(row.path);
                setNote("Copied here, with where it came from written down.");
              })
              .catch((caught: unknown) => setNote(caught instanceof Error ? caught.message : String(caught)))
              .finally(() => setBusy(false));
          }}
        >
          Bring it
        </Button>
      </div>
      {note && <span className="hint">{note}</span>}
    </div>
  );
}
