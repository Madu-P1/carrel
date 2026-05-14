import { api } from "@/services/api/client";
import type { components } from "@/services/api/types.gen";
import type { CalendarFeed } from "./calendarApi";

/**
 * Plan endpoints — events + suggestions + feeds for the Plan view.
 *
 * GET /api/plan implements stale-while-revalidate:
 *   - returns local cached data instantly
 *   - kicks background refreshes for any stale feed (no blocking)
 *   - sets `is_freshening: true` so the UI can render a subtle
 *     "syncing" affordance until the next call returns false
 *
 * Suggestion accept/dismiss/restore: dismiss is paired with restore so
 * the frontend can implement the 5-second-undo toast cleanly. Accept
 * adds the suggested time block to the user's plan; restore reverses
 * a dismiss within the undo window.
 */

export interface PlanEvent {
  id: string;
  feed_id: string;
  summary: string;
  start_at: string;
  end_at: string;
  timezone: string | null;
  all_day: boolean;
  location: string | null;
  status: "confirmed" | "cancelled" | "tentative";
}

/**
 * Re-export of the auto-generated StudySuggestionRow schema. Single
 * source of truth: ./script/generate-api-types.sh derives this from
 * api_models.py:StudySuggestionRow on every verify run, so the
 * frontend can never drift from the backend Pydantic Literal again
 * (which used to happen when this was hand-written).
 */
export type PlanSuggestion = components["schemas"]["StudySuggestionRow"];

export interface PlanResponse {
  events: PlanEvent[];
  suggestions: PlanSuggestion[];
  feeds: CalendarFeed[];
  is_freshening: boolean;
}

/** Self-reported stress + energy snapshot. Backend caps each at 1..5
 *  via Pydantic AND the DB CHECK constraint, so out-of-range payloads
 *  surface as a 422 from the API helper. */
export type CheckInRequest = components["schemas"]["CheckInRequest"];
export type CheckInResponse = components["schemas"]["CheckInResponse"];

export const planApi = {
  get: () => api<PlanResponse>("/api/plan"),

  checkIn: (payload: CheckInRequest) =>
    api<CheckInResponse>("/api/plan/check-in", {
      method: "POST",
      body: payload,
    }),

  accept: (suggestionId: string) =>
    api<{ status: string }>(
      `/api/plan/suggestions/${encodeURIComponent(suggestionId)}/accept`,
      { method: "POST", body: {} }
    ),

  dismiss: (suggestionId: string) =>
    api<{ status: string }>(
      `/api/plan/suggestions/${encodeURIComponent(suggestionId)}/dismiss`,
      { method: "POST", body: {} }
    ),

  /** Reverse a recently-dismissed suggestion within the 5-second undo
   *  window. Backend doesn't enforce timing; the frontend toast does. */
  restore: (suggestionId: string) =>
    api<{ status: string }>(
      `/api/plan/suggestions/${encodeURIComponent(suggestionId)}/restore`,
      { method: "POST", body: {} }
    ),

  /** Read-only "best time to insert a study session" advice. Computed
   * by the backend from free blocks + detected deadlines + time-of-day
   * fit. Pass the browser timezone so the fit calculation uses local
   * hours. Returns up to 3 ranked suggestions.
   *
   * NOTE: backend route lands with the planning subsystem in a
   * follow-up PR. Until then this 404s and callers should use
   * Promise.allSettled to fall through to the calendar-only path. */
  insertions: (timezone: string) =>
    api<StudySessionInsertionsResponse>(
      `/api/plan/insertions?tz=${encodeURIComponent(timezone)}`
    ),
};

export interface StudySessionInsertion {
  start_at: string;
  end_at: string;
  duration_minutes: number;
  score: number;                       // 0..1, top normalized to 1.0
  reason_text: string;
  reason_code: "deadline_imminent" | "free_block_overdue_srs" | "free_block";
  deadline_label: string | null;
  deadline_at: string | null;
  source_event_id: string | null;
}

export interface StudySessionInsertionsResponse {
  insertions: StudySessionInsertion[];
  user_timezone: string;
}
