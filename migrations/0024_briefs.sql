-- 0024_briefs.sql
--
-- Cachet PR6 (Shelf persistence, A5). One saved brief per row: the checked
-- draft, its SHA-256 fingerprint, the full verify response + the client-built
-- certification model as JSON, and the human's seal state. Local SQLite,
-- single user, no auth. Additive; the schema is migrations-sourced and is
-- never ALTERed at startup.
--
-- Columns:
--   id            app-generated uuid4 string (note_folders / calendar / jobs style).
--   title         operator-supplied at save time, or derived from the draft's
--                 first line when omitted. VerifyResponse carries no matter
--                 caption / court / brief-type, so the Shelf card identity cannot
--                 be derived from verify data; court / brief_type are deferred.
--   draft         the verified draft text (privileged attorney work product).
--   fingerprint   64-char lowercase-hex SHA-256 of draft_text, captured at save
--                 (== CertificationModel.fingerprint). Enables the "cracked"
--                 comparison when the brief is reopened against a changed draft.
--   response_json the full VerifyResponse payload (verify_result_to_payload),
--                 stored verbatim as TEXT JSON. Opinion bodies are already
--                 stripped upstream, so this is bounded.
--   cert_json     the client-built CertificationModel as TEXT JSON, stored so
--                 the warm list/cover renders without recompute. Nullable: a
--                 brief saved before the human built a cert has none.
--   seal_state    free TEXT; only 'unsealed' | 'sealed' is ever persisted.
--                 'cracked' is DERIVED at render (sealStateFor compares the
--                 stored fingerprint to the live draft) and never written.
--   created_at    UTC timestamp, most-recent-first ordering on the Shelf.
--   updated_at    bumped on rename / reseal.
--
-- No FK: briefs is a standalone top-level entity (it does not reference
-- documents), so it applies cleanly on a migrations-only fresh DB.

CREATE TABLE IF NOT EXISTS briefs (
    id TEXT PRIMARY KEY,
    title TEXT,
    draft TEXT NOT NULL,
    fingerprint TEXT NOT NULL,
    response_json TEXT NOT NULL,
    cert_json TEXT,
    seal_state TEXT NOT NULL DEFAULT 'unsealed',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Shelf list ordering: most-recent first.
CREATE INDEX IF NOT EXISTS idx_briefs_created ON briefs (created_at DESC);

-- "Have I already saved this exact draft?" dedupe + cracked lookups.
CREATE INDEX IF NOT EXISTS idx_briefs_fingerprint ON briefs (fingerprint);
