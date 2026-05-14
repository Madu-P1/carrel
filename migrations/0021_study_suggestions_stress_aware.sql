-- 0021_study_suggestions_stress_aware.sql
--
-- Coach Phase 2.B rule: add 'stress_aware_duration' to the
-- study_suggestions.reason_code CHECK enum. This rule senses recent
-- high stress from session_check_ins (migration 0020), reasons that a
-- long block is the wrong mode right now, and acts by emitting a
-- 25-min Pomodoro review block instead of the routine 60-min block.
--
-- Same SQLite rebuild pattern as migration 0019: CHECK constraints
-- cannot be ALTERed in place, so we copy the table with the extended
-- enum and rename. Wrapped in BEGIN/COMMIT for atomicity so a partial
-- failure leaves the prior state intact.

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
        'rebalance_on_miss',
        'stress_aware_duration'
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
