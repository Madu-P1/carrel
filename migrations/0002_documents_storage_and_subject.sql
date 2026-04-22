BEGIN TRANSACTION;

ALTER TABLE documents ADD COLUMN storage_name TEXT;
ALTER TABLE documents ADD COLUMN subject_name TEXT DEFAULT 'General';

UPDATE documents
SET subject_name = 'General'
WHERE subject_name IS NULL OR TRIM(subject_name) = '';

COMMIT;
