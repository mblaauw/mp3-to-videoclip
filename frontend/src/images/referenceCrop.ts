/** Pixels of the source still for a rectangle dragged on its shown image. */
export function cropBox(
  from: { x: number; y: number },
  to: { x: number; y: number },
  shown: { width: number; height: number },
  source: { width: number; height: number },
): [number, number, number, number] | null {
  const scaleX = source.width / shown.width;
  const scaleY = source.height / shown.height;
  const clamp = (value: number, top: number) => Math.min(Math.max(value, 0), top);
  const left = Math.round(clamp(Math.min(from.x, to.x), shown.width) * scaleX);
  const right = Math.round(clamp(Math.max(from.x, to.x), shown.width) * scaleX);
  const top = Math.round(clamp(Math.min(from.y, to.y), shown.height) * scaleY);
  const bottom = Math.round(clamp(Math.max(from.y, to.y), shown.height) * scaleY);
  // A click or a tiny drag isn't a crop: it means the whole still.
  if (right - left < 32 || bottom - top < 32) return null;
  return [left, top, right, bottom];
}
