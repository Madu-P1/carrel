CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    storage_name TEXT,
    subject_name TEXT DEFAULT 'General',
    file_type TEXT NOT NULL,
    upload_date DATETIME DEFAULT CURRENT_TIMESTAMP,
    page_count INTEGER,
    status TEXT DEFAULT 'processing'
);

CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    doc_id TEXT REFERENCES documents(id),
    content TEXT NOT NULL,
    section TEXT,
    page_num INTEGER,
    chunk_index INTEGER,
    token_count INTEGER,
    embedding_id TEXT
);

CREATE TABLE IF NOT EXISTS concepts (
    id TEXT PRIMARY KEY,
    doc_id TEXT REFERENCES documents(id),
    name TEXT NOT NULL,
    description TEXT,
    mastery REAL DEFAULT 0.1,
    last_tested DATETIME,
    source_chunks TEXT
);

CREATE TABLE IF NOT EXISTS concept_edges (
    source_id TEXT REFERENCES concepts(id),
    target_id TEXT REFERENCES concepts(id),
    doc_id TEXT REFERENCES documents(id),
    relationship TEXT NOT NULL,
    weight INTEGER DEFAULT 1,
    PRIMARY KEY (source_id, target_id, relationship)
);

CREATE TABLE IF NOT EXISTS questions (
    id TEXT PRIMARY KEY,
    concept_id TEXT REFERENCES concepts(id),
    type TEXT NOT NULL,
    difficulty REAL,
    question TEXT NOT NULL,
    answer TEXT NOT NULL,
    distractors TEXT,
    explanation TEXT,
    times_shown INTEGER DEFAULT 0,
    times_correct INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS quiz_log (
    id TEXT PRIMARY KEY,
    question_id TEXT REFERENCES questions(id),
    response TEXT,
    correct BOOLEAN,
    time_taken INTEGER,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS srs_cards (
    id TEXT PRIMARY KEY,
    concept_id TEXT REFERENCES concepts(id),
    card_type TEXT,
    front TEXT NOT NULL,
    back TEXT NOT NULL,
    state TEXT DEFAULT 'new',
    stability REAL DEFAULT 1.0,
    difficulty REAL DEFAULT 0.3,
    elapsed_days REAL DEFAULT 0,
    scheduled_days REAL DEFAULT 0,
    reps INTEGER DEFAULT 0,
    lapses INTEGER DEFAULT 0,
    due_date DATE,
    last_review DATETIME
);

CREATE TABLE IF NOT EXISTS dialogue_sessions (
    id TEXT PRIMARY KEY,
    concept_id TEXT REFERENCES concepts(id),
    started_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    messages TEXT,
    misconceptions TEXT,
    final_understanding INTEGER
);

CREATE TABLE IF NOT EXISTS notes (
    id TEXT PRIMARY KEY,
    doc_id TEXT REFERENCES documents(id),
    concept_id TEXT REFERENCES concepts(id),
    title TEXT,
    content TEXT NOT NULL,
    source_snippet TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS study_events (
    id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    doc_id TEXT REFERENCES documents(id),
    concept_id TEXT REFERENCES concepts(id),
    confidence REAL,
    duration_seconds INTEGER,
    payload TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS app_settings (
    key TEXT PRIMARY KEY,
    value TEXT
);
