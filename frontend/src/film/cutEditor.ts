import type { EditPayload } from "../api";

/** Saves one whole cut against the last cut the server confirmed. */
export type SaveCut = (next: EditPayload, base: EditPayload) => Promise<EditPayload>;

export type ApplyResult = "saved" | "failed" | "conflict" | "dropped";

/**
 * The cut being edited. Changes show at once and save one at a time, each based
 * on the server's previous answer, so two quick edits can never race or lose a
 * revision. A failure returns to the last confirmed cut and drops later changes
 * built on the failed one.
 */
export class CutEditor {
  current: EditPayload | null = null;
  /** Bumps on every local change, so a slower reload can't overwrite it. */
  version = 0;
  private confirmed: EditPayload | null = null;
  private tail: Promise<unknown> = Promise.resolve();
  private generation = 0;
  private pending = 0;
  private readonly save: SaveCut;
  private readonly changed: () => void;

  constructor(save: SaveCut, changed: () => void) {
    this.save = save;
    this.changed = changed;
  }

  get saving(): boolean {
    return this.pending > 0;
  }

  /** Take the server's cut, unless a local change is on its way. */
  sync(edit: EditPayload | null, atVersion = this.version) {
    if (this.pending > 0 || atVersion !== this.version) return;
    if (edit === this.confirmed) return;
    this.confirmed = edit;
    this.current = edit;
    this.changed();
  }

  apply(next: EditPayload): Promise<ApplyResult> {
    const generation = this.generation;
    this.current = next;
    this.version += 1;
    this.pending += 1;
    this.changed();
    const run = this.tail.then(async (): Promise<ApplyResult> => {
      try {
        if (generation !== this.generation) return "dropped";
        const saved = await this.save(next, this.confirmed as EditPayload);
        this.confirmed = saved;
        if (this.current === next) this.current = saved;
        return "saved";
      } catch (error) {
        this.generation += 1;
        this.current = this.confirmed;
        const conflict =
          !!error && typeof error === "object" && "status" in error && error.status === 409;
        return conflict ? "conflict" : "failed";
      } finally {
        this.pending -= 1;
        this.changed();
      }
    });
    this.tail = run;
    return run;
  }
}
