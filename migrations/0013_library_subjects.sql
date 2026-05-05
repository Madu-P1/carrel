-- 0013_library_subjects.sql
--
-- Library subjects are user-created folders for organizing sources. Older
-- builds inferred subjects only from documents.subject_name, which meant a
-- subject could not exist until after a file had already been imported into
-- it. This table makes the folder explicit while preserving the existing
-- document-level subject field.

BEGIN TRANSACTION;

CREATE TABLE IF NOT EXISTS library_subjects (
    name TEXT PRIMARY KEY,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO library_subjects (name)
SELECT DISTINCT COALESCE(NULLIF(TRIM(subject_name), ''), 'General')
FROM documents;

CREATE INDEX IF NOT EXISTS idx_library_subjects_updated
    ON library_subjects (updated_at);

COMMIT;
