-- 0015_calendar_manual_feed_kind.sql
--
-- Phase 2 of the deadline-as-unit-of-work thesis. Until now, deadlines
-- could only enter Carrel via the user's calendar (HTTP feed or local
-- EventKit). That gates the wedge on calendar discipline — students
-- who think "exam Friday" but never put it in iCal got nothing from
-- the coach.
--
-- This migration extends `calendar_feeds.kind` with a `'manual'` value.
-- The companion code in routes/plan.py lazily creates a per-user
-- "Manual deadlines" feed on the first manual deadline insert and
-- writes calendar_events rows into it. The existing detector
-- (services/planning/deadlines.py) picks them up automatically because
-- the keyword regex doesn't care about feed kind.
--
-- The HTTP sync path already short-circuits non-`'url'` feeds in
-- services/calendar/sync_service.py:88, so manual feeds are never
-- touched by network sync. The EventKit reconciler in
-- services/calendar/local_sync.py only deletes events whose feed_id
-- matches the calendar it's reconciling, so manual deadlines survive
-- there too.

-- SQLite cannot ALTER TABLE ... DROP/MODIFY CHECK in place. The
-- migration recreates the table with the looser CHECK and copies the
-- rows over. PRAGMA foreign_keys is implicitly OFF for this DB
-- (foreign_keys.py controls that), so we don't need a guard.

PRAGMA foreign_keys = OFF;

CREATE TABLE calendar_feeds_v15 (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'local',
    label TEXT NOT NULL,
    url TEXT NOT NULL,
    url_hash TEXT NOT NULL,
    color TEXT,
    is_enabled INTEGER NOT NULL DEFAULT 1,
    etag TEXT,
    last_modified TEXT,
    last_synced_at TEXT,
    last_successful_sync_at TEXT,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    last_error TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    keychain_ref TEXT,
    kind TEXT NOT NULL DEFAULT 'url'
        CHECK (kind IN ('url', 'local', 'manual')),
    UNIQUE (user_id, url_hash)
);

INSERT INTO calendar_feeds_v15
SELECT id, user_id, label, url, url_hash, color, is_enabled, etag,
       last_modified, last_synced_at, last_successful_sync_at,
       consecutive_failures, last_error, created_at, updated_at,
       keychain_ref, kind
FROM calendar_feeds;

DROP TABLE calendar_feeds;
ALTER TABLE calendar_feeds_v15 RENAME TO calendar_feeds;

CREATE INDEX IF NOT EXISTS idx_calendar_feeds_kind ON calendar_feeds(kind);

PRAGMA foreign_keys = ON;
