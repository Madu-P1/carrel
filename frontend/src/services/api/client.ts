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
 * The user-facing message for a failed API call: the FastAPI `detail` string
 * when the response carried one (the backend writes actionable copy there,
 * e.g. "This vault still holds records. Move or delete them first."), else the
 * generic `API <status> <statusText>` message, else the caller's fallback.
 * Without this, surfaces toast the raw "API 409 Conflict" and the designed
 * copy never reaches the user.
 */
export function apiErrorMessage(e: unknown, fallback?: string): string | undefined {
  if (e instanceof ApiError) {
    const detail = (e.body as { detail?: unknown } | undefined)?.detail;
    if (typeof detail === "string" && detail.trim()) return detail;
    // The app's structured-error convention is detail = {code, message}
    // (e.g. /api/documents/upload, /api/verify/extract-draft). Without this
    // branch the actionable `message` is lost and the raw "API 4xx ..." status
    // line surfaces instead.
    if (detail && typeof detail === "object") {
      const message = (detail as { message?: unknown }).message;
      if (typeof message === "string" && message.trim()) return message;
    }
    return e.message;
  }
  if (e instanceof Error && e.message) return e.message;
  return fallback;
}

/**
 * The backend at API_BASE wasn't reachable at all — connection
 * refused, DNS failure, CORS preflight failure, or any other network-layer error
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

export class ApiTimeoutError extends Error {
  readonly timeoutMs: number;

  constructor(timeoutMs: number) {
    super(`API request timed out after ${timeoutMs}ms`);
    this.name = "ApiTimeoutError";
    this.timeoutMs = timeoutMs;
  }
}

/** Type guard for callers that want to branch on the error kind. */
export function isBackendOffline(err: unknown): err is BackendOfflineError {
  return err instanceof BackendOfflineError;
}

export function isApiTimeout(err: unknown): err is ApiTimeoutError {
  return err instanceof ApiTimeoutError;
}

export type RequestInitEx = Omit<RequestInit, "body"> & {
  body?: BodyInit | object | null;
  timeoutMs?: number;
};

const DEFAULT_TIMEOUT_MS = 30_000;
export const LOCAL_TOKEN_HEADER = "X-Carrel-Local-Token";
let cachedLocalApiToken: string | null = null;

export async function api<T>(path: string, init: RequestInitEx = {}): Promise<T> {
  const { body, headers, timeoutMs = DEFAULT_TIMEOUT_MS, signal, ...rest } = init;
  const isObjectBody =
    body !== undefined && body !== null && !(body instanceof FormData) && typeof body === "object";
  // PR-S1: send the local-API token on every request (including GET). The
  // backend now gates all /api/* paths except /api/health, closing the
  // local privilege-escalation hole where a malicious local HTML file
  // could read unauthenticated GET endpoints.
  const token = await resolveLocalApiToken();
  const timeout = createTimeoutSignal(timeoutMs);
  const requestSignal = mergeSignals(signal, timeout.signal);

  let response: Response;
  try {
    response = await fetch(`${API_BASE}${path}`, {
      ...rest,
      headers: {
        ...(isObjectBody ? { "content-type": "application/json" } : {}),
        ...(token ? { [LOCAL_TOKEN_HEADER]: token } : {}),
        ...headers
      },
      body: isObjectBody ? JSON.stringify(body) : (body as BodyInit | null | undefined),
      signal: requestSignal
    });
  } catch (cause) {
    if (timeout.didTimeout()) {
      throw new ApiTimeoutError(timeoutMs);
    }
    // `fetch()` only throws on network-layer failures: connection
    // refused, DNS failure, caller abort, CORS preflight failure, etc. Any
    // HTTP response (even 500) resolves the promise. So a thrown
    // error here means the backend wasn't reachable, not that an
    // endpoint is broken. Map to BackendOfflineError so the UI can
    // distinguish the two.
    throw new BackendOfflineError(cause);
  } finally {
    timeout.dispose();
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

export async function resolveLocalApiToken(): Promise<string | null> {
  if (cachedLocalApiToken) return cachedLocalApiToken;

  const envToken = import.meta.env.VITE_CARREL_LOCAL_API_TOKEN;
  if (typeof envToken === "string" && envToken.length > 0) {
    cachedLocalApiToken = envToken;
    return cachedLocalApiToken;
  }

  const windowToken = readWindowLocalApiToken();
  if (windowToken) {
    cachedLocalApiToken = windowToken;
    return cachedLocalApiToken;
  }

  // PR-S1: the previous `fetch('/api/local-token')` fallback was a local
  // privilege escalation — any malicious HTML on the local filesystem
  // could read the token over an unauthenticated GET. The token is now
  // injected via WKUserScript into `window.__CARREL_LOCAL_API_TOKEN`
  // before any frontend JS runs. If neither the env nor the window
  // global is populated, we surface the boot-error overlay instead of
  // recovering with an insecure HTTP call.
  return null;
}

function readWindowLocalApiToken(): string | null {
  if (typeof window === "undefined") return null;
  const token = (window as Window & { __CARREL_LOCAL_API_TOKEN?: unknown }).__CARREL_LOCAL_API_TOKEN;
  return typeof token === "string" && token.length > 0 ? token : null;
}

/**
 * SSE / EventSource flavor of `api()` — EventSource cannot set custom
 * headers, so the backend accepts the token via `?token=` for safe
 * methods. Returns the URL with the token appended (or unchanged if
 * no token is available, which yields a 403 the SSE client surfaces
 * as a closed connection).
 */
export async function withLocalApiToken(url: string): Promise<string> {
  const token = await resolveLocalApiToken();
  if (!token) return url;
  const sep = url.includes("?") ? "&" : "?";
  return `${url}${sep}token=${encodeURIComponent(token)}`;
}

interface TimeoutHandle {
  signal: AbortSignal | null;
  didTimeout: () => boolean;
  dispose: () => void;
}

function createTimeoutSignal(timeoutMs: number): TimeoutHandle {
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0) {
    return { signal: null, didTimeout: () => false, dispose: () => {} };
  }

  if (typeof AbortSignal !== "undefined" && typeof AbortSignal.timeout === "function") {
    const signal = AbortSignal.timeout(timeoutMs);
    return {
      signal,
      didTimeout: () => signal.aborted,
      dispose: () => {}
    };
  }

  const controller = new AbortController();
  let timedOut = false;
  const timer = window.setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  return {
    signal: controller.signal,
    didTimeout: () => timedOut,
    dispose: () => window.clearTimeout(timer)
  };
}

function mergeSignals(
  callerSignal: AbortSignal | null | undefined,
  timeoutSignal: AbortSignal | null
): AbortSignal | undefined {
  if (!callerSignal) return timeoutSignal ?? undefined;
  if (!timeoutSignal) return callerSignal;
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (callerSignal.aborted || timeoutSignal.aborted) {
    controller.abort();
    return controller.signal;
  }
  callerSignal.addEventListener("abort", abort, { once: true });
  timeoutSignal.addEventListener("abort", abort, { once: true });
  return controller.signal;
}
