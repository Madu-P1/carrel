export const API_BASE = import.meta.env.VITE_API_BASE ?? "http://127.0.0.1:8000";

/**
 * The backend returned a non-2xx HTTP response. `status` and `body`
 * carry the FastAPI error shape so callers can branch on
 * `err.status === 404` or pull `err.body.detail`.
 */
export class ApiError extends Error {
  body?: unknown;
  status: number;
  statusText: string;

  constructor(status: number, statusText: string, body?: unknown) {
    super(`API ${status} ${statusText}`);
    this.name = "ApiError";
    this.status = status;
    this.statusText = statusText;
    this.body = body;
  }
}

/**
 * The backend at API_BASE wasn't reachable at all — connection
 * refused, DNS failure, timeout, or any other network-layer error
 * before a response. Distinct from ApiError because the recovery
 * is different: ApiError means "the endpoint is broken or the
 * request was malformed"; BackendOfflineError means "the entire
 * backend is gone and every API call is failing right now".
 *
 * The desktop app surfaces this state via the sidebar's "Backend
 * offline" pill (commit 516f35b9). Per-feature error states should
 * also honour it: instead of generic "Load failed", they can say
 * "Carrel's backend isn't running" with a recovery hint pointing at
 * the supervisor.
 */
export class BackendOfflineError extends Error {
  readonly cause: unknown;

  constructor(cause: unknown) {
    super("Backend offline");
    this.name = "BackendOfflineError";
    this.cause = cause;
  }
}

/** Type guard for callers that want to branch on the error kind. */
export function isBackendOffline(err: unknown): err is BackendOfflineError {
  return err instanceof BackendOfflineError;
}

export type RequestInitEx = Omit<RequestInit, "body"> & { body?: BodyInit | object | null };

export async function api<T>(path: string, init: RequestInitEx = {}): Promise<T> {
  const { body, headers, ...rest } = init;
  const isObjectBody =
    body !== undefined && body !== null && !(body instanceof FormData) && typeof body === "object";

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...rest,
      headers: {
        ...(isObjectBody ? { "content-type": "application/json" } : {}),
        ...headers
      },
      body: isObjectBody ? JSON.stringify(body) : (body as BodyInit | null | undefined)
    });
  } catch (cause) {
    // `fetch()` only throws on network-layer failures: connection
    // refused, DNS failure, abort, CORS preflight failure, etc. Any
    // HTTP response (even 500) resolves the promise. So a thrown
    // error here means the backend wasn't reachable, not that an
    // endpoint is broken. Map to BackendOfflineError so the UI can
    // distinguish the two.
    throw new BackendOfflineError(cause);
  }

  if (!response.ok) {
    let payload: unknown;
    try {
      payload = await response.json();
    } catch {
      payload = undefined;
    }
    throw new ApiError(response.status, response.statusText, payload);
  }

  if (response.status === 204) {
    return undefined as T;
  }

  return response.json() as Promise<T>;
}
