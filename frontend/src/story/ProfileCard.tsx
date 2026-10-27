import type { Brief } from "../api";
import { Button } from "../ui";

export const PROFILE_PROMPT =
  "Read the treatment and script with get_brief. Build the film's creative profile with " +
  "set_creative_profile: every recurring person as a character with identity and states, " +
  "every recurring place as a scene, the arc, at most six global image rules, at most eight " +
  "avoid entries, and a compact rendering-only look of 90–150 words. Do not put characters " +
  "or places in direction or look, and do not repeat identity or wardrobe in shot prompts.";

export function ProfileCard({
  brief,
  onAsk,
}: {
  brief: Brief;
  onAsk: (text: string) => void;
}) {
  const creative = brief.creative;
  const characters = brief.characters || [];
  const scenes = creative?.scenes || [];
  const rules = creative?.image_rules || [];
  const avoid = brief.avoid || [];
  const look = (creative?.look || "").trim();
  const lookWords = look ? look.split(/\s+/).length : 0;
  const ready = (creative?.profile_version || 0) >= 1;

  return (
    <section className="stage-block profile-card">
      <h2>
        Cast &amp; places <small>One structured profile every picture uses</small>
        {ready && <span className="saved-note">Ready</span>}
      </h2>
      {!ready ? (
        <div className="empty-block">
          <p>
            The Writer builds the cast, places and rendering rules from the treatment and
            script. The story is not approved until this profile exists.
          </p>
          <Button variant="primary" size="small" onClick={() => onAsk(PROFILE_PROMPT)}>
            Build cast &amp; places
          </Button>
        </div>
      ) : (
        <>
          <p className="hint">
            {characters.length} character{characters.length === 1 ? "" : "s"} · {scenes.length}{" "}
            place{scenes.length === 1 ? "" : "s"} · {rules.length} image rule
            {rules.length === 1 ? "" : "s"} · {lookWords}-word look
          </p>

          {characters.length > 0 && (
            <div className="profile-list">
              <b className="profile-label">People</b>
              {characters.map((character) => {
                const states = Object.keys(character.states || {});
                return (
                  <div className="profile-row" key={character.id}>
                    <b>{character.id}</b>
                    <span>{character.identity || character.description || "No identity"}</span>
                    {states.length > 0 && <em>{states.join(" · ")}</em>}
                  </div>
                );
              })}
            </div>
          )}

          {scenes.length > 0 && (
            <div className="profile-list">
              <b className="profile-label">Places</b>
              {scenes.map((scene) => (
                <div className="profile-row" key={scene.id}>
                  <b>{scene.id}</b>
                  <span>{scene.description || "No description"}</span>
                </div>
              ))}
            </div>
          )}

          {rules.length > 0 && (
            <div className="chips">
              {rules.map((rule) => (
                <span className="ui-chip" key={rule}>
                  {rule}
                </span>
              ))}
            </div>
          )}

          <p className="hint">
            {avoid.length} avoid item{avoid.length === 1 ? "" : "s"} ·{" "}
            {lookWords > 180 ? "look is over the 180-word budget" : "look budget is healthy"}
          </p>
          <div className="row-actions">
            <Button size="small" variant="quiet" onClick={() => onAsk(PROFILE_PROMPT)}>
              Ask the Writer to revise the profile
            </Button>
          </div>
        </>
      )}
    </section>
  );
}
