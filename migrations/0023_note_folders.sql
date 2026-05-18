-- 0020_note_folders.sql
--
-- Add user-organizable folders for notes.
--
-- Until now, notes had `doc_id` (which derived a subject through
-- documents.subject_name) and that was the only organization. The
-- global Notes page needs a second axis: user-created folders within
-- a subject so a student can split "Lecture notes", "Exam prep",
-- "Open questions" inside Math without that splitting bleeding into
-- Physics.
--
-- Schema choices:
--
-- 1. Folders belong to a subject_name, not to a documents row. The
--    subject_name on a folder is the source of truth for "what subject
--    is this folder under"; notes assigned to it inherit that subject
--    even if their doc lives under a different subject. This lets the
--    user reclassify a note by moving it.
--
-- 2. notes.folder_id is nullable. A note with no folder still gets a
--    subject via doc_id -> documents.subject_name. A note with no
--    folder AND no doc_id surfaces under "Unfiled" in the UI.
--
-- 3. sort_order is a plain INTEGER. Drag-and-drop reorder is not a
--    v1 feature, but pinning the column now means we don't need a
--    second migration the day we add it.
--
-- 4. Plain ADD COLUMN on notes is safe: SQLite supports it directly
--    and a nullable REFERENCES column with no default doesn't rewrite
--    existing rows.

CREATE TABLE IF NOT EXISTS note_folders (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    subject_name TEXT NOT NULL,
    sort_order INTEGER DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_note_folders_subject
    ON note_folders (subject_name, sort_order, name);

ALTER TABLE notes ADD COLUMN folder_id TEXT REFERENCES note_folders(id);

CREATE INDEX IF NOT EXISTS idx_notes_folder ON notes (folder_id);
