import type { StoryData } from "./useStoryData";

/** What moved since the approval, so approving again is a reading, not a guess. */
export function StoryChanges({ story }: { story: StoryData }) {
  const { approval, changes } = story;
  if (approval?.state !== "stale") return null;
  return (
      <section className="stage-block changed-panel" id="story-changes">
        <h2>Changed since you approved it</h2>
        <p>{approval.reason || changes?.reason || "The story differs from what you approved."}</p>
        {changes?.changes?.length ? (
          <dl className="change-list">
            {changes.changes.map((change) => (
              <div key={change.field}>
                <dt>{change.field}</dt>
                <dd>
                  <span className="before">{change.before}</span>
                  <span className="arrow">→</span>
                  <span className="after">{change.after}</span>
                </dd>
              </div>
            ))}
          </dl>
        ) : (
          <p className="hint">
            {changes?.available
              ? "The supporting files changed; the current story is what approval will bind."
              : "This approval predates the change log. Read the current story before approving it again."}
          </p>
        )}
      </section>
  );
}
