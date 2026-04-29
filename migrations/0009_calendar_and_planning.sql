-- 0009_calendar_and_planning.sql
--
-- Phase 1 of the study-coach feature: calendar feed sync + a stub
-- coach that emits one suggestion type ("free block + overdue SRS").
--
-- Design notes (paired with the canonical block in schema.sql):
--   - Single-user app today; `user_id` columns default to 'local' so
--     the multi-tenant migration path is one ALTER away rather than
--     a re-architecture.
--   - All timestamps are ISO 8601 UTC TEXT (e.g. "2026-04-29T10:25:55Z").
--     Display TZ is the browser's job.
--   - Feed URL storage is plaintext-at-rest with a strict redaction
--     discipline at every other boundary (logs, error fields, GET
--     responses). See services/calendar/validators.py::mask_url. v2
--     work alongside Gmail OAuth tokens swaps to macOS Keychain.
--   - Recurrence handling: the parser expands a 90-day window per
--     sync and stores one row per occurrence keyed on
--     (uid, recurrence_id, start_at) so EXDATE removals + RECURRENCE-ID
--     overrides upsert into the right row.
--   - reason_code on study_suggestions is an enum (CHECK constraint)
--     pre-listing all four planned codes — Phase 1 only emits one,
--     Phase 2 plug-in rules emit the others. The constraint catches
--     typos before they hit the DB.

CREATE TABLE IF NOT EXISTS calendar_feeds (
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
    UNIQUE (user_id, url_hash)
);

CREATE TABLE IF NOT EXISTS calendar_sync_runs (
    id TEXT PRIMARY KEY,
    feed_id TEXT NOT NULL REFERENCES calendar_feeds(id) ON DELETE CASCADE,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    finished_at TEXT,
    status TEXT NOT NULL CHECK (status IN ('running', 'success', 'error', 'not_modified')),
    http_status INTEGER,
    items_seen INTEGER NOT NULL DEFAULT 0,
    items_upserted INTEGER NOT NULL DEFAULT 0,
    items_deleted INTEGER NOT NULL DEFAULT 0,
    error TEXT
);

CREATE TABLE IF NOT EXISTS calendar_events (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'local',
    feed_id TEXT NOT NULL REFERENCES calendar_feeds(id) ON DELETE CASCADE,
    uid TEXT NOT NULL,
    occurrence_key TEXT NOT NULL,
    master_event_id TEXT REFERENCES calendar_events(id) ON DELETE CASCADE,
    recurrence_id TEXT,
    rrule TEXT,
    summary TEXT,
    start_at TEXT NOT NULL,
    end_at TEXT NOT NULL,
    timezone TEXT,
    all_day INTEGER NOT NULL DEFAULT 0,
    location TEXT,
    categories TEXT,
    status TEXT NOT NULL DEFAULT 'confirmed' CHECK (status IN ('confirmed', 'cancelled', 'tentative')),
    source_updated_at TEXT,
    source_hash TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    UNIQUE (feed_id, occurrence_key)
);

CREATE INDEX IF NOT EXISTS idx_calendar_events_window
    ON calendar_events (user_id, start_at, end_at);

CREATE TABLE IF NOT EXISTS study_suggestions (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'local',
    kind TEXT NOT NULL CHECK (kind IN ('study_block', 'review_block', 'catchup')),
    status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'accepted', 'dismissed', 'expired')),
    start_at TEXT NOT NULL,
    end_at TEXT NOT NULL,
    due_at TEXT,
    doc_id TEXT REFERENCES documents(id) ON DELETE SET NULL,
    source_event_id TEXT REFERENCES calendar_events(id) ON DELETE SET NULL,
    reason_code TEXT NOT NULL CHECK (reason_code IN (
        'free_block_overdue_srs',
        'deadline_imminent',
        'low_recent_review',
        'gap_between_classes'
    )),
    reason_text TEXT NOT NULL,
    score REAL,
    accepted_at TEXT,
    dismissed_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_study_suggestions_active
    ON study_suggestions (user_id, status, start_at);
