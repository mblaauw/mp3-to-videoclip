import { api, type ScriptPayload, type TimedLine } from "../api";
import { useResource } from "../api/useResource";

const NONE: TimedLine[] = [];

/** A story film's board binds its shots to lines; no other film's does. */
export function isSpoken(board: { shots: { line_ids?: string[] }[] } | null | undefined): boolean {
  return Boolean(board?.shots.some((shot) => shot.line_ids?.length));
}

/** The script stage's whole answer: timing, mix and what was measured. */
export function useScriptPayload(slug: string, spine?: string | null): ScriptPayload | null {
  const story = spine === "soundtrack";
  const { value } = useResource<ScriptPayload | null>(
    story ? `/api/projects/${slug}/script` : `none:${slug}`,
    () => (story ? api.script(slug) : Promise.resolve(null)),
  );
  return value ?? null;
}

/** When each line is said, for the Spine. Only a story film asks. */
export function useSpokenLines(slug: string, spine?: string | null): TimedLine[] {
  return useScriptPayload(slug, spine)?.timing.lines ?? NONE;
}
