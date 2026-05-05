CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    storage_name TEXT,
    subject_name TEXT DEFAULT 'General',
    file_type TEXT NOT NULL,
    upload_date DATETIME DEFAULT CURRENT_TIMESTAMP,
    page_count INTEGER,
    status TEXT DEFAULT 'processing'
);

CREATE TABLE IF NOT EXISTS library_subjects (
    name TEXT PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_library_subjects_updated
    ON library_subjects (updated_at);

CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    doc_id TEXT REFERENCES documents(id),
    content TEXT NOT NULL,
    section TEXT,
    page_num INTEGER,
    chunk_index INTEGER,
    token_count INTEGER,
    embedding_id TEXT
);

CREATE TABLE IF NOT EXISTS concepts (
    id TEXT PRIMARY KEY,
    doc_id TEXT REFERENCES documents(id),
    name TEXT NOT NULL,
    description TEXT,
    mastery REAL DEFAULT 0.1,
    last_tested DATETIME,
    source_chunks TEXT
);

CREATE TABLE IF NOT EXISTS concept_edges (
    source_id TEXT REFERENCES concepts(id),
    target_id TEXT REFERENCES concepts(id),
    doc_id TEXT REFERENCES documents(id),
    relationship TEXT NOT NULL,
    weight INTEGER DEFAULT 1,
    PRIMARY KEY (source_id, target_id, relationship)
);

CREATE TABLE IF NOT EXISTS questions (
    id TEXT PRIMARY KEY,
    concept_id TEXT REFERENCES concepts(id),
    type TEXT NOT NULL,
    difficulty REAL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    distractors TEXT,
    explanation TEXT,
    times_shown INTEGER DEFAULT 0,
    times_correct INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS quiz_log (
    id TEXT PRIMARY KEY,
    question_id TEXT REFERENCES questions(id),
    response TEXT,
    correct BOOLEAN,
    time_taken INTEGER,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS srs_cards (
    id TEXT PRIMARY KEY,
    concept_id TEXT REFERENCES concepts(id),
    card_type TEXT,
    front TEXT NOT NULL,
    back TEXT NOT NULL,
    state TEXT DEFAULT 'new',
    stability REAL DEFAULT 1.0,
    difficulty REAL DEFAULT 0.3,
    elapsed_days REAL DEFAULT 0,
    scheduled_days REAL DEFAULT 0,
    reps INTEGER DEFAULT 0,
    lapses INTEGER DEFAULT 0,
    due_date DATE,
    last_review DATETIME
);

CREATE TABLE IF NOT EXISTS dialogue_sessions (
    id TEXT PRIMARY KEY,
    concept_id TEXT REFERENCES concepts(id),
    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    messages TEXT,
    misconceptions TEXT,
    final_understanding INTEGER
);

CREATE TABLE IF NOT EXISTS notes (
    id TEXT PRIMARY KEY,
    doc_id TEXT REFERENCES documents(id),
    concept_id TEXT REFERENCES concepts(id),
    title TEXT,
    content TEXT NOT NULL,
    source_snippet TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS study_events (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    doc_id TEXT REFERENCES documents(id),
    concept_id TEXT REFERENCES concepts(id),
    confidence REAL,
    duration_seconds INTEGER,
    payload TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT
);

-- ----------------------------------------------------------------------
-- Calendar + study planning (Phase 1 of the coach feature)
--
-- Single-user app today, but `user_id` columns default to 'local' so the
-- multi-tenant migration path is obvious without pretending today's
-- product is multi-user.
--
-- All timestamps are ISO 8601 UTC strings (TEXT). Display TZ is browser
-- territory; storage is unambiguous.
--
-- URL storage threat model: calendar feed URLs ARE secrets (a leaked
-- Google Calendar "secret address" is read access to the calendar) but
-- are revocable from the source UI in one click. SQLite stores only the
-- masked display URL, url_hash duplicate key, and keychain_ref. Raw URLs
-- live in the local secret store; see services/calendar/secrets.py.
-- ----------------------------------------------------------------------

CREATE TABLE IF NOT EXISTS calendar_feeds (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'local',
    label TEXT NOT NULL,
    url TEXT NOT NULL,                                -- masked display URL only
    url_hash TEXT NOT NULL,                           -- sha256(url) for dedup
    keychain_ref TEXT,                                -- secret-store reference
    color TEXT,                                       -- hex, set on add (not from CATEGORIES v1)
    is_enabled INTEGER NOT NULL DEFAULT 1,
    etag TEXT,                                        -- HTTP cache: If-None-Match
    last_modified TEXT,                               -- HTTP cache: If-Modified-Since
    last_synced_at TEXT,                              -- last attempt
    last_successful_sync_at TEXT,                     -- last 200/304 + parse OK
    consecutive_failures INTEGER NOT NULL DEFAULT 0,  -- exponential backoff signal
    last_error TEXT,                                  -- masked URL only
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
    error TEXT                                        -- masked URL only
);

CREATE TABLE IF NOT EXISTS calendar_events (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'local',
    feed_id TEXT NOT NULL REFERENCES calendar_feeds(id) ON DELETE CASCADE,
    uid TEXT NOT NULL,                                -- iCal UID
    occurrence_key TEXT NOT NULL,                     -- uid + recurrence_id (RFC 5545 dedup)
    master_event_id TEXT REFERENCES calendar_events(id) ON DELETE CASCADE,
    recurrence_id TEXT,                               -- NULL on master + non-recurring
    rrule TEXT,                                       -- only set on master rows
    summary TEXT,
    start_at TEXT NOT NULL,                           -- ISO 8601 UTC
    end_at TEXT NOT NULL,                             -- ISO 8601 UTC
    timezone TEXT,                                    -- source TZID for round-trip fidelity
    all_day INTEGER NOT NULL DEFAULT 0,
    location TEXT,
    categories TEXT,                                  -- comma-separated iCal CATEGORIES (v2 color hint)
    status TEXT NOT NULL DEFAULT 'confirmed' CHECK (status IN ('confirmed', 'cancelled', 'tentative')),
    source_updated_at TEXT,                           -- iCal LAST-MODIFIED
    source_hash TEXT,                                 -- content fingerprint for change detection
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
    -- doc + event references with on-delete-set-null so a deleted source
    -- doesn't leave a dangling FK; the suggestion still renders useful
    -- explainability via reason_text even if its anchor disappeared.
    doc_id TEXT REFERENCES documents(id) ON DELETE SET NULL,
    source_event_id TEXT REFERENCES calendar_events(id) ON DELETE SET NULL,
    -- reason_code is the stable analytics token; reason_text is the
    -- user-facing line. Voice rules from Ship 7 apply (verb-led, sentence,
    -- no AI-flavored phrasing). Whitelist v1 codes; extend as Phase 2's
    -- deadline-aware coach lands.
    reason_code TEXT NOT NULL CHECK (reason_code IN (
        'free_block_overdue_srs',     -- v1 stub
        'deadline_imminent',          -- Phase 2
        'low_recent_review',           -- Phase 2
        'gap_between_classes'         -- Phase 2
    )),
    reason_text TEXT NOT NULL,
    score REAL,
    accepted_at TEXT,
    dismissed_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_study_suggestions_active
    ON study_suggestions (user_id, status, start_at);
