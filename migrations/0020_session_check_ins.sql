-- 0020_session_check_ins.sql
--
-- Coach Phase 2.B foundation: persist self-reported stress + energy
-- snapshots from the user. First new signal source after migration 0019
-- introduced the multi-signal rule architecture; the rule that consumes
-- this table (_rule_stress_aware_duration) lands in a follow-up commit.
--
-- Scoping:
--   - One row per check-in. User picks stress 1..5 and energy 1..5.
--   - No 'note' or 'suggestion_id' columns yet. Both are easy to add
--     later via ALTER TABLE ADD COLUMN since they're nullable additions
--     and don't change CHECK constraints. Ship minimum.
--   - CHECK constraints on stress/energy enforce the 1..5 contract at
--     the DB so a misconfigured client can't poison the rule's math.

CREATE TABLE IF NOT EXISTS session_check_ins (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL DEFAULT 'local',
    stress_level INTEGER NOT NULL CHECK (stress_level BETWEEN 1 AND 5),
    energy_level INTEGER NOT NULL CHECK (energy_level BETWEEN 1 AND 5),
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

-- "Recent check-ins for this user" is the only query shape today
-- (rule reads the last 24h). Cover it with a single composite index.
CREATE INDEX IF NOT EXISTS idx_session_check_ins_recent
    ON session_check_ins (user_id, created_at DESC);
