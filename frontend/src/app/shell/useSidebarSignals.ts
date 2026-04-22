import { useEffect, useState } from "preact/hooks";

import {
  documents,
  study,
  system,
  type ProviderStatus
} from "@/services/api/endpoints";

/**
 * Shell-level data that feeds the left sidebar's live signals.
 *
 * The sidebar is visible on every route, so polling happens at the shell
 * level rather than from each feature. Three independent signals:
 *   - dueCount     — SRS cards the scheduler considers due today. Drives
 *                    the badge next to the Study nav entry and the
 *                    "N cards due" line in the Today panel.
 *   - docCount     — Total sources in the library. Used for the Library
 *                    hint and the Today "X sources" rollup.
 *   - provider     — Which AI backend is active. Rendered as the trust
 *                    signal in the sidebar footer.
 *
 * Polling cadence: 30s. Long enough to avoid noise, short enough that a
 * card rated "Good" drops off the Study badge within one study break.
 * Each signal fetches independently so a slow backend on one endpoint
 * doesn't stall the others.
 *
 * Everything is best-effort. Fetch errors leave the previous value in
 * place and set `provider.kind = "unknown"` in the footer. The sidebar
 * never shows a spinner or blocks interaction.
 */
const POLL_INTERVAL_MS = 30_000;

export interface SidebarSignals {
  dueCount: number | null;
  docCount: number | null;
  provider: ProviderStatus | null;
}

export function useSidebarSignals(): SidebarSignals {
  const [signals, setSignals] = useState<SidebarSignals>({
    dueCount: null,
    docCount: null,
    provider: null
  });

  useEffect(() => {
    let cancelled = false;

    const refreshDue = async () => {
      try {
        const data = await study.due();
        if (!cancelled) {
          setSignals((prev) => ({ ...prev, dueCount: data.cards.length }));
        }
      } catch {
        // Swallow — the sidebar stays on the last known value.
      }
    };

    const refreshDocs = async () => {
      try {
        const data = await documents.list();
        if (!cancelled) {
          setSignals((prev) => ({ ...prev, docCount: data.length }));
        }
      } catch {
        /* ignore */
      }
    };

    const refreshProvider = async () => {
      try {
        const data = await system.provider();
        if (!cancelled) {
          setSignals((prev) => ({ ...prev, provider: data }));
        }
      } catch {
        if (!cancelled) {
          setSignals((prev) => ({
            ...prev,
            provider: {
              kind: "unknown",
              ai_enabled: false,
              model_balanced: "",
              preference: "auto"
            }
          }));
        }
      }
    };

    const refreshAll = () => {
      void refreshDue();
      void refreshDocs();
      void refreshProvider();
    };

    refreshAll();
    const timer = window.setInterval(refreshAll, POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(timer);
    };
  }, []);

  return signals;
}
