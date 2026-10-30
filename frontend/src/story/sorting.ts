import type { IdeaPart, IdeaParts } from "../api";

export const PART_NAMES: Record<IdeaPart, string> = {
  story: "Story",
  style: "Style",
  rules: "Rules",
  avoid: "Avoid",
};

export const IDEA_PARTS = Object.keys(PART_NAMES) as IdeaPart[];

export type Sentence = { part: IdeaPart; index: number; text: string };

function sentencesOfText(text: string): string[] {
  return text
    .split(/(?<=[.!?…]["”’')]?)\s+/)
    .map((sentence) => sentence.trim())
    .filter(Boolean);
}

/** Every sentence you can move, each still word for word from the paste. */
export function sentences(parts: IdeaParts): Sentence[] {
  return IDEA_PARTS.flatMap((part) =>
    parts[part]
      .flatMap(sentencesOfText)
      .map((text, index) => ({ part, index, text })),
  );
}

/** The sort after moving one sentence. The server decides the order and paragraphs. */
export function moveSentence(parts: IdeaParts, sentence: Sentence, to: IdeaPart): IdeaParts {
  const next = Object.fromEntries(
    IDEA_PARTS.map((part) => [part, parts[part].flatMap(sentencesOfText)]),
  ) as IdeaParts;
  next[sentence.part] = next[sentence.part].filter((_, index) => index !== sentence.index);
  next[to] = [...next[to], sentence.text];
  return next;
}
