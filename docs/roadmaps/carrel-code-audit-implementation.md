# Carrel Code Audit Implementation Plan

Source: `Carrel_Code_Audit_and_Perfection_Roadmap.pdf`.

## Execution Rules

- Treat the first verified citation as the activation loop.
- Prefer additive API contracts; keep existing routes compatible.
- Keep metrics local-only and privacy-filtered.
- Do not upload source content, filenames, secrets, or user-identifying payloads to third-party services.
- Verify each shipped slice with focused backend, frontend, type, lint, and build checks.

## Phase 1: Trust Loop And Safety

- Replace placeholder-based Ask focus with a stable focus target.
- Add an Ask route parser/builder for `q`, `auto`, `scope_kind`, `doc_id`, and `subject_name`.
- Hydrate Ask scope before auto-submit.
- Wire or remove native menu commands that previously dead-ended.
- Stream uploads to disk with an allow-list and a 100 MB cap.
- Clean up partial files on oversized, unsupported, extraction, duplicate, and ingestion failures.
- Add typed API timeout errors distinct from backend-offline errors.
- Add a first-run state controller and activation-loop events.

Status: implemented in this slice.

## Phase 2: Architecture Cleanup

- Use `/api/shell/status` for sidebar counts and provider state instead of polling full lists.
- Move calendar background sync onto a lifecycle-managed queue.
- Continue splitting the large API endpoint wrapper by domain while preserving exports.
- Continue splitting `routes/tutor.py` into thin routes and services.
- Standardize backend error envelopes where caller recovery is user-visible.

Status: shell status, calendar queue, and note expansion metadata implemented in this slice; endpoint/tutor splits remain follow-up work.

## Phase 3: Release-Grade Trust

- Move raw calendar feed secrets into Keychain with masked/hash rows in SQLite.
- Add a local API token for mutating frontend-to-backend calls.
- Add a RAG evaluation dashboard for retrieval quality, groundedness, and quote validity.
- Enable stricter TypeScript flags after the current surface is clean.
- Keep production sourcemaps disabled unless `CARREL_DEBUG_SOURCEMAPS=1`.

Status: sourcemap policy implemented in this slice; Keychain, local token, RAG eval, and strict TS flags remain follow-up work.
