import { useEffect, useState } from "react";
import { api, type Brief } from "../api";
import { notifyProjectChanged } from "../shell/projectEvents";
import { Button, Field } from "../ui";

type Character = NonNullable<Brief["characters"]>[number];

function slugify(value: string): string {
  const text = value
    .normalize("NFKD")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-+|-+$/g, "")
    .slice(0, 63);
  return text || "character";
}

function displayName(id: string): string {
  return id
    .split(/[-_]/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(" ");
}

export function CharactersCard({
  slug,
  brief,
  onBriefChange,
}: {
  slug: string;
  brief: Brief;
  onBriefChange: (brief: Brief) => void;
}) {
  const [characters, setCharacters] = useState<Character[]>(brief.characters || []);
  const [name, setName] = useState("");
  const [identity, setIdentity] = useState("");
  const [permission, setPermission] = useState(false);
  const [adding, setAdding] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setCharacters(brief.characters || []);
  }, [brief.characters]);

  const save = async (next: Character[]) => {
    if (saving) return;
    setSaving(true);
    setError(null);
    try {
      const updated = await api.patchBrief(slug, { characters: next });
      setCharacters(updated.characters || []);
      onBriefChange(updated);
      notifyProjectChanged();
    } catch (caught) {
      setError(String(caught));
    } finally {
      setSaving(false);
    }
  };

  const update = (index: number, patch: Partial<Character>) => {
    setCharacters((current) =>
      current.map((item, position) =>
        position === index ? { ...item, ...patch } : item,
      ),
    );
  };

  const add = async () => {
    const clean = name.trim();
    if (!clean) return;
    const base = slugify(clean);
    let id = base;
    let suffix = 2;
    while (characters.some((character) => character.id === id)) {
      id = `${base}-${suffix}`;
      suffix += 1;
    }
    const created: Character = {
      id,
      identity: identity.trim() || undefined,
      description: "",
      permission_confirmed: permission,
    };
    setAdding(true);
    await save([...characters, created]);
    setAdding(false);
    setName("");
    setIdentity("");
    setPermission(false);
  };

  return (
    <section className="stage-block characters-card">
      <h2>
        Characters <small>People the pictures must keep consistent</small>
        {saving && <span className="saved-note">Saving…</span>}
      </h2>
      {!characters.length && (
        <p className="hint">
          No characters yet. The Writer adds recurring people with the creative profile; a film
          can also work with places and objects alone.
        </p>
      )}
      {characters.map((character, index) => {
        const states = Object.entries(character.states || {});
        return (
        <div className="character-row" key={character.id}>
          <div className="character-avatar">No photo</div>
          <div className="character-fields">
            <b>{displayName(character.id)}</b>
            {states.length > 0 && (
              <div className="chips">
                {states.map(([state, value]) => (
                  <span
                    className="ui-chip"
                    key={state}
                    title={value?.description || undefined}
                  >
                    {state}
                  </span>
                ))}
                {character.default_state && (
                  <span className="hint">
                    default {character.default_state}
                  </span>
                )}
              </div>
            )}
            <input
              value={character.identity || ""}
              aria-label={`Identity for ${displayName(character.id)}`}
              placeholder="One-line identity"
              maxLength={400}
              onChange={(event) => update(index, { identity: event.target.value || undefined })}
              onBlur={() =>
                void save(
                  characters.map((item, position) =>
                    position === index
                      ? { ...item, identity: item.identity?.trim() || undefined }
                      : item,
                  ),
                )
              }
            />
            <label className="check-line">
              <input
                type="checkbox"
                checked={!!character.permission_confirmed}
                onChange={(event) => {
                  const next = characters.map((item, position) =>
                    position === index
                      ? { ...item, permission_confirmed: event.target.checked }
                      : item,
                  );
                  setCharacters(next);
                  void save(next);
                }}
              />
              I have permission to depict this person
            </label>
          </div>
        </div>
        );
      })}
      <div className="add-character">
        <Field label="Add a character">
          <div className="inline-fields">
            <input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Name"
              maxLength={63}
              aria-label="Character name"
            />
            <input
              value={identity}
              onChange={(event) => setIdentity(event.target.value)}
              placeholder="One-line identity"
              maxLength={400}
              aria-label="Character identity"
            />
          </div>
        </Field>
        <label className="check-line">
          <input
            type="checkbox"
            checked={permission}
            onChange={(event) => setPermission(event.target.checked)}
          />
          I have permission to depict this person
        </label>
        <Button
          size="small"
          onClick={() => void add()}
          disabled={!name.trim() || adding || saving}
        >
          {adding ? "Adding…" : "Add character"}
        </Button>
      </div>
      {error && <p className="error">{error}</p>}
    </section>
  );
}
