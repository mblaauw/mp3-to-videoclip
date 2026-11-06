import type { TurnUsage } from "../shell/modelCost";
import type { Stage } from "../shell/nextStep";
import type { ToolItem } from "./ToolRows";

export type Role = "writer" | "editor" | "critic";

export const ROLE_NAME: Record<Role, string> = { writer: "Writer", editor: "Editor", critic: "Critic" };

export type ChatItem =
  | { kind: "user"; text: string }
  | { kind: "assistant"; text: string; role?: Role; options?: string[]; usage?: TurnUsage }
  | ToolItem;

export type StreamEvent = {
  kind: string;
  text?: string;
  tool?: string;
  arguments?: string;
  result?: string;
  payload?: Record<string, unknown>;
};


/** Text for the composer, or with `send` a Writer job a button has already asked for. */
export type DirectorPrompt = {
  text: string;
  at: number;
  send?: boolean;
  task?: string;
  role?: Role;
};

/** Who opens the drawer on each stage; the engine's STAGE_ROLE says the same. */
export const STAGE_ROLE: Record<Stage, Role> = {
  track: "editor",
  script: "writer",
  story: "writer",
  storyboard: "writer",
  images: "writer",
  sound: "writer",
  film: "editor",
  publish: "writer",
};

export function roleForStage(stage: Stage): Role {
  return STAGE_ROLE[stage] ?? "writer";
}

export const SUGGESTIONS: Record<Stage, string[]> = {
  script: [
    "Write the narration on this structure.",
    "Which beat runs long, and what would you cut?",
    "List every invented fact in the script.",
  ],
  track: ["Describe the song's structure in plain words.", "Which sections carry the most energy?"],
  story: [
    "Give me three structurally different directions.",
    "Tighten the treatment and keep the ending.",
    "What in the story is not shootable yet?",
  ],
  storyboard: [
    "Check the pacing against the music.",
    "Rewrite the weakest three shots.",
    "Which shots need on-screen text?",
  ],
  images: ["Review the stills against the brief.", "Rewrite the prompts of the shots marked Redo."],
  sound: ["Write the sound cues for this film.", "Which moment earns an effect?", "What should the bed avoid?"],
  publish: ["Write the release copy.", "Three titles that lead with different things.", "Which tags fit this film?"],
  film: ["Make a first cut.", "Where does the cut feel slow?", "Suggest transitions for the chorus."],
};

export function modelLabel(model: unknown): string {
  const raw = String(model || "");
  const name = raw.split("/").pop() || raw;
  return name
    .split("-")
    .map((part) => {
      if (/^gpt$/i.test(part)) return "GPT";
      if (/^deepseek$/i.test(part)) return "DeepSeek";
      if (/^ai$/i.test(part)) return "AI";
      return part ? part[0].toUpperCase() + part.slice(1) : part;
    })
    .join(" ");
}

export function clock(seconds: number): string {
  const value = Math.max(0, Math.floor(seconds));
  return `${Math.floor(value / 60)}:${String(value % 60).padStart(2, "0")}`;
}
