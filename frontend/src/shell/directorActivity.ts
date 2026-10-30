/** What the Director says while a reply is on its way. Kept apart so it can be tested. */

/**
 * A whole Writer turn has been seen to take 55 s and a tool call can be silent for
 * most of that, so a shorter wait would cry wolf. The server ends the turn itself
 * later (`IDLE_LIMIT` in `director/llm.py`); this only offers the choice sooner.
 */
export const QUIET_AFTER_SECONDS = 60;

export type Writing = { tool: string; chars: number };

const WRITING_LABEL: Record<string, string> = {
  update_brief: "the story",
  update_shots: "storyboard changes",
  create_storyboard: "the storyboard",
  update_edit: "the cut",
  update_treatments: "the concepts",
  sort_idea: "your idea",
  place_story: "the story on the song",
  generate_images: "a request for pictures",
};

function clock(seconds: number): string {
  const value = Math.max(0, Math.floor(seconds));
  return `${Math.floor(value / 60)}:${String(value % 60).padStart(2, "0")}`;
}

/** The gateway names its tools `clipstudio_update_brief`. */
function bareTool(tool: string): string {
  return tool.replace(/^clipstudio_/, "");
}

export function writingLine(who: string, writing: Writing): string {
  const tool = bareTool(writing.tool);
  const what = WRITING_LABEL[tool] || "its next step";
  const amount = writing.chars > 0 ? ` · ${writing.chars.toLocaleString("en-US")} characters` : "";
  return `The ${who} is writing ${what}…${amount}`;
}

/** Null until the silence has lasted long enough to be worth saying. */
export function quietLine(quietSeconds: number): string | null {
  if (quietSeconds < QUIET_AFTER_SECONDS) return null;
  return (
    `Nothing new for ${clock(quietSeconds)}. Long steps can take a few minutes. ` +
    "If you would rather not wait, you can stop this. Anything already saved stays saved."
  );
}
