import { useEffect, useRef, useState, type PointerEvent } from "react";
import { api, type Brief } from "../api";
import { notifyProjectChanged } from "../shell/projectEvents";
import { Button } from "../ui";
import { cropBox } from "./referenceCrop";

type Point = { x: number; y: number };
type Character = NonNullable<Brief["characters"]>[number];

/** Make a still the reference that keeps a character the same across the film. */
export function ReferencePicker({
  slug,
  shotId,
  version,
  src,
}: {
  slug: string;
  shotId: string;
  version: number;
  src: string;
}) {
  const [characters, setCharacters] = useState<Character[]>([]);
  const [who, setWho] = useState("");
  const [from, setFrom] = useState<Point | null>(null);
  const [to, setTo] = useState<Point | null>(null);
  const [busy, setBusy] = useState(false);
  const [done, setDone] = useState<string | null>(null);
  const image = useRef<HTMLImageElement>(null);

  useEffect(() => {
    let current = true;
    void api.brief(slug).then((brief) => {
      if (!current) return;
      setCharacters(brief.characters || []);
      setWho((value) => value || brief.characters?.[0]?.id || "");
    }, () => undefined);
    return () => {
      current = false;
    };
  }, [slug]);

  const point = (event: PointerEvent): Point => {
    const box = image.current!.getBoundingClientRect();
    return { x: event.clientX - box.left, y: event.clientY - box.top };
  };

  const crop = () => {
    const element = image.current;
    if (!element || !from || !to) return null;
    return cropBox(
      from,
      to,
      { width: element.clientWidth, height: element.clientHeight },
      { width: element.naturalWidth, height: element.naturalHeight },
    );
  };

  const use = async () => {
    setBusy(true);
    setDone(null);
    try {
      await api.addCharacterReference(slug, who, { shot_id: shotId, version, box: crop() });
      setDone(`Now the reference for ${who}. Stills showing them are out of date until remade.`);
      notifyProjectChanged();
    } catch {
      // The request helper has already shown what went wrong.
    } finally {
      setBusy(false);
    }
  };

  const rectangle =
    from && to
      ? {
          left: Math.min(from.x, to.x),
          top: Math.min(from.y, to.y),
          width: Math.abs(from.x - to.x),
          height: Math.abs(from.y - to.y),
        }
      : null;

  return (
    <details className="reference-picker">
      <summary>Use as a character's reference</summary>
      <p className="hint">Drag around the character to crop to them, or leave it to use the whole still.</p>
      <div
        className="reference-crop"
        onPointerDown={(event) => {
          event.currentTarget.setPointerCapture(event.pointerId);
          const start = point(event);
          setFrom(start);
          setTo(start);
        }}
        onPointerMove={(event) => {
          if (event.buttons) setTo(point(event));
        }}
      >
        <img ref={image} src={src} alt="The still to crop" draggable={false} />
        {rectangle && <span className="reference-box" style={rectangle} />}
      </div>
      <div className="row-actions">
        <select aria-label="Which character" value={who} onChange={(event) => setWho(event.target.value)}>
          {characters.map((character) => (
            <option key={character.id} value={character.id}>
              {character.id}
            </option>
          ))}
        </select>
        <Button size="small" disabled={busy || !who} onClick={() => void use()}>
          {busy ? "Saving…" : "Use as reference"}
        </Button>
      </div>
      {done && <p className="hint">{done}</p>}
    </details>
  );
}
