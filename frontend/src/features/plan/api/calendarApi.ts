import { api } from "@/services/api/client";

/**
 * Calendar feed endpoints.
 *
 * The `url` field on responses is ALWAYS the masked form
 * (`https://host/***`). The createFeed response keeps `raw_url_echo`
 * for compatibility, but it is also masked; raw feed URLs stay in the
 * local secret store only.
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

export interface CalendarIcsUploadResponse {
  feed: CalendarFeed;
  raw_url_echo: string;
  items_seen: number;
  items_upserted: number;
  items_deleted: number;
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

  uploadIcsFile: (input: { label: string; file: File; color?: string | null }) => {
    const form = new FormData();
    form.append("label", input.label);
    if (input.color) form.append("color", input.color);
    form.append("file", input.file);
    return api<CalendarIcsUploadResponse>("/api/calendar/ics-upload", {
      method: "POST",
      body: form,
      timeoutMs: 60_000,
    });
  },

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
