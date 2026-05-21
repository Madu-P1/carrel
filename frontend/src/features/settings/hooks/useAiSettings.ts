import { signal } from "@preact/signals";
import { useEffect } from "preact/hooks";

import type { AiSettings, AiSettingsUpdate } from "@/services/api/endpoints";
import { settings } from "@/services/api/endpoints";
import { createQuery } from "@/lib/query";

/* Module-scoped query so the SettingsView and the sidebar's provider
 * footer (a future consumer) share one cache — same pattern as
 * `documentsQuery` in features/library/hooks/useDocumentsQuery.ts. */
export const aiSettingsQuery = createQuery<AiSettings>(() => settings.getAi());
const aiSettingsQueryInitialized = signal(false);

/* `save()` is a write, not a fetch — it does not belong inside the
 * query's loading signal (which gates the page skeleton). A separate
 * signal lets the Save buttons show their own spinner while the page
 * content stays mounted. */
const savingSignal = signal(false);

export interface UseAiSettings {
  /** Latest settings payload, or undefined until the first load lands. */
  data: typeof aiSettingsQuery.data;
  /** True only during the initial load (gates the page skeleton). */
  loading: typeof aiSettingsQuery.loading;
  /** Initial-load error. Write errors surface via `save()`'s rejection. */
  error: typeof aiSettingsQuery.error;
  /** True while a `save()` POST is in flight. */
  saving: typeof savingSignal;
  /** Re-fetch the current settings. */
  refetch: () => Promise<void>;
  /**
   * POST a provider and/or key change. On success the shared query data
   * is updated in place so every subscriber re-renders without a second
   * round-trip. On failure the error is re-thrown so the caller can
   * surface a toast — the query's own `error` signal is left untouched
   * (a failed write must not blank the page).
   */
  save: (body: AiSettingsUpdate) => Promise<AiSettings>;
}

export function useAiSettings(): UseAiSettings {
  useEffect(() => {
    const unsubscribe = aiSettingsQuery.subscribe();
    if (
      !aiSettingsQueryInitialized.value &&
      aiSettingsQuery.data.value === undefined &&
      !aiSettingsQuery.loading.value
    ) {
      aiSettingsQueryInitialized.value = true;
      void aiSettingsQuery.refetch();
    }
    return unsubscribe;
  }, []);

  const save = async (body: AiSettingsUpdate): Promise<AiSettings> => {
    savingSignal.value = true;
    try {
      const next = await settings.updateAi(body);
      // The POST returns the same shape as GET — push it straight into
      // the shared cache so the picker, the cards, and any other
      // subscriber reflect the new state immediately.
      aiSettingsQuery.data.value = next;
      return next;
    } finally {
      savingSignal.value = false;
    }
  };

  return {
    data: aiSettingsQuery.data,
    loading: aiSettingsQuery.loading,
    error: aiSettingsQuery.error,
    saving: savingSignal,
    refetch: aiSettingsQuery.refetch,
    save
  };
}

/** Test/teardown helper — mirrors `resetDocumentsQuery`. */
export function resetAiSettingsQuery(): void {
  aiSettingsQueryInitialized.value = false;
  savingSignal.value = false;
  aiSettingsQuery.reset();
}
