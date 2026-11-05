import type { Stage } from "./nextStep";

export const STAGES: readonly { id: Stage; label: string }[] = [
  { id: "track", label: "Track" },
  { id: "story", label: "Story" },
  { id: "storyboard", label: "Storyboard" },
  { id: "images", label: "Images" },
  { id: "sound", label: "Sound" },
  { id: "film", label: "Film" },
];

/** A story film has no song to measure: its words come after its brief. */
const STORY_FILM_STAGES: readonly { id: Stage; label: string }[] = [
  { id: "story", label: "Story" },
  { id: "script", label: "Script" },
  { id: "storyboard", label: "Storyboard" },
  { id: "images", label: "Images" },
  { id: "sound", label: "Sound" },
  { id: "film", label: "Film" },
];

export function stagesFor(spine?: string | null): readonly { id: Stage; label: string }[] {
  return spine === "soundtrack" ? STORY_FILM_STAGES : STAGES;
}

export function stageLabel(stage: Stage): string {
  return [...STAGES, ...STORY_FILM_STAGES].find((item) => item.id === stage)?.label || stage;
}

export function isStage(value: string): value is Stage {
  return [...STAGES, ...STORY_FILM_STAGES].some((item) => item.id === value);
}
