# Einstein Tutor Handoff

## What this app does

Einstein Tutor is a local-first adaptive study workspace built as a single FastAPI app with a vanilla HTML/CSS/JS frontend.

Current product surface:
- Upload TXT, MD, and PDF study materials.
- Persist each uploaded file as a distinct document in SQLite.
- Group multiple documents under a user-defined `subject_name`.
- Extract heuristic concepts/questions/cards from uploaded text.
- Show a source-aware concept graph.
- Support grounded tutor responses, notes, compare mode, SRS review, and a lightweight "Adaptive Study Momentum Engine".

The app is not yet a true AI tutoring system. It is a structured local MVP with deterministic heuristics and a richer UI shell.

## Current architecture in one sentence

`main.py` owns all backend logic, persistence, ingestion, domain logic, and API routes; `index.html` defines the entire UI shell; `app.js` contains all client state management and rendering; `styles.css` contains the full visual system.

## Highest-priority context for takeover

1. Document identity and source tracking were recently repaired.
2. Subject grouping was added recently and works, but needs hardening.
3. A lot of logic is centralized in `main.py` and `app.js`, so the codebase is functional but fragile.
4. Extraction/generation quality is still heuristic and weak for many real documents, especially PDFs.

## Files Claude should inspect first

1. `main.py`
2. `app.js`
3. `index.html`
4. `schema.sql`
5. `tests/test_einstein_tutor.py`
6. `styles.css`

## Critical flows

### Upload -> persist -> render

1. Frontend upload starts in `uploadDocument(file)` in `app.js`.
2. UI sends multipart form data with `file` and `subject_name`.
3. FastAPI route `/api/documents/upload` in `main.py` saves the uploaded file, extracts text, ingests the document, logs an event, and returns the new `doc_id`.
4. `refreshSummaryData()` reloads bootstrap state.
5. `loadDocumentDetail()` fetches the selected document and also re-syncs graph filters.

### Document identity and graph traceability

Document identity now depends on:
- `documents.id`
- `concepts.doc_id`
- `concept_edges.doc_id`

The concept graph should be read as document-owned data, not as a global concept soup.

## What was fixed most recently

### 1. Concept map source tracking

Previously, concept ownership was inferred too loosely. The current fix makes concept and edge ownership explicit in the database and graph query path.

Relevant code:
- schema ownership fields in `schema.sql:1`
- DB migration/backfill in `main.py:671`
- ingestion writes `doc_id` to concepts/edges in `main.py:750`
- graph filtering in `main.py:1657`

### 2. Grouping multiple documents under one subject

Documents now carry a normalized `subject_name`. Uploads can set it, and the library can update it later.

Relevant code:
- `normalize_subject_name()` at `main.py:229`
- `set_document_subject()` at `main.py:1093`
- `/api/documents/{doc_id}/subject` at `main.py:1858`
- upload subject field in `index.html:493`
- `saveDocumentSubject()` at `app.js:547` and `uploadDocument()` at `app.js:604`

### 3. Library render failure

There was a frontend bug where `renderLibrary()` used a local variable named `document`, which shadowed `window.document` and broke rendering. That was fixed by renaming the loop variable and explicitly using `window.document.createElement(...)`.

## What is still broken or unfinished

### Product-quality broken

- Concept extraction is still heuristic, not model-backed.
- Many PDFs will ingest, but concept names/descriptions can be noisy.
- Source-grounded tutor answers are grounded to stored chunks, but the answer generation itself is still templated/heuristic rather than real LLM reasoning.

### Architecture broken

- `main.py` is too large and mixes parsing, storage, business logic, and HTTP routes.
- `app.js` is too large and mixes state, orchestration, rendering, and event binding.
- There is no clean service/module boundary around ingestion, graphing, SRS, tutoring, or workspace logic.

### Testing broken

- Coverage is backend-heavy and targeted only at the recent document/grouping fixes.
- There are no browser/integration tests.
- There are no tests for the tutor UI, compare UI, study mode UI, or graph interaction in a real browser.

## Recommended takeover strategy

1. Read `FILE_GUIDE.md`.
2. Read `ARCHITECTURE.md`.
3. Read `BUGS_AND_RISKS.md`.
4. Run the tests.
5. Inspect `main.py` upload/graph/grouping paths first.
6. Inspect `app.js` bootstrap/library/graph code second.
7. Then decide whether to refactor before adding more features.
