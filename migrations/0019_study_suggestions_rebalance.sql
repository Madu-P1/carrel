-- 0019_study_suggestions_rebalance.sql
--
-- Coach Phase 2, first holistic loop: add 'rebalance_on_miss' to the
-- study_suggestions.reason_code CHECK enum. This rule senses the user
-- falling behind on overdue SRS, reasons about available capacity in
-- the next 24h, and acts by surfacing an urgent catchup block longer
-- than the routine free_block_overdue_srs suggestion.
--
-- SQLite limitation: CHECK constraints cannot be ALTERed in place.
-- Rebuild pattern: create new table with the extended CHECK, copy
-- existing rows, drop the old table, rename the new one, recreate the
-- index. Wrapped in BEGIN/COMMIT so a partial failure leaves the prior
-- table intact rather than a half-migrated schema.
--
-- Inbound FK references: study_suggestions is currently a leaf table
-- (no other table FK-references it). If a future migration adds an
-- inbound FK, this rebuild pattern needs PRAGMA foreign_keys = OFF
-- outside the BEGIN/COMMIT (mirrors migration 0018's pattern for
-- srs_cards). Not needed today.

BEGIN TRANSACTION;

DROP TABLE IF EXISTS study_suggestions_new;

CREATE TABLE study_suggestions_new (
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
        'gap_between_classes',
        'rebalance_on_miss'
    )),
    reason_text TEXT NOT NULL,
    score REAL,
    accepted_at TEXT,
    dismissed_at TEXT,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO study_suggestions_new
SELECT id, user_id, kind, status, start_at, end_at, due_at,
       doc_id, source_event_id, reason_code, reason_text, score,
       accepted_at, dismissed_at, created_at
FROM study_suggestions;

DROP TABLE study_suggestions;
ALTER TABLE study_suggestions_new RENAME TO study_suggestions;

CREATE INDEX IF NOT EXISTS idx_study_suggestions_active
    ON study_suggestions (user_id, status, start_at);

COMMIT;
