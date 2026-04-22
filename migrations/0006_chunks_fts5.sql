PRAGMA journal_mode = WAL;

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(
    content,
    section,
    id UNINDEXED,
    doc_id UNINDEXED,
    content='chunks',
    content_rowid='rowid',
    tokenize='porter unicode61'
);

CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, content, section, id, doc_id)
    VALUES (NEW.rowid, NEW.content, NEW.section, NEW.id, NEW.doc_id);
END;

CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, content, section, id, doc_id)
    VALUES ('delete', OLD.rowid, OLD.content, OLD.section, OLD.id, OLD.doc_id);
END;

CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
    INSERT INTO chunks_fts(chunks_fts, rowid, content, section, id, doc_id)
    VALUES ('delete', OLD.rowid, OLD.content, OLD.section, OLD.id, OLD.doc_id);
    INSERT INTO chunks_fts(rowid, content, section, id, doc_id)
    VALUES (NEW.rowid, NEW.content, NEW.section, NEW.id, NEW.doc_id);
END;

INSERT INTO chunks_fts(chunks_fts) VALUES('rebuild');
