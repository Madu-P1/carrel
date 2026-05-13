-- 0017_srs_cards_kind.sql
--
-- PR 5.1 of flashcards-focus (ADR 0002). Adds a typed render-mode
-- discriminator to srs_cards. Mirrors the validated precedent in
-- 0014_calendar_local_feed_kind.sql: default + CHECK + no backfill.
--
-- Why `kind` and not `card_type` (already on the table since the
-- initial schema): card_type is descriptive provenance ('custom',
-- 'anchor', 'ai-draft') used for filtering in the manage view and
-- for AI-draft routing. It is free-text, has no CHECK, and changing
-- its semantics would touch every existing row. A typed `kind`
-- column keeps render-mode and provenance on separate axes. The
-- reconciliation cleanup is a follow-up PR (see ADR 0002).
--
-- Why the CHECK pre-lists only 'qa' and 'cloze' for now: 'reverse'
-- is the PR 5.2 value but adding it speculatively here would make
-- this migration a lie. The PR 5.2 migration will rebuild the table
-- to widen the enum, per the ADR's accepted-debt list.
--
-- Existing rows read kind='qa' after this migration — the SRS
-- back-compat path for every shipped card.

BEGIN TRANSACTION;

ALTER TABLE srs_cards ADD COLUMN kind TEXT NOT NULL DEFAULT 'qa'
    CHECK (kind IN ('qa', 'cloze'));

-- Most queries filter on due_date + state; kind is a render-time
-- discriminator and rarely the primary WHERE clause. No index added
-- here — revisit if list_cards/Manage view filters by kind become
-- common enough to dominate query plans.

COMMIT;
