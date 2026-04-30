import { ApiError, BackendOfflineError, isBackendOffline } from "./client";

/**
 * Translate a fetch error into UI copy that distinguishes the two
 * recovery paths the user can act on:
 *
 *   1. **Backend offline** — the FastAPI process isn't running. The
 *      .app's BackendSupervisor will respawn it within ~60s; the
 *      sidebar's "Backend offline" pill is already showing it.
 *      Recovery: wait a minute, or kick `bash script/build_and_run.sh`.
 *
 *   2. **Endpoint failure** — the backend is up but this specific
 *      route returned non-2xx. Could be a 4xx (request wrong) or
 *      5xx (logic bug, DB issue, AI provider out of credits).
 *      Recovery: depends on the route; usually retry, sometimes
 *      check inputs.
 *
 * Returns `{ title, detail, recovery }` so the calling error state
 * can render with whatever shape it already uses (state-card, toast,
 * inline). All three are short — the title is the headline, the
 * detail is one sentence, the recovery is one verb-led action.
 */
export interface FriendlyError {
  title: string;
  detail: string;
  recovery?: string;
}

export function friendlyError(err: unknown, context: { surface?: string } = {}): FriendlyError {
  if (isBackendOffline(err)) {
    return {
      title: "Backend offline",
      detail:
        "Carrel's backend isn't responding at 127.0.0.1:8000. The desktop app's supervisor probes every 60s and respawns it on failure.",
      recovery: "Wait ~60s for the supervisor to restart it, or run `bash script/build_and_run.sh`.",
    };
  }

  if (err instanceof ApiError) {
    // Pull a useful message out of the FastAPI {detail: "..."} shape
    // when present. Falls back to the HTTP status line.
    const body = err.body as { detail?: unknown } | null | undefined;
    const detail = typeof body?.detail === "string" ? body.detail : null;
    return {
      title: surfaceTitle(context.surface, err.status),
      detail: detail ?? `${err.status} ${err.statusText}`,
      recovery:
        err.status >= 500
          ? "Reload to retry — if it keeps failing, the backend log at dist/einstein-backend.log usually has the stack."
          : err.status === 404
            ? "The route doesn't exist. This usually means you're on an older build."
            : err.status === 409
              ? "Concurrent modification — re-read and retry."
              : undefined,
    };
  }

  // Anything else (CSP, parse error, programmer bug). Show the raw
  // message but don't pretend to know what to do.
  const message = err instanceof Error ? err.message : String(err);
  return {
    title: surfaceTitle(context.surface),
    detail: message || "Unknown error",
  };
}

function surfaceTitle(surface: string | undefined, status?: number): string {
  if (status === 404) return "Not found";
  if (status === 409) return "Concurrent modification";
  if (status && status >= 500) return surface ? `${surface} failed` : "Server error";
  if (surface) return `Couldn't load ${surface.toLowerCase()}`;
  return "Request failed";
}

// Re-export BackendOfflineError + isBackendOffline so callers don't
// have to import from two places.
export { BackendOfflineError, isBackendOffline };
