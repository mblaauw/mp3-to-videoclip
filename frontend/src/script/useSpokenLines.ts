import { api, type ScriptPayload, type TimedLine } from "../api";
import { useResource } from "../api/useResource";

const NONE: TimedLine[] = [];

/** When each line is said, for the Spine. Only a story film asks. */
export function useSpokenLines(slug: string, spine?: string | null): TimedLine[] {
  const story = spine === "soundtrack";
  const { value } = useResource<ScriptPayload | null>(
    story ? `/api/projects/${slug}/script` : `none:${slug}`,
    () => (story ? api.script(slug) : Promise.resolve(null)),
  );
  return value?.timing.lines ?? NONE;
}
