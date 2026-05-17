-- 0018_srs_cards_kind_drop_check_and_card_pairs.sql
--
-- PR 5.2 of flashcards-focus (ADR 0003). Two coupled schema moves:
--
--   1. Drop the CHECK (kind IN ('qa', 'cloze')) from srs_cards.kind so
--      'reverse' rows can be inserted. SQLite cannot ALTER ... DROP
--      CONSTRAINT, so we use the canonical 12-step rebuild ONCE.
--      Validation of the kind enum moves entirely to application code
--      (Pydantic Literal on CardCreateRequest plus the allowlist in
--      services/study.py::create_card). Future card kinds add a value
--      to the Python list — no more SQL migrations to widen the enum.
--
--   2. Add a card_pairs(card_a_id, card_b_id) junction table so a
--      reverse-pair card knows its inverse. CHECK (card_a_id <
--      card_b_id) plus the composite PRIMARY KEY guarantees no
--      self-pairs, no duplicate pairs, no asymmetric pairs. ON DELETE
--      CASCADE on both FKs collapses the pair if either card is
--      deleted (the surviving card stays alive; the pair link is gone).
--
-- PRAGMA foreign_keys placement: the PRAGMAs sit OUTSIDE the
-- BEGIN/COMMIT block. db.py::apply_migrations runs each migration via
-- conn.executescript(), which issues an implicit COMMIT before
-- executing — that means a PRAGMA at the top of the script lands
-- outside any open transaction and DOES take effect. A PRAGMA inside
-- the BEGIN block would be a no-op per SQLite's docs (foreign_keys
-- cannot change mid-transaction).
--
-- Inbound FK references that survive the rebuild:
--   - reviewlog.card_id           (NO ACTION, from 0001)
--   - study_plans.card_id         (NO ACTION, from 0001)
--   - anchors.srs_card_id         (ON DELETE SET NULL, from 0008)
-- With foreign_keys=OFF the rename auto-updates these references in
-- sqlite_master (SQLite's documented behavior for the rebuild
-- pattern). foreign_key_check before COMMIT verifies no orphans.

PRAGMA foreign_keys = OFF;

BEGIN TRANSACTION;

CREATE TABLE srs_cards_new (
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
    confidence REAL,
    kind TEXT NOT NULL DEFAULT 'qa'
);

INSERT INTO srs_cards_new (
    id, concept_id, card_type, front, back, state, stability, difficulty,
    elapsed_days, scheduled_days, reps, lapses, due_date, last_review,
    artifact_id, source_snapshot_hash, confidence, kind
)
SELECT
    id, concept_id, card_type, front, back, state, stability, difficulty,
    elapsed_days, scheduled_days, reps, lapses, due_date, last_review,
    artifact_id, source_snapshot_hash, confidence, kind
FROM srs_cards;

DROP TABLE srs_cards;
ALTER TABLE srs_cards_new RENAME TO srs_cards;

-- Recreate the only index that lived on the old table (from 0011).
-- The IF NOT EXISTS in 0011 protected against re-runs; here we must
-- recreate because DROP TABLE took it with it.
CREATE INDEX IF NOT EXISTS idx_srs_cards_due_state
    ON srs_cards (due_date, state);

CREATE TABLE IF NOT EXISTS card_pairs (
    card_a_id TEXT NOT NULL,
    card_b_id TEXT NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (card_a_id, card_b_id),
    CHECK (card_a_id < card_b_id),
    FOREIGN KEY (card_a_id) REFERENCES srs_cards(id) ON DELETE CASCADE,
    FOREIGN KEY (card_b_id) REFERENCES srs_cards(id) ON DELETE CASCADE
);

-- Reverse-direction lookup: "find the pair containing card X" must hit
-- either column. PK already covers (card_a_id, ...); this index covers
-- card_b_id lookups.
CREATE INDEX IF NOT EXISTS idx_card_pairs_b ON card_pairs(card_b_id);

COMMIT;

PRAGMA foreign_keys = ON;
