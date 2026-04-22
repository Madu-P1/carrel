# File Guide For Claude

## Read these first

### 1. `/Users/madu/Desktop/Codex/main.py`

Why first:
- All core backend behavior is here.
- You need this to understand ingestion, grouping, graphing, tutoring, and routes.

Read in this order:
1. `initialize_database()` at `main.py:671`
2. `ingest_document_record()` at `main.py:750`
3. `fetch_document_detail()` at `main.py:910`
4. `delete_document_record()` at `main.py:982`
5. `fetch_subject_groups()` at `main.py:1081`
6. `set_document_subject()` at `main.py:1093`
7. `fetch_graph()` at `main.py:1657`
8. `fetch_workspace_state()` at `main.py:1385`
9. upload/group/graph/tutor/note/compare routes at `main.py:1798`, `1858`, `1888`, `2002`, `2018`, `2057`

### 2. `/Users/madu/Desktop/Codex/app.js`

Why second:
- All client-side orchestration is here.
- Recent bugs were caused by render/state interactions in this file.

Read in this order:
1. `state` at `app.js:13`
2. `loadBootstrap()` at `app.js:380`
3. `loadDocumentDetail()` at `app.js:308`
4. `loadGraph()` at `app.js:263`
5. `uploadDocument()` at `app.js:604`
6. `saveDocumentSubject()` at `app.js:547`
7. `renderLibrary()` at `app.js:1086`
8. `renderConceptMap()` at `app.js:1207`
9. event listeners near `app.js:1562+`

### 3. `/Users/madu/Desktop/Codex/index.html`

Why third:
- This reveals the UI contract that `app.js` expects.
- Many regressions in this app come from mismatched IDs.

Inspect:
- library subject management controls around `index.html:330`
- concept graph controls around `index.html:450`
- upload subject input around `index.html:493`
- workspace dropdowns and source cards around `index.html:118` and `index.html:290`

### 4. `/Users/madu/Desktop/Codex/schema.sql`

Why:
- The document/source-tracking fix is encoded here.

Look for:
- `documents.subject_name` at `schema.sql:5`
- `concepts.doc_id` at `schema.sql:25`
- `concept_edges.doc_id` at `schema.sql:36`

### 5. `/Users/madu/Desktop/Codex/tests/test_einstein_tutor.py`

Why:
- This is the current regression net for the document/grouping fixes.

Inspect:
- distinct documents under one subject
- regrouping without losing traceability
- graph source filtering
- deletion isolation
- upload metadata persistence

## Secondary files

### `/Users/madu/Desktop/Codex/styles.css`

Why:
- Useful only if changing layout/controls.
- Includes the new graph and subject-management layouts.

## File responsibilities

### `main.py`

Contains:
- parsing
- chunking
- concept extraction
- question/card generation
- notes
- compare mode
- momentum engine
- graph generation
- routes

### `app.js`

Contains:
- state
- fetch wrapper
- render pipeline
- upload flow
- library flow
- workspace flow
- concept graph interactions
- event wiring

### `index.html`

Contains:
- all panels
- all required DOM IDs
- no component abstraction

### `schema.sql`

Contains:
- full SQLite schema
- the current source-tracking contract

### `tests/test_einstein_tutor.py`

Contains:
- backend regression tests for document identity and grouping

## Places where the code lies to you

- "AI tutor" mostly means deterministic response scaffolding.
- "Adaptive" mostly means heuristic momentum and review logic.
- "Concept graph" is currently derived from extracted phrases plus simple relationship inference, not a deeply modeled knowledge graph.
