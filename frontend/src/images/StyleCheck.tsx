import { type ImagesStageProps, useImagesData } from "./useImagesData";
import { sourceUrl, statusOf } from "./imageStatus";

export function StyleCheck({ data, props }: { data: ReturnType<typeof useImagesData>; props: ImagesStageProps }) {
  const { open, price, proofIds, proofMissing, proofShots, proofStale, setFilter, styleState } = data;
  const { slug } = props;
  return (
        <section className="style-check images-style-check">
          <div className="style-check-say">
            <b>Style check · {proofIds.length} hard shots first</b>
            <span>
              When they look right, make the rest. Only these three are paid now.
              {proofStale.length > 0 &&
                " Older-prompt shots are from the previous look; remake them, then keep the new version."}
            </span>
          </div>
          <div className="style-shots">
            {proofShots.map((shot) => {
              const src = sourceUrl(slug, shot);
              return (
                <button
                  type="button"
                  className={`style-shot ${statusOf(shot).tone}`}
                  key={shot.id}
                  onClick={() => {
                    setFilter("all");
                    open(shot.id);
                  }}
                >
                  {src ? <img src={src} alt="" loading="lazy" /> : <span className="hatch" />}
                  <span>
                    <b>{shot.id}</b>
                    <em>{styleState(shot)}</em>
                  </span>
                </button>
              );
            })}
          </div>
          <div className="style-check-actions">
            {proofMissing.length > 0 || proofStale.length > 0 ? (
              <span className="hint">
                {proofMissing.length > 0 && `${proofMissing.length} not made yet`}
                {proofMissing.length > 0 && proofStale.length > 0 && " and "}
                {proofStale.length > 0 &&
                  `${proofStale.length} older-prompt style still${
                    proofStale.length === 1 ? "" : "s"
                  }`}
                {` · make or remake them with the button in the bar at the top (${price(
                  proofMissing.length + proofStale.length,
                )}).`}
              </span>
            ) : (
              <span className="hint">
                {proofShots.every((shot) => shot.review?.verdict === "accept" && !shot.stale)
                  ? "All kept. Approve the style check in the bar at the top."
                  : `Open each one and keep or redo it (${
                      proofShots.filter((shot) => shot.review?.verdict === "accept" && !shot.stale)
                        .length
                    } of ${proofShots.length} kept).`}
              </span>
            )}
          </div>
        </section>
  );
}
