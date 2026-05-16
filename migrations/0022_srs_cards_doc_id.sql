-- 0019_srs_cards_doc_id.sql
--
-- Add a direct document linkage to srs_cards.
--
-- Until now a card's source document was derived only through its
-- concept: srs_cards.concept_id -> concepts.doc_id -> documents.id.
-- Manually-authored cards created from the Reader have no concept, so
-- they had no way to remember which PDF they came from.
--
-- This adds an optional direct doc_id. The card-read queries in
-- services/study.py COALESCE it with the concept-derived doc_id, so
-- existing concept-linked cards are completely unaffected and Reader
-- cards now resolve their document, document_name, and subject.
--
-- Plain ADD COLUMN, no 12-step rebuild: SQLite supports ALTER TABLE
-- ADD COLUMN directly, and a nullable column with no default (and a
-- NULL-defaulting REFERENCES clause) is the cheap, safe path.

ALTER TABLE srs_cards ADD COLUMN doc_id TEXT REFERENCES documents(id);
