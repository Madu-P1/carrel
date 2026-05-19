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
