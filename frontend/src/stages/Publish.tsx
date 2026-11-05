import { useEffect, useState } from "react";
import { api, type PublishView } from "../api";
import { useResource } from "../api/useResource";
import { heardWords } from "../film/heard";
import { notifyProjectChanged } from "../shell/projectEvents";
import { Button, ErrorState } from "../ui";
import "../publish/publish.css";

const ASK_PROMPT =
  "Read the brief, then write the release copy with write_publish_copy: three titles that lead " +
  "with different things, a description that opens with the message and ends with the call to " +
  "action exactly as the brief gives it, and eight to fifteen plain tags.";

function Lines({ data, onNavigate }: { data: PublishView; onNavigate: (stage: string) => void }) {
  return (
    <ul className="panel-gates">
      {data.lines.map((line) => (
        <li key={line.id} className={line.state}>
          <span className="gate-mark" aria-hidden="true">
            {line.state === "done" ? "✓" : line.state === "optional" ? "–" : "•"}
          </span>
          <div className="gate-copy">
            <b>{line.label}</b>
            <span>{line.detail}</span>
            {line.id === "heard" && data.heard.total > 0 && (
              <div className="heard-bar" aria-hidden="true">
                <span style={{ width: `${Math.round(data.heard.share * 100)}%` }} />
              </div>
            )}
          </div>
          {line.state !== "done" && line.stage !== "publish" && (
            <Button size="small" variant="quiet" onClick={() => onNavigate(line.stage)}>
              Go to {line.stage.charAt(0).toUpperCase() + line.stage.slice(1)}
            </Button>
          )}
        </li>
      ))}
    </ul>
  );
}

function CopyCard({
  slug,
  data,
  onData,
}: {
  slug: string;
  data: PublishView;
  onData: (next: PublishView) => void;
}) {
  const copy = data.copy;
  const [titles, setTitles] = useState<string[]>(copy?.titles ?? [""]);
  const [description, setDescription] = useState(copy?.description ?? "");
  const [tags, setTags] = useState((copy?.tags ?? []).join(", "));
  const [problems, setProblems] = useState<string[] | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    if (!copy) return;
    setTitles(copy.titles);
    setDescription(copy.description);
    setTags(copy.tags.join(", "));
  }, [copy]);
  const payload = () => ({
    titles: titles.map((title) => title.trim()).filter(Boolean),
    description: description.trim(),
    tags: tags.split(",").map((tag) => tag.trim()).filter(Boolean),
  });
  const run = async (step: () => Promise<void>) => {
    setBusy(true);
    try {
      await step();
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="stage-block publish-copy">
      <h2>
        Title, description and tags{" "}
        {copy && <small>written by the {copy.by}</small>}
      </h2>
      <p className="hint">
        Only what the brief and the script state. A link that is not the call to action's, or a
        figure the brief never gave, is refused.
      </p>
      {titles.map((title, index) => (
        <input
          key={index}
          aria-label={`Title ${index + 1}`}
          placeholder={index === 0 ? "A title" : "Another title, leading with something else"}
          value={title}
          maxLength={100}
          onChange={(event) => setTitles((all) => all.map((item, at) => (at === index ? event.target.value : item)))}
        />
      ))}
      {titles.length < 3 && (
        <Button size="small" variant="quiet" onClick={() => setTitles((all) => [...all, ""])}>
          Another title
        </Button>
      )}
      <textarea
        aria-label="Description"
        rows={6}
        maxLength={5000}
        placeholder="The message in one sentence a stranger can repeat, what the film shows, the call to action with its link."
        value={description}
        onChange={(event) => setDescription(event.target.value)}
      />
      <input
        aria-label="Tags"
        placeholder="Tags, separated by commas"
        value={tags}
        onChange={(event) => setTags(event.target.value)}
      />
      {problems && problems.length > 0 && (
        <ul className="publish-problems" role="alert">
          {problems.map((problem) => (
            <li key={problem}>{problem}</li>
          ))}
        </ul>
      )}
      {problems && problems.length === 0 && <p className="hint">Nothing stops this copy.</p>}
      <div className="row-actions">
        <Button
          size="small"
          variant="primary"
          disabled={busy || !titles.some((title) => title.trim())}
          onClick={() =>
            void run(async () => {
              const checked = await api.checkPublishCopy(slug, payload());
              setProblems(checked.problems);
              if (checked.problems.length === 0) {
                onData(await api.savePublishCopy(slug, payload()));
                notifyProjectChanged({ slug });
              }
            })
          }
        >
          {busy ? "Checking…" : "Check and save"}
        </Button>
        <Button
          size="small"
          variant="quiet"
          onClick={() => window.dispatchEvent(new CustomEvent("studio:ask-director", { detail: { text: ASK_PROMPT } }))}
        >
          Ask the Writer
        </Button>
      </div>
    </section>
  );
}

export function PublishStage({ slug }: { slug: string }) {
  const { value: data, error, setValue } = useResource(`/api/projects/${slug}/publish`, () => api.publish(slug));
  const [busy, setBusy] = useState<string | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [note, setNote] = useState("");
  if (error && !data) return <ErrorState what="reading the release" error={String(error)} />;
  if (!data) return <p className="hint">Reading the release…</p>;
  const act = async (what: string, step: () => Promise<PublishView>) => {
    setBusy(what);
    setProblem(null);
    try {
      setValue(await step());
      notifyProjectChanged({ slug });
    } catch (caught) {
      setProblem(caught instanceof Error ? caught.message : String(caught));
    } finally {
      setBusy(null);
    }
  };
  const navigate = (stage: string) => {
    window.location.hash = `#/${encodeURIComponent(slug)}/${stage}`;
  };
  return (
    <div className="publish-stage">
      <section className="stage-block">
        <h2>
          Publish{" "}
          <small>{data.final ? data.final : "no final yet"}</small>
        </h2>
        {data.released ? (
          <p className="hint">
            Released {new Date(data.released.at).toLocaleString()} as {data.released.final} for{" "}
            {data.released.presets.join(", ")}.
          </p>
        ) : (
          <p className="hint">{heardWords(data.heard.heard, data.heard.total)}</p>
        )}
        <Lines data={data} onNavigate={navigate} />
        {problem && <ErrorState what="updating the release" error={problem} compact />}
        <div className="row-actions">
          <input
            aria-label="Release note"
            placeholder="A note for the record (optional)"
            value={note}
            maxLength={300}
            onChange={(event) => setNote(event.target.value)}
          />
          <Button
            variant="primary"
            disabled={!data.can_release || busy !== null || Boolean(data.released)}
            title={data.can_release ? "Record the release beside the final" : data.outstanding.join("; ")}
            onClick={() => void act("release", () => api.release(slug, note))}
          >
            {data.released ? "Released" : busy === "release" ? "Recording…" : "Mark as released"}
          </Button>
        </div>
        <p className="hint">Uploading stays yours: the record names the files by their bytes.</p>
      </section>

      <section className="stage-block">
        <h2>Where it goes</h2>
        <div className="chips">
          {data.presets_available.map((preset) => (
            <label className="ui-chip" key={preset.id}>
              <input
                type="checkbox"
                checked={data.presets.includes(preset.id)}
                disabled={busy !== null}
                onChange={(event) => {
                  const next = event.target.checked
                    ? [...data.presets, preset.id]
                    : data.presets.filter((id) => id !== preset.id);
                  if (next.length) void act("presets", () => api.savePresets(slug, next));
                }}
              />{" "}
              {preset.label} ({preset.aspect})
            </label>
          ))}
        </div>
        <ul className="publish-plan">
          {data.plan.map((row) => (
            <li key={row.id}>
              <b>{row.label}</b>
              {row.has.map((name) => (
                <span key={name} className="hint">
                  ✓{" "}
                  <a href={`/api/projects/${slug}/film/package/${encodeURIComponent(name)}`} download={name}>
                    {name}
                  </a>
                </span>
              ))}
              {row.missing.map((what) => (
                <span key={what} className="hint">
                  • Still to make: {what}
                </span>
              ))}
            </li>
          ))}
        </ul>
      </section>

      <section className="stage-block">
        <h2>
          Thumbnail{" "}
          {data.thumbnail && <small>{data.thumbnail.name}</small>}
        </h2>
        <div className="row-actions">
          <Button
            size="small"
            disabled={!data.final || busy !== null}
            onClick={() => void act("thumbnails", () => api.makeThumbnails(slug))}
          >
            {busy === "thumbnails" ? "Drawing…" : data.thumbnails.length ? "Draw them again with the current title" : "Draw three candidates"}
          </Button>
        </div>
        {data.thumbnails.length > 0 && (
          <ul className="thumb-grid">
            {data.thumbnails.map((row) => (
              <li key={row.name} className={data.thumbnail?.name === row.name ? "chosen" : ""}>
                <button
                  type="button"
                  disabled={busy !== null}
                  onClick={() => void act("choose", () => api.chooseThumbnail(slug, row.name))}
                  aria-pressed={data.thumbnail?.name === row.name}
                >
                  <img src={`/api/projects/${slug}/publish/thumb/${encodeURIComponent(row.name)}?v=${row.sha256.slice(0, 8)}`} alt={`Frame ${row.frame}`} loading="lazy" />
                  <span>
                    Frame {row.frame} · {Math.round(row.bytes / 1024)} KB
                  </span>
                </button>
              </li>
            ))}
          </ul>
        )}
      </section>

      <CopyCard slug={slug} data={data} onData={setValue} />
    </div>
  );
}
