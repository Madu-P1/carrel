import { useCallback, useEffect, useRef, useState } from "preact/hooks";

import {
  calendarApi,
  type CalendarFeed,
  type CalendarFeedCreatedResponse,
  type SyncFeedResponse,
} from "../api/calendarApi";
import {
  planApi,
  type PlanEvent,
  type PlanResponse,
  type PlanSuggestion,
} from "../api/planApi";

/**
 * The single hook that backs the Plan surface. Returns a wide bag of
 * state + actions; components destructure what they need. One hook
 * per feature beats three hooks for the same resource — keeps the
 * SWR + freshening signal coherent and means components never see a
 * partial refresh.
 *
 * SWR loop:
 *   - Initial mount fetches /api/plan
 *   - If `is_freshening` came back true, the backend has kicked
 *     stale-feed refreshes; we poll once after a short delay to pick
 *     up the fresh data
 *   - Manual refresh path: `refresh()` does a hard refetch (used by
 *     "Sync now" button + after add/delete feed)
 */

interface UsePlanState {
  events: PlanEvent[];
  suggestions: PlanSuggestion[];
  feeds: CalendarFeed[];
  isFreshening: boolean;
  loading: boolean;
  error: string | null;
}

const EMPTY: UsePlanState = {
  events: [],
  suggestions: [],
  feeds: [],
  isFreshening: false,
  loading: true,
  error: null,
};

// How long to wait after a freshening response before re-polling for
// the post-refresh data. The background sync should be sub-second for
// most feeds; 1.5s gives the slow case room without making the UI
// feel laggy.
const FRESHENING_POLL_MS = 1500;

export function usePlan() {
  const [state, setState] = useState<UsePlanState>(EMPTY);
  const pollTimeoutRef = useRef<number | null>(null);
  const mountedRef = useRef(true);

  const apply = useCallback((next: PlanResponse) => {
    if (!mountedRef.current) return;
    setState({
      events: next.events,
      suggestions: next.suggestions,
      feeds: next.feeds,
      isFreshening: next.is_freshening,
      loading: false,
      error: null,
    });
  }, []);

  const refresh = useCallback(async () => {
    try {
      const data = await planApi.get();
      apply(data);
      // SWR poll: if backend says feeds are freshening, schedule a
      // single follow-up read. We deliberately use a one-shot
      // setTimeout rather than a polling loop — once the freshen
      // resolves, the next /api/plan call returns is_freshening:false
      // and the loop terminates naturally.
      if (data.is_freshening) {
        if (pollTimeoutRef.current !== null) {
          window.clearTimeout(pollTimeoutRef.current);
        }
        pollTimeoutRef.current = window.setTimeout(() => {
          void refresh();
        }, FRESHENING_POLL_MS);
      }
    } catch (caught) {
      if (!mountedRef.current) return;
      setState((prev) => ({
        ...prev,
        loading: false,
        error: (caught as Error).message,
      }));
    }
  }, [apply]);

  // Initial fetch
  useEffect(() => {
    mountedRef.current = true;
    void refresh();
    return () => {
      mountedRef.current = false;
      if (pollTimeoutRef.current !== null) {
        window.clearTimeout(pollTimeoutRef.current);
        pollTimeoutRef.current = null;
      }
    };
  }, [refresh]);

  // Multi-tab + window-focus refresh — match Dashboard's behavior.
  useEffect(() => {
    const onFocus = () => void refresh();
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [refresh]);

  // ---- Mutation actions ----

  const addFeed = useCallback(
    async (input: {
      label: string;
      url: string;
      color?: string | null;
    }): Promise<CalendarFeedCreatedResponse> => {
      const result = await calendarApi.createFeed(input);
      await refresh();
      return result;
    },
    [refresh]
  );

  const removeFeed = useCallback(
    async (id: string) => {
      await calendarApi.deleteFeed(id);
      await refresh();
    },
    [refresh]
  );

  const renameFeed = useCallback(
    async (id: string, label: string) => {
      await calendarApi.renameFeed(id, label);
      await refresh();
    },
    [refresh]
  );

  const syncFeed = useCallback(
    async (id: string): Promise<SyncFeedResponse> => {
      const result = await calendarApi.syncFeed(id);
      await refresh();
      return result;
    },
    [refresh]
  );

  const acceptSuggestion = useCallback(
    async (id: string) => {
      await planApi.accept(id);
      await refresh();
    },
    [refresh]
  );

  const dismissSuggestion = useCallback(
    async (id: string) => {
      // Optimistic: drop from local state immediately so the UI
      // collapses smoothly, then write through. The 5-second-undo
      // toast is mounted by the component; restore() reverses if the
      // user clicks Undo.
      setState((prev) => ({
        ...prev,
        suggestions: prev.suggestions.filter((s) => s.id !== id),
      }));
      await planApi.dismiss(id);
    },
    []
  );

  const restoreSuggestion = useCallback(
    async (id: string) => {
      await planApi.restore(id);
      await refresh();
    },
    [refresh]
  );

  return {
    ...state,
    refresh,
    addFeed,
    removeFeed,
    renameFeed,
    syncFeed,
    acceptSuggestion,
    dismissSuggestion,
    restoreSuggestion,
  };
}
