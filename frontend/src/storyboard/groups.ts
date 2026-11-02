import { type Music, type Shot, type Storyboard } from "../api";

export function clock(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}

type Group = { key: string; title: string; range: string; shots: Shot[] };

export function groupsFor(board: Storyboard, music: Music | null): Group[] {
  const fps = board.fps || 24;
  const sections = (music?.sections || []).filter(
    (section) => Number(section.end) > Number(section.start),
  );
  if (!sections.length) {
    return [{ key: "whole", title: "Whole film", range: "", shots: board.shots }];
  }
  const buckets = new Map<string, Group>();
  const groups: Group[] = sections.map((section, index) => {
    const key = `section-${index}`;
    const title =
      section.name ||
      (section.label && section.label !== "unreviewed" ? section.label : `Section ${index + 1}`);
    const group: Group = {
      key,
      title,
      range: `${clock(Number(section.start))}–${clock(Number(section.end))}`,
      shots: [],
    };
    buckets.set(key, group);
    return group;
  });
  const gaps: Group = { key: "between", title: "Between sections", range: "", shots: [] };
  for (const shot of board.shots) {
    const at = shot.start_frame / fps;
    const home = sections.findIndex(
      (section) => at >= Number(section.start) && at < Number(section.end),
    );
    if (home >= 0) groups[home].shots.push(shot);
    else gaps.shots.push(shot);
  }
  const result = groups.filter((group) => group.shots.length > 0);
  if (gaps.shots.length) result.push(gaps);
  return result;
}
