import { useCallback, useRef, useState } from "react";
import {
  api,
  type Budget,
  type BudgetDecision,
  type ImageEstimate,
} from "../api";

export type PaidScope = "proof" | "stills";

export type PaidQuote = {
  estimate: ImageEstimate;
  decision: BudgetDecision;
  budget: Omit<Budget, "history"> | null;
  ids: string[];
  scope: PaidScope;
  regenerate: boolean;
};

type GenerateReply = Awaited<ReturnType<typeof api.generateImages>>;

/**
 * The one paid-image flow: estimate, then either generate immediately (when the
 * budget and uploads are clear) or keep the quote for a top-up / upload
 * confirmation. No provider call happens without an explicit click.
 */
export function usePaidImages(
  slug: string,
  reserve: string,
  onDone: () => void,
) {
  const [quote, setQuote] = useState<PaidQuote | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const done = useRef(onDone);
  done.current = onDone;

  const generateQuote = useCallback(
    async (current: PaidQuote, uploadsConfirmed: boolean) => {
      setBusy(true);
      setError(null);
      setMessage(null);
      try {
        const result: GenerateReply = await api.generateImages(slug, {
          quote_id: current.estimate.quote_id,
          note: "user confirmed the quoted stills in Studio",
          uploads_confirmed: uploadsConfirmed,
        });
        if (result.needs_budget && result.decision) {
          setQuote({
            ...current,
            decision: result.decision,
            budget: result.budget || current.budget,
          });
          return;
        }
        if (result.error) {
          setError(result.error);
          return;
        }
        setQuote(null);
        setMessage(
          `Queued ${result.tasks || current.estimate.tasks} still${
            (result.tasks || current.estimate.tasks) === 1 ? "" : "s"
          } · $${result.reserve_usd || current.estimate.reserve_usd} reserved.`,
        );
        done.current();
      } catch (caught) {
        setError(String(caught));
      } finally {
        setBusy(false);
      }
    },
    [slug],
  );

  const request = useCallback(
    async (ids: string[], scope: PaidScope, regenerate = false) => {
      if (!ids.length || busy) return;
      setBusy(true);
      setQuote(null);
      setError(null);
      setMessage(null);
      try {
        const response = await api.imageEstimate(slug, {
          shot_ids: ids,
          reserve_usd: reserve,
          scope,
          regenerate,
        });
        if (response.error || !response.estimate || !response.decision) {
          setError(response.error || "The pictures could not be estimated.");
          return;
        }
        const next: PaidQuote = {
          estimate: response.estimate,
          decision: response.decision,
          budget: response.budget || null,
          ids,
          scope,
          regenerate,
        };
        if (response.decision.needs_budget || response.estimate.uploads_required) {
          setQuote(next);
          return;
        }
        await generateQuote(next, false);
      } catch (caught) {
        setError(String(caught));
      } finally {
        setBusy(false);
      }
    },
    [busy, generateQuote, reserve, slug],
  );

  const topUp = useCallback(
    async (amount: string, uploadsConfirmed: boolean) => {
      if (!quote || busy) return;
      setBusy(true);
      setError(null);
      try {
        const cap = quote.estimate.cap_usd ?? quote.budget?.cap_usd ?? null;
        const nextCap = cap
          ? (Number(cap) + Number(amount)).toFixed(2)
          : Number(amount).toFixed(2);
        await api.addBudget(slug, nextCap, "Images: top-up for a quoted batch");
        await generateQuote(quote, uploadsConfirmed);
      } catch (caught) {
        setError(String(caught));
      } finally {
        setBusy(false);
      }
    },
    [busy, generateQuote, quote, slug],
  );

  const confirm = useCallback(
    async (uploadsConfirmed: boolean) => {
      if (!quote || busy) return;
      await generateQuote(quote, uploadsConfirmed);
    },
    [busy, generateQuote, quote],
  );

  const clear = useCallback(() => {
    setQuote(null);
    setError(null);
    setMessage(null);
  }, []);

  return { quote, busy, error, message, request, topUp, confirm, clear };
}
