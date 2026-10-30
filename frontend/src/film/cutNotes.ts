import type { EditFinding } from "../api";

export type CutNote = {
  index: number;
  title: string;
  why: string;
  /** Film frame to jump to. */
  frame: number;
  shotId: string | null;
};

type Context = {
  sections: { id: string; name: string; start_frame: number }[];
  shots: { shot_id: string; start_frame: number }[];
};

const first = (value: string, pattern: RegExp) => value.match(pattern)?.[1] ?? "";

/** A report finding in plain language, anchored to where it happens. */
export function describeNote(finding: EditFinding, index: number, context: Context): CutNote {
  const section = context.sections.find((item) => item.id === finding.section);
  const shot = context.shots.find((item) => item.shot_id === finding.shot_id);
  const place = section?.name ?? shot?.shot_id ?? "The cut";
  const note = (title: string, why: string): CutNote => ({
    index,
    title,
    why,
    frame: shot?.start_frame ?? section?.start_frame ?? 0,
    shotId: shot?.shot_id ?? null,
  });
  const text = finding.message;
  switch (finding.code) {
    case "hold_ratio": {
      const counts = text.match(/holds (\d+) of (\d+)/);
      return note(
        `${place}: ${counts?.[1]} of ${counts?.[2]} shots hold still`,
        "Fine if this section is meant to breathe. If not, give one a slow move.",
      );
    }
    case "hold_ratio_total":
      return note("Most of the film holds still", "Give a few shots a slow move, or keep it if stillness is the idea.");
    case "density_target":
      return note(
        `${place}: ${first(text, /cuts ([\d.]+)/)} cuts per 10 seconds`,
        `The target for this section is ${first(text, /a ([\d.]+)\/10s/)}.`,
      );
    case "energy_density":
      return text.startsWith("high")
        ? note(`${place}: loud, but only ${first(text, /only ([\d.]+)/)} cuts per 10 seconds`, "A loud section usually wants more cuts.")
        : note(`${place}: quiet, with ${first(text, /at ([\d.]+)/)} cuts per 10 seconds`, "A quiet section usually wants fewer cuts.");
    case "motion_repetition":
      return note(`${place}: third ${first(text, /three (\w+)/) || "same"} move in a row`, "A different move here would vary the rhythm.");
    case "framing_repetition": {
      const framing = first(text, /back-to-back (\w+) framings/).replace("_", " ");
      return note(`${place}: same framing as the shot before`, `Both are ${framing || "the same"} shots.`);
    }
    case "transition_repetition":
      return note(`${place}: the same join repeats`, "Varying it, or using a plain cut, keeps it from becoming a habit.");
    case "opening_transition":
      return note(`${place}: the first shot has a transition`, "Nothing comes before the first shot, so it has nothing to transition from.");
    case "transition_handle":
      return note(`${place}: this join has no length`, "Give the transition some frames, or make it a cut.");
    case "transition_reason":
      return note(`${place}: this join has no reason`, "Add a note saying why, or make it a cut.");
    case "flash_rate":
      return note("Too many flashes close together", "Flashing is limited to three per second, for people sensitive to it.");
    case "reading_time":
    case "text_reading_time":
      return note(`${place}: on-screen text may be too quick to read`, text);
    default:
      return note(`${place}: ${text.replace(/section section-\d+\s*/g, "")}`, "");
  }
}

export function describeNotes(findings: EditFinding[], context: Context): CutNote[] {
  return findings.map((finding, index) => describeNote(finding, index, context));
}
