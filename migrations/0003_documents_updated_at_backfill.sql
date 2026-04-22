BEGIN TRANSACTION;

ALTER TABLE documents ADD COLUMN updated_at DATETIME;

UPDATE documents
SET updated_at = COALESCE(updated_at, upload_date, CURRENT_TIMESTAMP)
WHERE updated_at IS NULL;

COMMIT;
