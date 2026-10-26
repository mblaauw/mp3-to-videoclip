import { useEffect, useState } from "react";
import type { Stage } from "./nextStep";
import { isStage } from "./stages";

export type Route =
  | { kind: "library" }
  | { kind: "film"; slug: string; stage: Stage }
  | { kind: "archive"; slug: string };

export function parseHash(hash: string): Route {
  const parts = hash
    .replace(/^#\/?/, "")
    .split("/")
    .filter(Boolean)
    .map((part) => {
      try {
        return decodeURIComponent(part);
      } catch {
        return part;
      }
    });
  if (parts[0] === "archive" && parts[1]) return { kind: "archive", slug: parts[1] };
  if (parts[0] && parts[1] && isStage(parts[1])) {
    return { kind: "film", slug: parts[0], stage: parts[1] };
  }
  return { kind: "library" };
}

export function useHashRoute(): Route {
  const [route, setRoute] = useState<Route>(() => parseHash(window.location.hash));
  useEffect(() => {
    const update = () => setRoute(parseHash(window.location.hash));
    window.addEventListener("hashchange", update);
    return () => window.removeEventListener("hashchange", update);
  }, []);
  return route;
}

export function goLibrary() {
  window.location.hash = "#/";
}

export function goFilm(slug: string, stage: Stage | string) {
  window.location.hash = `#/${encodeURIComponent(slug)}/${stage}`;
}

export function goArchive(slug: string) {
  window.location.hash = `#/archive/${encodeURIComponent(slug)}`;
}
