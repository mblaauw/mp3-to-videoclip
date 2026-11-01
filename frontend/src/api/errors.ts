/** Stable API failures: every 4xx/5xx carries `{ detail, code }`. */

export type ErrorEnvelope = {
  detail?: unknown;
  code?: string;
};

const COPY: Record<string, string> = {
  no_llm_key: "The director has no model key. Add one in Settings.",
  director_unavailable: "The director is not available right now.",
  director_model_unavailable: "That director model is not available. Choose another in Settings.",
  internal_error: "Something went wrong. Details are in the log.",
  loopback_only: "Studio only answers on this computer.",
  origin_not_allowed: "That request came from an unexpected page.",
  json_required: "Studio expected a JSON request.",
  job_not_found: "That job is no longer there.",
  approval_stale: "The stage changed. Check the current version before approving again.",
  approval_not_found: "That approval stage does not exist.",
  message_too_long:
    "That message is too long. Paste your idea into Story under Start instead.",
  not_found: "That item could not be found.",
  payload_too_large: "That file is too large.",
  unsupported_media_type: "That file type is not supported here.",
  project_busy: "Another job is working on this film. Try again when it finishes.",
  conflict: "This changed somewhere else. Reload and check it before saving again.",
  approval_invalid: "That approval could not be recorded.",
  no_runware_key: "Pictures and voices need a Runware key. Add one in Settings.",
  storyboard_missing: "The storyboard has not been made yet.",
  brief_missing: "The story has not been written yet.",
  edit_missing: "The cut has not been made yet.",
  analysis_missing: "The song has not been analyzed yet.",
  artifact_missing: "That file is not there yet.",
  quote_missing: "That quote is no longer there. Estimate again.",
  service_unavailable: "Studio is still starting up. Try again in a moment.",
  // What a provider answered. Nothing was charged for a refused request.
  network_error: "The provider could not be reached. Check the connection and try again.",
  invalidApiKey: "The provider refused the key. Check it in Settings.",
  insufficientCredits: "The provider account is out of credit.",
  rateLimitExceeded: "The provider is limiting requests. Try again shortly.",
  invalidModel: "The provider does not offer that model.",
  modelNotFound: "The provider does not offer that model.",
  invalidRequest: "The provider refused the request.",
  invalidTaskUUID: "The provider refused the request.",
  taskNotFound: "The provider has no record of that task.",
  provider_error: "The provider answered with an error.",
  upstream_error: "The provider answered with an error.",
};

export type ErrorAction = { label: string; settings: true } | { label: string; stage: string };

const SETTINGS_CODES = new Set([
  "no_llm_key",
  "director_model_unavailable",
  "no_runware_key",
  "invalidApiKey",
]);

const STAGE_CODES: Record<string, { label: string; stage: string }> = {
  storyboard_missing: { label: "Go to Storyboard", stage: "storyboard" },
  brief_missing: { label: "Go to Story", stage: "story" },
  edit_missing: { label: "Go to Film", stage: "film" },
  analysis_missing: { label: "Go to Track", stage: "track" },
};

/** The sentence for a code, or nothing when only the server's detail can say. */
export function errorCopy(code: string | null | undefined): string | undefined {
  return code ? COPY[code] : undefined;
}

/** What the owner can do about a code, if there is one thing to do. */
export function errorAction(code: string | null | undefined): ErrorAction | undefined {
  if (!code) return undefined;
  if (SETTINGS_CODES.has(code)) return { label: "Open settings", settings: true };
  return STAGE_CODES[code];
}

function detailText(detail: unknown): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const parts = detail.map((item) => {
      if (item && typeof item === "object") {
        const entry = item as { msg?: unknown; loc?: unknown };
        const where = Array.isArray(entry.loc) ? entry.loc.join(".") : "";
        const message = typeof entry.msg === "string" ? entry.msg : JSON.stringify(item);
        return where ? `${where}: ${message}` : message;
      }
      return String(item);
    });
    return parts.join("; ");
  }
  if (detail === undefined || detail === null) return "";
  if (typeof detail === "object") return JSON.stringify(detail);
  return String(detail);
}

export class ApiError extends Error {
  status: number;
  code: string;
  detail: unknown;

  constructor(status: number, code: string, detail: unknown) {
    const raw = detailText(detail);
    super(COPY[code] || raw || `Request failed with status ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.detail = detail;
  }

  /** So a screen that prints the failure shows the sentence, not the class name. */
  toString(): string {
    return this.message;
  }
}

/** Read an error response once; tolerates proxies and legacy text bodies. */
export async function readApiError(response: Response): Promise<ApiError> {
  const text = await response.text();
  let body: ErrorEnvelope = {};
  try {
    const parsed = JSON.parse(text);
    if (parsed && typeof parsed === "object") body = parsed as ErrorEnvelope;
  } catch {
    // Keep the raw text as the detail below.
  }
  const empty = Object.keys(body).length === 0;
  return new ApiError(
    response.status,
    body.code || `http_${response.status}`,
    empty ? text : body.detail,
  );
}
