import type { EditPayload, EditVoiceLine } from "../api";

function withLines(edit: EditPayload, lines: EditVoiceLine[]): EditPayload {
  const ordered = [...lines].sort((a, b) => a.start_frame - b.start_frame);
  return { ...edit, voice: ordered };
}

/** The first free id, so a removed line's takes are never handed to a new one. */
function nextId(lines: EditVoiceLine[], used: string[]): string {
  const taken = new Set([...lines.map((line) => line.id), ...used]);
  let number = 1;
  while (taken.has(`line-${number}`)) number += 1;
  return `line-${number}`;
}

export function addVoiceLine(
  edit: EditPayload,
  startFrame: number,
  text: string,
  usedIds: string[] = [],
): EditPayload {
  const lines = edit.voice ?? [];
  return withLines(edit, [
    ...lines,
    { id: nextId(lines, usedIds), text, start_frame: Math.max(0, Math.round(startFrame)) },
  ]);
}

export function updateVoiceLine(
  edit: EditPayload,
  id: string,
  patch: Partial<Pick<EditVoiceLine, "text" | "start_frame" | "gain_db">>,
): EditPayload {
  return withLines(
    edit,
    (edit.voice ?? []).map((line) => (line.id === id ? { ...line, ...patch } : line)),
  );
}

export function removeVoiceLine(edit: EditPayload, id: string): EditPayload {
  return withLines(
    edit,
    (edit.voice ?? []).filter((line) => line.id !== id),
  );
}

export function setVoiceStart(
  edit: EditPayload,
  id: string,
  seconds: number,
  fps: number,
  totalFrames: number,
): EditPayload {
  const frame = Math.round(seconds * fps);
  return updateVoiceLine(edit, id, {
    start_frame: Math.min(Math.max(0, frame), Math.max(0, totalFrames - 1)),
  });
}
