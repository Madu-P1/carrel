# Einstein Tutor Architecture

## Stack

- Backend: FastAPI
- Database: SQLite
- Frontend: server-served HTML + CSS + vanilla JS
- Persistence: local DB + uploaded files under `data/uploads`

## Runtime shape

This is a single-process local web app.

- `main.py` boots FastAPI, initializes/migrates SQLite, seeds demo data, and exposes all API routes.
- `index.html` is served at `/`.
- static files are served under `/static`.
- frontend state is fully client-managed in `app.js`.

## Backend layout

There is no package/module split yet. Everything meaningful is in `main.py`.

Main logical sections:

### Schema/bootstrap/migrations

- `initialize_database()`
- `seed_demo_data()`

Code start points:
- `main.py:671`
- `main.py:728`

Responsibilities:
- create tables from `schema.sql`
- add missing columns during startup migration
- backfill `concepts.doc_id`
- backfill `concept_edges.doc_id`

### Ingestion pipeline

- `extract_text(path)`
- `chunk_text(text)`
- `summarize_document(text)`
- concept extraction helpers around `select_concept_phrases`, `sentence_for_term`, `concept_description`
- `ingest_document_record(...)`

Code start points:
- `main.py:456`
- `main.py:234`
- `main.py:517`
- `main.py:750`

Responsibilities:
- extract text from TXT/MD/PDF
- split into chunks
- generate heuristic concepts
- generate one question per concept
- generate SRS cards
- generate simple linear concept edges

### Document/detail/grouping

- `fetch_documents()`
- `fetch_document_detail()`
- `collect_document_concepts()`
- `fetch_subject_groups()`
- `set_document_subject()`
- `delete_document_record()`

Code start points:
- `main.py:867`
- `main.py:910`
- `main.py:886`
- `main.py:1081`
- `main.py:1093`
- `main.py:982`

Responsibilities:
- list files
- load file detail
- update subject grouping
- delete document-owned records cleanly

### Workspace/tutoring/study

- `fetch_workspace_state()`
- `build_momentum_engine()`
- `grounded_tutor_response(...)`
- `fetch_questions()`
- `fetch_due_cards()`
- SRS review route logic
- notes + compare + dialogue routes

Code start points:
- `main.py:1385`
- `main.py:1248`
- `main.py:2002`
- `main.py:2018`
- `main.py:2057`

Responsibilities:
- provide the dashboard/workspace payload
- tutor response scaffolding
- note transforms
- compare mode
- SRS queue

### Graph

- `fetch_graph(conn, doc_id=None, subject_name=None)`

Code start point:
- `main.py:1657`

Responsibilities:
- return concept nodes with `document_id`, `document_name`, `subject_name`
- filter by document or subject
- return only edges fully inside the current node set

## Frontend layout

### UI shell

`index.html` contains all screens:
- Workspace
- Library
- Study Mode
- Concept Map
- Upload

It also contains the subject-group controls for both upload and library reassignment.

### Client state and orchestration

`app.js` owns:
- global `state`
- API wrapper
- bootstrap loading
- document detail loading
- graph loading
- all render functions
- all DOM event binding

Key frontend orchestration functions:
- `loadBootstrap()`
- `loadDocumentDetail()`
- `loadGraph()`
- `refreshSummaryData()`

Code start points:
- `app.js:380`
- `app.js:308`
- `app.js:263`

## Upload/document/concept-map pipeline

### Upload pipeline

1. User picks a file in `#docInput`.
2. `uploadDocument(file)` sends `file` plus `subject_name`.
3. `/api/documents/upload` saves the file, extracts text, calls `ingest_document_record(...)`, logs the upload, returns `doc_id`.
4. Frontend calls `refreshSummaryData()`.
5. `loadBootstrap()` reloads all high-level state.
6. `loadDocumentDetail()` loads the selected file and then `loadGraph()`.

### Subject grouping pipeline

1. User enters or edits a subject name.
2. Frontend calls `saveDocumentSubject()`.
3. Backend route `/api/documents/{doc_id}/subject` updates `documents.subject_name`.
4. Workspace subject groups are refreshed from `fetch_subject_groups()`.
5. Graph and library now reflect the new grouping.

### Concept graph pipeline

1. Frontend tracks `state.graphFilters = { subjectName, docId }`.
2. `loadGraph()` calls `/api/concepts/graph` with either `doc_id` or `subject_name`.
3. `fetch_graph()` joins concepts to documents and returns source-aware nodes/edges.
4. `renderConceptMap()` draws nodes, edge labels, and truncated document subtitles.
5. Clicking a concept node re-syncs graph filters and document detail.

Main code entry points:
- upload route: `main.py:1798`
- grouping route: `main.py:1858`
- graph route: `main.py:1888`
- upload UI: `app.js:604`
- regroup UI: `app.js:547`
- graph rendering: `app.js:1207`

## Why the code is fragile

- No backend module boundaries.
- No typed frontend state model.
- Render order matters a lot in `app.js`.
- Bootstrap and detail loading are intertwined.
- There are several refresh chains that can produce subtle state desync if changed carelessly.

## Best architectural improvements next

1. Split `main.py` into modules:
   - `db.py`
   - `ingestion.py`
   - `documents.py`
   - `graph.py`
   - `study.py`
   - `workspace.py`
   - `routes/*.py`
2. Split `app.js` into:
   - state
   - api
   - workspace view
   - library view
   - concept graph view
   - study view
3. Add integration tests for API flows.
4. Add browser tests for upload, grouping, graph filtering, and deletion.
