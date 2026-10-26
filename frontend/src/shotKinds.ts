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
  return kind === "scene";
}
