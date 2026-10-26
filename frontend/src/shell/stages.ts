import type { Stage } from "./nextStep";

export const STAGES: readonly { id: Stage; label: string }[] = [
  { id: "track", label: "Track" },
  { id: "story", label: "Story" },
  { id: "storyboard", label: "Storyboard" },
  { id: "images", label: "Images" },
  { id: "film", label: "Film" },
];

export function stageLabel(stage: Stage): string {
  return STAGES.find((item) => item.id === stage)?.label || stage;
}

export function isStage(value: string): value is Stage {
  return STAGES.some((item) => item.id === value);
}
