BEGIN TRANSACTION;

ALTER TABLE concepts ADD COLUMN doc_id TEXT REFERENCES documents(id);

UPDATE concepts
SET doc_id = (
    SELECT ch.doc_id
    FROM chunks ch
    WHERE ch.id = json_extract(concepts.source_chunks, '$[0]')
    LIMIT 1
)
WHERE doc_id IS NULL;

COMMIT;
