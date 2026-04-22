CREATE VIRTUAL TABLE IF NOT EXISTS chunks_vec USING vec0(
    chunk_id INTEGER PRIMARY KEY,
    embedding float[384]
);

INSERT OR IGNORE INTO app_settings (key, value)
VALUES ('chunks_vec_backfill_pending', '1');
