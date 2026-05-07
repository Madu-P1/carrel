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

  /** Read-only "best time to insert a study session" advice. Computed
   * by the backend from free blocks + detected deadlines + time-of-day
   * fit. Pass the browser timezone so the fit calculation uses local
   * hours. Returns up to 3 ranked suggestions. */
  insertions: (timezone: string) =>
    api<StudySessionInsertionsResponse>(
      `/api/plan/insertions?tz=${encodeURIComponent(timezone)}`
    ),

  /** Read-only list of upcoming deadlines within the next 30 days.
   * Combines calendar-event keyword matches (midterm/exam/final/test/
   * quiz/deadline) with the overdue-SRS aggregate. Each item carries a
   * severity (high/normal/low) tied to days_until. */
  deadlines: () => api<DeadlinesResponse>("/api/plan/deadlines"),

  /** Add a deadline directly, without needing it on the calendar.
   * The backend lazy-creates a per-user 'manual' feed and writes the
   * deadline as a calendar_events row inside it; the detector picks it
   * up automatically. `deadline_at` is ISO 8601 in UTC. */
  createManualDeadline: (label: string, deadlineAt: string) =>
    api<{ id: string; status: string }>("/api/plan/deadlines/manual", {
      method: "POST",
      body: { label, deadline_at: deadlineAt },
    }),

  deleteManualDeadline: (eventId: string) =>
    api<{ status: string }>(
      `/api/plan/deadlines/manual/${encodeURIComponent(eventId)}`,
      { method: "DELETE" }
    ),
};

export interface PlanDeadline {
  label: string;
  deadline_at: string;
  days_until: number;
  severity: "high" | "normal" | "low";
  source: "calendar_event" | "srs_overdue";
  event_id: string | null;
  /** Calendar feed kind for event-driven deadlines:
   *    'url'    — HTTP-synced ICS feed
   *    'local'  — macOS EventKit
   *    'manual' — user-added via AddDeadlineDialog; only these can be
   *               removed from inside Carrel.
   * null for aggregate (SRS) deadlines. */
  feed_kind: "url" | "local" | "manual" | null;
}

export interface DeadlinesResponse {
  deadlines: PlanDeadline[];
}

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
