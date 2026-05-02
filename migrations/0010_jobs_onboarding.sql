-- 0010_jobs_onboarding.sql
--
-- Public beta product-loop infrastructure:
--   - ingestion_jobs: durable import visibility for the Jobs Tray
--   - job_events: append-only-ish UI event stream for polling/SSE
--   - onboarding_state: small local flags such as demo-library seed status

BEGIN TRANSACTION;

CREATE TABLE IF NOT EXISTS ingestion_jobs (
    id TEXT PRIMARY KEY,
    kind TEXT NOT NULL DEFAULT 'document_import' CHECK (kind IN ('document_import', 'demo_import')),
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'ready', 'partial', 'failed', 'cancelled')),
    stage TEXT NOT NULL CHECK (stage IN (
        'importing',
        'extracting_text',
        'ocr_fallback',
        'indexing',
        'generating_cards',
        'ready'
    )),
    filename TEXT NOT NULL,
    subject_name TEXT,
    temp_storage_name TEXT,
    document_id TEXT REFERENCES documents(id) ON DELETE SET NULL,
    error TEXT,
    progress REAL NOT NULL DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    started_at TEXT,
    finished_at TEXT
);

CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_status
    ON ingestion_jobs (status, created_at);

CREATE INDEX IF NOT EXISTS idx_ingestion_jobs_document
    ON ingestion_jobs (document_id);

CREATE TABLE IF NOT EXISTS job_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    job_id TEXT NOT NULL REFERENCES ingestion_jobs(id) ON DELETE CASCADE,
    event_type TEXT NOT NULL,
    status TEXT NOT NULL,
    stage TEXT NOT NULL,
    message TEXT,
    payload TEXT DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_job_events_job
    ON job_events (job_id, id);

CREATE TABLE IF NOT EXISTS onboarding_state (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

COMMIT;
