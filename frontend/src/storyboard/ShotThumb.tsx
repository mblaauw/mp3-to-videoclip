import { useEffect, useState } from "react";
import type { ImageShot, Shot } from "../api";
import { isPaidShot, kindMeta, kindOf } from "../shotKinds";

export function imageUrl(slug: string, image: ImageShot | undefined): string | null {
  if (!image) return null;
  if (image.plate) return image.plate;
  if (image.selected === null) return null;
  return `/api/projects/${slug}/images/${encodeURIComponent(image.owner)}/${image.selected}`;
}

/**
 * The one picture representation used by Storyboard cards, the table and the
 * inspector. Local kinds get a designed plate instead of a hatched missing
 * still; generated shots without a version keep the framing placeholder.
 */
export function ShotThumb({
  slug,
  shot,
  image,
  className = "",
}: {
  slug: string;
  shot: Shot;
  image?: ImageShot;
  className?: string;
}) {
  const kind = kindOf(shot);
  const meta = kindMeta(kind);
  const source = imageUrl(slug, image);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    setFailed(false);
  }, [source]);

  const local = !isPaidShot(shot);
  const framing = shot.framing ? shot.framing.replace("_", " ") : "framing to set";
  const text = shot.text || [];

  return (
    <div
      className={`shot-thumb ${source && !failed ? "has-picture" : ""} ${
        local ? "is-local" : "is-paid"
      } ${className}`}
    >
      {source && !failed ? (
        <img src={source} alt="" onError={() => setFailed(true)} loading="lazy" />
      ) : local ? (
        <div className={`designed-plate kind-${kind}`}>
          <span className="designed-mark" aria-hidden="true">
            {meta.icon}
          </span>
          {shot.message && <span className="designed-message">{shot.message}</span>}
          {text.length > 0 && (
            <span className="designed-text">
              {text.slice(0, 3).map((line) => (
                <span key={line}>{line}</span>
              ))}
            </span>
          )}
          {!shot.message && text.length === 0 && (
            <span className="designed-message muted">Made here, free</span>
          )}
        </div>
      ) : (
        <div className="shot-hatch">
          <span>{framing}</span>
        </div>
      )}
      {kind !== "scene" && (
        <span className={`shot-kind kind-${kind}`} title={meta.hint}>
          {meta.icon} {meta.label}
        </span>
      )}
    </div>
  );
}
