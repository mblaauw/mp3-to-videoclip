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

const MOVES: Record<string, string> = {
  push_in: "push-in",
  pull_back: "pull-back",
  pan_left: "pan left",
  pan_right: "pan right",
  hold: "hold",
};
const move = (name: string) => MOVES[name] ?? name.replace(/_/g, " ");

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
      return note(`${place}: third ${move(first(text, /three (\w+)/)) || "same"} in a row`, "A different move here would vary the rhythm.");
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
    case "travel_repetition":
      return note(`${place}: the same ${move(first(text, /\d+ (\w+) moves/)) || "move"} repeats`, "Several shots in a row travel the same distance. Varying one keeps it from feeling mechanical.");
    case "long_static_shot":
      return note(`${place}: still for ${first(text, /([\d.]+)s/)} seconds`, "Fine if it is meant to hold. If not, give it a slow move or a new framing.");
    case "crop_soft":
      return note(`${place}: this crop may look soft`, `It enlarges the still ${first(text, /([\d.]+)x/)} times. A wider crop or a sharper still would hold up better.`);
    case "section_no_feel":
      return note(`${place}: no feel written for this section`, "A line about how it should feel guides the cuts and moves here.");
    case "text_not_drawn":
      return note(`${place}: the storyboard's words are not on screen`, "They only show if the cut draws them. Add them as text on this shot, or remove them from the storyboard.");
    case "reprise_uncropped":
      return note(`${place}: a repeated still with no new framing`, "A crop on its first frame makes the repeat read as a new shot.");
    case "reading_time":
    case "text_reading_time":
      return note(`${place}: on-screen text may be too quick to read`, text);
    case "off_grid":
      return note(`${place}: cuts away from the beat`, "A full passage lands harder on a downbeat. Move these joins, or keep them if the drift is the point.");
    case "late_cut":
      return note(`${place}: cuts just after the beat`, "The picture arrives after the hit. A frame or two earlier reads as on time.");
    case "caption_overlap":
      return note(`${shot?.shot_id ?? place}: two lines of text at once`, "Shorten the first line so the second starts clear of it.");
    default:
      return note(`${place}: ${text.replace(/section section-\d+\s*/g, "")}`, "");
  }
}

export function describeNotes(findings: EditFinding[], context: Context): CutNote[] {
  return findings.map((finding, index) => describeNote(finding, index, context));
}
