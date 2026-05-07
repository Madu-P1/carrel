import { useEffect } from "preact/hooks";
import { signal } from "@preact/signals";

import { planApi, type PlanDeadline } from "../api/planApi";

/**
 * Shared deadline source for the Plan view.
 *
 * Hosts a module-level signal (`deadlinesSignal`) so both the
 * DeadlineRail and the WeekTimeGrid subscribe to the same data
 * without duplicate fetches. Self-refreshes every 60 seconds; callers
 * can force a refetch (e.g., after the user adds a manual deadline)
 * via the returned `refresh` callback.
 *
 * Implemented as a hook rather than direct signal access so the
 * fetch lifecycle is clearly bounded — only one mounted consumer
 * needs to drive the timer; multiple consumers won't double-fetch
 * because of the `lastFetchTs` throttle.
 */

export const planDeadlinesSignal = signal<PlanDeadline[]>([]);
let lastFetchTs = 0;
const FETCH_TTL_MS = 60_000;

async function fetchPlanDeadlines(force = false): Promise<void> {
  const now = Date.now();
  if (!force && now - lastFetchTs < FETCH_TTL_MS) return;
  lastFetchTs = now;
  try {
    const response = await planApi.deadlines();
    planDeadlinesSignal.value = response.deadlines;
  } catch {
    // Silent fail — the rail collapses, the grid simply renders no
    // markers. The next /api/plan poll triggers another retry.
    planDeadlinesSignal.value = [];
  }
}

export function usePlanDeadlines() {
  useEffect(() => {
    void fetchPlanDeadlines();
    const id = setInterval(() => void fetchPlanDeadlines(), FETCH_TTL_MS);
    return () => clearInterval(id);
  }, []);

  return {
    deadlines: planDeadlinesSignal.value,
    refresh: () => fetchPlanDeadlines(true),
  };
}
