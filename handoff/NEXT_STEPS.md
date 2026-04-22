# Next Steps For Claude

## Immediate priorities

### 1. Stabilize document/source correctness

Goal:
- Keep document identity airtight across upload, graph, notes, compare, tutor citations, and deletion.

Do next:
- Add API tests for tutor citations and compare citations to ensure document provenance stays attached.
- Add tests that cover multiple documents with overlapping concept names under one subject.

Relevant code:
- `main.py:1555`
- `main.py:2002`
- `tests/test_einstein_tutor.py:66`

### 2. Add browser-level regression coverage

Goal:
- Catch render/state breakages that backend tests cannot see.

Do next:
- Add Playwright or another browser test runner.
- Cover:
  - upload a file with subject
  - upload a second file with same subject
  - verify library shows both
  - verify graph filters work
  - verify deleting one file leaves the other
  - verify changing subject updates grouping

Relevant UI code:
- `app.js:604`
- `app.js:547`
- `app.js:1086`
- `app.js:1207`

### 3. Refactor the monolith carefully

Goal:
- Reduce breakage risk.

Do next:
- Extract document/graph logic from `main.py` first.
- Extract bootstrap/library/graph logic from `app.js` first.

Best refactor anchors:
- backend: `main.py:750`, `910`, `982`, `1093`, `1657`
- frontend: `app.js:263`, `308`, `380`, `1086`, `1207`

Suggested backend split:
- `services/documents.py`
- `services/graph.py`
- `services/ingestion.py`
- `services/study.py`
- `services/workspace.py`

Suggested frontend split:
- `state.js`
- `api.js`
- `views/library.js`
- `views/concepts.js`
- `views/workspace.js`
- `views/study.js`

### 4. Improve ingestion quality

Goal:
- Make the graph and study assets worth using.

Do next:
- Add text cleaning for PDFs.
- Improve chunk-source mapping so concepts point to more precise source chunks.
- Replace adjacent-concept edge generation with stronger relationship extraction.

### 5. Harden subject-group management

Goal:
- Make grouping a real first-class feature.

Do next:
- Add subject rename flow.
- Add subject overview UI or API.
- Add counts and filters everywhere subject grouping matters.

## Medium-term improvements

### Source-grounded tutoring

Do next:
- Ensure tutor responses always include chunk/document provenance.
- Add tests that fail if citations lose `document_id`.
- Consider saving tutor turns with stable citation references.

### Notes and study assets

Do next:
- Persist transformed flashcards/quizzes instead of generating ephemeral drafts only.
- Let notes be filtered by subject and document.

### Compare mode

Do next:
- Make compare mode explicitly source-aware in the UI.
- Show source document labels more prominently.

Relevant code:
- `main.py:1555`
- `main.py:2057`
- `app.js:562`

### Momentum engine

Do next:
- Make recommendations subject-aware.
- Incorporate repeated topic switching and document-level confusion more explicitly.

Relevant code:
- `main.py:1248`

## Specific bugs or debt likely to surface next

1. UI state desync after a sequence of upload -> regroup -> graph filter -> delete.
2. Overlapping concept names across documents causing confusion in compare and explanation flows.
3. PDF extraction producing empty or low-signal chunks.
4. Refresh order issues between bootstrap state and document detail state.
5. New schema changes becoming harder to manage without real migrations.

## First 10 concrete inspections Claude should do

1. Read `schema.sql` and confirm the source-of-truth ownership fields.
2. Read `initialize_database()` in `main.py`.
3. Read `ingest_document_record()` in `main.py`.
4. Read `fetch_document_detail()` in `main.py`.
5. Read `fetch_graph()` in `main.py`.
6. Read `/api/documents/upload` and `/api/documents/{doc_id}/subject` routes in `main.py`.
7. Read `state` in `app.js`.
8. Read `loadBootstrap()`, `loadDocumentDetail()`, and `loadGraph()` in `app.js`.
9. Read `renderLibrary()` and `renderConceptMap()` in `app.js`.
10. Run `python3 -m unittest discover -s tests -v` before changing behavior.
