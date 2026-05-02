-- 0011_usage_events.sql
--
-- Local-only product metrics:
--   - usage_events stores coarse, privacy-safe interaction events
--   - supporting indexes cover local debugging and dashboard queries
--   - targeted app indexes support due cards, library filters, concepts,
--     jobs, and page-aware reader/source lookups

BEGIN TRANSACTION;

CREATE TABLE IF NOT EXISTS usage_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    event_name TEXT NOT NULL,
    surface TEXT,
    properties TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_usage_events_name_created
    ON usage_events (event_name, created_at);

CREATE INDEX IF NOT EXISTS idx_usage_events_created
    ON usage_events (created_at);

CREATE INDEX IF NOT EXISTS idx_srs_cards_due_state
    ON srs_cards (due_date, state);

CREATE INDEX IF NOT EXISTS idx_documents_subject_status
    ON documents (subject_name, status, updated_at);

CREATE INDEX IF NOT EXISTS idx_concepts_canonical_doc
    ON concepts (canonical_name, doc_id);

CREATE INDEX IF NOT EXISTS idx_chunks_doc_page
    ON chunks (doc_id, page_num, chunk_index);

CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_updated
    ON ingestion_jobs (status, updated_at);

COMMIT;
