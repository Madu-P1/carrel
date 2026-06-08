-- 0025_document_vaults.sql
--
-- Persist a "vault" (a document folder) even when it holds no documents.
--
-- A vault is just a documents.subject_name: a record's membership in a vault is
-- its subject_name, and the move endpoint already re-files a record by updating
-- that column. The gap this closes is folder-FIRST creation. Until now the set of
-- vaults was derived purely from the distinct subject_names across documents, so
-- a vault could not exist before its first record and vanished when its last
-- record left. The Cachet Vault page lets a user create a named, empty vault and
-- then file records into it, which needs the name to persist on its own.
--
-- Schema choice: a thin registry of names, NOT a foreign-key parent of documents.
-- subject_name stays the single source of truth for membership (no documents
-- column changes, no backfill, the existing move/group queries are untouched).
-- The list of vaults the UI shows is the UNION of distinct documents.subject_name
-- and document_vaults.name, so a vault appears whether it was created empty here
-- or implied by a record filed under it. Deleting a registry row only forgets an
-- empty vault; it never touches documents.
CREATE TABLE IF NOT EXISTS document_vaults (
    name TEXT PRIMARY KEY,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
