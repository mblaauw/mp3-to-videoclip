import { useEffect, useRef, useState } from "react";
import { resources } from "./resources.ts";

/**
 * One shared value per key: every consumer reads the same fetch, and each is told when it goes
 * out of date. ``load`` must be a GET through ``api``, which is what makes the fetch shared.
 */
export function useResource<T>(key: string, load: () => Promise<T>) {
  const [value, setValue] = useState<T | null>(null);
  const [error, setError] = useState<unknown>(null);
  const loader = useRef(load);
  loader.current = load;
  useEffect(() => {
    let live = true;
    const read = () => {
      loader.current().then(
        (next) => {
          if (live) {
            setValue(next);
            setError(null);
          }
        },
        (caught: unknown) => {
          if (live) setError(caught);
        },
      );
    };
    read();
    const stop = resources.subscribe(key, read);
    return () => {
      live = false;
      stop();
    };
  }, [key]);
  return { value, error, setValue };
}
