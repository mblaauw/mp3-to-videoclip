/** What a turn's model use reads as. An unknown cost never reads as free. */
export type TurnUsage = {
  prompt_tokens: number;
  completion_tokens: number;
  cost_usd: string | null;
  cost_basis: string;
  model?: string;
};

function dollars(value: string | number): string {
  const amount = Number(value);
  if (amount > 0 && amount < 0.01) return `$${amount.toFixed(4).replace(/0+$/, "")}`;
  return `$${amount.toFixed(2)}`;
}

export function usageLine(usage: TurnUsage | undefined | null): string | null {
  if (!usage) return null;
  if (usage.cost_basis === "tokens not reported") return "Tokens not reported";
  const counts = `${usage.prompt_tokens.toLocaleString("en-US")} in · ${usage.completion_tokens.toLocaleString("en-US")} out`;
  return usage.cost_usd === null ? `${counts} · no price known` : `${counts} · about ${dollars(usage.cost_usd)}`;
}

export type FilmUsage = {
  turns: number;
  prompt_tokens: number;
  completion_tokens: number;
  cost_usd: string;
  unpriced_turns: number;
};

/** A film's total, saying so when some turns have no price, because then it's a floor. */
export function filmUsageLine(usage: FilmUsage | null | undefined): string | null {
  if (!usage || !usage.turns) return null;
  const turns = `${usage.turns} ${usage.turns === 1 ? "turn" : "turns"}`;
  if (usage.unpriced_turns === usage.turns) return `${turns}, no price known`;
  const total = `about ${dollars(usage.cost_usd)}`;
  return usage.unpriced_turns ? `${turns}, at least ${total}` : `${turns}, ${total}`;
}
