import type { Shot, ShotKind } from "./api";

export const SHOT_KINDS: {
  id: ShotKind;
  label: string;
  icon: string;
  paid: boolean;
  hint: string;
}[] = [
  { id: "scene", label: "Scene", icon: "◉", paid: true, hint: "Generated story still" },
  { id: "product", label: "Product", icon: "▣", paid: true, hint: "Generated product still, or local with an upload" },
  { id: "upload", label: "Upload", icon: "⬒", paid: false, hint: "Local user-owned image" },
  { id: "card", label: "Card", icon: "▤", paid: false, hint: "Designed message card" },
  { id: "bridge", label: "Bridge", icon: "⇄", paid: false, hint: "Designed bridge, or generated match" },
  { id: "split", label: "Split", icon: "◫", paid: false, hint: "Two or three panes, local" },
  { id: "reprise", label: "Reprise", icon: "↺", paid: false, hint: "New crop of an existing still" },
  { id: "logo", label: "Logo", icon: "◆", paid: false, hint: "Local brand lockup" },
  { id: "end_card", label: "End card", icon: "▮", paid: false, hint: "Local CTA close" },
  { id: "plate", label: "Plate", icon: "▧", paid: false, hint: "Uploaded period or archival image" },
  { id: "era", label: "Era", icon: "◷", paid: true, hint: "The film's place in one era, generated" },
  { id: "document", label: "Document", icon: "▭", paid: true, hint: "Generated close-up of a prop" },
  { id: "date_card", label: "Date card", icon: "#", paid: false, hint: "A year, drawn locally" },
  { id: "title_card", label: "Title card", icon: "T", paid: false, hint: "A chapter or film title, drawn locally" },
];

export function kindOf(shot: Pick<Shot, "kind">): ShotKind {
  return shot.kind ?? "scene";
}

export function kindMeta(kind: string) {
  return SHOT_KINDS.find((item) => item.id === kind) ?? SHOT_KINDS[0];
}

export function isPaidShot(shot: Shot): boolean {
  if (shot.asset_shot_id) return false;
  const kind = kindOf(shot);
  if (kind === "bridge") return shot.bridge?.mode === "generated";
  if (kind === "product") return !shot.asset;
  return kind === "scene" || kind === "era" || kind === "document";
}
