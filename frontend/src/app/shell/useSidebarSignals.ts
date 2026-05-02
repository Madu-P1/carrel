import { useEffect, useState } from "preact/hooks";

import {
  system,
  type ProviderStatus
} from "@/services/api/endpoints";

/**
 * Shell-level data that feeds the left sidebar's live signals.
 *
 * The sidebar is visible on every route, so polling happens at the shell
 * level rather than from each feature. The heavy counts come from the compact
 * /api/shell/status endpoint so this hook does not pull full document/card
 * lists just to show two badges.
 *   - dueCount  — SRS cards the scheduler considers due today.
 *   - docCount  — Total sources in the library.
 *   - provider  — Which AI backend is active. Rendered in the footer.
 *   - backend   — FastAPI liveness. "ok" when /api/health returns 2xx,
 *                 "down" on connection refused / timeout / 5xx. Drives
 *                 the footer's "Backend offline" override when the
 *                 BackendSupervisor hasn't yet respawned uvicorn.
 *
 * Polling cadence:
 *   - dueCount / docCount / provider: 30s (long enough to avoid noise).
 *   - backend: 10s (short enough that a recovered backend updates the
 *     UI within one beat — the BackendSupervisor's monitor interval is
 *     60s on the Swift side, so 10s on the frontend means the user sees
 *     the recovery within the same minute).
 *
 * Errors leave the previous value in place (sidebar stays on last known)
 * except for `backend`, which flips to "down" on any failure so the user
 * gets immediate visible feedback.
 */
const POLL_INTERVAL_MS = 30_000;
const HEALTH_POLL_INTERVAL_MS = 10_000;

export type BackendStatus = "ok" | "down";

export interface SidebarSignals {
  dueCount: number | null;
  docCount: number | null;
  provider: ProviderStatus | null;
  backend: BackendStatus | null;
}

export function useSidebarSignals(): SidebarSignals {
  const [signals, setSignals] = useState<SidebarSignals>({
    dueCount: null,
    docCount: null,
    provider: null,
    backend: null
  });

  useEffect(() => {
    let cancelled = false;

    const refreshStatus = async () => {
      try {
        const data = await system.status();
        if (!cancelled) {
          setSignals((prev) => ({
            ...prev,
            dueCount: data.due_count,
            docCount: data.doc_count,
            provider: data.provider
          }));
        }
      } catch {
        // Swallow — the sidebar stays on the last known value.
      }
    };

    const refreshBackend = async () => {
      try {
        await system.health();
        if (!cancelled) {
          setSignals((prev) => ({ ...prev, backend: "ok" }));
        }
      } catch {
        if (!cancelled) {
          setSignals((prev) => ({ ...prev, backend: "down" }));
        }
      }
    };

    const refreshHeavy = () => {
      void refreshStatus();
    };

    // First paint: kick everything off immediately.
    refreshHeavy();
    void refreshBackend();

    const heavyTimer = window.setInterval(refreshHeavy, POLL_INTERVAL_MS);
    const healthTimer = window.setInterval(refreshBackend, HEALTH_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(heavyTimer);
      window.clearInterval(healthTimer);
    };
  }, []);

  return signals;
}
