import { useEffect, useState } from "react";
import { api } from "../api";
import { Button } from "../ui";
import type { LibraryEntry, LibraryKind } from "./entries";

/** One click to bring a library entry into this film; the story then needs approving again. */
export function FromLibrary({
  slug,
  kinds,
  onAdopted,
}: {
  slug: string;
  kinds: LibraryKind[];
  onAdopted: () => void;
}) {
  const [entries, setEntries] = useState<LibraryEntry[]>([]);
  const [key, setKey] = useState("");
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    api.library().then(
      (view) => setEntries(view.entries.filter((entry) => kinds.includes(entry.kind))),
      () => setEntries([]),
    );
  }, [kinds]);
  if (!entries.length) return null;
  return (
    <span className="from-library">
      <select aria-label="From the library" value={key} onChange={(event) => setKey(event.target.value)}>
        <option value="">From the library…</option>
        {entries.map((entry) => (
          <option key={entry.key} value={entry.key}>
            {entry.label} ({entry.kind}, from {entry.from.title})
          </option>
        ))}
      </select>
      <Button
        size="small"
        disabled={!key || busy}
        onClick={() => {
          setBusy(true);
          void api
            .adoptEntry(slug, key)
            .then(() => {
              setKey("");
              onAdopted();
            })
            .finally(() => setBusy(false));
        }}
      >
        Use it here
      </Button>
    </span>
  );
}

/** Copy one thing this film settled into the library. The film is only read. */
export function PromoteButton({ slug, kind, id, label }: { slug: string; kind: LibraryKind; id: string; label?: string }) {
  const [state, setState] = useState<"idle" | "busy" | "done">("idle");
  return (
    <Button
      size="small"
      variant="quiet"
      disabled={state === "busy"}
      title="Keep this in the library for the next film"
      onClick={() => {
        setState("busy");
        void api
          .promoteEntry(slug, kind, id, label)
          .then(() => setState("done"))
          .catch(() => setState("idle"));
      }}
    >
      {state === "done" ? "In the library" : "Promote"}
    </Button>
  );
}
