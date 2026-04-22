BEGIN TRANSACTION;

ALTER TABLE concept_edges ADD COLUMN doc_id TEXT REFERENCES documents(id);

UPDATE concept_edges
SET doc_id = (
    SELECT c.doc_id
    FROM concepts c
    WHERE c.id = concept_edges.source_id
    LIMIT 1
)
WHERE doc_id IS NULL;

COMMIT;
