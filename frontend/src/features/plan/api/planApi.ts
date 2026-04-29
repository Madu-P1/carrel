import { api } from "@/services/api/client";
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

export interface PlanSuggestion {
  id: string;
  kind: "study_block" | "review_block" | "catchup";
  status: "pending" | "accepted" | "dismissed" | "expired";
  start_at: string;
  end_at: string;
  due_at: string | null;
  reason_code:
    | "free_block_overdue_srs"
    | "deadline_imminent"
    | "low_recent_review"
    | "gap_between_classes";
  reason_text: string;
  score: number | null;
}

export interface PlanResponse {
  events: PlanEvent[];
  suggestions: PlanSuggestion[];
  feeds: CalendarFeed[];
  is_freshening: boolean;
}

export const planApi = {
  get: () => api<PlanResponse>("/api/plan"),

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
};
