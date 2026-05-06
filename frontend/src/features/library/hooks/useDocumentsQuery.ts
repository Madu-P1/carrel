import { signal } from "@preact/signals";
import { useEffect } from "preact/hooks";

import { createQuery } from "@/lib/query";
import type { DocumentRow } from "@/services/api/endpoints";
import { documents } from "@/services/api/endpoints";

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
