import { api } from "@/services/api/client";

/**
 * Calendar feed endpoints.
 *
 * The `url` field on responses is ALWAYS the masked form
 * (`https://host/***`). The raw URL only appears once on the
 * createFeed response's `raw_url_echo` so the user can copy/verify
 * what they pasted; subsequent listFeeds calls return the masked form.
 */

export interface CalendarFeed {
  id: string;
  label: string;
  url: string; // masked — never raw after the create POST
  color: string | null;
  is_enabled: boolean;
  last_synced_at: string | null;
  last_successful_sync_at: string | null;
  consecutive_failures: number;
  last_error: string | null;
}

export interface CalendarFeedCreatedResponse {
  feed: CalendarFeed;
  raw_url_echo: string;
}

export interface SyncFeedResponse {
  feed: CalendarFeed;
  items_seen: number;
  items_upserted: number;
  items_deleted: number;
  status: "success" | "not_modified" | "error";
  error: string | null;
}

export const calendarApi = {
  listFeeds: () => api<CalendarFeed[]>("/api/calendar/feeds"),

  createFeed: (input: { label: string; url: string; color?: string | null }) =>
    api<CalendarFeedCreatedResponse>("/api/calendar/feeds", {
      method: "POST",
      body: input,
    }),

  deleteFeed: (id: string) =>
    api<{ deleted: boolean }>(`/api/calendar/feeds/${encodeURIComponent(id)}`, {
      method: "DELETE",
    }),

  renameFeed: (id: string, label: string) =>
    api<CalendarFeed>(`/api/calendar/feeds/${encodeURIComponent(id)}`, {
      method: "PATCH",
      body: { label },
    }),

  syncFeed: (id: string) =>
    api<SyncFeedResponse>(`/api/calendar/feeds/${encodeURIComponent(id)}/sync`, {
      method: "POST",
      body: {},
    }),
};
