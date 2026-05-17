import { signal } from "@preact/signals";
import { useEffect } from "preact/hooks";

import type { DocumentRow } from "@/services/api/endpoints";
import { documents } from "@/services/api/endpoints";
import { createQuery } from "@/lib/query";

export const documentsQuery = createQuery<DocumentRow[]>(() => documents.list());
const documentsQueryInitialized = signal(false);

/** Polling interval (ms) used while any doc is in "processing" status. */
const PROCESSING_POLL_INTERVAL_MS = 2000;

function anyProcessing(rows: DocumentRow[] | undefined): boolean {
  if (!rows) return false;
  return rows.some((row) => (row.status ?? "").toLowerCase() === "processing");
}

export function useDocumentsQuery() {
  useEffect(() => {
    const unsubscribe = documentsQuery.subscribe();
    if (
      (
        !documentsQueryInitialized.value ||
        (documentsQuery.data.value === undefined &&
          documentsQuery.error.value === null &&
          !documentsQuery.loading.value)
      ) &&
      documentsQuery.data.value === undefined &&
      !documentsQuery.loading.value
    ) {
      documentsQueryInitialized.value = true;
      void documentsQuery.refetch();
    }
    return unsubscribe;
  }, []);

  // SM-4: while any document is in processing state, poll so the UI can
  // observe the transition to "ready" and trigger the pulse-once animation
  // on the newly-ready card. Stops polling once every doc has settled.
  useEffect(() => {
    let cancelled = false;
    const tick = () => {
      if (cancelled) return;
      if (!anyProcessing(documentsQuery.data.value)) return;
      void documentsQuery.refetch();
    };
    const interval = window.setInterval(() => {
      if (cancelled) return;
      if (anyProcessing(documentsQuery.data.value)) {
        tick();
      }
    }, PROCESSING_POLL_INTERVAL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, []);

  return documentsQuery;
}

export function resetDocumentsQuery() {
  documentsQueryInitialized.value = false;
  documentsQuery.reset();
}

/* Companion cube → Library refresh bridge.
 *
 * FloatingCompanionWindow.swift's nudgeLibraryRefresh() looks for
 * `window.__carrelRefreshLibrary` after a successful cube drop and
 * calls it so the open Library view sees the new document without
 * waiting on the SM-4 processing poll. The Swift comment used to claim
 * this hook was registered on "the very first JS line of main.tsx"; in
 * reality nothing wired it, so every cube drop logged "Library refresh
 * nudge could not reach the main webview after 4 attempts" while the
 * file did land in the DB.
 *
 * Registering here (module scope) means the hook is live as soon as
 * any code path imports useDocumentsQuery — which the LibraryView
 * does on mount. If the user drops on the cube before Library has
 * ever been opened, the nudge still no-ops, but the component-mount
 * refetch when Library opens picks up the new doc. No harm.
 *
 * No-op on non-browser environments (Vitest's jsdom always provides
 * `window`, so the guard is mostly belt + suspenders for SSR sanity).
 */
if (typeof window !== "undefined") {
  (window as unknown as { __carrelRefreshLibrary?: () => void }).__carrelRefreshLibrary =
    () => {
      void documentsQuery.refetch();
    };
}
