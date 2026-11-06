import type { ClipEstimate, ClipModel } from "../api";

/** The catalogue's price for a model, as the menu says it. */
export function modelWords(model: ClipModel): string {
  if (!model.price) return `${model.label} · price unknown`;
  const unit = model.price.unit === "clip" ? "per clip" : "per second";
  return `${model.label} · from $${model.price.amount} ${unit}`;
}

/** What the purchase button says: the published price for the choices, or the reserve. */
export function priceWords(estimate: ClipEstimate): string {
  const size = estimate.choices?.resolution ? ` at ${estimate.choices.resolution}` : "";
  const sound = estimate.choices?.audio ? ", with its own sound" : "";
  const length = `${estimate.seconds} s`;
  if (estimate.price_basis === "published rate" && estimate.rate) {
    return `Make it · $${Number(estimate.reserve_usd).toFixed(2)} for ${length}${size}${sound}, the published rate`;
  }
  return `Make it · up to $${Number(estimate.reserve_usd).toFixed(2)} for ${length}${size}${sound}, Settings' reserve`;
}

/** The length a model offers nearest above the one wanted, else its longest. */
export function nearestLength(offered: number[], wanted: number): number | null {
  if (!offered.length) return null;
  return offered.find((value) => value >= wanted) ?? offered[offered.length - 1];
}
