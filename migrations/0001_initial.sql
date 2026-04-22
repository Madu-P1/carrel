BEGIN TRANSACTION;

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    file_type TEXT NOT NULL,
    upload_date DATETIME DEFAULT CURRENT_TIMESTAMP,
    page_count INTEGER,
    status TEXT DEFAULT 'processing',
    source_kind TEXT DEFAULT 'uploaded_file',
    source_hash TEXT,
    source_version INTEGER DEFAULT 1,
    parser_status TEXT DEFAULT 'ready',
    parser_diagnostics TEXT,
    duplicate_of TEXT REFERENCES documents(id),
    extracted_at DATETIME
);

CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    doc_id TEXT REFERENCES documents(id),
    content TEXT NOT NULL,
    section TEXT,
    page_num INTEGER,
    chunk_index INTEGER,
    token_count INTEGER,
    embedding_id TEXT,
    chunk_hash TEXT,
    source_version INTEGER DEFAULT 1,
    provenance_json TEXT,
    embedding_status TEXT DEFAULT 'pending'
);

CREATE TABLE IF NOT EXISTS concepts (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    description TEXT,
    mastery REAL DEFAULT 0.1,
    last_tested DATETIME,
    source_chunks TEXT,
    canonical_name TEXT,
    concept_type TEXT DEFAULT 'core',
    source_count INTEGER DEFAULT 0,
    misconception_count INTEGER DEFAULT 0,
    open_question_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS concept_edges (
    source_id TEXT REFERENCES concepts(id),
    target_id TEXT REFERENCES concepts(id),
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
    times_correct INTEGER DEFAULT 0,
    artifact_id TEXT,
    source_snapshot_hash TEXT,
    confidence REAL
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
    last_review DATETIME,
    artifact_id TEXT,
    source_snapshot_hash TEXT,
    confidence REAL
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
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    note_type TEXT DEFAULT 'saved_insight',
    goal_id TEXT,
    session_id TEXT,
    provenance_json TEXT
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

CREATE TABLE IF NOT EXISTS goals (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    description TEXT,
    status TEXT DEFAULT 'active',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS claims (
    id TEXT PRIMARY KEY,
    concept_id TEXT NOT NULL REFERENCES concepts(id),
    source_chunk_id TEXT REFERENCES chunks(id),
    claim_text TEXT NOT NULL,
    claim_type TEXT DEFAULT 'fact',
    confidence REAL DEFAULT 0.5,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS concept_examples (
    id TEXT PRIMARY KEY,
    concept_id TEXT NOT NULL REFERENCES concepts(id),
    source_chunk_id TEXT REFERENCES chunks(id),
    example_text TEXT NOT NULL,
    example_type TEXT DEFAULT 'worked_example',
    confidence REAL DEFAULT 0.5,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS misconceptions (
    id TEXT PRIMARY KEY,
    concept_id TEXT NOT NULL REFERENCES concepts(id),
    source_chunk_id TEXT REFERENCES chunks(id),
    label TEXT NOT NULL,
    description TEXT NOT NULL,
    repair_strategy TEXT,
    confidence REAL DEFAULT 0.5,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS evidence_references (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES documents(id),
    chunk_id TEXT REFERENCES chunks(id),
    concept_id TEXT REFERENCES concepts(id),
    anchor_text TEXT NOT NULL,
    anchor_start INTEGER,
    anchor_end INTEGER,
    page_num INTEGER,
    section_label TEXT,
    contradiction_group TEXT,
    confidence REAL DEFAULT 0.5,
    snapshot_hash TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tutor_exchanges (
    id TEXT PRIMARY KEY,
    session_id TEXT REFERENCES sessions(id),
    goal_id TEXT REFERENCES goals(id),
    source_scope TEXT,
    concept_scope TEXT,
    mode TEXT DEFAULT 'tutor',
    depth TEXT DEFAULT 'standard',
    evidence_strictness TEXT DEFAULT 'normal',
    question TEXT NOT NULL,
    answer TEXT,
    classification TEXT,
    learner_confidence REAL,
    model_confidence REAL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tutor_exchange_evidence (
    exchange_id TEXT NOT NULL REFERENCES tutor_exchanges(id),
    evidence_reference_id TEXT NOT NULL REFERENCES evidence_references(id),
    PRIMARY KEY (exchange_id, evidence_reference_id)
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    goal_id TEXT REFERENCES goals(id),
    objective TEXT NOT NULL,
    source_scope TEXT,
    concept_scope TEXT,
    difficulty_target TEXT DEFAULT 'standard',
    duration_minutes INTEGER DEFAULT 20,
    mode TEXT DEFAULT 'focus_sprint',
    status TEXT DEFAULT 'planned',
    interruptions TEXT,
    mastery_delta REAL DEFAULT 0,
    unresolved_items TEXT,
    suggested_next_session TEXT,
    started_at DATETIME,
    completed_at DATETIME,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS session_artifacts (
    session_id TEXT NOT NULL REFERENCES sessions(id),
    artifact_id TEXT NOT NULL REFERENCES artifacts(id),
    PRIMARY KEY (session_id, artifact_id)
);

CREATE TABLE IF NOT EXISTS mastery_states (
    id TEXT PRIMARY KEY,
    concept_id TEXT NOT NULL REFERENCES concepts(id),
    goal_id TEXT REFERENCES goals(id),
    session_id TEXT REFERENCES sessions(id),
    recall_score REAL DEFAULT 0.1,
    transfer_score REAL DEFAULT 0.1,
    misconception_risk REAL DEFAULT 0.0,
    confidence_alignment REAL DEFAULT 0.0,
    last_evidence_quality REAL DEFAULT 0.0,
    next_due_at DATETIME,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS review_events (
    id TEXT PRIMARY KEY,
    mastery_state_id TEXT REFERENCES mastery_states(id),
    card_id TEXT REFERENCES srs_cards(id),
    question_id TEXT REFERENCES questions(id),
    outcome TEXT NOT NULL,
    classification TEXT,
    confidence REAL,
    duration_seconds INTEGER,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS artifacts (
    id TEXT PRIMARY KEY,
    artifact_kind TEXT NOT NULL,
    parent_artifact_id TEXT REFERENCES artifacts(id),
    goal_id TEXT REFERENCES goals(id),
    session_id TEXT REFERENCES sessions(id),
    source_scope TEXT,
    concept_scope TEXT,
    audience TEXT,
    difficulty TEXT,
    depth TEXT,
    style TEXT,
    output_length TEXT,
    evidence_strictness TEXT DEFAULT 'normal',
    prompt_text TEXT,
    output_markdown TEXT,
    output_json TEXT,
    source_snapshot_hash TEXT,
    version INTEGER DEFAULT 1,
    status TEXT DEFAULT 'draft',
    stale BOOLEAN DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS artifact_evidence (
    artifact_id TEXT NOT NULL REFERENCES artifacts(id),
    evidence_reference_id TEXT NOT NULL REFERENCES evidence_references(id),
    PRIMARY KEY (artifact_id, evidence_reference_id)
);

CREATE TABLE IF NOT EXISTS artifact_exports (
    id TEXT PRIMARY KEY,
    artifact_id TEXT REFERENCES artifacts(id),
    export_format TEXT NOT NULL,
    export_path TEXT,
    status TEXT DEFAULT 'ready',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS flashcard_evidence (
    card_id TEXT NOT NULL REFERENCES srs_cards(id),
    evidence_reference_id TEXT NOT NULL REFERENCES evidence_references(id),
    PRIMARY KEY (card_id, evidence_reference_id)
);

CREATE TABLE IF NOT EXISTS quiz_evidence (
    question_id TEXT NOT NULL REFERENCES questions(id),
    evidence_reference_id TEXT NOT NULL REFERENCES evidence_references(id),
    PRIMARY KEY (question_id, evidence_reference_id)
);

CREATE TABLE IF NOT EXISTS note_evidence (
    note_id TEXT NOT NULL REFERENCES notes(id),
    evidence_reference_id TEXT NOT NULL REFERENCES evidence_references(id),
    PRIMARY KEY (note_id, evidence_reference_id)
);

CREATE TABLE IF NOT EXISTS stale_dependencies (
    id TEXT PRIMARY KEY,
    source_id TEXT NOT NULL REFERENCES documents(id),
    dependent_kind TEXT NOT NULL,
    dependent_id TEXT NOT NULL,
    source_snapshot_hash TEXT NOT NULL,
    current_snapshot_hash TEXT,
    status TEXT DEFAULT 'fresh',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_documents_source_hash ON documents(source_hash);
CREATE INDEX IF NOT EXISTS idx_chunks_doc_version ON chunks(doc_id, source_version);
CREATE INDEX IF NOT EXISTS idx_claims_concept_id ON claims(concept_id);
CREATE INDEX IF NOT EXISTS idx_examples_concept_id ON concept_examples(concept_id);
CREATE INDEX IF NOT EXISTS idx_misconceptions_concept_id ON misconceptions(concept_id);
CREATE INDEX IF NOT EXISTS idx_evidence_source_id ON evidence_references(source_id);
CREATE INDEX IF NOT EXISTS idx_tutor_exchanges_session_id ON tutor_exchanges(session_id);
CREATE INDEX IF NOT EXISTS idx_mastery_concept_goal ON mastery_states(concept_id, goal_id);
CREATE INDEX IF NOT EXISTS idx_artifacts_status ON artifacts(status, stale);
CREATE INDEX IF NOT EXISTS idx_stale_dependencies_source ON stale_dependencies(source_id, status);

COMMIT;
