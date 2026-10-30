/** Stable API failures: every 4xx/5xx carries `{ detail, code }`. */

export type ErrorEnvelope = {
  detail?: unknown;
  code?: string;
};

const COPY: Record<string, string> = {
  no_llm_key: "The director has no model key. Open Settings.",
  director_unavailable: "The director is not available right now.",
  director_model_unavailable: "That director model is not available. Open Settings.",
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
};

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
