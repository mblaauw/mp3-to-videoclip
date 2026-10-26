import { useEffect, useState } from "react";
import { api, type CreditCard, type GraphicsSpec } from "../api";
import { notifyProjectChanged } from "../shell/projectEvents";
import { Button } from "../ui";

function cleanCards(cards: CreditCard[]): CreditCard[] {
  return cards
    .map(([role, name]) => [role.trim(), name.trim()] as CreditCard)
    .filter(([role, name]) => role && name);
}

export function CreditsCard({ slug }: { slug: string }) {
  const [graphics, setGraphics] = useState<GraphicsSpec | null>(null);
  const [cards, setCards] = useState<CreditCard[]>([]);
  const [confirmed, setConfirmed] = useState(false);
  const [useTemplate, setUseTemplate] = useState(false);
  const [editing, setEditing] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .graphics(slug)
      .then((value) => {
        setGraphics(value);
        const stored = value.spec?.credits?.cards || [];
        setCards(stored.length ? stored : [["", ""]]);
        setConfirmed(value.spec?.credit_roles_confirmed === true);
        setEditing(value.guided !== false && value.spec?.credit_roles_confirmed !== true);
      })
      .catch(() => setGraphics(null));
  }, [slug]);

  if (!graphics?.available) return null;

  const guided = graphics.guided !== false;
  const valid = cleanCards(cards).length > 0;

  const change = (index: number, position: 0 | 1, value: string) => {
    setCards((current) =>
      current.map((card, offset) => {
        if (offset !== index) return card;
        const next: CreditCard = [card[0], card[1]];
        next[position] = value;
        return next;
      }),
    );
  };

  const confirm = async () => {
    if (!valid || saving) return;
    setSaving(true);
    setError(null);
    try {
      const result = await api.saveCredits(slug, cleanCards(cards), useTemplate);
      setCards(result.cards);
      setConfirmed(true);
      setEditing(false);
      setGraphics({
        ...graphics,
        spec: {
          ...(graphics.spec || {}),
          credit_roles_confirmed: true,
          credits: { ...(graphics.spec?.credits || {}), cards: result.cards },
        },
      });
      notifyProjectChanged();
    } catch (caught) {
      setError(String(caught));
    } finally {
      setSaving(false);
    }
  };

  return (
    <section className="stage-block credits-card">
      <h2>
        Credits <small>The closing roll for this film</small>
        {confirmed && <span className="saved-note">Confirmed</span>}
      </h2>
      {!guided && (
        <p className="hint">
          This older production records credits inside its story approval. Ask your agent to
          revise the signature and approve the story again.
        </p>
      )}
      {!editing && (
        <div className="credit-list">
          {cleanCards(cards).map(([role, name], index) => (
            <div className="credit-line" key={`${role}-${index}`}>
              <b>{role}</b>
              <span>{name}</span>
            </div>
          ))}
          {!cleanCards(cards).length && <p className="hint">No factual roles recorded yet.</p>}
        </div>
      )}
      {guided && editing && (
        <div className="credit-editor">
          {cards.map((card, index) => (
            <div className="credit-edit-row" key={index}>
              <input
                value={card[0]}
                aria-label={`Credit role ${index + 1}`}
                placeholder="Role, e.g. MUSIC"
                maxLength={120}
                onChange={(event) => change(index, 0, event.target.value)}
              />
              <input
                value={card[1]}
                aria-label={`Credit name ${index + 1}`}
                placeholder="Name"
                maxLength={120}
                onChange={(event) => change(index, 1, event.target.value)}
              />
              <button
                type="button"
                className="ui-btn ui-btn--small ui-btn--quiet"
                aria-label={`Remove credit ${index + 1}`}
                onClick={() => setCards((current) => current.filter((_, offset) => offset !== index))}
              >
                Remove
              </button>
            </div>
          ))}
          <div className="row-actions">
            <Button size="small" onClick={() => setCards((current) => [...current, ["", ""]])}>
              Add role
            </Button>
            <label className="check-line">
              <input
                type="checkbox"
                checked={useTemplate}
                onChange={(event) => setUseTemplate(event.target.checked)}
              />
              Use these roles for new films
            </label>
          </div>
          <div className="row-actions">
            <Button
              size="small"
              variant="primary"
              onClick={() => void confirm()}
              disabled={!valid || saving}
            >
              {saving ? "Confirming…" : "Confirm credits"}
            </Button>
            {confirmed && (
              <Button size="small" variant="quiet" onClick={() => setEditing(false)}>
                Cancel
              </Button>
            )}
          </div>
        </div>
      )}
      {guided && !editing && (
        <div className="row-actions">
          <Button size="small" onClick={() => setEditing(true)}>
            Edit credits
          </Button>
        </div>
      )}
      <p className="hint">
        These are factual roles, not guesses. They appear at the end of the film.
        {guided
          ? " Correcting them here does not invalidate the pictures."
          : " This film records them inside the story approval."}
      </p>
      {error && <p className="error">{error}</p>}
    </section>
  );
}
