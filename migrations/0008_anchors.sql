-- 0008_anchors.sql
--
-- The Anchor is the atomic unit of learning in Einstein: a piece of evidence
-- tied to a source, with an optional question + optional claim + lifecycle
-- state that can mature into a flashcard. Every highlight, every AI answer
-- citation, every manually-created study object becomes an anchor.
--
-- This migration lands the table + indexes only. No writers yet. Services
-- (highlights, AI citations, card promotion) plug in over the next several
-- releases. Landing the primitive first, alone, is deliberate: the shape of
-- this table will constrain half the product, so it's cheap to ship without
-- dependencies and verify the schema holds up.
--
-- Design notes:
--   - `origin` is a string enum because SQLite lacks native enums; constraint
--     is a CHECK at the column level. Keeps queries simple and extensible.
--   - `promotion_state` is the lifecycle machine. A weak anchor is a
--     highlight or provisional AI citation. saved = user confirmed. carded
--     = promoted to an SRS card (srs_card_id set). mastered / archived are
--     terminal-ish states but still queryable.
--   - `chunk_id` and `srs_card_id` are FKs to existing tables with
--     ON DELETE SET NULL so losing a chunk or a card doesn't orphan anchors.
--     The anchor itself survives; the back-reference is cleared.
--   - `bbox` + text_offset_start/end are ALL nullable. Different anchor
--     origins capture different fidelity: a PDF highlight has bbox, a
--     text-layer anchor has offsets, a manual anchor has neither. The
--     Evidence Inspector's fallback hierarchy (bbox -> offset -> nearest
--     paragraph -> page-level) reads these columns in order.
--   - `user_question` + `claim_text` are nullable because different origins
--     populate them differently. A highlight has neither; an AI answer
--     citation has both; a manually authored anchor might have just a
--     question.
--   - `citations_out` stores the in-flight citation ids for AI-generated
--     anchors so we can render "this anchor was cited in 3 answers" later
--     without a junction table. JSON string for now; graduate to a table
--     when we have evidence of query patterns that need it.

BEGIN TRANSACTION;

CREATE TABLE IF NOT EXISTS anchors (
    id TEXT PRIMARY KEY,

    -- Source binding. document_id is required for v1 (every anchor has a
    -- source). chunk_id is a convenience link when the anchor maps cleanly
    -- to a retrieval chunk.
    document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
    chunk_id TEXT REFERENCES chunks(id) ON DELETE SET NULL,
    page_num INTEGER,

    -- Location fidelity. Readers pick the best available; UI marks
    -- approximate anchors explicitly ("approximate location").
    bbox TEXT,                      -- JSON [x,y,w,h] in PDF points; optional
    text_offset_start INTEGER,      -- char offset in extracted text; optional
    text_offset_end INTEGER,

    -- Content. quote_text is the only required content field: every anchor
    -- has a verbatim span it points to.
    quote_text TEXT NOT NULL,
    user_question TEXT,
    claim_text TEXT,

    -- Lifecycle.
    origin TEXT NOT NULL CHECK (origin IN (
        'highlight',
        'ai_answer_citation',
        'manual',
        'imported'
    )),
    promotion_state TEXT NOT NULL DEFAULT 'weak' CHECK (promotion_state IN (
        'weak',
        'saved',
        'carded',
        'mastered',
        'archived'
    )),

    -- Promotion into the SRS system. null until a user promotes an anchor
    -- into a card. SET NULL on card deletion so the anchor survives but
    -- loses its card back-reference.
    srs_card_id TEXT REFERENCES srs_cards(id) ON DELETE SET NULL,

    -- Optional thread the anchor originated from (for ai_answer_citation
    -- origin). No FK yet because threads aren't a table; this is a free
    -- string id the tutor service assigns. Can be upgraded to a FK when
    -- threads get their own table.
    thread_id TEXT,

    -- AI confidence, 0-1. Used to distinguish high-confidence auto-created
    -- anchors from speculative ones the user should review before saving.
    confidence REAL,

    -- citations_out: JSON array of other-anchor ids this anchor cites. Used
    -- to render "this idea was cited in N answers". JSON string so we don't
    -- need a junction table until query patterns justify it.
    citations_out TEXT DEFAULT '[]',

    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Hot paths:
--   "show me every anchor on this document" -> document_id index
--   "show me anchors I haven't dealt with yet" -> promotion_state index
--   "show me the anchor column for page 12" -> composite (document_id, page_num)
--   "find the anchor that produced this card" -> srs_card_id index
--   "show provenance of an ai-generated anchor" -> thread_id index
CREATE INDEX IF NOT EXISTS idx_anchors_document ON anchors(document_id);
CREATE INDEX IF NOT EXISTS idx_anchors_promotion_state ON anchors(promotion_state);
CREATE INDEX IF NOT EXISTS idx_anchors_document_page ON anchors(document_id, page_num);
CREATE INDEX IF NOT EXISTS idx_anchors_srs_card ON anchors(srs_card_id);
CREATE INDEX IF NOT EXISTS idx_anchors_thread ON anchors(thread_id);
CREATE INDEX IF NOT EXISTS idx_anchors_origin ON anchors(origin);
CREATE INDEX IF NOT EXISTS idx_anchors_created_at ON anchors(created_at);

COMMIT;
