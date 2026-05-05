import { useEffect, useMemo, useState } from "preact/hooks";

import { useQuery } from "@/lib/query";
import { API_BASE } from "@/services/api/client";
import { planApi } from "@/features/plan/api/planApi";
import type { StudySessionInsertionsResponse } from "@/features/plan/api/planApi";

/**
 * Live "best time to insert a study session" data + auto-refresh on
 * calendar changes.
 *
 * The hook does two things:
 *
 *   1. Fetches `/api/plan/insertions?tz=<browser-tz>` once on mount
 *      and exposes the result via signal-based state.
 *
 *   2. Subscribes to `GET /api/plan/events/stream` (Server-Sent
 *      Events). Whenever the backend emits a `calendar-changed`
 *      event — which happens every time the macOS shell POSTs new
 *      calendar data via EventKit — the hook refetches insertions.
 *
 * Result: the user moves a meeting in Calendar.app, EventKit fires
 * EKEventStoreChanged on the macOS side, the bridge POSTs the new
 * events, the backend logs a `local_calendar_synced` study event,
 * the SSE stream notifies the dashboard, this hook refetches, and
 * the user sees fresh advice within ~1-2 seconds — no manual
 * refresh, no React Query polling.
 *
 * Falls back gracefully when EventSource isn't available (older
 * environments / SSR): the initial fetch still works, but live
 * updates require a manual reload.
 */
export function useStudyInsertions() {
  // Browser timezone — recomputed once per mount. Time zone changes
  // mid-session (the user crossed a time zone boundary on a flight)
  // are rare enough not to optimize for; a manual refresh suffices.
  const timezone = useMemo(
    () => Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC",
    []
  );

  const fetcher = useMemo(
    () => () => planApi.insertions(timezone),
    [timezone]
  );

  const query = useQuery<StudySessionInsertionsResponse>(fetcher);

  // SSE-driven live refresh. Connection state surfaced for the UI
  // so we can show a "live" / "reconnecting" pill if useful.
  const [streamState, setStreamState] = useState<
    "connecting" | "open" | "closed"
  >("connecting");

  useEffect(() => {
    if (typeof EventSource === "undefined") {
      setStreamState("closed");
      return;
    }
    const url = `${API_BASE}/api/plan/events/stream`;
    const source = new EventSource(url);

    source.addEventListener("hello", () => {
      setStreamState("open");
    });

    source.addEventListener("calendar-changed", () => {
      // The event payload itself is small + uninteresting (just a
      // timestamp); the data we actually want is fresh insertions.
      void query.refetch();
    });

    source.onerror = () => {
      // EventSource auto-reconnects with backoff; just surface the
      // state for the UI. Don't dispose — that prevents reconnect.
      setStreamState("closed");
    };

    return () => {
      source.close();
      setStreamState("closed");
    };
  }, [query]);

  return {
    insertions: query.data.value?.insertions ?? [],
    timezone: query.data.value?.user_timezone ?? timezone,
    loading: query.loading.value,
    error: query.error.value,
    streamState,
    refetch: query.refetch,
  };
}
