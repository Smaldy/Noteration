/**
 * Typed fetch wrapper for the FastAPI backend under `/api`.
 *
 * The backend returns JSON for success and a JSON `{ detail }` body on error
 * (FastAPI's default). The Phase-1b routing fix guarantees unknown `/api/*`
 * paths 404 as JSON rather than serving index.html, so a parse here is safe.
 */

const API_BASE = "/api";

/** Thrown for any non-2xx response; carries the HTTP status and server detail. */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, {
      headers: { Accept: "application/json", ...init?.headers },
      ...init,
    });
  } catch {
    // Network/connection failure (backend down) — surface as a 0-status error.
    throw new ApiError(0, "Cannot reach the Noteration backend.");
  }

  if (!res.ok) {
    const detail = await extractDetail(res);
    throw new ApiError(res.status, detail);
  }

  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

async function extractDetail(res: Response): Promise<string> {
  try {
    const body = (await res.json()) as { detail?: unknown };
    if (typeof body.detail === "string") return body.detail;
  } catch {
    // non-JSON error body; fall through to the generic message
  }
  return `Request failed (${res.status})`;
}

export const api = {
  get: <T>(path: string) => request<T>(path),
  post: <T>(path: string, body?: unknown) =>
    request<T>(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    }),
};
