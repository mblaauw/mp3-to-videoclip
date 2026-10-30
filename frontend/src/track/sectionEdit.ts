/** The owner's section changes, as pure steps on an ordered list of starts and names. */

export type SectionEdit = { start: number; name: string };

export const MIN_SECTION = 2;

/** Moves the edge at the start of section `index`, keeping both neighbours long enough. */
export function moveEdge(
  sections: SectionEdit[],
  index: number,
  time: number,
  duration: number,
): SectionEdit[] {
  if (index <= 0 || index >= sections.length) return sections;
  const low = sections[index - 1].start + MIN_SECTION;
  const high = (index + 1 < sections.length ? sections[index + 1].start : duration) - MIN_SECTION;
  const start = Math.round(Math.max(low, Math.min(high, time)) * 1000) / 1000;
  return sections.map((section, position) => (position === index ? { ...section, start } : section));
}

/** Adds an edge at this time, or returns null if either side would be too short. */
export function addEdge(
  sections: SectionEdit[],
  time: number,
  duration: number,
): SectionEdit[] | null {
  let index = sections.length - 1;
  while (index > 0 && sections[index].start > time) index -= 1;
  const end = index + 1 < sections.length ? sections[index + 1].start : duration;
  if (time - sections[index].start < MIN_SECTION || end - time < MIN_SECTION) return null;
  const added = { start: Math.round(time * 1000) / 1000, name: `${sections[index].name} (2)` };
  return [...sections.slice(0, index + 1), added, ...sections.slice(index + 1)];
}

/** Joins a section with the next one; the first keeps its name. */
export function joinNext(sections: SectionEdit[], index: number): SectionEdit[] {
  if (index < 0 || index + 1 >= sections.length) return sections;
  return sections.filter((_, position) => position !== index + 1);
}
