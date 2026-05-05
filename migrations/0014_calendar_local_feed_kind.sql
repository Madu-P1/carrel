-- 0014_calendar_local_feed_kind.sql
--
-- Phase 1 of native Apple Calendar (EventKit) integration. The macOS
-- shell now reads the user's local calendars via EventKit and POSTs
-- events to the backend; we model each EKCalendar as a `calendar_feeds`
-- row with kind='local' so the existing planning + coach pipelines
-- (events table, suggestions, sync_runs) light up without a parallel
-- code path.
--
-- The synthetic URL for a local feed is `eventkit://local/{calendarIdentifier}`.
-- That stays in `url` so url_hash unique-ness still applies — two macs
-- syncing the same calendar produce the same identifier and dedupe
-- naturally.
--
-- The `kind` column defaults to 'url' so existing rows are correct
-- without a backfill. The CHECK constraint pre-lists the planned
-- values (catches typos before they hit the DB; codex pattern).

ALTER TABLE calendar_feeds ADD COLUMN kind TEXT NOT NULL DEFAULT 'url'
    CHECK (kind IN ('url', 'local'));

-- The supervisor + sync queue check `kind` to skip HTTP fetches for
-- local feeds — they're write-only from the macOS bridge.
CREATE INDEX IF NOT EXISTS idx_calendar_feeds_kind ON calendar_feeds(kind);
