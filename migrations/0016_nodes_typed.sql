-- 0016_nodes_typed.sql
--
-- Foundation for the Ask-pipeline rebuild (PR 1 of 6). Adds a parallel
-- typed-node ingest target that runs alongside the existing `chunks`
-- pipeline. End-user behavior does not change in this PR — both paths
-- write rows; retrieval still reads from `chunks` until PR 2 flips
-- behind its own flag.
--
-- The three tables here mirror chunks/chunks_fts/chunks_vec from
-- migrations 0001 + 0006 + 0007. The vec0 dimension stays at 384 so
-- the same `BAAI/bge-small-en-v1.5` embedder serves both indexes.
--
-- Triggers on insert/update/delete keep `node_fts` in sync with `nodes`.
-- Without them the FTS index drifts the moment a row is updated or
-- deleted and BM25 hits would point at stale text.

PRAGMA journal_mode = WAL;

-- One row per leaf in the parsed document tree. reading_order is
-- monotonic per doc_id and resolves multi-column PDFs.
CREATE TABLE IF NOT EXISTS nodes (
    id              INTEGER PRIMARY KEY,
    doc_id          TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    node_type       TEXT NOT NULL CHECK (node_type IN (
        'heading', 'body', 'list_item', 'caption',
        'table_cell', 'equation', 'footnote', 'header', 'footer'
    )),
    heading_path    TEXT NOT NULL DEFAULT '',
    page            INTEGER,
    char_start      INTEGER NOT NULL,
    char_end        INTEGER NOT NULL,
    verbatim_text   TEXT NOT NULL,
    parent_block_id INTEGER REFERENCES nodes(id) ON DELETE CASCADE,
    reading_order   INTEGER NOT NULL,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_nodes_doc ON nodes(doc_id);
CREATE INDEX IF NOT EXISTS idx_nodes_type ON nodes(node_type);
CREATE INDEX IF NOT EXISTS idx_nodes_doc_order ON nodes(doc_id, reading_order);

-- Vector index — same float[384] shape as chunks_vec so the existing
-- embedder serves both indexes.
CREATE VIRTUAL TABLE IF NOT EXISTS node_embeddings USING vec0(
    node_id INTEGER PRIMARY KEY,
    embedding float[384]
);

-- BM25 index. Contentless FTS5 mirroring `nodes` via content/content_rowid.
CREATE VIRTUAL TABLE IF NOT EXISTS node_fts USING fts5(
    verbatim_text,
    heading_path,
    node_type UNINDEXED,
    id UNINDEXED,
    doc_id UNINDEXED,
    content='nodes',
    content_rowid='id',
    tokenize='porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS nodes_fts_insert AFTER INSERT ON nodes BEGIN
    INSERT INTO node_fts(rowid, verbatim_text, heading_path, node_type, id, doc_id)
    VALUES (new.id, new.verbatim_text, new.heading_path, new.node_type, new.id, new.doc_id);
END;

CREATE TRIGGER IF NOT EXISTS nodes_fts_delete AFTER DELETE ON nodes BEGIN
    INSERT INTO node_fts(node_fts, rowid, verbatim_text, heading_path, node_type, id, doc_id)
    VALUES ('delete', old.id, old.verbatim_text, old.heading_path, old.node_type, old.id, old.doc_id);
END;

CREATE TRIGGER IF NOT EXISTS nodes_fts_update AFTER UPDATE ON nodes BEGIN
    INSERT INTO node_fts(node_fts, rowid, verbatim_text, heading_path, node_type, id, doc_id)
    VALUES ('delete', old.id, old.verbatim_text, old.heading_path, old.node_type, old.id, old.doc_id);
    INSERT INTO node_fts(rowid, verbatim_text, heading_path, node_type, id, doc_id)
    VALUES (new.id, new.verbatim_text, new.heading_path, new.node_type, new.id, new.doc_id);
END;

INSERT OR IGNORE INTO app_settings (key, value)
VALUES ('node_embeddings_backfill_pending', '0');
