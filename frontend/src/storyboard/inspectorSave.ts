/** One inspector selection owns one outstanding write and its completions. */
export type SaveTicket = { identity: string; sequence: number };

export class InspectorSaveGuard {
  private identity = "";
  private sequence = 0;
  private pending = false;

  select(identity: string) {
    if (this.identity === identity) return;
    this.identity = identity;
    this.invalidate();
  }

  invalidate() {
    this.sequence += 1;
    this.pending = false;
  }

  begin(identity: string): SaveTicket | null {
    if (this.identity !== identity || this.pending) return null;
    this.pending = true;
    return { identity, sequence: ++this.sequence };
  }

  current(ticket: SaveTicket, identity: string): boolean {
    return this.identity === identity && ticket.identity === identity && ticket.sequence === this.sequence;
  }

  finish(ticket: SaveTicket, identity: string): boolean {
    if (!this.current(ticket, identity)) return false;
    this.pending = false;
    return true;
  }

  isSaving(): boolean {
    return this.pending;
  }
}

/** Navigation may not discard pending, failed or newly typed draft values. */
export async function leaveInspector({
  saving, dirty, save, leave,
}: {
  saving: () => boolean;
  dirty: () => boolean;
  save: () => Promise<boolean>;
  leave: () => void;
}): Promise<boolean> {
  if (saving()) return false;
  if (dirty() && !(await save())) return false;
  if (saving() || dirty()) return false;
  leave();
  return true;
}

/** Only clear values acknowledged by this write; typing during it survives. */
export function remainingDraft<T extends object>(current: Partial<T>, sent: Partial<T>): Partial<T> {
  const next = { ...current };
  for (const key of Object.keys(sent) as (keyof T)[]) {
    if (JSON.stringify(current[key]) === JSON.stringify(sent[key])) delete next[key];
  }
  return next;
}
